"""Untrusted one-job PDF safety helpers for the versioned engine boundary."""

from __future__ import annotations

import hashlib
import math
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from src.pipeline.engine_contract import EngineError, ErrorCategory

_MIB = 1024 * 1024
_GIB = 1024 * _MIB
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass(frozen=True)
class JobSafetyPolicy:
    """Configurable hard bounds for one untrusted PDF job."""

    max_pdf_bytes: int = 256 * _MIB
    max_document_pages: int = 500
    max_selected_pages: int = 200
    max_render_width_px: int = 12_000
    max_render_height_px: int = 12_000
    max_render_pixels_per_page: int = 64_000_000
    max_total_render_pixels: int = 1_000_000_000
    max_attempt_disk_bytes: int = 16 * _GIB
    allow_symlinks: bool = False
    require_input_root: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_pdf_bytes",
            "max_document_pages",
            "max_selected_pages",
            "max_render_width_px",
            "max_render_height_px",
            "max_render_pixels_per_page",
            "max_total_render_pixels",
            "max_attempt_disk_bytes",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be an integer > 0")
        if not isinstance(self.allow_symlinks, bool) or not isinstance(
            self.require_input_root, bool
        ):
            raise ValueError("safety policy flags must be boolean")

    def resource_budget(self) -> dict[str, int]:
        return {
            name: getattr(self, name)
            for name in (
                "max_pdf_bytes",
                "max_document_pages",
                "max_selected_pages",
                "max_render_width_px",
                "max_render_height_px",
                "max_render_pixels_per_page",
                "max_total_render_pixels",
                "max_attempt_disk_bytes",
            )
        }


DEFAULT_JOB_SAFETY_POLICY = JobSafetyPolicy()


@dataclass(frozen=True)
class ValidatedPageMetadata:
    page_number: int
    render_width_px: int
    render_height_px: int
    render_pixels: int


@dataclass(frozen=True)
class ValidatedPdfMetadata:
    source_name: str
    sha256: str
    byte_size: int
    page_count: int
    selected_pages: tuple[int, ...]
    render_dpi: float
    pages: tuple[ValidatedPageMetadata, ...]
    total_render_pixels: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "sha256": self.sha256,
            "byte_size": self.byte_size,
            "page_count": self.page_count,
            "selected_pages": list(self.selected_pages),
            "render_dpi": self.render_dpi,
            "pages": [
                {
                    "page_number": page.page_number,
                    "render_width_px": page.render_width_px,
                    "render_height_px": page.render_height_px,
                    "render_pixels": page.render_pixels,
                }
                for page in self.pages
            ],
            "total_render_pixels": self.total_render_pixels,
        }


