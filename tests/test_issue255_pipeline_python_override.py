from src.pipeline.core import python_env


def test_explicit_pipeline_python_wins_over_running_container(monkeypatch) -> None:
    monkeypatch.setenv("PIPELINE_PYTHON", "/custom/python")
    monkeypatch.setattr(
        python_env,
        "get_docker_exec_prefix",
        lambda: ["docker", "exec", "pdfscore_pipeline_gpu"],
    )
    monkeypatch.setattr(python_env, "is_in_container", lambda: False)

    assert python_env.get_pipeline_python("omr_dln") == ["/custom/python"]
