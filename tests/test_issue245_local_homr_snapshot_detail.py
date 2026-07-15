from tools.issue245.collect_local_homr_snapshot_detail import (
    parse_unreachable_commits,
    reference_lines,
)


def test_parse_unreachable_commits_filters_non_commit_objects() -> None:
    output = """
unreachable blob 1111111111111111111111111111111111111111
unreachable commit 2222222222222222222222222222222222222222
dangling commit 3333333333333333333333333333333333333333
"""

    assert parse_unreachable_commits(output) == [
        "2222222222222222222222222222222222222222",
        "3333333333333333333333333333333333333333",
    ]


def test_reference_lines_keeps_model_and_version_context() -> None:
    content = """
plain = 1
segnet_path = "segnet_155.onnx"
package_version = "0.6.0"
download_url = "https://example.invalid/model.zip"
"""

    assert reference_lines(content) == [
        'segnet_path = "segnet_155.onnx"',
        'package_version = "0.6.0"',
        'download_url = "https://example.invalid/model.zip"',
    ]