class InputSafetyError(RuntimeError):
    """Deterministic preflight rejection with v1 EngineError mapping."""

    def __init__(
        self,
        *,
        category: ErrorCategory,
        code: str,
        public_message: str,
        user_actionable: bool,
        retryable: bool = False,
        debug_context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(public_message)
        self.category = category
        self.code = code
        self.public_message = public_message
        self.user_actionable = user_actionable
        self.retryable = retryable
        self.debug_context = dict(debug_context or {})

    def to_engine_error(self) -> EngineError:
        return EngineError(
            category=self.category,
            code=self.code,
            public_message=self.public_message,
            user_actionable=self.user_actionable,
            retryable=self.retryable,
            debug_context=self.debug_context,
        )


def _error(
    category: ErrorCategory,
    code: str,
    public_message: str,
    *,
    actionable: bool = True,
    debug: dict[str, Any] | None = None,
) -> InputSafetyError:
    return InputSafetyError(
        category=category,
        code=code,
        public_message=public_message,
        user_actionable=actionable,
        debug_context=debug,
    )


def _has_control_character(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def validate_output_name(value: str, *, max_utf8_bytes: int = 200) -> str:
    """Require a filename stem, never a caller-controlled path."""

    if not isinstance(value, str) or not value.strip():
        raise _error(
            ErrorCategory.INVALID_REQUEST,
            "output_name_invalid",
            "The requested output name is invalid.",
        )
    if (
        value in {".", ".."}
        or "/" in value
        or "\\" in value
        or _has_control_character(value)
        or len(value.encode("utf-8")) > max_utf8_bytes
    ):
        raise _error(
            ErrorCategory.INVALID_REQUEST,
            "output_name_invalid",
            "The requested output name is invalid.",
            debug={"reason": "unsafe basename syntax"},
        )
    return value


def validate_local_input_reference(reference: str) -> str:
    """Reject URL-like and traversal-style local references before filesystem access."""

    if not isinstance(reference, str) or not reference.strip():
        raise _error(
            ErrorCategory.INVALID_REQUEST,
            "input_reference_invalid",
            "The input PDF reference is invalid.",
        )
    if _has_control_character(reference) or _URI_SCHEME.match(reference):
        raise _error(
            ErrorCategory.INPUT,
            "input_reference_not_allowed",
            "The input PDF reference is not allowed.",
            debug={"reason": "URL-like or control-character reference"},
        )
    if ".." in Path(reference).parts:
        raise _error(
            ErrorCategory.INPUT,
            "input_reference_not_allowed",
            "The input PDF reference is not allowed.",
            debug={"reason": "parent traversal component"},
        )
    return reference


def _reject_symlink_components(candidate: Path, root: Path) -> None:
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise _error(
            ErrorCategory.INPUT,
            "input_reference_not_allowed",
            "The input PDF reference is not allowed.",
            debug={"reason": "path is outside the allowed input root"},
        ) from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise _error(
                ErrorCategory.INPUT,
                "input_reference_not_allowed",
                "The input PDF reference is not allowed.",
                debug={"reason": "path crosses a symlink"},
            )


def resolve_local_input_path(
    reference: str,
    *,
    allowed_root: Path | None,
    policy: JobSafetyPolicy = DEFAULT_JOB_SAFETY_POLICY,
) -> Path:
    """Resolve one local input under a worker-owned root."""

    validate_local_input_reference(reference)
    if allowed_root is None:
        if policy.require_input_root:
            raise ValueError("allowed_root is required by the untrusted-input safety policy")
        return Path(reference).resolve(strict=True)

    root = Path(allowed_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("allowed_root must resolve to a directory")
    raw_path = Path(reference)
    candidate = raw_path if raw_path.is_absolute() else root / raw_path
    if not policy.allow_symlinks:
        _reject_symlink_components(candidate, root)
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise _error(
            ErrorCategory.INPUT,
            "input_pdf_unavailable",
            "The input PDF is unavailable.",
            debug={"exception": type(exc).__name__},
        ) from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise _error(
            ErrorCategory.INPUT,
            "input_reference_not_allowed",
            "The input PDF reference is not allowed.",
            debug={"reason": "resolved path escapes allowed input root"},
        ) from exc
    return resolved


def _read_bounded_file(
    path: Path, *, max_bytes: int, allow_symlinks: bool
) -> tuple[bytearray, int, str]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if not allow_symlinks:
        flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise _error(
            ErrorCategory.INPUT,
            "input_pdf_unavailable",
            "The input PDF is unavailable.",
            debug={"exception": type(exc).__name__},
        ) from exc
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise _error(
                ErrorCategory.INPUT,
                "input_pdf_unavailable",
                "The input PDF is unavailable.",
                debug={"reason": "input is not a regular file"},
            )
        if file_stat.st_size > max_bytes:
            raise _error(
                ErrorCategory.RESOURCE,
                "input_pdf_bytes_limit_exceeded",
                "The input PDF exceeds the per-job size limit.",
                debug={"byte_size": file_stat.st_size, "limit": max_bytes},
            )
        payload = bytearray()
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(fd, min(_MIB, max_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise _error(
                    ErrorCategory.RESOURCE,
                    "input_pdf_bytes_limit_exceeded",
                    "The input PDF exceeds the per-job size limit.",
                    debug={"byte_size": total, "limit": max_bytes},
                )
            digest.update(chunk)
            payload.extend(chunk)
        return payload, total, digest.hexdigest()
    finally:
        os.close(fd)


def _selected_pages(
    requested_pages: Sequence[int] | None,
    *,
    page_count: int,
    policy: JobSafetyPolicy,
) -> tuple[int, ...]:
    if requested_pages is None:
        selected = tuple(range(1, page_count + 1))
    else:
        values: set[int] = set()
        for page in requested_pages:
            if not isinstance(page, int) or isinstance(page, bool) or page < 1:
                raise _error(
                    ErrorCategory.INVALID_REQUEST,
                    "request_pages_invalid",
                    "The requested page selection is invalid.",
                )
            values.add(page)
        if not values:
            raise _error(
                ErrorCategory.INVALID_REQUEST,
                "request_pages_invalid",
                "The requested page selection is invalid.",
            )
        selected = tuple(sorted(values))
    if len(selected) > policy.max_selected_pages:
        raise _error(
            ErrorCategory.RESOURCE,
            "input_pdf_selected_pages_limit_exceeded",
            "The requested PDF pages exceed the per-job page limit.",
            debug={"selected_pages": len(selected), "limit": policy.max_selected_pages},
        )
    if selected[-1] > page_count:
        raise _error(
            ErrorCategory.INVALID_REQUEST,
            "request_page_out_of_range",
            "The requested page selection is outside the input PDF.",
            debug={"requested_page": selected[-1], "page_count": page_count},
        )
    return selected


def validate_local_pdf(
    reference: str,
    *,
    allowed_root: Path | None,
    requested_pages: Sequence[int] | None = None,
    render_dpi: float = 300.0,
    policy: JobSafetyPolicy = DEFAULT_JOB_SAFETY_POLICY,
) -> ValidatedPdfMetadata:
    """Parse metadata and reject unsafe work before page rendering/inference."""

    dpi = float(render_dpi)
    if not math.isfinite(dpi) or dpi <= 0:
        raise ValueError("render_dpi must be finite and > 0")
    path = resolve_local_input_path(reference, allowed_root=allowed_root, policy=policy)
    payload, byte_size, source_sha256 = _read_bounded_file(
        path,
        max_bytes=policy.max_pdf_bytes,
        allow_symlinks=policy.allow_symlinks,
    )
    if byte_size == 0:
        raise _error(
            ErrorCategory.INPUT,
            "input_pdf_invalid",
            "The input PDF could not be read.",
            debug={"reason": "empty input"},
        )

    try:
        import fitz

        with fitz.open(stream=payload, filetype="pdf") as document:
            if document.needs_pass:
                raise _error(
                    ErrorCategory.INPUT,
                    "input_pdf_encrypted",
                    "Password-protected PDFs are not supported.",
                )
            page_count = int(document.page_count)
            if page_count < 1:
                raise _error(
                    ErrorCategory.INPUT,
                    "input_pdf_invalid",
                    "The input PDF could not be read.",
                    debug={"reason": "PDF has no pages"},
                )
            if page_count > policy.max_document_pages:
                raise _error(
                    ErrorCategory.RESOURCE,
                    "input_pdf_page_limit_exceeded",
                    "The input PDF exceeds the per-job page limit.",
                    debug={"page_count": page_count, "limit": policy.max_document_pages},
                )
            selected = _selected_pages(requested_pages, page_count=page_count, policy=policy)
            matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
            pages: list[ValidatedPageMetadata] = []
            total_pixels = 0
            for page_number in selected:
                render_box = (document.load_page(page_number - 1).rect * matrix).irect
                width, height = int(render_box.width), int(render_box.height)
                if width <= 0 or height <= 0:
                    raise _error(
                        ErrorCategory.INPUT,
                        "input_pdf_invalid",
                        "The input PDF contains an invalid page.",
                        debug={"page_number": page_number},
                    )
                if width > policy.max_render_width_px or height > policy.max_render_height_px:
                    raise _error(
                        ErrorCategory.RESOURCE,
                        "input_pdf_render_dimension_limit_exceeded",
                        "A PDF page exceeds the per-job render dimension limit.",
                        debug={
                            "page_number": page_number,
                            "render_width_px": width,
                            "render_height_px": height,
                            "max_render_width_px": policy.max_render_width_px,
                            "max_render_height_px": policy.max_render_height_px,
                        },
                    )
                pixels = width * height
                if pixels > policy.max_render_pixels_per_page:
                    raise _error(
                        ErrorCategory.RESOURCE,
                        "input_pdf_render_pixels_limit_exceeded",
                        "A PDF page exceeds the per-job render pixel limit.",
                        debug={"page_number": page_number, "render_pixels": pixels},
                    )
                total_pixels += pixels
                if total_pixels > policy.max_total_render_pixels:
                    raise _error(
                        ErrorCategory.RESOURCE,
                        "input_pdf_total_render_pixels_limit_exceeded",
                        "The requested PDF pages exceed the per-job render budget.",
                        debug={"total_render_pixels": total_pixels},
                    )
                pages.append(ValidatedPageMetadata(page_number, width, height, pixels))
    except InputSafetyError:
        raise
    except Exception as exc:
        raise _error(
            ErrorCategory.INPUT,
            "input_pdf_invalid",
            "The input PDF could not be read.",
            debug={"exception": type(exc).__name__, "message": str(exc)},
        ) from exc

    return ValidatedPdfMetadata(
        source_name=path.name,
        sha256=source_sha256,
        byte_size=byte_size,
        page_count=page_count,
        selected_pages=selected,
        render_dpi=dpi,
        pages=tuple(pages),
        total_render_pixels=total_pixels,
    )


def enforce_attempt_disk_budget(
    bytes_used: int,
    *,
    policy: JobSafetyPolicy = DEFAULT_JOB_SAFETY_POLICY,
) -> None:
    """Reusable hook for attempt-local temp/intermediate/output usage."""

    if not isinstance(bytes_used, int) or isinstance(bytes_used, bool) or bytes_used < 0:
        raise ValueError("bytes_used must be an integer >= 0")
    if bytes_used > policy.max_attempt_disk_bytes:
        raise _error(
            ErrorCategory.RESOURCE,
            "attempt_disk_budget_exceeded",
            "The job exceeded its temporary storage budget.",
            actionable=False,
            debug={"bytes_used": bytes_used, "limit": policy.max_attempt_disk_bytes},
        )
