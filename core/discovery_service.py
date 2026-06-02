"""Enriched laser discovery for UI layers."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from discovery import LaserDiscovery

from core.idn_registry import display_id_from_idn
from core.models import DiscoveredDevice


class DiscoveryService:
    """Scan COM ports for models listed in supported_models.json."""

    def __init__(
        self,
        config_path: Optional[Path | str] = None,
        *,
        baudrate: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> None:
        kwargs: dict = {}
        if config_path is not None:
            kwargs["config_path"] = config_path
        if baudrate is not None:
            kwargs["baudrate"] = baudrate
        if timeout is not None:
            kwargs["timeout"] = timeout
        self._discovery = LaserDiscovery(**kwargs)

    def scan(self, ports: Optional[Sequence[str]] = None) -> list[DiscoveredDevice]:
        candidates = list(ports) if ports is not None else self._discovery.list_usb_ports()
        devices: list[DiscoveredDevice] = []
        for port in candidates:
            result = self._discovery.probe_port(port)
            if result is None:
                continue
            raw_idn, model = result
            devices.append(
                DiscoveredDevice(
                    port=port,
                    model=model.model,
                    raw_idn=raw_idn,
                    display_id=display_id_from_idn(model.model, raw_idn),
                )
            )
        return devices

    @property
    def baudrate(self) -> int:
        return self._discovery.baudrate
