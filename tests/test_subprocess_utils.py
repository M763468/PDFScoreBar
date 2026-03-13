import logging

from src.pipeline.core.subprocess_utils import run_with_logging


def test_run_with_logging_captures_output(caplog):
    # Set up caplog to capture DEBUG level and above because run_with_logging defaults to DEBUG
    caplog.set_level(logging.DEBUG)

    # Run a simple bash command that prints to stdout and stderr
    cmd = ["bash", "-c", "echo 'stdout line 1'; sleep 0.1; echo 'stderr line 2' >&2; exit 0"]

    run_with_logging(cmd)

    # Check if lines were captured and logged
    log_messages = [record.message for record in caplog.records]
    assert "|> stdout line 1" in log_messages
    assert "|> stderr line 2" in log_messages
