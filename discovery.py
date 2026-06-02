"""Discover supported New Focus lasers on USB serial ports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import serial
from serial.tools import list_ports

from newfocus.tlb8800_utilities.protocol import DEFAULT_BAUDRATE, DEFAULT_TIMEOUT, SerialTransport

_DEFAULT_CONFIG = Path(__file__).resolve().parent / "supported_models.json"


@dataclass(frozen=True)
class SupportedModel:
    model: str
    idn_query: str
    match: str


def _load_config(config_path: Path) -> tuple[int, tuple[SupportedModel, ...]]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    baudrate = int(data.get("baudrate", DEFAULT_BAUDRATE))
    models: list[SupportedModel] = []
    for entry in data.get("models", []):
        models.append(
            SupportedModel(
                model=str(entry["model"]),
                idn_query=str(entry["idn_query"]),
                match=str(entry["match"]),
            )
        )
    if not models:
        raise ValueError(f"No models defined in {config_path}")
    return baudrate, tuple(models)


class LaserDiscovery:
    """
    Scan COM ports for lasers listed in ``supported_models.json`` (Laser project root).

    Returns ``{com_port: idn_response}`` for each supported device found.
    """

    def __init__(
        self,
        config_path: Optional[Path | str] = None,
        *,
        baudrate: Optional[int] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        path = Path(config_path) if config_path is not None else _DEFAULT_CONFIG
        self._config_path = path
        file_baudrate, self._models = _load_config(path)
        self.baudrate = file_baudrate if baudrate is None else baudrate
        self.timeout = timeout

    @property
    def supported_models(self) -> tuple[SupportedModel, ...]:
        return self._models

    @property
    def config_path(self) -> Path:
        return self._config_path

    @staticmethod
    def list_usb_ports() -> list[str]:
        """COM ports on USB adapters. If none are tagged USB, returns all COM ports."""
        usb_ports: list[str] = []
        all_ports: list[str] = []
        for info in list_ports.comports():
            all_ports.append(info.device)
            text = f"{info.hwid or ''} {info.description or ''}".upper()
            if "USB" in text:
                usb_ports.append(info.device)
        return usb_ports if usb_ports else all_ports

    def _query_idn(self, port: str, query: str) -> Optional[str]:
        try:
            with SerialTransport(
                port,
                baudrate=self.baudrate,
                timeout=self.timeout,
            ) as transport:
                transport.flush()
                return transport.query(query, timeout=self.timeout).strip()
        except (serial.SerialException, TimeoutError, OSError):
            return None

    def _match_model(self, idn: str, query: str) -> Optional[SupportedModel]:
        for model in self._models:
            if model.idn_query == query and model.match in idn:
                return model
        return None

    def probe_port(self, port: str) -> Optional[tuple[str, SupportedModel]]:
        """Return ``(idn, model)`` if the port has a supported laser, else None."""
        queries = {m.idn_query for m in self._models}
        for query in queries:
            idn = self._query_idn(port, query)
            if idn is None:
                continue
            matched = self._match_model(idn, query)
            if matched is not None:
                return idn, matched
        return None

    def discover(self, ports: Optional[Sequence[str]] = None) -> dict[str, str]:
        """Scan ports and return ``{com_port: idn_string}`` for supported models."""
        candidates = list(ports) if ports is not None else self.list_usb_ports()
        found: dict[str, str] = {}
        for port in candidates:
            result = self.probe_port(port)
            if result is None:
                continue
            idn, _model = result
            found[port] = idn
        return found


def list_usb_ports() -> list[str]:
    return LaserDiscovery.list_usb_ports()


def discover(
    *,
    baudrate: Optional[int] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, str]:
    return LaserDiscovery(baudrate=baudrate, timeout=timeout).discover()
