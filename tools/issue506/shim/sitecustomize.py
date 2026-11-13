"""Issue #506 PoC-only POSIX constant shim. NOT production code."""
import os

if os.name == "nt" and not hasattr(os, "O_NOFOLLOW"):
    os.O_NOFOLLOW = 0  # NTFS reparse points are not followed-checked by this PoC.
