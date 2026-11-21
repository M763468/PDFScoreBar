"""Serve the PDFScoreBar job launcher and its package-scoped review pages."""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import socket
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from types import SimpleNamespace
from urllib.parse import quote, unquote, urlsplit

from tools.browser_jobs.jobs import JOB_ID, MAX_BYTES, MAX_PAGES, Jobs, exclusive_root
from tools.review_correction.application import CorrectionApplication
from tools.review_correction.server import (
    LocalThreadingHTTPServer,
    ReviewHandler,
    ReviewPackage,
)

UI_ROOT = Path(__file__).resolve().parent


class JobHandler(ReviewHandler):
    timeout = 30

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def _trusted_host(self):
        if self.headers.get_all("Host", []) != [self._host]:
            self.send_error(403, "Use the local application address")
            return False
        origins = self.headers.get_all("Origin", [])
        if origins and origins != [f"http://{self._host}"]:
            self.send_error(403, "Use the local application origin")
            return False
        return True

    @property
    def _host(self):
        return f"127.0.0.1:{self.server.server_port}"

    def _review_context(self):
        return self.review_context

    def _route(self, write=False):
        if not self._trusted_host():
            return
        parsed = urlsplit(self.path)
        parts = parsed.path.split("/", 4)
        if len(parts) >= 4 and parts[1] == "jobs" and JOB_ID.fullmatch(parts[2]):
            job_id, action = parts[2:4]
            if action == "review" and len(parts) == 5:
                self._review(job_id, "/" + parts[4], parsed.query, write)
                return
            if not write and action == "pdf" and len(parts) == 4:
                self._pdf(job_id)
                return
        if parsed.query:
            self.send_error(404)
        elif write and parsed.path == "/api/jobs":
            self._submit()
        elif not write and parsed.path == "/api/jobs":
            self._json({"jobs": self.server.jobs.list()})
        elif not write and parsed.path in {"/", "/jobs.js"}:
            self._file(UI_ROOT / ("index.html" if parsed.path == "/" else "jobs.js"))
        else:
            self.send_error(404)

    def do_GET(self):
        self._route()

    def do_POST(self):
        self._route(write=True)

    def _submit(self):
        if self.headers.get_all("Origin") != [f"http://{self._host}"]:
            self.send_error(403, "Same-origin submission required")
            return
        if self.headers.get_all("Content-Type") != ["application/pdf"]:
            self.send_error(415, "PDF content type required")
            return
        sizes = self.headers.get_all("Content-Length", [])
        if (
            self.headers.get("Transfer-Encoding")
            or len(sizes) != 1
            or not re.fullmatch(r"[0-9]{1,12}", sizes[0])
        ):
            self.send_error(411, "A PDF content length is required")
            return
        size = int(sizes[0])
        if not 0 < size <= MAX_BYTES:
            self.send_error(413, "PDF is empty or exceeds the upload limit")
            return
        try:
            name = unquote(self.headers.get("X-PDF-Name", ""), errors="strict")
            if not re.fullmatch(r"[^/\\\x00-\x1f\x7f]{1,255}", name) or not name.lower().endswith(
                ".pdf"
            ):
                raise ValueError("Choose a PDF filename")
            selection = self.headers.get("X-PDF-Pages", "")
            pages = []
            if selection:
                entries = selection.split(",")
                if len(entries) > MAX_PAGES or any(
                    not re.fullmatch(r"[1-9][0-9]{0,8}", p.strip()) for p in entries
                ):
                    raise ValueError("Enter positive page numbers separated by commas")
                pages = [int(p) for p in entries]
            job_id = self.server.jobs.submit(self.rfile, size, name, pages)
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        except OverflowError as exc:
            self.send_error(409, str(exc))
            return
        except TimeoutError:
            self.send_error(408, "PDF upload timed out")
            return
        except OSError:
            logging.exception("Unable to store uploaded PDF")
            self.send_error(500, "Could not store the uploaded PDF")
            return
        self._json({"id": job_id})

    def _pdf(self, job_id):
        try:
            path = self.server.jobs.artifact(job_id, "final.score_numbered_pdf")
            stream = path.open("rb")
        except (OSError, ValueError):
            self.send_error(404, "Numbered PDF unavailable")
            return
        with stream:
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(path.stat().st_size))
            self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{quote(path.name)}")
            self.end_headers()
            shutil.copyfileobj(stream, self.wfile)

    def _review(self, job_id, path, query, write):
        # Preserve the standalone review server's serialized request handling.
        with self.server.review_lock:
            try:
                if job_id not in self.server.reviews:
                    handoff = self.server.jobs.artifact(job_id, "review.manual_correction_input")
                    package = ReviewPackage(handoff)
                    self.server.reviews[job_id] = SimpleNamespace(
                        package=package,
                        application=CorrectionApplication(package, handoff),
                        sessions={},
                    )
                self.review_context = self.server.reviews[job_id]
            except (OSError, ValueError, KeyError, TypeError):
                logging.exception("Review package unavailable for %s", job_id)
                self.send_error(404, "Review package unavailable")
                return
            self.path = path + ("?" + query if query else "")
            if write:
                super().do_POST()
            else:
                super().do_GET()


def create_server(jobs: Jobs, *, port: int = 8010) -> ThreadingHTTPServer:
    server = LocalThreadingHTTPServer(("127.0.0.1", port), JobHandler)
    server.daemon_threads = False
    server.jobs = jobs
    server.reviews = {}
    server.review_lock = Lock()
    return server


def serve(output: Path, *, port: int = 8010, relay_port: int | None = None, run_job=None):
    """Start the loopback UI after the launcher has validated its runtime."""
    output = output.resolve()
    with exclusive_root(output):
        jobs = Jobs(output, **({"run_job": run_job} if run_job is not None else {}))
        try:
            with create_server(jobs, port=port) as server:
                if relay_port is not None:
                    from docker.review_relay import default_gateway, serve_relay

                    gateway = default_gateway()
                    listener = socket.create_server(("0.0.0.0", relay_port))
                    Thread(
                        target=serve_relay,
                        args=(listener,),
                        kwargs={"target_port": server.server_port, "allowed_peer": gateway},
                        daemon=True,
                    ).start()
                print(f"PDFScoreBar: http://127.0.0.1:{server.server_port}/", flush=True)
                server.serve_forever()
        finally:
            jobs.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--relay-port", type=int)
    args = parser.parse_args()
    try:
        serve(args.output, port=args.port, relay_port=args.relay_port)
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        parser.exit(2, f"Could not start PDFScoreBar: {exc}\n")


if __name__ == "__main__":
    main()
