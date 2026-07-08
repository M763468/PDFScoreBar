from pathlib import Path

from src.pipeline.utils.images import collect_images


def _write_text(path: Path, text: str = "image") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _config(*, review_enabled: bool, output_dir: Path) -> dict:
    return {
        "inputs": {
            "pdf_to_images": {
                "output_dir": str(output_dir),
                "image_glob": "page_*.png",
            }
        },
        "outputs": {
            "review": {
                "manual_correction_package": review_enabled,
            }
        },
    }


def test_collect_images_stages_external_source_images_for_review_package(tmp_path):
    run_dir = tmp_path / "source_run"
    external_dir = tmp_path / "external_images"
    external_image = external_dir / "page_001.png"
    _write_text(external_image, "external-image")

    images = collect_images(
        _config(review_enabled=True, output_dir=external_dir),
        run_dir,
    )

    expected = run_dir / "inputs" / "images" / "page_001.png"
    assert images == [expected]
    assert expected.read_text(encoding="utf-8") == "external-image"


def test_collect_images_keeps_external_source_images_without_review_package(tmp_path):
    run_dir = tmp_path / "source_run"
    external_dir = tmp_path / "external_images"
    external_image = external_dir / "page_001.png"
    _write_text(external_image, "external-image")

    images = collect_images(
        _config(review_enabled=False, output_dir=external_dir),
        run_dir,
    )

    assert images == [external_image]
    assert not (run_dir / "inputs" / "images" / "page_001.png").exists()


def test_collect_images_keeps_run_dir_source_images_for_review_package(tmp_path):
    run_dir = tmp_path / "source_run"
    internal_dir = run_dir / "inputs" / "images"
    internal_image = internal_dir / "page_001.png"
    _write_text(internal_image, "internal-image")

    images = collect_images(
        _config(review_enabled=True, output_dir=internal_dir),
        run_dir,
    )

    assert images == [internal_image]
    assert internal_image.read_text(encoding="utf-8") == "internal-image"
