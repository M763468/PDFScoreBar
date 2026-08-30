from pathlib import Path

from tools.issue284.compare_full68_variants import resolve_retained_path as compare_resolve
from tools.issue284.render_full68_numbering_review import resolve_retained_path as render_resolve


def _assert_relocated_resolver(resolve, tmp_path: Path) -> None:
    variant = tmp_path / "issue284_compile_full68_01_eager"
    artifact = variant / "Score" / "hybrid_output" / "page_001_hybrid.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("[]\n", encoding="utf-8")

    recorded = Path(
        "/workspace/logs/issue284/issue284_compile_full68_01_eager/"
        "Score/hybrid_output/page_001_hybrid.json"
    )

    assert resolve(recorded, variant_root=variant) == artifact.resolve()


def test_comparator_resolves_relocated_variant_artifact(tmp_path: Path) -> None:
    _assert_relocated_resolver(compare_resolve, tmp_path)


def test_numbering_review_resolves_relocated_variant_artifact(tmp_path: Path) -> None:
    _assert_relocated_resolver(render_resolve, tmp_path)
