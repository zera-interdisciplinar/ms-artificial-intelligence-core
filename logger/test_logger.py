import pytest

from logger.logger import logger

FIXED_TIMESTAMP = "2026-08-09 12:00:00"


@pytest.fixture(autouse=True)
def freeze_timestamp(monkeypatch):
    monkeypatch.setattr(logger, "_timestamp", staticmethod(lambda: FIXED_TIMESTAMP))


def test_info_prints_message_in_blue(capsys):
    logger().Info("booting up")

    out = capsys.readouterr().out
    assert out == f"{logger.BLUE}[{FIXED_TIMESTAMP}] [INFO] booting up{logger.RESET}\n"


def test_error_prints_message_and_error_in_red(capsys):
    logger().Error("failed to connect: ", ValueError("timeout"))

    out = capsys.readouterr().out
    assert out == f"{logger.RED}[{FIXED_TIMESTAMP}] [ERROR] failed to connect: timeout{logger.RESET}\n"


def test_debug_prints_message_in_cyan(capsys):
    logger().Debug("state dump")

    out = capsys.readouterr().out
    assert out == f"{logger.CYAN}[{FIXED_TIMESTAMP}] [DEBUG] state dump{logger.RESET}\n"


def test_warning_prints_message_in_yellow(capsys):
    logger().Warning("retrying")

    out = capsys.readouterr().out
    assert out == f"{logger.YELLOW}[{FIXED_TIMESTAMP}] [WARNING] retrying{logger.RESET}\n"


def test_color_codes_are_distinct():
    codes = [logger.BLUE, logger.RED, logger.CYAN, logger.YELLOW, logger.RESET]
    assert len(set(codes)) == len(codes)


def test_instances_do_not_carry_state():
    """Methods only print, so two instances must behave identically."""
    assert logger().Info("a") is None
    assert logger().Info("a") is None
