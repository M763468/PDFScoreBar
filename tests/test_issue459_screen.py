import pytest

from tools.issue459.screen import verdict


def test_primary_gate_uses_median_and_retains_regression():
    result = verdict([100, 102], [99, 101])
    assert result['primary_gate'] == 'failed'
    assert result['candidate_range'] == [99, 101]
    assert result['adoption'] == 'not_authorized_by_screen'


def test_primary_gate_pass_is_not_adoption():
    result = verdict([100, 100], [96, 96])
    assert result['primary_gate'] == 'passed'
    assert result['adoption'] == 'not_authorized_by_screen'


@pytest.mark.parametrize('baseline,candidate', [([100], [90, 90]),
    ([100, 100], [0, 90]), ([100, 100], [float('nan'), 90]),
    ([100, 100], [float('inf'), 90])])
def test_incomplete_or_invalid_measurements_are_rejected(baseline, candidate):
    with pytest.raises(ValueError):
        verdict(baseline, candidate)


def test_launcher_binds_explicit_uid_and_issue_root(tmp_path, monkeypatch):
    import json
    import sys
    from tools.issue447 import run_experiment as launcher

    script = tmp_path / 'tools/issue447/run_experiment.py'
    script.parent.mkdir(parents=True)
    script.write_text('')
    (tmp_path / 'configs').mkdir()
    (tmp_path / 'configs/dense_full_pipeline.yaml').write_text(
        'inputs: {}\ndetection: {}\n')
    (tmp_path / 'models/omr_dln').mkdir(parents=True)
    (tmp_path / 'models/omr_dln/manifest.json').write_text(json.dumps({
        'runtime_path': '/opt/model.pt', 'cache_path': 'model.pt'}))
    monkeypatch.setattr(launcher, '__file__', str(script))
    monkeypatch.setattr(sys, 'argv', ['run_experiment.py', '--issue-id', '459',
        '--uid', '0', '--gid', '0', '--label', 'root-test',
        '--image', 'sha256:' + 'a' * 64])
    calls = []
    monkeypatch.setattr(launcher.subprocess, 'run', lambda command, **kw: calls.append(command))

    def output(command, **kwargs):
        if command[0] == 'nvidia-smi':
            return 'pid,process_name,used_memory\n'
        if '--git-common-dir' in command:
            return str(tmp_path / '.git')
        return ''

    monkeypatch.setattr(launcher.subprocess, 'check_output', output)

    class StopBeforeLaunch(Exception):
        pass

    def stop(*args, **kwargs):
        raise StopBeforeLaunch

    monkeypatch.setattr(launcher.subprocess, 'Popen', stop)
    with pytest.raises(StopBeforeLaunch):
        launcher.main()
    provenance = json.loads((tmp_path /
        'logs/issue459/runs/root-test/provenance.json').read_text())
    command = provenance['command']
    assert command[command.index('--user') + 1] == '0:0'
    assert command[command.index('--name') + 1] == 'pdfscore-issue459-root-test'
    assert provenance['experiment']['issue_id'] == 459
    assert calls[0][-3:] == ['--image-ref', 'sha256:' + 'a' * 64, '--explicit']
