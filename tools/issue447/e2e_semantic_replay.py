"""Actual production Phase C replay over matrix outputs, reusing real MMR results."""

import argparse
import json
from pathlib import Path

from tools.issue447.replay_numbering import replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    results, baseline = [], None
    for label in args.labels:
        result = replay(Path.cwd(), label, args.output / label)
        if baseline is None:
            baseline = result["pages"]
        checks = {**result["checks"], "pages_and_metadata_equal": result["pages"] == baseline}
        results.append({"label": label, "checks": checks})
    (args.output / "result.json").write_text(json.dumps(results, indent=2) + "\n")
    if not all(all(r["checks"].values()) for r in results):
        raise SystemExit(1)
    print(json.dumps(results))


if __name__ == "__main__":
    main()
