"""The stderr spinner: silent off a terminal, frames on one, cleared before every log line."""

import io
import logging
import time

from manc import progress


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_silent_when_stderr_is_not_a_terminal() -> None:
    stream = io.StringIO()
    with progress.spinner("tagging", stream=stream, interval=10) as spinner:
        spinner.tick()
    assert stream.getvalue() == ""


def test_draws_frames_and_clears_the_line_on_a_terminal() -> None:
    stream = Terminal()
    with progress.spinner("tagging", stream=stream, interval=10) as spinner:
        spinner.tick()
        spinner.tick()
    written = stream.getvalue()
    assert f"\r{progress.FRAMES[0]} tagging" in written
    assert f"\r{progress.FRAMES[1]} tagging" in written
    assert written.endswith(progress.CLEAR)


def test_log_records_clear_the_spinner_line_first() -> None:
    stream = Terminal()
    handler = progress.Handler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("manc.test_progress")
    logger.addHandler(handler)
    logger.propagate = False
    try:
        with progress.spinner("tagging", stream=stream, interval=10) as spinner:
            spinner.tick()
            logger.warning("feed x skipped")
            spinner.tick()
    finally:
        logger.removeHandler(handler)
    written = stream.getvalue()
    assert f"{progress.FRAMES[0]} tagging{progress.CLEAR}feed x skipped\n" in written
    assert written.endswith(progress.CLEAR)


def test_handler_without_a_spinner_just_logs() -> None:
    stream = Terminal()
    handler = progress.Handler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.emit(logging.makeLogRecord({"msg": "plain", "levelno": logging.INFO}))
    assert stream.getvalue() == "plain\n"


def test_spins_on_its_own_while_the_block_runs() -> None:
    stream = Terminal()
    with progress.spinner("tagging", stream=stream, interval=0.001):
        time.sleep(0.05)
    assert stream.getvalue().count("\r") > 2
