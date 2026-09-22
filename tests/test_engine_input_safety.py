from __future__ import annotations

import hashlib
from pathlib import Path

import fitz
import pytest

from src.pipeline.engine_contract import ContractValidationError, JobRequest
from src.pipeline.engine_input_safety import (
    DEFAULT_JOB_SAFETY_POLICY,
    InputSafetyError,
    JobSafetyPolicy,
    enforce_attempt_disk_budget,
    validate_local_input_reference,
    validate_local_pdf,
    validate_output_name,
)


def _write_pdf(
    path: Path,
    *,
    page_count: int = 1,
    width: float = 612,
    height: float = 792,
) -> None:
    document = fitz.open()
    for _ in range(page_count):
        document.new_page(width=width, height=height)
    document.save(path)
    document.close()


def test_default_policy_has_concrete_bounded_job_limits():
    policy = DEFAULT_JOB_SAFETY_POLICY

    assert policy.max_pdf_bytes == 256 * 1024 * 1024
    assert policy.max_document_pages == 500
    assert policy.max_selected_pages == 200
    assert policy.max_render_width_px == 12_000
    assert policy.max_render_height_px == 12_000
    assert policy.max_render_pixels_per_page == 64_000_000
    assert policy.max_total_render_pixels == 1_000_000_000
    assert policy.max_attempt_disk_bytes == 16 * 1024 * 1024 * 1024
    assert policy.allow_symlinks is False
    assert policy.require_input_root is True


def test_valid_pdf_preflight_returns_safe_metadata_without_internal_path(tmp_path: Path):
    pdf_path = tmp_path / "score.pdf"
    _write_pdf(pdf_path, page_count=2)

    metadata = validate_local_pdf(
        "score.pdf",
        allowed_root=tmp_path,
        requested_pages=[2, 1, 2],
        render_dpi=300,
    )
    payload = metadata.to_dict()

    assert payload["source_name"] == "score.pdf"
    assert payload["sha256"] == hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    assert payload["byte_size"] == pdf_path.stat().st_size
    assert payload["page_count"] == 2
    assert payload["selected_pages"] == [1, 2]
    assert payload["pages"][0]["render_width_px"] == 2550
    assert payload["pages"][0]["render_height_px"] == 3300
    assert payload["total_render_pixels"] == 2 * 2550 * 3300
    assert str(tmp_path) not in str(payload)


@pytest.mark.parametrize(
    ("reference", "code"),
    [
        ("../outside.pdf", "input_reference_not_allowed"),
        ("https://example.com/score.pdf", "input_reference_not_allowed"),
        ("file:/tmp/score.pdf", "input_reference_not_allowed"),
    ],
)
def test_local_input_reference_rejects_traversal_and_urls(reference: str, code: str):
    with pytest.raises(InputSafetyError) as exc_info:
        validate_local_input_reference(reference)

    assert exc_info.value.code == code


def test_symlink_input_is_rejected_by_default(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.pdf"
    _write_pdf(outside)
    symlink = tmp_path / "score.pdf"
    try:
        symlink.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable in this environment")

    with pytest.raises(InputSafetyError) as exc_info:
        validate_local_pdf("score.pdf", allowed_root=tmp_path)

    assert exc_info.value.code == "input_reference_not_allowed"


def test_pdf_byte_limit_is_enforced_before_parser_work(tmp_path: Path):
    pdf_path = tmp_path / "score.pdf"
    _write_pdf(pdf_path)

    with pytest.raises(InputSafetyError) as exc_info:
        validate_local_pdf(
            "score.pdf",
            allowed_root=tmp_path,
            policy=JobSafetyPolicy(max_pdf_bytes=100),
        )

    assert exc_info.value.code == "input_pdf_bytes_limit_exceeded"
    assert exc_info.value.category.value == "resource"


def test_malformed_and_password_protected_pdfs_are_deterministic_input_errors(tmp_path: Path):
    malformed = tmp_path / "malformed.pdf"
    malformed.write_bytes(b"not a PDF")

    with pytest.raises(InputSafetyError) as invalid_info:
        validate_local_pdf("malformed.pdf", allowed_root=tmp_path)

    assert invalid_info.value.code == "input_pdf_invalid"
    public_payload = invalid_info.value.to_engine_error().to_dict()
    assert public_payload["public_message"] == "The input PDF could not be read."
    assert "debug_context" not in public_payload

    encrypted = tmp_path / "encrypted.pdf"
    document = fitz.open()
    document.new_page()
    document.save(
        encrypted,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="secret",
    )
    document.close()

    with pytest.raises(InputSafetyError) as encrypted_info:
        validate_local_pdf("encrypted.pdf", allowed_root=tmp_path)

    assert encrypted_info.value.code == "input_pdf_encrypted"
    assert encrypted_info.value.retryable is False


def test_page_and_render_amplification_are_rejected_before_rendering(tmp_path: Path):
    pdf_path = tmp_path / "score.pdf"
    _write_pdf(pdf_path, page_count=2)

    with pytest.raises(InputSafetyError) as page_info:
        validate_local_pdf(
            "score.pdf",
            allowed_root=tmp_path,
            policy=JobSafetyPolicy(max_document_pages=1),
        )
    assert page_info.value.code == "input_pdf_page_limit_exceeded"

    with pytest.raises(InputSafetyError) as selected_info:
        validate_local_pdf(
            "score.pdf",
            allowed_root=tmp_path,
            requested_pages=[1, 2],
            policy=JobSafetyPolicy(max_selected_pages=1),
        )
    assert selected_info.value.code == "input_pdf_selected_pages_limit_exceeded"

    with pytest.raises(InputSafetyError) as pixel_info:
        validate_local_pdf(
            "score.pdf",
            allowed_root=tmp_path,
            requested_pages=[1],
            render_dpi=300,
            policy=JobSafetyPolicy(max_render_pixels_per_page=1_000_000),
        )
    assert pixel_info.value.code == "input_pdf_render_pixels_limit_exceeded"

    with pytest.raises(InputSafetyError) as total_info:
        validate_local_pdf(
            "score.pdf",
            allowed_root=tmp_path,
            render_dpi=300,
            policy=JobSafetyPolicy(max_total_render_pixels=10_000_000),
        )
    assert total_info.value.code == "input_pdf_total_render_pixels_limit_exceeded"


def test_out_of_range_page_and_disk_budget_have_stable_codes(tmp_path: Path):
    pdf_path = tmp_path / "score.pdf"
    _write_pdf(pdf_path)

    with pytest.raises(InputSafetyError) as page_info:
        validate_local_pdf(
            "score.pdf",
            allowed_root=tmp_path,
            requested_pages=[2],
        )
    assert page_info.value.code == "request_page_out_of_range"

    with pytest.raises(InputSafetyError) as disk_info:
        enforce_attempt_disk_budget(
            101,
            policy=JobSafetyPolicy(max_attempt_disk_bytes=100),
        )
    assert disk_info.value.code == "attempt_disk_budget_exceeded"
    assert disk_info.value.user_actionable is False


@pytest.mark.parametrize("output_name", ["../escape", "nested/name", r"nested\name", ".", ".."])
def test_output_name_is_a_stem_not_a_path(output_name: str):
    with pytest.raises(InputSafetyError) as safety_info:
        validate_output_name(output_name)
    assert safety_info.value.code == "output_name_invalid"

    with pytest.raises(ContractValidationError, match="output_name"):
        JobRequest(
            input={"kind": "local_path", "reference": "score.pdf"},
            config_overrides={"output_name": output_name},
        )
