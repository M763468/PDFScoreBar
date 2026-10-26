"""Rescore the fixed #441 browser run and retrieve its result after server restart.

No inference. Execute inside the same Docker mount/network as the review server.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import re
from pathlib import Path
from urllib.parse import urlparse


def require(condition, message):
    if not condition:
        raise ValueError(message)


def numbers(run):
    paths = sorted((run / "outputs").glob("page_*/numbering_final.json"))
    require(len(paths) == 15, "Fixed experiment requires all 15 numbering outputs")
    return [
        [
            [measure.get("number") for measure in system.get("measures", [])]
            for system in json.loads(path.read_text())["pages"][0]["systems"]
        ]
        for path in paths
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    require(report["passed"] is True and report["errors"] == [], "Browser workflow failed")
    require(re.fullmatch(r"s_[0-9a-f]{32}", report["session"]), "Invalid session ID")
    baseline, edited, undone = [
        numbers(Path(report[key]["corrected_run"])) for key in ("baseline", "edited", "undone")
    ]
    expected = numbers(args.job / "review/application_runs/attempt_0012/corrected")
    require(baseline == expected, "Resumed baseline numbering differs from retained checkpoint")
    require(edited != baseline, "MMR edit did not change numbering")
    require(undone == baseline, "Undo did not restore all numbering sequences")
    url = urlparse(args.url)
    require(
        url.scheme == "http" and url.hostname == "127.0.0.1" and url.port,
        "Use the local review server URL",
    )
    conn = http.client.HTTPConnection(url.hostname, url.port, timeout=15)
    try:
        query = "?session=" + report["session"]
        conn.request("GET", "/api/state" + query)
        response = conn.getresponse()
        data = response.read()
        require(response.status == 200, "Session state unavailable after restart")
        state = json.loads(data)
        require(
            state["package"]["current_result"]["final_pdf_sha256"]
            == report["undone"]["final_pdf_sha256"],
            "Restart did not restore the exact current result",
        )
        conn.request("GET", "/api/checkpoints" + query)
        response = conn.getresponse()
        history = json.loads(response.read())
        require(
            response.status == 200
            and [item["status"] for item in history["applications"]] == ["succeeded"] * 3,
            "Per-attempt history did not survive restart",
        )
        conn.request("GET", "/api/result" + query)
        response = conn.getresponse()
        pdf = response.read()
        require(
            response.status == 200
            and hashlib.sha256(pdf).hexdigest() == report["undone"]["final_pdf_sha256"],
            "Downloaded result differs after restart",
        )
    finally:
        conn.close()
    result = {
        key: True
        for key in (
            "baseline_matches_retained",
            "edit_changes_numbers",
            "undo_restores_all_numbers",
            "server_restart_restores_exact_result",
            "all_three_attempts_retained_after_restart",
        )
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print("All 15-page numbering and post-restart result gates passed")


if __name__ == "__main__":
    main()
