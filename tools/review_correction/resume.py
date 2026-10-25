"""Resume one immutable checkpoint in a separate, package-contained session."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path

import fitz
from PIL import Image

from src.pipeline.review.number_layer import strip_returned_layer
from tools.review_correction.history import digest, encoded, package_path

MAX_PDF_BYTES = 32_000_000


def _full_page(page, *, annotations):
    crop = page.cropbox
    try:
        page.set_cropbox(page.mediabox)
        return page.get_pixmap(alpha=False, annots=annotations)
    finally:
        page.set_cropbox(crop)


def validate_pdf(source, candidate):
    """Bounded support: exact original page raster plus native annotations.

    Re-encoded, flattened, rotated and native-content edits fail correspondence;
    unknown input is never classified as our numbering or erased.
    """
    with fitz.open(source) as original, fitz.open(candidate) as annotated:
        if annotated.needs_pass or original.needs_pass:
            raise ValueError("Encrypted PDFs are not supported")
        if len(original) != len(annotated) or not len(original):
            raise ValueError("PDF page count does not match the saved source")
        if annotated.embfile_count():
            raise ValueError("Embedded files are not supported in resume PDFs")
        for clean, page in zip(original, annotated):
            if (
                clean.mediabox != page.mediabox
                or clean.rotation
                or page.rotation
                or page.mediabox.top_left != fitz.Point(0, 0)
            ):
                raise ValueError("PDF page geometry does not match the saved source")
            if page.get_links():
                raise ValueError("Interactive PDF links are not supported for resume")
            for note in page.annots() or []:
                if note.type[1] not in {
                    "Ink",
                    "Circle",
                    "Square",
                    "Stamp",
                    "FreeText",
                    "Highlight",
                }:
                    raise ValueError("Unsupported annotation type in resume PDF")
            original_images = [original.extract_image(x[0])["image"] for x in clean.get_images()]
            uploaded_images = [annotated.extract_image(x[0])["image"] for x in page.get_images()]
            if original_images != uploaded_images:
                raise ValueError("PDF background image bytes do not match the saved source")
            left = _full_page(clean, annotations=False)
            right = _full_page(page, annotations=False)
            if (left.width, left.height, left.samples) != (
                right.width,
                right.height,
                right.samples,
            ):
                raise ValueError(
                    "PDF background does not match the saved source; cannot safely resume"
                )


def trusted_numbered_results(package):
    """Only attested results under this server's package/session directories."""
    roots = [package.root]
    sessions = package_path(package.root, "resumed_sessions")
    if sessions.is_dir():
        for item in sorted(sessions.iterdir()):
            if re.fullmatch(r"s_[0-9a-f]{32}", item.name):
                review = package_path(package.root, f"resumed_sessions/{item.name}/review")
                if review.is_dir():
                    roots.append(review)
    seen = set()
    for root in roots:
        records = package_path(root, "history/applications")
        if not records.is_dir():
            continue
        for item in sorted(records.glob("attempt_*.json")):
            if not re.fullmatch(r"attempt_[0-9]{4,}\.json", item.name):
                continue
            item = package_path(root, str(item.relative_to(root)))
            record = json.loads(item.read_text())
            if record.get("status") != "succeeded":
                continue
            result = record.get("result") or {}
            if not result.get("number_layer_sidecar"):
                continue
            try:
                pdf_rel = Path(result["final_pdf"]).relative_to(root)
                layer_rel = Path(result["number_layer_sidecar"]).relative_to(root)
            except ValueError:
                continue
            pdf = package_path(root, str(pdf_rel))
            layer = package_path(root, str(layer_rel))
            if (
                pdf_rel.parts[0] != "application_runs"
                or layer.parent != pdf.parent
                or not pdf.is_file()
                or not layer.is_file()
                or digest(pdf.read_bytes()) != result.get("final_pdf_sha256")
                or digest(layer.read_bytes()) != result.get("number_layer_sidecar_sha256")
            ):
                continue
            identity = (str(pdf), str(layer))
            if identity not in seen:
                seen.add(identity)
                yield pdf, layer


def prepare_pdf(package, uploaded, original, output):
    try:
        validate_pdf(original, uploaded)
    except ValueError as original_error:
        for trusted, sidecar in trusted_numbered_results(package):
            try:
                proof = strip_returned_layer(uploaded, trusted, sidecar, original, output)
            except ValueError:
                continue
            validate_pdf(original, output)
            return output, proof
        raise ValueError(
            "PDF background/content does not match the source or an attested numbering result in this review package"
        ) from original_error
    return uploaded, None


def create_session(package, checkpoint, pdf_bytes):
    if not isinstance(pdf_bytes, bytes) or not 0 < len(pdf_bytes) <= MAX_PDF_BYTES:
        raise ValueError("Resume PDF must be at most 32 MB")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("Resume input must be a PDF")
    value = package.history.validate_dependencies(checkpoint)
    context = value.get("source_context") or {}
    if not context.get("source_pdf"):
        raise ValueError("This checkpoint has no verified original PDF provenance")
    root = package_path(package.root, "resumed_sessions")
    root.mkdir(exist_ok=True)
    session_id = "s_" + uuid.uuid4().hex
    staged = root / (".preparing_" + session_id)
    staged.mkdir()
    try:
        review = staged / "review"
        package.history.materialize(checkpoint, review)
        resume = review / "resume"
        resume.mkdir()
        uploaded = resume / "input.pdf"
        uploaded.write_bytes(pdf_bytes)
        original = staged / "retained/source.pdf"
        background, proof = prepare_pdf(package, uploaded, original, resume / "background.pdf")
        payload = json.loads((review / "manual_correction_input.json").read_text())
        # A partial selection or reordered source pages requires an explicit mapping.
        if context.get("source_pages") != list(range(len(payload["pages"]))):
            raise ValueError("Resume currently requires all original pages in source order")
        with fitz.open(background) as doc:
            if len(doc) != len(payload["pages"]):
                raise ValueError("Checkpoint page selection does not match PDF")
            for page, spec in zip(doc, payload["pages"]):
                image_path = package_path(review, spec["source_image"])
                with Image.open(image_path) as image:
                    size = image.size
                crop = page.cropbox
                page.set_cropbox(page.mediabox)
                try:
                    scale = size[0] / page.mediabox.width
                    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    if abs(size[0] / size[1] - page.mediabox.width / page.mediabox.height) > 0.001:
                        raise ValueError("Review image geometry does not match PDF")
                    image = image.resize(size)
                    rel = f"resume/{spec['page_id']}.png"
                    image.save(package_path(review, rel))
                    spec["display_image"] = rel
                finally:
                    page.set_cropbox(crop)
        payload["resume"] = {
            "schema_version": 1,
            "input_pdf": "resume/input.pdf",
            "input_sha256": digest(pdf_bytes),
            "checkpoint_id": checkpoint,
            "source_identity": value["identity"],
        }
        if proof:
            payload["resume"]["background_pdf"] = "resume/background.pdf"
            payload["resume"]["background_sha256"] = proof["cleaned_sha256"]
            payload["resume"]["roundtrip"] = proof
        (review / "manual_correction_input.json").write_bytes(encoded(payload))
        final = root / session_id
        staged.rename(final)
        return session_id
    except BaseException as exc:
        shutil.rmtree(staged)
        if isinstance(exc, Exception) and not isinstance(exc, (ValueError, OSError)):
            raise ValueError("Resume PDF is unsupported or invalid") from exc
        raise
