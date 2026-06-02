"""Per-connection file logger for TLB laser serial traffic."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional, Union

_LEVEL_NAMES = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
}


def parse_log_level(level: Union[int, str]) -> int:
    if isinstance(level, int):
        return level
    key = str(level).strip().lower()
    if key not in _LEVEL_NAMES:
        raise ValueError(f"Unknown log level {level!r}; use DEBUG, INFO, WARNING, or CRITICAL")
    return _LEVEL_NAMES[key]


class LaserSessionLogger:
    """
    Session log for one TLB instrument.

    Default level INFO: connect/disconnect, WARNING (&/! without err codes), CRITICAL (err codes).
    DEBUG adds every READ/SET/WRITE line.
    """

    def __init__(
        self,
        log_path: Path,
        *,
        port: str,
        log_id: str,
        level: Union[int, str] = logging.INFO,
    ) -> None:
        self.log_path = log_path
        self.log_id = log_id
        self.port = port

        self._logger = logging.getLogger(f"newfocus.laser.{log_id}.{id(self)}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        self._logger.addHandler(handler)
        self._handler = handler
        self.set_level(level)

        self._logger.info("SESSION OPEN port=%s id=%s log=%s", port, log_id, log_path)

    def set_level(self, level: Union[int, str]) -> int:
        """Set minimum log level (INFO default; DEBUG logs all commands)."""
        numeric = parse_log_level(level)
        self._logger.setLevel(numeric)
        self._handler.setLevel(numeric)
        return numeric

    def close(self) -> None:
        self._logger.info("SESSION CLOSE port=%s id=%s", self.port, self.log_id)
        self._handler.flush()
        self._handler.close()
        self._logger.removeHandler(self._handler)

    @staticmethod
    def _one_line(text: str) -> str:
        return text.replace("\r", " ").replace("\n", " ").strip()

    def log_read(self, command: str, response: str) -> None:
        self._logger.debug("READ  %-12s -> %s", command, self._one_line(response))

    def log_set(
        self,
        command: str,
        response: str,
        *,
        error_codes: Optional[Iterable[int]] = None,
        error_messages: Optional[Iterable[str]] = None,
    ) -> None:
        line_resp = self._one_line(response)
        codes = [c for c in (error_codes or ()) if c != 0]
        messages = list(error_messages or ())

        self._logger.debug("SET   %-12s -> %s", command, line_resp)

        if response == "*":
            return

        if codes:
            parts = [f"[{c}] {messages[i] if i < len(messages) else c}" for i, c in enumerate(codes)]
            self._logger.critical(
                "SET   %-12s -> %s  %s",
                command,
                line_resp,
                "  ".join(parts),
            )
            return

        if response in ("&", "!"):
            self._logger.warning(
                "SET   %-12s -> %s  (%s, no error code in buffer)",
                command,
                line_resp,
                interpret_protocol_char(response),
            )
            return

        if response == "#":
            self._logger.warning(
                "SET   %-12s -> %s  (illegal argument, no error code in buffer)",
                command,
                line_resp,
            )
            return

        self._logger.warning("SET   %-12s -> %s  (unexpected response)", command, line_resp)

    def log_write(self, command: str, note: str = "") -> None:
        extra = f" ({note})" if note else ""
        self._logger.debug("WRITE %-12s%s", command, extra)


def interpret_protocol_char(response: str) -> str:
    labels = {
        "&": "execution error",
        "!": "unknown command",
        "#": "illegal argument",
    }
    return labels.get(response.strip(), "protocol error")
