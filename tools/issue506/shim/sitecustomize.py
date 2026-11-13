"""Issue #506 PoC-only shims. NOT production code.

* ``os.O_NOFOLLOW`` constant for the review application on Windows.
* Optional ONNX Runtime session audit: when ``PDFSCORE_POC_ORT_AUDIT_DIR`` is set, every
  ``onnxruntime.InferenceSession`` created in any process that inherits this PYTHONPATH is
  recorded (requested/active providers, model, argv, pid) to ``<dir>/ort-<pid>.jsonl``.
  This observes, and never changes, provider selection.
"""

import os

if os.name == "nt" and not hasattr(os, "O_NOFOLLOW"):
    os.O_NOFOLLOW = 0


def _install_ort_audit(audit_dir: str) -> None:
    import importlib.abc
    import importlib.util
    import json
    import sys
    import time

    def wrap(module) -> None:
        original = module.InferenceSession
        if getattr(original, "_issue506_audit", False):
            return

        class AuditedInferenceSession(original):
            _issue506_audit = True

            def __init__(self, path_or_bytes, *args, **kwargs):
                requested = kwargs.get("providers", args[1] if len(args) >= 2 else None)
                record = {
                    "time": time.time(),
                    "pid": os.getpid(),
                    "argv": sys.argv,
                    "model": path_or_bytes if isinstance(path_or_bytes, str) else "<bytes>",
                    "requested_providers": json.loads(json.dumps(requested, default=str)),
                }
                try:
                    super().__init__(path_or_bytes, *args, **kwargs)
                    record["active_providers"] = list(self.get_providers())
                except Exception as error:  # recorded, then re-raised unchanged
                    record["error"] = f"{type(error).__name__}: {error}"
                    raise
                finally:
                    os.makedirs(audit_dir, exist_ok=True)
                    with open(os.path.join(audit_dir, f"ort-{os.getpid()}.jsonl"), "a", encoding="utf-8") as out:
                        out.write(json.dumps(record) + "\n")

        module.InferenceSession = AuditedInferenceSession
        capi = sys.modules.get("onnxruntime.capi.onnxruntime_inference_collection")
        if capi is not None:
            capi.InferenceSession = AuditedInferenceSession

    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name != "onnxruntime":
                return None
            sys.meta_path.remove(self)
            try:
                spec = importlib.util.find_spec(name)
            finally:
                sys.meta_path.insert(0, self)
            if spec is None or spec.loader is None:
                return spec
            loader = spec.loader
            original_exec = loader.exec_module

            def exec_module(module):
                original_exec(module)
                wrap(module)

            loader.exec_module = exec_module
            return spec

    sys.meta_path.insert(0, Finder())


if os.environ.get("PDFSCORE_POC_ORT_AUDIT_DIR"):
    _install_ort_audit(os.environ["PDFSCORE_POC_ORT_AUDIT_DIR"])
