from types import SimpleNamespace

from src.pipeline.core import python_env


def test_get_docker_exec_prefix_uses_canonical_container(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="pdfscore_pipeline_gpu\n")

    monkeypatch.setattr(python_env, "is_in_container", lambda: False)
    monkeypatch.setattr(python_env.subprocess, "run", fake_run)

    assert python_env.get_docker_exec_prefix() == [
        "docker",
        "exec",
        "-w",
        "/workspace",
        "-e",
        "PYTHONPATH=/workspace",
        "pdfscore_pipeline_gpu",
    ]
    assert len(calls) == 1
    assert "name=pdfscore_pipeline_gpu" in calls[0]


def test_get_docker_exec_prefix_does_not_probe_another_container(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(python_env, "is_in_container", lambda: False)
    monkeypatch.setattr(python_env.subprocess, "run", fake_run)

    assert python_env.get_docker_exec_prefix() == []
    assert len(calls) == 1
    assert "name=pdfscore_pipeline_gpu" in calls[0]


def test_get_pipeline_python_uses_pipeline_venv_in_container(monkeypatch):
    monkeypatch.setattr(python_env, "is_in_container", lambda: True)
    monkeypatch.setattr(
        python_env.Path,
        "exists",
        lambda path: str(path) == "/opt/venv_pipeline/bin/python",
    )
    monkeypatch.setenv("PIPELINE_PYTHON", "/custom/python")

    assert python_env.get_pipeline_python("homr") == ["/opt/venv_pipeline/bin/python"]


def test_get_pipeline_python_uses_explicit_override_without_managed_environment(monkeypatch):
    monkeypatch.setattr(python_env, "is_in_container", lambda: False)
    monkeypatch.setattr(python_env, "get_docker_exec_prefix", lambda: [])
    monkeypatch.setenv("PIPELINE_PYTHON", "/custom/python")

    assert python_env.get_pipeline_python("sr") == ["/custom/python"]
