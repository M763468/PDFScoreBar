"""Non-blocking exclusive lock files shared by POSIX and Windows (#535).

POSIX keeps the existing behaviour: ``O_NOFOLLOW`` and ``flock(LOCK_EX | LOCK_NB)``,
released when the descriptor closes.

Windows has neither. A lock file must be a regular file that is not a symlink or
other reparse point; this is checked before opening and re-checked on the open
handle (same file identity), so a swap between the check and the open is refused.
The lock is a mandatory ``msvcrt`` byte-range lock on byte 0, which the OS releases
when the handle is closed or the process exits. Contention raises
``BlockingIOError`` on both platforms, as ``flock`` does.
"""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path
from typing import IO, Any

_IS_WINDOWS = os.name == "nt"
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

if _IS_WINDOWS:  # pragma: no cover - exercised by the Windows-only tests
    import msvcrt
else:
    import fcntl


def _is_link_or_reparse(info: os.stat_result) -> bool:
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def open_lock_file(path: Path | str, *, create: bool = True, mode: int = 0o600) -> int:
    """Open a lock file without following links; return the raw descriptor."""

    lock_path = Path(path)
    flags = os.O_RDWR | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    if create:
        flags |= os.O_CREAT
    if not _IS_WINDOWS:
        return os.open(lock_path, flags | os.O_NOFOLLOW, mode)

    try:
        before = os.lstat(lock_path)
    except FileNotFoundError:
        if not create:
            raise
        before = None
    if before is not None and (_is_link_or_reparse(before) or not stat.S_ISREG(before.st_mode)):
        raise OSError(errno.ELOOP, "Lock file must be a regular file, not a link", str(lock_path))
    descriptor = os.open(lock_path, flags, mode)
    try:
        after = os.lstat(lock_path)
        opened = os.fstat(descriptor)
        if (
            _is_link_or_reparse(after)
            or not stat.S_ISREG(opened.st_mode)
            or (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise OSError(errno.ELOOP, "Lock file changed while opening", str(lock_path))
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def lock_exclusive_nonblocking(stream: IO[Any] | int) -> None:
    """Take an exclusive lock or raise ``BlockingIOError`` when another holder has it."""

    descriptor = stream if isinstance(stream, int) else stream.fileno()
    if not _IS_WINDOWS:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    os.lseek(descriptor, 0, os.SEEK_SET)
    try:
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EDEADLK, getattr(errno, "EDEADLOCK", -1)):
            raise BlockingIOError(errno.EAGAIN, "Lock is held by another holder") from exc
        raise
