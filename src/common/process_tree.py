"""Owned child-process trees that are killed as a unit (#535).

POSIX keeps the existing contract: the child leads a new session and the whole
process group is killed with SIGKILL, including descendants that outlive it.

Windows has no process groups. The child is created suspended, assigned to a Job
Object configured with ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` and only then resumed,
so every descendant it creates is in the job before it can run. ``kill()`` terminates
the job (child and all descendants, including ones whose parent already exited), and
the job handle is closed when the owner releases it or exits, so an owner that dies
first also takes its tree down.
"""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Sequence
from typing import Any

_IS_WINDOWS = os.name == "nt"

if _IS_WINDOWS:  # pragma: no cover - exercised by the Windows-only tests
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ntdll = ctypes.WinDLL("ntdll")

    _CREATE_SUSPENDED = 0x00000004
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_ulonglong)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.TerminateJobObject.restype = wintypes.BOOL
    _kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _ntdll.NtResumeProcess.restype = ctypes.c_long
    _ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]

    def _check(ok: Any, what: str) -> None:
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error(), what)

    def _new_kill_on_close_job() -> int:
        job = _kernel32.CreateJobObjectW(None, None)
        _check(job, "CreateJobObjectW")
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            _check(
                _kernel32.SetInformationJobObject(
                    job,
                    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                    ctypes.byref(info),
                    ctypes.sizeof(info),
                ),
                "SetInformationJobObject",
            )
        except BaseException:
            _kernel32.CloseHandle(job)
            raise
        return int(job)


class OwnedProcessTree:
    """A started child process whose whole descendant tree this object owns."""

    def __init__(self, command: Sequence[str] | str, **kwargs: Any) -> None:
        if "start_new_session" in kwargs or "preexec_fn" in kwargs:
            raise ValueError("OwnedProcessTree manages the process session itself")
        self._job: int | None = None
        if not _IS_WINDOWS:
            self.process = subprocess.Popen(command, start_new_session=True, **kwargs)
            return
        flags = int(kwargs.pop("creationflags", 0)) | _CREATE_SUSPENDED
        job = _new_kill_on_close_job()
        try:
            self.process = subprocess.Popen(command, creationflags=flags, **kwargs)
        except BaseException:
            _kernel32.CloseHandle(job)
            raise
        handle = int(self.process._handle)  # type: ignore[attr-defined]
        try:
            _check(_kernel32.AssignProcessToJobObject(job, handle), "AssignProcessToJobObject")
            status = _ntdll.NtResumeProcess(handle)
            if status < 0:
                raise OSError(f"NtResumeProcess failed: NTSTATUS 0x{status & 0xFFFFFFFF:08X}")
        except BaseException:
            # Closing a kill-on-close job terminates the still-suspended child.
            _kernel32.CloseHandle(job)
            self.process.wait()
            raise
        self._job = job

    @property
    def pid(self) -> int:
        return self.process.pid

    def poll(self) -> int | None:
        return self.process.poll()

    def wait(self, timeout: float | None = None) -> int:
        return self.process.wait(timeout)

    def kill_tree(self) -> None:
        """Kill the child and every descendant; safe to call more than once."""

        if _IS_WINDOWS:
            if self._job is not None:
                _kernel32.TerminateJobObject(self._job, 1)
            return
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def close(self) -> None:
        """Kill the tree, reap the child and release the job handle."""

        try:
            self.kill_tree()
            self.process.wait()
        finally:
            if self._job is not None:
                job, self._job = self._job, None
                _kernel32.CloseHandle(job)

    def __enter__(self) -> OwnedProcessTree:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
