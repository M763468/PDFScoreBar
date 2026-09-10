#!/usr/bin/env python3
"""Run an all-positive retained MMR risk-slice for the Issue #277 composed retry.

The experiment compares the current merged J2 production baseline with an
experiment-only composed detector on every retained positive Issue #274 key,
plus the page_033 one-bar/fallback causal keys.

No detector/HOMR/SR/OMR/numbering/full68 scan is executed. Existing primary
CNN probabilities are reused for retained positive keys; only page_033 causal
keys absent from that positive inventory may require focused CNN inference.
RapidOCR is rerun so OCR-call cost and current output are directly attributable.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.mmr import MMROCREngine, MMRProcessor
from src.measure_numbering.rapidocr_provider import (
    collect_rapidocr_providers,
    create_mmr_rapidocr,
    providers_include_cuda,
)
from tools.issue264.run_phase_c_mmr_regression import build_page_specs
from tools.issue274.audit_positive_geometry_disagreements import slice_one_measure
from tools.issue277.diagnose_retained_mmr_ocr_provenance import rank_numeric_candidates
from tools.issue277.evaluate_composed_mmr_retry_candidate import (
    candidate_is_measure_staff_anchored,
)
from tools.issue277.run_retained_mmr_normalized_roi_probe import normalized_roi_bounds

DEFAULT_POSITIVE_AUDIT = (
    PROJECT_ROOT
    / "logs/issue274_positive_geometry_audit/issue274_positive_geometry_audit.json"
)
DEFAULT_REUSE_ROOT = PROJECT_ROOT / "logs/issue274_full68_mmr_reuse"
DEFAULT_NUMBERING_ROOT = (
    PROJECT_ROOT
    / "logs/issue264_phase_c_mmr_regression/issue264_phase_c_current_production_full68_02"
)
DEFAULT_PAGE033_CAUSAL = (
    PROJECT_ROOT / "logs/issue274_page033_xy_causal/issue274_page033_xy_causal.json"
)
DEFAULT_MODEL = PROJECT_ROOT / "tools/mmr_training/models/mmr_classifier_best.pth"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "logs/issue277/issue277_composed_positive_risk_slice_01/"
    "composed_mmr_positive_risk_slice_01.json"
)

PRIMARY_VARIANTS = ("standard", "no_dilate", "heavy_dilate")
NORMALIZED_MODE = "heavy_dilate"
SHIFT_MODE = "no_dilate"
SHIFT_FRACTION = 0.01
REQUIRED_POSITIVE_COUNT = 175


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def unique_vote(values: Sequence[int | None]) -> int | None:
    """Return a unique plurality winner among values >=2; reject ties/empties."""

    counts = Counter(int(value) for value in values if value is not None and int(value) >= 2)
    if not counts:
        return None
    support = max(counts.values())
    leaders = [value for value, count in counts.items() if count == support]
    return leaders[0] if len(leaders) == 1 else None


def scale_relative_x1_bbox(bbox: Sequence[int], fraction: float = SHIFT_FRACTION) -> list[int]:
    """Shift only x1 by a scale-relative fraction; never invent a fixed pixel minimum."""

    x1, y1, x2, y2 = (int(value) for value in bbox)
    dx = int(round((x2 - x1) * float(fraction)))
    return [x1 + dx, y1, x2, y2]


def choose_anchored_consensus(
    evidence_units: Sequence[Mapping[str, Any]],
    minimum_support: int = 2,
) -> tuple[int | None, int, dict[str, int]]:
    """Choose a unique anchored cross-variant/staff consensus."""

    counts = Counter(
        int(item["value"])
        for item in evidence_units
        if int(item.get("value", 0)) >= 2
    )
    if not counts:
        return None, 0, {}
    support = max(counts.values())
    leaders = [value for value, count in counts.items() if count == support]
    selected = leaders[0] if support >= minimum_support and len(leaders) == 1 else None
    return selected, support, {str(value): int(count) for value, count in sorted(counts.items())}


class CountingOCR:
    def __init__(self, wrapped: Any):
        self.wrapped = wrapped
        self.calls = 0

    def __call__(self, image: Any):
        self.calls += 1
        return self.wrapped(image)


class FixedClassifier:
    def __init__(self, probability: float = 0.0):
        self.probability = float(probability)
        self.calls = 0

    def predict(self, _image: Any) -> float:
        self.calls += 1
        return self.probability


class ComposedProcessor(MMRProcessor):
    """Experiment-only replacement path that falls back to merged J2 when unresolved."""

    def __init__(self, *, ocr_engine: MMROCREngine, classifier: FixedClassifier):
        import torch

        super().__init__(
            Path("unused"),
            torch.device("cpu"),
            classifier=classifier,
            ocr_engine=ocr_engine,
        )
        self.decision_trace: list[dict[str, Any]] = []

    def reset_decision_trace(self) -> None:
        self.decision_trace = []

    def _run_masked_staff(
        self,
        image: Any,
        measure_bbox: Sequence[int],
        staff_bbox: Sequence[int],
        mode: str,
        w_img: int,
        h_img: int,
    ) -> dict[str, Any]:
        x1, _y1, x2, _y2 = (int(value) for value in measure_bbox)
        _sx1, sy1, _sx2, sy2 = (int(value) for value in staff_bbox)
        margin_y = 80
        ox1 = max(0, x1 - 30)
        ox2 = min(w_img, x2 + 30)
        oy1 = max(0, sy1 - margin_y)
        oy2 = min(h_img, sy2 + margin_y)
        crop = image[oy1:oy2, ox1:ox2]
        if crop is None or crop.size == 0:
            return {
                "crop_bounds": [ox1, oy1, ox2, oy2],
                "ranked": [],
                "one_bar_evidence": 0,
            }
        crop = self.ocr.mask_hbar_candidates(crop, margin_y, sy2 - sy1)
        processed = self.ocr.preprocess_variant(crop, mode=mode, angle=0)
        if processed is None or processed.size == 0:
            return {
                "crop_bounds": [ox1, oy1, ox2, oy2],
                "ranked": [],
                "one_bar_evidence": 0,
            }
        raw, _elapsed = self.ocr.ocr_engine(processed)
        raw = raw or []
        ranked = rank_numeric_candidates(
            self.ocr,
            list(raw),
            processed.shape[1],
            processed.shape[0],
        )
        return {
            "crop_bounds": [ox1, oy1, ox2, oy2],
            "ranked": ranked,
            "one_bar_evidence": self._count_high_confidence_one_bar_evidence(raw),
        }

    def _primary_anchored(
        self,
        image: Any,
        system: Mapping[str, Any],
        measure_bbox: Sequence[int],
        prob: float,
        w_img: int,
        h_img: int,
    ) -> dict[str, Any]:
        variants = ("standard",) if prob <= self.threshold else PRIMARY_VARIANTS
        evidence_units: list[dict[str, Any]] = []
        evidence_by_variant: list[int] = []
        measure_width = int(measure_bbox[2]) - int(measure_bbox[0])

        staves = system.get("staves", [])
        for variant in variants:
            variant_one_bar = 0
            for staff_index, stave in enumerate(staves):
                staff_bbox = stave["bbox"]
                run = self._run_masked_staff(
                    image,
                    measure_bbox,
                    staff_bbox,
                    variant,
                    w_img,
                    h_img,
                )
                variant_one_bar += int(run["one_bar_evidence"])
                anchored = [
                    candidate
                    for candidate in run["ranked"]
                    if not (
                        int(candidate["value"]) > 20 and measure_width < 100
                    )
                    and candidate_is_measure_staff_anchored(
                        candidate,
                        {"crop_bounds": run["crop_bounds"]},
                        measure_bbox,
                        staff_bbox,
                    )
                ]
                if not anchored:
                    continue
                candidate = anchored[0]
                evidence_units.append(
                    {
                        "variant": variant,
                        "staff_index": staff_index,
                        "value": int(candidate["value"]),
                        "score": float(candidate["score"]),
                        "text": str(candidate.get("text", "")),
                    }
                )
            evidence_by_variant.append(variant_one_bar)

        selected, support, vote_counts = choose_anchored_consensus(evidence_units)
        selected_score = 0.0
        if selected is not None:
            selected_score = max(
                float(item["score"])
                for item in evidence_units
                if int(item["value"]) == selected
            )
        return {
            "selected_num": selected,
            "selected_score": selected_score,
            "support": support,
            "vote_counts": vote_counts,
            "evidence_units": evidence_units,
            "one_bar_evidence": max(evidence_by_variant, default=0),
        }

    def _run_normalized_staff(
        self,
        image: Any,
        measure_bbox: Sequence[int],
        staff_bbox: Sequence[int],
        w_img: int,
        h_img: int,
    ) -> tuple[int | None, float]:
        roi = normalized_roi_bounds(
            measure_bbox,
            staff_bbox,
            w_img,
            h_img,
            0.0,
            1.0,
        )
        x1, y1, x2, y2 = roi
        crop = image[y1:y2, x1:x2]
        if crop is None or crop.size == 0:
            return None, 0.0
        processed = self.ocr.preprocess_variant(
            crop,
            mode=NORMALIZED_MODE,
            angle=0,
        )
        if processed is None or processed.size == 0:
            return None, 0.0
        raw, _elapsed = self.ocr.ocr_engine(processed)
        raw = raw or []
        num, score, _debug = self.ocr.select_best_candidate(
            list(raw),
            processed.shape[1],
            processed.shape[0],
        )
        if num is None or int(num) < 2:
            return None, 0.0
        return int(num), float(score)

    def _run_shifted_staff(
        self,
        image: Any,
        shifted_bbox: Sequence[int],
        staff_bbox: Sequence[int],
        w_img: int,
        h_img: int,
    ) -> tuple[int | None, float]:
        run = self._run_masked_staff(
            image,
            shifted_bbox,
            staff_bbox,
            SHIFT_MODE,
            w_img,
            h_img,
        )
        ranked = [
            candidate
            for candidate in run["ranked"]
            if int(candidate["value"]) >= 2
        ]
        if not ranked:
            return None, 0.0
        candidate = ranked[0]
        return int(candidate["value"]), float(candidate["score"])

    @staticmethod
    def _aggregate_staff(values: Sequence[tuple[int | None, float]]) -> tuple[int | None, float]:
        selected = unique_vote([value for value, _score in values])
        if selected is None:
            return None, 0.0
        score = max(
            float(score)
            for value, score in values
            if value is not None and int(value) == selected
        )
        return selected, score

    def _detect_number_with_evidence(
        self,
        image: Any,
        system: Mapping[str, Any],
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        prob: float,
        w_img: int,
        h_img: int,
    ):
        measure_bbox = [int(x1), int(y1), int(x2), int(y2)]
        primary = self._primary_anchored(
            image,
            system,
            measure_bbox,
            prob,
            w_img,
            h_img,
        )
        one_bar_evidence = int(primary["one_bar_evidence"])

        # Preserve the merged J2 path for low-CNN rescue and one-bar-sensitive
        # cases. This keeps the first experiment conservative.
        if prob <= self.threshold or (
            self.threshold < prob < self.ONE_BAR_VETO_PROB_MAX
            and one_bar_evidence >= self.ONE_BAR_VETO_MIN_EVIDENCE
        ):
            result = super()._detect_number_with_evidence_j2(
                image,
                system,
                x1,
                y1,
                x2,
                y2,
                prob,
                w_img,
                h_img,
            )
            self.decision_trace.append(
                {
                    "stage": "merged_j2_contract_fallback",
                    "primary": primary,
                    "selected_num": result[0],
                }
            )
            return result

        if primary["selected_num"] is not None:
            result = (
                int(primary["selected_num"]),
                float(primary["selected_score"]),
                "issue277_primary_anchored_consensus",
                one_bar_evidence,
            )
            self.decision_trace.append(
                {
                    "stage": "primary_anchored_consensus",
                    "primary": primary,
                    "selected_num": result[0],
                }
            )
            return result

        staves = system.get("staves", [])
        normalized_values = [
            self._run_normalized_staff(
                image,
                measure_bbox,
                stave["bbox"],
                w_img,
                h_img,
            )
            for stave in staves
        ]
        normalized_num, normalized_score = self._aggregate_staff(normalized_values)
        if normalized_num is not None:
            result = (
                normalized_num,
                normalized_score,
                "issue277_normalized_unmasked_heavy_dilate",
                one_bar_evidence,
            )
            self.decision_trace.append(
                {
                    "stage": "normalized_unmasked_heavy_dilate",
                    "primary": primary,
                    "normalized_values": normalized_values,
                    "selected_num": normalized_num,
                }
            )
            return result

        shifted_bbox = scale_relative_x1_bbox(measure_bbox)
        shifted_values: list[tuple[int | None, float]] = []
        if shifted_bbox[0] != measure_bbox[0]:
            shifted_values = [
                self._run_shifted_staff(
                    image,
                    shifted_bbox,
                    stave["bbox"],
                    w_img,
                    h_img,
                )
                for stave in staves
            ]
        shifted_num, shifted_score = self._aggregate_staff(shifted_values)
        if shifted_num is not None:
            result = (
                shifted_num,
                shifted_score,
                "issue277_scale_relative_x1_retry",
                one_bar_evidence,
            )
            self.decision_trace.append(
                {
                    "stage": "scale_relative_x1_retry",
                    "primary": primary,
                    "shifted_bbox": shifted_bbox,
                    "shifted_values": shifted_values,
                    "selected_num": shifted_num,
                }
            )
            return result

        # Unresolved cases retain the current merged J2 contract. This is
        # intentionally conservative for the risk-slice; call-cost impact is
        # measured explicitly and determines whether the composition is useful.
        result = super()._detect_number_with_evidence_j2(
            image,
            system,
            x1,
            y1,
            x2,
            y2,
            prob,
            w_img,
            h_img,
        )
        self.decision_trace.append(
            {
                "stage": "merged_j2_unresolved_fallback",
                "primary": primary,
                "normalized_values": normalized_values,
                "shifted_bbox": shifted_bbox,
                "shifted_values": shifted_values,
                "selected_num": result[0],
            }
        )
        return result


def _primary_probability(audit_record: Mapping[str, Any]) -> float:
    traces = audit_record.get("production_path_trace", [])
    matches = [trace for trace in traces if trace.get("view") == "primary"]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one primary production trace for {audit_record.get('page_id')} "
            f"{audit_record.get('key')}"
        )
    return float(matches[0]["passed_prob"])


def _normalise_overrides(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, int]]:
    return sorted(
        [
            {
                "skip": int(row.get("skip") or 0),
            }
            for row in rows
        ],
        key=lambda row: row["skip"],
    )


def _reset_support_stats(processor: MMRProcessor) -> None:
    processor.support_stats = {
        "phase_a_ocr_fallback": 0,
        "alternate_veto_suppression": 0,
    }


def _replay_one(
    *,
    processor: MMRProcessor,
    classifier: FixedClassifier,
    probability: float,
    image: Any,
    page_data: Mapping[str, Any],
    support: Mapping[str, Any],
    page_num: int,
    sys_idx: int,
    measure_idx: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    classifier.probability = float(probability)
    classifier.calls = 0
    _reset_support_stats(processor)
    if isinstance(processor, ComposedProcessor):
        processor.reset_decision_trace()
    sliced_page, sliced_support = slice_one_measure(
        page_data,
        support,
        sys_idx,
        measure_idx,
    )
    height, width = image.shape[:2]
    overrides = processor._process_page_with_support(
        page_data=sliced_page,
        support=sliced_support,
        image=image,
        page_num=page_num,
        image_width=width,
        image_height=height,
        debug_img=None,
    )
    if classifier.calls != 1:
        raise RuntimeError(f"Expected one classifier call, got {classifier.calls}")
    return overrides, dict(processor.support_stats)


def _positive_inventory(positive_audit: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records = positive_audit.get("production_path_traces")
    if not isinstance(records, list):
        raise ValueError("Positive audit lacks production_path_traces")
    if len(records) != REQUIRED_POSITIVE_COUNT:
        raise ValueError(
            f"Expected {REQUIRED_POSITIVE_COUNT} retained positive records, got {len(records)}"
        )
    return records


def _page033_extra_keys(causal: Mapping[str, Any], positive_keys: set[tuple[int, int, int]]) -> list[tuple[int, int]]:
    keys = {
        (int(item["system"]), int(item["measure"]))
        for item in causal.get("detect_calls", [])
        if item.get("one_bar_veto")
    }
    page_index = 32
    return sorted(
        (system, measure)
        for system, measure in keys
        if (page_index, system, measure) not in positive_keys
    )


def _preflight(
    *,
    positive_audit_path: Path,
    reuse_root: Path,
    numbering_root: Path,
    page033_causal_path: Path,
) -> dict[str, Any]:
    for path in (positive_audit_path, page033_causal_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    positive = _load_json(positive_audit_path)
    if not isinstance(positive, Mapping) or positive.get("status") != "completed":
        raise ValueError("Positive audit is not completed")
    records = _positive_inventory(positive)
    page_ids = sorted({str(record["page_id"]) for record in records})
    specs = {spec.page_id: spec for spec in build_page_specs()}
    missing = []
    for page_id in page_ids:
        required = (
            reuse_root / "intermediate" / page_id / "mmr_support.json",
            numbering_root / "intermediate" / page_id / "numbering_base.json",
            Path(specs[page_id].image),
        )
        for path in required:
            if not path.is_file():
                missing.append(str(path))
    if missing:
        raise FileNotFoundError("Missing retained risk-slice inputs:\n" + "\n".join(missing))
    return {
        "positive_records": len(records),
        "positive_pages": len(page_ids),
        "reuse_root": str(reuse_root),
        "numbering_root": str(numbering_root),
        "page033_causal": str(page033_causal_path),
    }


def run(
    *,
    positive_audit_path: Path,
    reuse_root: Path,
    numbering_root: Path,
    page033_causal_path: Path,
    model_path: Path,
    output_path: Path,
    provider_mode: str,
    preflight_only: bool = False,
) -> dict[str, Any]:
    preflight = _preflight(
        positive_audit_path=positive_audit_path,
        reuse_root=reuse_root,
        numbering_root=numbering_root,
        page033_causal_path=page033_causal_path,
    )
    if preflight_only:
        payload = {
            "schema_version": "issue277.composed_mmr_positive_risk_slice.preflight.v1",
            "status": "preflight_passed",
            "preflight": preflight,
        }
        _write_json(output_path, payload)
        return payload

    import cv2
    import torch

    from src.measure_numbering.mmr import MMRClassifier

    positive_audit = _load_json(positive_audit_path)
    positive_records = _positive_inventory(positive_audit)
    positive_keys = {
        tuple(int(value) for value in record["key"])
        for record in positive_records
    }
    causal = _load_json(page033_causal_path)
    page033_extras = _page033_extra_keys(causal, positive_keys)

    provider = create_mmr_rapidocr(provider_mode)
    providers = collect_rapidocr_providers(provider)
    if provider_mode == "cuda" and not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR CUDA requested but not confirmed: {providers}")

    baseline_counter = CountingOCR(provider)
    candidate_counter = CountingOCR(provider)
    baseline_classifier = FixedClassifier()
    candidate_classifier = FixedClassifier()
    baseline = MMRProcessor(
        Path("unused"),
        torch.device("cpu"),
        classifier=baseline_classifier,
        ocr_engine=MMROCREngine(ocr_engine=baseline_counter),
    )
    candidate = ComposedProcessor(
        ocr_engine=MMROCREngine(ocr_engine=candidate_counter),
        classifier=candidate_classifier,
    )

    specs = {spec.page_id: spec for spec in build_page_specs()}
    page_cache: dict[str, tuple[Any, Mapping[str, Any], Mapping[str, Any]]] = {}

    def load_page(page_id: str):
        if page_id not in page_cache:
            image = cv2.imread(str(specs[page_id].image))
            if image is None:
                raise FileNotFoundError(specs[page_id].image)
            page_data = _load_json(
                numbering_root / "intermediate" / page_id / "numbering_base.json"
            )
            support = _load_json(
                reuse_root / "intermediate" / page_id / "mmr_support.json"
            )
            page_cache[page_id] = (image, page_data, support)
        return page_cache[page_id]

    records_out: list[dict[str, Any]] = []
    stage_counts: Counter[str] = Counter()
    multi_staff = 0
    variant_disagreement = 0

    baseline_elapsed = 0.0
    candidate_elapsed = 0.0

    for index, audit_record in enumerate(positive_records, start=1):
        page_id = str(audit_record["page_id"])
        page_index, sys_idx, measure_idx = (int(value) for value in audit_record["key"])
        probability = _primary_probability(audit_record)
        image, page_data, support = load_page(page_id)

        primary_system = support["views"]["primary"]["pages"][0]["systems"][sys_idx]
        staff_count = len(primary_system.get("staves", []))
        multi_staff += int(staff_count > 1)

        before = baseline_counter.calls
        started = time.perf_counter()
        baseline_result, baseline_stats = _replay_one(
            processor=baseline,
            classifier=baseline_classifier,
            probability=probability,
            image=image,
            page_data=page_data,
            support=support,
            page_num=page_index + 1,
            sys_idx=sys_idx,
            measure_idx=measure_idx,
        )
        baseline_elapsed += time.perf_counter() - started
        baseline_calls = baseline_counter.calls - before

        before = candidate_counter.calls
        started = time.perf_counter()
        candidate_result, candidate_stats = _replay_one(
            processor=candidate,
            classifier=candidate_classifier,
            probability=probability,
            image=image,
            page_data=page_data,
            support=support,
            page_num=page_index + 1,
            sys_idx=sys_idx,
            measure_idx=measure_idx,
        )
        candidate_elapsed += time.perf_counter() - started
        candidate_calls = candidate_counter.calls - before

        decision_trace = list(candidate.decision_trace)
        for decision in decision_trace:
            stage_counts[str(decision["stage"])] += 1
            votes = decision.get("primary", {}).get("vote_counts", {})
            variant_disagreement += int(len(votes) > 1)

        exact = _normalise_overrides(baseline_result) == _normalise_overrides(candidate_result)
        records_out.append(
            {
                "kind": "retained_positive",
                "page_id": page_id,
                "key": [page_index, sys_idx, measure_idx],
                "probability_reused": probability,
                "staff_count": staff_count,
                "baseline_overrides": baseline_result,
                "candidate_overrides": candidate_result,
                "semantic_exact": exact,
                "baseline_support_stats": baseline_stats,
                "candidate_support_stats": candidate_stats,
                "baseline_rapidocr_calls": baseline_calls,
                "candidate_rapidocr_calls": candidate_calls,
                "candidate_decision_trace": decision_trace,
            }
        )
        if index % 20 == 0 or index == len(positive_records):
            print(
                f"positive risk slice: {index}/{len(positive_records)}",
                flush=True,
            )

    # Page_033 non-positive veto keys need a probability. Run the CNN only for
    # these few keys and reuse the resulting probability for baseline/candidate.
    focused_cnn_calls = 0
    classifier = None
    if page033_extras:
        if not model_path.is_file():
            raise FileNotFoundError(model_path)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if device.type != "cuda":
            raise RuntimeError("CUDA required for focused page_033 CNN probabilities")
        classifier = MMRClassifier(model_path, device)

    page033_image, page033_data, page033_support = load_page("page_033")
    h_img, w_img = page033_image.shape[:2]
    for sys_idx, measure_idx in page033_extras:
        primary_system = page033_support["views"]["primary"]["pages"][0]["systems"][sys_idx]
        measure = primary_system["measures"][measure_idx]
        x1, y1, x2, y2 = (int(value) for value in measure["bbox"])
        crop = page033_image[
            max(0, y1 - 20) : min(h_img, y2 + 20),
            max(0, x1 - 20) : min(w_img, x2 + 20),
        ]
        probability = float(classifier.predict(crop))
        focused_cnn_calls += 1

        before = baseline_counter.calls
        started = time.perf_counter()
        baseline_result, baseline_stats = _replay_one(
            processor=baseline,
            classifier=baseline_classifier,
            probability=probability,
            image=page033_image,
            page_data=page033_data,
            support=page033_support,
            page_num=33,
            sys_idx=sys_idx,
            measure_idx=measure_idx,
        )
        baseline_elapsed += time.perf_counter() - started
        baseline_calls = baseline_counter.calls - before

        before = candidate_counter.calls
        started = time.perf_counter()
        candidate_result, candidate_stats = _replay_one(
            processor=candidate,
            classifier=candidate_classifier,
            probability=probability,
            image=page033_image,
            page_data=page033_data,
            support=page033_support,
            page_num=33,
            sys_idx=sys_idx,
            measure_idx=measure_idx,
        )
        candidate_elapsed += time.perf_counter() - started
        candidate_calls = candidate_counter.calls - before
        decision_trace = list(candidate.decision_trace)
        for decision in decision_trace:
            stage_counts[str(decision["stage"])] += 1

        records_out.append(
            {
                "kind": "page033_one_bar_control",
                "page_id": "page_033",
                "key": [32, sys_idx, measure_idx],
                "probability_focused_cnn": probability,
                "staff_count": len(primary_system.get("staves", [])),
                "baseline_overrides": baseline_result,
                "candidate_overrides": candidate_result,
                "semantic_exact": (
                    _normalise_overrides(baseline_result)
                    == _normalise_overrides(candidate_result)
                ),
                "baseline_support_stats": baseline_stats,
                "candidate_support_stats": candidate_stats,
                "support_stats_exact": baseline_stats == candidate_stats,
                "baseline_rapidocr_calls": baseline_calls,
                "candidate_rapidocr_calls": candidate_calls,
                "candidate_decision_trace": decision_trace,
            }
        )

    positive_only = [record for record in records_out if record["kind"] == "retained_positive"]
    page033_controls = [
        record for record in records_out if record["kind"] == "page033_one_bar_control"
    ]
    differences = [record for record in positive_only if not record["semantic_exact"]]

    def page_exact(page_id: str) -> bool:
        rows = [record for record in positive_only if record["page_id"] == page_id]
        return bool(rows) and all(record["semantic_exact"] for record in rows)

    page042_rows = [record for record in positive_only if record["page_id"] == "page_042"]
    page033_semantics = bool(page033_controls) and all(
        record["semantic_exact"] and record.get("support_stats_exact", False)
        for record in page033_controls
    )

    payload = {
        "schema_version": "issue277.composed_mmr_positive_risk_slice.v1",
        "status": "completed",
        "execution_contract": {
            "production_code_modified": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "numbering_reexecuted": False,
            "full68_mmr_reexecuted": False,
            "retained_positive_full_scan": True,
            "retained_positive_cnn_reexecuted": False,
            "page033_extra_focused_cnn_calls": focused_cnn_calls,
            "rapidocr_reexecuted": True,
            "frozen_A_geometry_used": False,
            "baseline": "current merged J2",
            "candidate": (
                "primary anchored consensus; normalized full-span unmasked heavy_dilate; "
                "+1% x1 masked no_dilate; merged-J2 fallback for unresolved/one-bar/low-CNN"
            ),
        },
        "inputs": {
            "positive_audit": str(positive_audit_path),
            "reuse_root": str(reuse_root),
            "numbering_root": str(numbering_root),
            "page033_causal": str(page033_causal_path),
        },
        "runtime": {
            "rapidocr_provider_mode": provider_mode,
            "providers": providers,
            "baseline_elapsed_sec": baseline_elapsed,
            "candidate_elapsed_sec": candidate_elapsed,
            "baseline_rapidocr_calls": baseline_counter.calls,
            "candidate_rapidocr_calls": candidate_counter.calls,
            "rapidocr_call_delta_candidate_minus_j2": (
                candidate_counter.calls - baseline_counter.calls
            ),
        },
        "summary": {
            "retained_positive_records": len(positive_only),
            "positive_semantic_exact": sum(record["semantic_exact"] for record in positive_only),
            "positive_semantic_differences": len(differences),
            "page033_extra_controls": len(page033_controls),
            "page033_semantic_exact": sum(
                record["semantic_exact"] for record in page033_controls
            ),
            "multi_staff_positive_records": multi_staff,
            "candidate_primary_variant_disagreement_events": variant_disagreement,
            "candidate_stage_counts": dict(sorted(stage_counts.items())),
        },
        "differences": differences,
        "page033_controls": page033_controls,
        "records": records_out,
        "gates": {
            "retained_positive_count_175": len(positive_only) == REQUIRED_POSITIVE_COUNT,
            "all_retained_positives_exact_vs_j2": not differences,
            "page_025_exact": page_exact("page_025"),
            "page_055_exact": page_exact("page_055"),
            "page_042_five_overrides_exact": (
                len(page042_rows) == 5
                and all(record["semantic_exact"] for record in page042_rows)
            ),
            "page_033_one_bar_fallback_semantics_exact": page033_semantics,
            "candidate_rapidocr_calls_below_j2": (
                candidate_counter.calls < baseline_counter.calls
            ),
        },
    }
    _write_json(output_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--positive-audit", type=Path, default=DEFAULT_POSITIVE_AUDIT)
    parser.add_argument("--reuse-root", type=Path, default=DEFAULT_REUSE_ROOT)
    parser.add_argument("--numbering-root", type=Path, default=DEFAULT_NUMBERING_ROOT)
    parser.add_argument("--page033-causal", type=Path, default=DEFAULT_PAGE033_CAUSAL)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--provider", choices=("auto", "cpu", "cuda"), default="cuda")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()

    payload = run(
        positive_audit_path=args.positive_audit,
        reuse_root=args.reuse_root,
        numbering_root=args.numbering_root,
        page033_causal_path=args.page033_causal,
        model_path=args.model,
        output_path=args.output,
        provider_mode=args.provider,
        preflight_only=args.preflight,
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "summary": payload.get("summary"),
                "runtime": payload.get("runtime"),
                "gates": payload.get("gates"),
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
