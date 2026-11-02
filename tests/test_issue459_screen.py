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


def test_screen_runs_root_abba_with_independent_seed_copies(tmp_path, monkeypatch):
    import json
    import sys
    from tools.issue459 import screen
    from tools.issue447 import analyze, deepening_analyze

    seed = tmp_path / 'seed'
    seed.mkdir()
    (seed / 'kernel').write_bytes(b'seed')
    monkeypatch.setattr(screen, '__file__', str(tmp_path / 'tools/issue459/screen.py'))
    monkeypatch.setattr(sys, 'argv', ['screen', '--image', 'sha256:' + 'a' * 64,
        '--seed', str(seed), '--label', 'test'])
    monkeypatch.setattr(analyze, 'proc_summary', lambda p: {})
    monkeypatch.setattr(analyze, 'gpu_summary', lambda p: {})
    monkeypatch.setattr(deepening_analyze, 'pipeline_checks', lambda *a: {'all_equal': True})
    calls = []

    def execute(command, **kwargs):
        calls.append(command)
        assert command[command.index('--uid') + 1] == '0'
        assert command[command.index('--gid') + 1] == '0'
        assert command[command.index('--home') + 1] == '/root'
        cache = Path(command[command.index('--compile-cache') + 1])
        assert (cache / 'kernel').read_bytes() == b'seed'
        (cache / 'kernel').write_bytes(b'mutated by this run')
        label = command[command.index('--label') + 1]
        output = tmp_path / 'logs/issue459/runs' / label
        output.mkdir(parents=True)
        (output / 'result.json').write_text(json.dumps({'status': 'completed',
            'trace': 'off', 'timed_out': False,
            'docker_e2e_wall_seconds': 90 if '--omr-reuse' in command else 100}))

    from pathlib import Path
    monkeypatch.setattr(screen.subprocess, 'run', execute)
    screen.main()
    assert ['--omr-reuse' in c for c in calls] == [False, True, True, False]
    assert (seed / 'kernel').read_bytes() == b'seed'
    summary = json.loads((tmp_path / 'logs/issue459/screens/test/summary.json').read_text())
    assert summary['primary_gate'] == 'passed'
    assert summary['adoption'] == 'not_authorized_by_screen'
