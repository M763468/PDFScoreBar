from tools.issue255.run_public_baseline_sr_x4_replay_safe import _with_safe_directory


def test_safe_directory_is_added_only_to_container_head_check() -> None:
    command = (
        "docker",
        "exec",
        "-w",
        "/workspace",
        "pdfscore_pipeline_gpu",
        "git",
        "rev-parse",
        "HEAD",
    )

    assert _with_safe_directory(command) == (
        "docker",
        "exec",
        "-w",
        "/workspace",
        "-e",
        "GIT_CONFIG_COUNT=1",
        "-e",
        "GIT_CONFIG_KEY_0=safe.directory",
        "-e",
        "GIT_CONFIG_VALUE_0=/workspace",
        "pdfscore_pipeline_gpu",
        "git",
        "rev-parse",
        "HEAD",
    )


def test_safe_directory_is_not_added_to_other_commands() -> None:
    command = ("docker", "ps", "--format", "{{.Names}}")

    assert _with_safe_directory(command) == command
