"""Serial transport and Legacy protocol helpers for TLB-8800 (manual §5.3)."""

from __future__ import annotations

import time
from typing import Optional, Union

import serial

from newfocus.tlb8800_utilities.errors import TLB8800ProtocolError

# Manual §5.1.1: 115200 baud, no parity, 8 data bits, 1 stop bit.
DEFAULT_BAUDRATE = 115_200
DEFAULT_TIMEOUT = 2.0
COMMAND_TERMINATOR = "\n"
RESPONSE_TERMINATOR = "\n\r"
ACK = "*"


class SerialTransport:
    """Low-level serial I/O for Legacy command protocol."""

    def __init__(
        self,
        port: str,
        *,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
        write_timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.port = port
        self._serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
            write_timeout=write_timeout,
        )

    @property
    def is_open(self) -> bool:
        return self._serial.is_open

    def close(self) -> None:
        if self._serial.is_open:
            self._serial.close()

    def __enter__(self) -> "SerialTransport":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def flush(self) -> None:
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()

    def write_command(self, command: str) -> None:
        payload = command.rstrip("\r\n") + COMMAND_TERMINATOR
        self._serial.write(payload.encode("ascii"))
        self._serial.flush()

    def read_response(self, timeout: Optional[float] = None) -> str:
        deadline = time.monotonic() + (timeout if timeout is not None else self._serial.timeout)
        chunks: list[str] = []
        while time.monotonic() < deadline:
            raw = self._serial.read(1)
            if not raw:
                continue
            chunks.append(raw.decode("ascii", errors="replace"))
            if "".join(chunks).endswith(RESPONSE_TERMINATOR):
                break
        response = "".join(chunks)
        if response.endswith(RESPONSE_TERMINATOR):
            return response[: -len(RESPONSE_TERMINATOR)]
        if not response:
            raise TimeoutError(f"No response from device on {self.port!r}")
        return response

    def query(self, command: str, *, timeout: Optional[float] = None) -> str:
        self.write_command(command)
        return self.read_response(timeout=timeout)


def parse_numeric_response(response: str) -> Union[int, float]:
    text = response.strip()
    if not text:
        raise ValueError("empty numeric response")
    if "." in text:
        return float(text)
    return int(text)


def ensure_command_ack(response: str, command: str = "") -> None:
    if response == ACK:
        return
    if response in (
        TLB8800ProtocolError.RESPONSE_CMD_ERR,
        TLB8800ProtocolError.RESPONSE_ARG_ERR,
        TLB8800ProtocolError.RESPONSE_EXE_ERR,
    ):
        raise TLB8800ProtocolError(response, command)
    raise TLB8800ProtocolError(response, command)
