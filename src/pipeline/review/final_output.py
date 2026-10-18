"""Materialize corrected final PDF outputs from final numbering artifacts."""

from __future__ import annotations

import io
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageDraw, ImageFont

_LABEL_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
    "Arial Bold.ttf",
    "Arial.ttf",
)
_LABEL_FONT_STAFF_HEIGHT_RATIO = 0.28
_LABEL_FONT_MIN_SIZE = 18
_LABEL_FONT_MAX_SIZE = 96


class CorrectedFinalOutputError(ValueError):
    """Raised when corrected final output materialization fails."""


def _load_json_object(path: Path, *, description: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CorrectedFinalOutputError(f"{description} must be a JSON object: {path}")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


_DEFAULT_FALLBACK_OUTPUT_NAME = "corrected"
_MAX_OUTPUT_STEM_UTF8_BYTES = 200
_SCORE_NUMBERED_SUFFIX_RE = re.compile(r"(?:_score_numbered)+$", re.IGNORECASE)
_PDF_SUFFIX_RE = re.compile(r"\.pdf$", re.IGNORECASE)
_GENERIC_ARTIFACT_ROOT_NAMES = frozenset(
    {
        "corrected",
        "final",
        "input",
        "input_review",
        "inputs",
        "output",
        "outputs",
        "publish",
        "review",
        "runs",
        "source",
        "work",
    }
)


def _strip_output_suffixes(raw_name: str) -> str:
    candidate = raw_name.strip()
    while True:
        updated = _PDF_SUFFIX_RE.sub("", candidate).strip()
        updated = _SCORE_NUMBERED_SUFFIX_RE.sub("", updated).strip()
        if updated == candidate:
            return candidate
        candidate = updated


def _truncate_utf8_bytes(value: str, *, max_utf8_bytes: int) -> str:
    if len(value.encode("utf-8")) <= max_utf8_bytes:
        return value
    chars: list[str] = []
    used = 0
    for char in value:
        char_bytes = len(char.encode("utf-8"))
        if used + char_bytes > max_utf8_bytes:
            break
        chars.append(char)
        used += char_bytes
    return "".join(chars)


def _sanitize_output_name(
    raw_name: str,
    *,
    fallback: str = _DEFAULT_FALLBACK_OUTPUT_NAME,
    is_path: bool = False,
    max_utf8_bytes: int = _MAX_OUTPUT_STEM_UTF8_BYTES,
) -> str:
    candidate = unicodedata.normalize("NFC", raw_name.strip())
    if is_path:
        normalized_path = candidate.replace("\\", "/").rstrip("/")
        candidate = normalized_path.rsplit("/", 1)[-1] if normalized_path else ""
        if candidate in {".", ".."}:
            candidate = ""
    elif candidate in {".", ".."} or "/" in candidate or "\\" in candidate:
        candidate = ""

    candidate = _strip_output_suffixes(candidate)
    name = "".join(char if char.isalnum() or char in "._-" else "_" for char in candidate)
    name = re.sub(r"_+", "_", name).strip("._-")
    name = _strip_output_suffixes(name)
    name = _truncate_utf8_bytes(name, max_utf8_bytes=max_utf8_bytes)
    name = _strip_output_suffixes(name)
    name = re.sub(r"_+", "_", name).strip("._-")
    return name or fallback


def _is_usable_artifact_root_name(name: str) -> bool:
    lowered = name.strip().lower()
    if not lowered or lowered.startswith("."):
        return False
    if lowered in _GENERIC_ARTIFACT_ROOT_NAMES:
        return False
    if re.fullmatch(r"attempt_\d+", lowered):
        return False
    return True


def _derive_output_name(explicit_output_name: str | None, handoff_payload: dict[str, Any]) -> str:
    if isinstance(explicit_output_name, str) and explicit_output_name.strip():
        sanitized = _sanitize_output_name(explicit_output_name, fallback="")
        if sanitized:
            return sanitized

    output_name_raw = handoff_payload.get("output_name")
    if isinstance(output_name_raw, str) and output_name_raw.strip():
        sanitized = _sanitize_output_name(output_name_raw, fallback="")
        if sanitized:
            return sanitized

    for key in ("input_pdf", "source_pdf"):
        raw_name = handoff_payload.get(key)
        if isinstance(raw_name, str) and raw_name.strip():
            sanitized = _sanitize_output_name(raw_name, fallback="", is_path=True)
            if sanitized:
                return sanitized

    source_root = handoff_payload.get("source_artifact_root")
    if isinstance(source_root, str) and source_root.strip():
        root_name = Path(source_root.replace("\\", "/").rstrip("/")).name
        if _is_usable_artifact_root_name(root_name):
            sanitized = _sanitize_output_name(root_name, fallback="")
            if sanitized:
                return sanitized

    return _DEFAULT_FALLBACK_OUTPUT_NAME


def _resolve_package_path(package_root: Path, raw_path: Any, *, description: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise CorrectedFinalOutputError(f"{description} must be a non-empty package-relative path")
    path = Path(raw_path)
    if path.is_absolute():
        raise CorrectedFinalOutputError(f"{description} must be package-relative: {raw_path}")
    resolved = (package_root / path).resolve()
    try:
        resolved.relative_to(package_root)
    except ValueError as exc:
        raise CorrectedFinalOutputError(
            f"{description} must stay inside the review package: {raw_path}"
        ) from exc
    if not resolved.exists():
        raise CorrectedFinalOutputError(f"{description} does not exist: {resolved}")
    return resolved


def _bbox_values(raw_bbox: Any, *, description: str) -> tuple[float, float, float, float]:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        raise CorrectedFinalOutputError(f"{description} must be a four-value bbox")
    try:
        x1, y1, x2, y2 = (float(v) for v in raw_bbox)
    except (TypeError, ValueError) as exc:
        raise CorrectedFinalOutputError(f"{description} must contain numeric bbox values") from exc
    return x1, y1, x2, y2


def _union_bbox(
    bboxes: list[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    if not bboxes:
        raise CorrectedFinalOutputError("Cannot compute row bbox from an empty bbox list")
    return (
        min(b[0] for b in bboxes),
        min(b[1] for b in bboxes),
        max(b[2] for b in bboxes),
        max(b[3] for b in bboxes),
    )


def _first_page_payload(numbering_payload: dict[str, Any], numbering_path: Path) -> dict[str, Any]:
    pages = numbering_payload.get("pages")
    if not isinstance(pages, list) or not pages:
        raise CorrectedFinalOutputError(f"numbering_final has no pages: {numbering_path}")
    page_payload = pages[0]
    if not isinstance(page_payload, dict):
        raise CorrectedFinalOutputError(
            f"numbering_final page payload must be an object: {numbering_path}"
        )
    return page_payload


def _measure_number(raw_measure: dict[str, Any]) -> int | None:
    value = raw_measure.get("number")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _row_label_records(
    *,
    page_id: str,
    page_number: int,
    page_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    systems = page_payload.get("systems")
    if not isinstance(systems, list):
        raise CorrectedFinalOutputError(f"{page_id}: numbering_final systems must be a list")

    records: list[dict[str, Any]] = []
    for row_index, system in enumerate(systems):
        if not isinstance(system, dict):
            continue
        measures = system.get("measures")
        staves = system.get("staves")
        if not isinstance(measures, list) or not measures:
            continue
        if not isinstance(staves, list) or not staves:
            continue

        first_measure = None
        first_measure_index = None
        for measure_index, measure in enumerate(measures):
            if not isinstance(measure, dict):
                continue
            number = _measure_number(measure)
            if number is None:
                continue
            first_measure = (measure, number)
            first_measure_index = measure_index
            break
        if first_measure is None or first_measure_index is None:
            continue

        staff_bboxes = [
            _bbox_values(
                staff.get("bbox"), description=f"{page_id}.systems[{row_index}].staves[].bbox"
            )
            for staff in staves
            if isinstance(staff, dict) and staff.get("bbox") is not None
        ]
        if not staff_bboxes:
            continue
        measure_bboxes = [
            _bbox_values(
                measure.get("bbox"),
                description=f"{page_id}.systems[{row_index}].measures[].bbox",
            )
            for measure in measures
            if isinstance(measure, dict) and measure.get("bbox") is not None
        ]

        row_bbox = _union_bbox(staff_bboxes + measure_bboxes)
        top_staff_bbox = min(staff_bboxes, key=lambda bbox: bbox[1])
        records.append(
            {
                "page_id": page_id,
                "page_number": page_number,
                "row_id": f"row_{row_index + 1:03d}",
                "row_bbox": list(row_bbox),
                "top_staff_bbox": list(top_staff_bbox),
                "row_start_measure_number": first_measure[1],
                "source_measure_index": first_measure_index,
                "placement": "primary_left_gutter",
            }
        )
    return records


def _font_size_for_staff_height(staff_height: float) -> int:
    size = round(staff_height * _LABEL_FONT_STAFF_HEIGHT_RATIO)
    return max(_LABEL_FONT_MIN_SIZE, min(_LABEL_FONT_MAX_SIZE, int(size)))


def _page_label_font_size(records: list[dict[str, Any]]) -> int:
    staff_heights = sorted(
        max(1.0, float(record["top_staff_bbox"][3]) - float(record["top_staff_bbox"][1]))
        for record in records
    )
    if not staff_heights:
        return _LABEL_FONT_MIN_SIZE

    mid = len(staff_heights) // 2
    if len(staff_heights) % 2 == 0:
        median_staff_height = (staff_heights[mid - 1] + staff_heights[mid]) / 2.0
    else:
        median_staff_height = staff_heights[mid]
    return _font_size_for_staff_height(median_staff_height)


def _load_label_font(size: int) -> ImageFont.ImageFont:
    for candidate in _LABEL_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _draw_row_start_labels(image: Image.Image, records: list[dict[str, Any]]) -> Image.Image:
    output = image.convert("RGB").copy()
    draw = ImageDraw.Draw(output)
    width, _height = output.size
    font_size = _page_label_font_size(records)
    font = _load_label_font(font_size)

    for record in records:
        text = str(record["row_start_measure_number"])
        top_staff = record["top_staff_bbox"]
        row_bbox = record["row_bbox"]
        text_w, text_h = _text_size(draw, text, font)
        label_gap = max(6, font_size // 6, int((row_bbox[3] - row_bbox[1]) * 0.035))
        x = int(max(2, min(width - text_w - 2, row_bbox[0] - label_gap - text_w)))
        y = int(max(2, top_staff[1] - text_h - label_gap))
        if y <= 2:
            y = int(max(2, top_staff[1] + label_gap))
            record["placement"] = "inside_left_fallback"
        else:
            record["placement"] = "primary_left_gutter"

        halo_padding = max(3, font_size // 10)
        halo_bbox = (
            x - halo_padding,
            y - halo_padding,
            x + text_w + halo_padding,
            y + text_h + halo_padding,
        )
        draw.rectangle(halo_bbox, fill="white")
        draw.text((x, y), text, fill="black", font=font)
        record["label_font_size"] = font_size
        record["label_bbox"] = [x, y, x + text_w, y + text_h]

    return output


def _render_final_page_image(
    *,
    source_image_path: Path,
    numbering_path: Path,
    page_id: str,
    page_number: int,
) -> tuple[Image.Image, list[dict[str, Any]]]:
    numbering_payload = _load_json_object(numbering_path, description=f"{page_id}.numbering_final")
    page_payload = _first_page_payload(numbering_payload, numbering_path)
    records = _row_label_records(
        page_id=page_id, page_number=page_number, page_payload=page_payload
    )
    with Image.open(source_image_path) as image:
        rendered = _draw_row_start_labels(image, records)
    return rendered, records


def _physical_page_size(
    page: dict[str, Any], image: Image.Image, warnings: list[str]
) -> tuple[float, float]:
    """Use captured PDF geometry, independent of render DPI or raster resizing."""
    size = page.get("page_size_points")
    if size is not None:
        if not isinstance(size, (list, tuple)) or len(size) != 2:
            raise CorrectedFinalOutputError("page_size_points must contain width and height")
        try:
            width, height = (float(value) for value in size)
        except (TypeError, ValueError) as exc:
            raise CorrectedFinalOutputError("page_size_points must contain numeric values") from exc
        if not all(math.isfinite(value) and value > 0 for value in (width, height)):
            raise CorrectedFinalOutputError("page_size_points must be finite and positive")
        return width, height

    # Older review packages do not contain physical geometry. Honor image DPI
    # when present; otherwise disclose the canonical render-DPI assumption.
    dpi = image.info.get("dpi")
    if isinstance(dpi, (list, tuple)) and len(dpi) == 2:
        try:
            x_dpi, y_dpi = (float(value) for value in dpi)
        except (TypeError, ValueError):
            x_dpi = y_dpi = 0.0
        if all(math.isfinite(value) and value > 0 for value in (x_dpi, y_dpi)):
            return image.width * 72.0 / x_dpi, image.height * 72.0 / y_dpi
    warnings.append(
        f"{page.get('page_id')}: physical page size unavailable; assuming 300 DPI "
        "for this legacy image (original paper size is unknown)"
    )
    return image.width * 72.0 / 300.0, image.height * 72.0 / 300.0


def materialize_corrected_final_outputs(
    *,
    handoff_path: str | Path,
    corrected_run_dir: str | Path,
    final_root: str | Path | None = None,
    review_root: str | Path | None = None,
    output_name: str | None = None,
) -> dict[str, Any]:
    """Render a clean final score-numbered PDF from corrected numbering outputs.

    The renderer consumes source page images from the review package coordinate
    space and corrected ``outputs/<page_id>/numbering_final.json`` files from the
    corrected run. Review/debug geometry and correction provenance are written to
    review metadata, not into ``final/``.
    """

    handoff_path = Path(handoff_path).resolve()
    package_root = handoff_path.parent
    corrected_run_dir = Path(corrected_run_dir).resolve()
    final_root_path = Path(final_root).resolve() if final_root else corrected_run_dir / "final"
    review_root_path = Path(review_root).resolve() if review_root else corrected_run_dir / "review"

    handoff_payload = _load_json_object(handoff_path, description="manual correction handoff")
    pages = handoff_payload.get("pages")
    if not isinstance(pages, list) or not pages:
        raise CorrectedFinalOutputError("manual correction handoff must contain at least one page")

    final_root_path.mkdir(parents=True, exist_ok=True)
    review_root_path.mkdir(parents=True, exist_ok=True)

    resolved_output_name = _derive_output_name(output_name, handoff_payload)
    final_pdf = final_root_path / f"{resolved_output_name}_score_numbered.pdf"

    rendered_pages: list[Image.Image] = []
    page_summaries: list[dict[str, Any]] = []
    warnings: list[str] = []

    try:
        for index, page in enumerate(pages):
            if not isinstance(page, dict):
                raise CorrectedFinalOutputError(f"pages[{index}] must be a JSON object")
            page_id = page.get("page_id")
            if not isinstance(page_id, str) or not page_id:
                raise CorrectedFinalOutputError(f"pages[{index}].page_id is required")
            page_number_raw = page.get("page_number", index + 1)
            try:
                page_number = int(page_number_raw)
            except (TypeError, ValueError) as exc:
                raise CorrectedFinalOutputError(
                    f"{page_id}: page_number must be an integer"
                ) from exc

            source_image = _resolve_package_path(
                package_root,
                page.get("source_image"),
                description=f"{page_id}.source_image",
            )
            corrected_numbering = corrected_run_dir / "outputs" / page_id / "numbering_final.json"
            if not corrected_numbering.exists():
                raise CorrectedFinalOutputError(
                    f"{page_id}: corrected numbering_final.json does not exist: "
                    f"{corrected_numbering}"
                )

            rendered, row_records = _render_final_page_image(
                source_image_path=source_image,
                numbering_path=corrected_numbering,
                page_id=page_id,
                page_number=page_number,
            )
            if not row_records:
                warnings.append(f"{page_id}: no row-start labels were rendered")
            rendered_pages.append(rendered)
            page_summaries.append(
                {
                    "page_id": page_id,
                    "page_number": page_number,
                    "source_image": str(source_image),
                    "corrected_numbering_final": str(corrected_numbering),
                    "rendered_row_labels": len(row_records),
                    "row_labels": row_records,
                    "page_size_points": list(_physical_page_size(page, rendered, warnings)),
                }
            )

        if not rendered_pages:
            raise CorrectedFinalOutputError("No pages were rendered for final PDF")

        # A single Pillow PDF dpi argument applies to the whole document. Place
        # each unchanged JPEG raster on its own physical page so mixed sizes,
        # rotations/crops and explicitly resized renderings are all preserved.
        with fitz.open() as document:
            for image, page_summary in zip(rendered_pages, page_summaries, strict=True):
                width, height = page_summary["page_size_points"]
                pdf_page = document.new_page(width=width, height=height)
                with io.BytesIO() as encoded:
                    image.save(encoded, format="JPEG")
                    pdf_page.insert_image(
                        pdf_page.rect, stream=encoded.getvalue(), keep_proportion=False
                    )
            document.save(final_pdf)
    finally:
        for page_image in rendered_pages:
            page_image.close()

    summary = {
        "kind": "corrected_final_output_summary",
        "schema_version": 1,
        "source_handoff": str(handoff_path),
        "corrected_run_dir": str(corrected_run_dir),
        "output_name": resolved_output_name,
        "final_pdf": str(final_pdf),
        "final_dir_contract": "final contains the final score-numbered PDF only for this slice",
        "rendering_contract": "row_start_measure_number_labels_from_corrected_final_numbering",
        "page_count": len(page_summaries),
        "pages": page_summaries,
        "warnings": warnings,
    }
    summary_path = review_root_path / "corrected_final_summary.json"
    summary["summary_path"] = str(summary_path)
    _write_json(summary_path, summary)
    return summary
