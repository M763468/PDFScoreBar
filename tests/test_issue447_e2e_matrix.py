"""Exercise fresh-output matrix orchestration without Docker, models or inference."""

import json
from types import SimpleNamespace

from tools.issue447 import e2e_candidate_matrix as matrix


def test_fresh_matrix_reaches_both_replays_and_conditional_combination(tmp_path, monkeypatch):
    issue = tmp_path / "logs/issue447"
    out = issue / "e2e-candidates"
    seed = issue / "cache"
    seed.mkdir(parents=True)
    (seed / "kernel").write_bytes(b"fixed warm seed")
    monkeypatch.setattr(matrix, "ROOT", tmp_path)
    monkeypatch.setattr(matrix, "ISSUE", issue)
    monkeypatch.setattr(matrix, "OUT", out)
    monkeypatch.setattr(matrix, "pipeline_checks", lambda *args: {"all_equal": True})
    monkeypatch.setattr(matrix, "proc_summary", lambda path: {"cgroup_memory_peak_bytes": 1024})
    monkeypatch.setattr(matrix, "gpu_summary", lambda path: {"memory.used [MiB]": {"peak": 100}})
    launched, replays = [], []

    def execute(command, **kwargs):
        if "--label" in command:
            label = command[command.index("--label") + 1]
            mode = label.split("-")[-2]
            launched.append(label)
            directory = issue / "runs" / label
            directory.mkdir(parents=True)
            (directory / "result.json").write_text(
                json.dumps({"docker_e2e_wall_seconds": {"b": 100, "p": 90, "o": 90, "c": 80}[mode]})
            )
        else:
            # The real replay subprocess can start only after its log was opened.
            assert command[0] == "docker"
            log = kwargs["stdout"]
            assert log.name in (
                str(out / "validation/replay-single.log"),
                str(out / "validation/replay-combined.log"),
            )
            assert not log.closed
            replays.append(command[command.index("--output") + 1])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(matrix.subprocess, "run", execute)
    matrix.main()

    assert len(launched) == 12
    assert [label.split("-")[-2] for label in launched[:6]] == ["b", "p", "o", "o", "p", "b"]
    assert [label.split("-")[-2] for label in launched[-3:]] == ["c", "c", "c"]
    assert replays == [
        "logs/issue447/e2e-candidates/replay-single",
        "logs/issue447/e2e-candidates/replay-combined",
    ]
    journal = [json.loads(line) for line in (out / "matrix.jsonl").read_text().splitlines()]
    assert journal[-1]["event"] == "complete"
    assert journal[-1]["combined_executed"] is True
