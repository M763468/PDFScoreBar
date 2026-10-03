"""Local application adapter for immutable, package-bound correction runs."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
from pathlib import Path
from threading import Lock, Thread

from src.pipeline.review.apply_corrections import (
    _resolve_source_manifest_path,
    apply_corrections_and_rerun,
)


class CorrectionApplication:
    def __init__(self, package, handoff: Path):
        self.package = package
        self.handoff = handoff.resolve()
        self.root = package.root / "application_runs"
        self.lock = Lock()
        self.thread = None
        self.process_lock = None

    def _safe_root(self):
        if self.root.is_symlink() or self.root.resolve() != self.root:
            raise ValueError("Application output directory must stay in the review package")
        self.root.mkdir(exist_ok=True)

    def start(self):
        if not self.lock.acquire(blocking=False):
            raise ValueError("A corrected result is already being generated")
        apply_started = False
        try:
            self._safe_root()
            descriptor = os.open(
                self.root / ".apply.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
            )
            self.process_lock = os.fdopen(descriptor, "r+")
            try:
                fcntl.flock(self.process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError(
                    "A corrected result is already being generated for this package"
                ) from exc
            identity = self.package.state.begin_apply()
            apply_started = True
            response = self.package.state.snapshot()
            self.thread = Thread(target=self._run, args=(identity,), daemon=True)
            self.thread.start()
            return response
        except Exception as exc:
            if apply_started:
                self.package.state.fail_apply(str(exc))
            if self.process_lock is not None:
                self.process_lock.close()
                self.process_lock = None
            self.lock.release()
            raise

    def _allocate(self):
        # Stable monotonic names, including failed attempts; never reuse an existing run.
        number = 1
        while True:
            attempt = self.root / f"attempt_{number:04d}"
            try:
                attempt.mkdir()
                return attempt
            except FileExistsError:
                number += 1

    def _run(self, identity):
        try:
            self._safe_root()
            attempt = self._allocate()
            review = attempt / "input_review"
            review.mkdir()
            # Snapshot only declared package artifacts and correction files. Derived
            # canonical files are generated in this copy, leaving recorded inputs intact.
            for rel in self.package.reads:
                source = self.package.readable(rel)
                target = review / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            for rel in self.package.writes:
                source = self.package.writable(rel)
                if source.is_file():
                    target = review / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
            payload = json.loads(self.handoff.read_text(encoding="utf-8"))
            manifest = _resolve_source_manifest_path(payload, self.package.root)
            payload["source_manifest"] = str(manifest)
            snapshot_handoff = review / "manual_correction_input.json"
            snapshot_handoff.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            if self.package.state.capture_identity() != identity:
                raise ValueError("Review inputs changed while preparing the corrected run")
            provenance = {
                **identity,
                "source_handoff": str(self.handoff),
                "snapshot_handoff": str(snapshot_handoff),
            }
            (attempt / "consumed_inputs.json").write_text(
                json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
            )
            run = apply_corrections_and_rerun(
                snapshot_handoff,
                output_root=attempt,
                run_id="corrected",
                overwrite=False,
                generate_final_pdf=True,
            )
            summary = json.loads(
                (run / "review" / "correction_summary.json").read_text(encoding="utf-8")
            )
            final = Path(summary.get("final_pdf") or "").resolve()
            if not final.is_file() or (run / "final").resolve() not in final.parents:
                raise ValueError("The corrected final PDF was not generated")
            data = final.read_bytes()
            if not data.startswith(b"%PDF-"):
                raise ValueError("The corrected output is not a PDF")
            movement_inputs = {
                rel: hashlib.sha256((review / rel).read_bytes()).hexdigest()
                for page in self.package.pages
                if (rel := page.get("movement_boundary_resolved_output"))
                and (review / rel).is_file()
            }
            self.package.state.finish_apply(
                {
                    **identity,
                    "source_handoff": str(self.handoff),
                    "consumed_inputs": str(attempt / "consumed_inputs.json"),
                    "movement_review_inputs": movement_inputs,
                },
                corrected_run=str(run.resolve()),
                final_pdf=str(final),
                final_pdf_sha256=hashlib.sha256(data).hexdigest(),
            )
        except Exception as exc:
            self.package.state.fail_apply(str(exc))
        finally:
            if self.process_lock is not None:
                self.process_lock.close()
                self.process_lock = None
            self.lock.release()

    def result(self):
        result = self.package.state.snapshot()["package"]["last_successful_result"]
        if not result:
            raise ValueError("No corrected final PDF has been generated")
        final = Path(result["final_pdf"])
        self._safe_root()
        if final.resolve() != final or self.root not in final.parents or not final.is_file():
            raise ValueError("The corrected final PDF is unavailable")
        if hashlib.sha256(final.read_bytes()).hexdigest() != result["final_pdf_sha256"]:
            raise ValueError("The corrected final PDF changed after generation")
        return final
