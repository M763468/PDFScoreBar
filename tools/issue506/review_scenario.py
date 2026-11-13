"""Issue #506: scripted review scenario against a running review server.

save one MMR correction -> apply (corrected PDF) -> resume in a new session from the
resulting checkpoint (uploads the original PDF) -> verify the session sees the record.
Writes a JSON summary to stdout. Works identically for Docker and native servers.
"""

from __future__ import annotations

import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = sys.argv[1].rstrip("/")  # e.g. http://127.0.0.1:8016
PDF = Path(sys.argv[2])  # original input PDF for resume upload
PORT = BASE.rsplit(":", 1)[1]


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(BASE + path, data=data, method=method)
    request.add_header("Host", f"127.0.0.1:{PORT}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
        request.add_header("Origin", f"http://127.0.0.1:{PORT}")
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read())


ITEMS = [
    {
        "op": "set_measure_span",
        "page": 0,
        "system": 1,
        "measure": 2,
        "reason": "issue506 scripted correction",
        "measure_span": 3,
    }
]

summary: dict = {}
summary["initial_counts"] = call("GET", "/api/state")["package"]["counts"]
summary["save"] = call("POST", "/api/save", {"page": 0, "correction_type": "mmr_measure_span", "items": ITEMS})
started = time.time()
summary["apply_start"] = call("POST", "/api/apply", {})
while True:
    state = call("GET", "/api/state")["package"]
    if not state["counts"].get("applying") and state.get("current_result"):
        break
    if time.time() - started > 900:
        raise SystemExit("apply timeout")
    time.sleep(2)
summary["apply_wall_sec"] = round(time.time() - started, 1)
result = state["current_result"]
summary["apply_result"] = {k: result.get(k) for k in ("checkpoint_id", "final_pdf_sha256", "identity", "result_identity", "corrections_identity", "source_identity")}
summary["after_apply_counts"] = state["counts"]
resume = call(
    "POST",
    "/api/resume",
    {"checkpoint_id": result["checkpoint_id"], "pdf_base64": base64.b64encode(PDF.read_bytes()).decode("ascii")},
)
summary["resume"] = resume
session_state = call("GET", "/api/state?session=" + resume["session"])
summary["resumed_session_counts"] = session_state["package"]["counts"]
summary["resumed_mmr"] = call("GET", "/api/manual_corrections?type=mmr_measure_span&page=0&session=" + resume["session"])
print(json.dumps(summary, indent=2))
