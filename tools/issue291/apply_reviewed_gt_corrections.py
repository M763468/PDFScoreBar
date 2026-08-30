#!/usr/bin/env python3
"""Apply the visually reviewed Issue #291 canonical GT corrections.

This is temporary issue tooling.  It edits only canonical
``data/evaluation2/annotations/*/page_*/boxes_sorted.json`` files and never
changes detector/model/threshold/runtime behavior.

The reviewed decision is:
- historical P1 #1-#11: two plain ``barline`` boxes describe one physical ink
  line; keep one existing representative (taller box, tie -> earlier index);
- historical P1 #12: both boxes cover a time-signature glyph, not a barline;
  remove both;
- semantic multi-line events (double/end/repeat) are never touched.

Run without ``--apply`` for a strict dry-run.  With ``--apply`` the script
verifies all expected pre-edit indices/bboxes first, writes the corrected JSON,
renumbers ``measure_number`` sequentially, and validates the full68 aggregate.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXPECTED_PAGE_COUNT = 68
EXPECTED_GT_BEFORE = 3580
EXPECTED_GT_AFTER = 3567


@dataclass(frozen=True)
class PairCorrection:
    pair_id: int
    score: str
    page: str
    index_a: int
    box_a: tuple[int, int, int, int]
    index_b: int
    box_b: tuple[int, int, int, int]
    keep_index: int | None

    @property
    def remove_indices(self) -> tuple[int, ...]:
        if self.keep_index is None:
            return (self.index_a, self.index_b)
        if self.keep_index == self.index_a:
            return (self.index_b,)
        if self.keep_index == self.index_b:
            return (self.index_a,)
        raise ValueError(f"invalid keep_index for P1 #{self.pair_id}: {self.keep_index}")


CORRECTIONS = (
    PairCorrection(1, "Shostakovich-Festival_Overture_Va", "page_009", 12, (1232, 1848, 1236, 1959), 13, (1234, 1848, 1238, 1959), 12),
    PairCorrection(2, "Shostakovich-Sym5-Va", "page_004", 33, (1688, 2626, 1692, 2725), 34, (1690, 2627, 1699, 2727), 34),
    PairCorrection(3, "Shostakovich-Sym5-Va", "page_004", 39, (2728, 1896, 2732, 1995), 40, (2730, 1893, 2739, 1995), 40),
    PairCorrection(4, "Shostakovich-Sym5-Va", "page_006", 30, (2726, 2619, 2730, 2718), 31, (2728, 2612, 2737, 2714), 31),
    PairCorrection(5, "Shostakovich-Sym5-Va", "page_008", 27, (2743, 428, 2747, 528), 28, (2745, 428, 2754, 530), 28),
    PairCorrection(6, "Shostakovich-Sym5-Va", "page_010", 5, (2713, 1520, 2717, 1620), 6, (2715, 1512, 2724, 1615), 6),
    PairCorrection(7, "Shostakovich-Sym5-Va", "page_013", 22, (1679, 1168, 1683, 1270), 23, (1679, 1202, 1683, 1296), 22),
    PairCorrection(8, "Shostakovich-Sym5-Va", "page_015", 30, (2294, 2244, 2298, 2344), 31, (2296, 2246, 2305, 2344), 30),
    PairCorrection(9, "Shostakovich-Sym5-Va", "page_022", 10, (2730, 2255, 2734, 2355), 11, (2732, 2247, 2741, 2351), 11),
    PairCorrection(10, "Sibelius-Violin_Concerto-Viola", "page_004", 53, (1514, 4015, 1518, 4195), 54, (1514, 4092, 1518, 4196), 53),
    PairCorrection(11, "Sibelius-Violin_Concerto-Viola", "page_004", 56, (1923, 4092, 1927, 4196), 57, (1924, 4015, 1928, 4195), 57),
    PairCorrection(12, "Va__Prokofiev_Symphony5", "page_007", 0, (665, 908, 669, 1018), 1, (668, 908, 672, 1018), None),
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def bbox(row: Any) -> tuple[int, int, int, int]:
    if not isinstance(row, dict):
        raise ValueError(f"GT row is not an object: {row!r}")
    raw = row.get("barline_location")
    if not isinstance(raw, list) or len(raw) != 4:
        raise ValueError(f"GT row lacks barline_location: {row!r}")
    return tuple(int(value) for value in raw)  # type: ignore[return-value]


def barline_type(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    return str(row.get("barline_type") or "barline")


def canonical_files(root: Path) -> list[Path]:
    return sorted(root.glob("*/page_*/boxes_sorted.json"))


def aggregate_count(root: Path) -> tuple[int, int]:
    files = canonical_files(root)
    total = 0
    for path in files:
        payload = load_json(path)
        if not isinstance(payload, list):
            raise ValueError(f"GT payload is not a list: {path}")
        total += len(payload)
    return len(files), total


def p1_conflicts(root: Path) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for path in canonical_files(root):
        payload = load_json(path)
        if not isinstance(payload, list):
            continue
        for i, first in enumerate(payload):
            if barline_type(first) != "barline":
                continue
            a = bbox(first)
            aw = max(1, a[2] - a[0])
            ah = max(1, a[3] - a[1])
            for j in range(i + 1, len(payload)):
                second = payload[j]
                if barline_type(second) != "barline":
                    continue
                b = bbox(second)
                bw = max(1, b[2] - b[0])
                bh = max(1, b[3] - b[1])
                x_overlap = max(0, min(a[2], b[2]) - max(a[0], b[0])) / min(aw, bw)
                if x_overlap < 0.25:
                    continue
                y_overlap = max(0, min(a[3], b[3]) - max(a[1], b[1])) / min(ah, bh)
                if y_overlap < 0.70:
                    continue
                conflicts.append(
                    {
                        "path": str(path),
                        "indices": [i, j],
                        "bboxes": [list(a), list(b)],
                        "x_overlap_over_min": x_overlap,
                        "y_overlap_over_min": y_overlap,
                    }
                )
    return conflicts


def verify_pair(payload: list[Any], correction: PairCorrection, path: Path) -> None:
    for index, expected in (
        (correction.index_a, correction.box_a),
        (correction.index_b, correction.box_b),
    ):
        if index >= len(payload):
            raise IndexError(f"P1 #{correction.pair_id}: index {index} missing in {path}")
        row = payload[index]
        actual = bbox(row)
        if actual != expected:
            raise RuntimeError(
                f"P1 #{correction.pair_id}: bbox mismatch at {path}[{index}]: "
                f"expected={expected}, actual={actual}"
            )
        if barline_type(row) != "barline":
            raise RuntimeError(
                f"P1 #{correction.pair_id}: expected plain barline at {path}[{index}], "
                f"got {barline_type(row)!r}"
            )

    if correction.keep_index is not None:
        ha = correction.box_a[3] - correction.box_a[1]
        hb = correction.box_b[3] - correction.box_b[1]
        expected_keep = correction.index_a if ha >= hb else correction.index_b
        if correction.keep_index != expected_keep:
            raise RuntimeError(
                f"P1 #{correction.pair_id}: representative policy mismatch: "
                f"planned={correction.keep_index}, taller/tie-earlier={expected_keep}"
            )


def renumber(payload: list[Any]) -> None:
    for number, row in enumerate(payload, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"GT row is not an object: {row!r}")
        row["measure_number"] = number


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gt-root",
        type=Path,
        default=Path("data/evaluation2/annotations"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the reviewed corrections. Default is strict dry-run only.",
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    page_count, total_before = aggregate_count(args.gt_root)
    if page_count != EXPECTED_PAGE_COUNT or total_before != EXPECTED_GT_BEFORE:
        raise RuntimeError(
            f"Unexpected canonical GT baseline: pages={page_count}, gt={total_before}; "
            f"expected {EXPECTED_PAGE_COUNT}/{EXPECTED_GT_BEFORE}"
        )

    by_path: dict[Path, list[PairCorrection]] = {}
    for correction in CORRECTIONS:
        path = args.gt_root / correction.score / correction.page / "boxes_sorted.json"
        by_path.setdefault(path, []).append(correction)

    plans: list[dict[str, Any]] = []
    for path, corrections in by_path.items():
        payload = load_json(path)
        if not isinstance(payload, list):
            raise ValueError(f"GT payload is not a list: {path}")
        for correction in corrections:
            verify_pair(payload, correction, path)

        remove_indices = sorted(
            {index for correction in corrections for index in correction.remove_indices},
            reverse=True,
        )
        before = len(payload)
        after = before - len(remove_indices)
        plans.append(
            {
                "path": str(path),
                "before": before,
                "after": after,
                "remove_indices": sorted(remove_indices),
                "pair_ids": [correction.pair_id for correction in corrections],
            }
        )

        if args.apply:
            for index in remove_indices:
                del payload[index]
            renumber(payload)
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    report: dict[str, Any] = {
        "schema_version": "issue291.reviewed_gt_correction.v1",
        "mode": "apply" if args.apply else "dry-run",
        "canonical_pages_before": page_count,
        "canonical_gt_before": total_before,
        "planned_removed_slots": sum(item["before"] - item["after"] for item in plans),
        "planned_canonical_gt_after": EXPECTED_GT_AFTER,
        "pages": plans,
        "p1_historical_pair_count": len(CORRECTIONS),
        "same_ink_duplicate_pairs_collapsed": 11,
        "false_gt_boxes_removed": 2,
    }

    if args.apply:
        page_count_after, total_after = aggregate_count(args.gt_root)
        conflicts = p1_conflicts(args.gt_root)
        report.update(
            {
                "canonical_pages_after": page_count_after,
                "canonical_gt_after": total_after,
                "remaining_plain_barline_p1_conflicts": conflicts,
            }
        )
        if page_count_after != EXPECTED_PAGE_COUNT or total_after != EXPECTED_GT_AFTER:
            raise RuntimeError(
                f"Unexpected corrected canonical GT: pages={page_count_after}, gt={total_after}; "
                f"expected {EXPECTED_PAGE_COUNT}/{EXPECTED_GT_AFTER}"
            )
        if conflicts:
            raise RuntimeError(f"P1 conflicts remain after correction: {conflicts}")

    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
