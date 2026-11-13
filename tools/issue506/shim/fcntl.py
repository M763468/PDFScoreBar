"""Issue #506 PoC-only fcntl.flock emulation for Windows. NOT production code.

Locks one byte far beyond EOF with msvcrt so the data region of a locked file stays
readable/writable through other handles. Advisory semantics are approximated; only
LOCK_EX|LOCK_NB and LOCK_UN are used by the review application.
"""
import msvcrt
import os

LOCK_SH, LOCK_EX, LOCK_NB, LOCK_UN = 1, 2, 4, 8
_OFFSET = 0x7FFFFFFF


def _fd(obj):
    return obj if isinstance(obj, int) else obj.fileno()


def flock(obj, operation):
    fd = _fd(obj)
    position = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, _OFFSET, os.SEEK_SET)
        if operation & LOCK_UN:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK if operation & LOCK_NB else msvcrt.LK_LOCK, 1)
            except OSError as exc:
                raise BlockingIOError(11, "Resource temporarily unavailable") from exc
    finally:
        os.lseek(fd, position, os.SEEK_SET)
