"""Replay the retained #447 source-coordinate correction against all multi-page runs."""

import json
from pathlib import Path

from tools.issue447.e2e_correction_replay import run


def main():
    root = Path.cwd()
    issue = root / "logs/issue454/final"
    output = issue / "correction-replay"
    output.mkdir(parents=True, exist_ok=False)
    overrides = json.loads((root / "tools/issue454/fixed-overrides.json").read_text())
    reference = None
    rows = []
    for uid in (0, 1000):
        for pair in (1, 2, 3):
            for state in ("cold", "warm"):
                label = f"u{uid}-multi-{pair}-{state}"
                result = run(label, output / label, overrides, source_runs=issue / "runs")
                compared = {
                    k: result[k] for k in ("corrected_boxes", "stats", "final_pages", "base_pages")
                }
                if reference is None:
                    reference = compared
                checks = dict(result["checks"], all_corrected_outputs_equal=compared == reference)
                rows.append(dict(label=label, checks=checks))
    (output / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    assert all(all(row["checks"].values()) for row in rows)
    print("12 multi-page correction replays passed")


if __name__ == "__main__":
    main()
