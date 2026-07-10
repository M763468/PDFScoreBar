import sys
from pathlib import Path

# Several lightweight correction tests install a fallback ``fitz`` module with
# ``setdefault`` during collection. Resolve the real PyMuPDF module first when
# it is available so those fallbacks cannot pollute later integration tests.
try:
    import fitz as _fitz  # noqa: F401
except ImportError:
    pass

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
