"""Shared data models for laser discovery and UI status."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoveredDevice:
    port: str
    model: str
    raw_idn: str
    display_id: str

    @property
    def list_label(self) -> str:
        return f"{self.display_id} — {self.port} ({self.model})"


@dataclass(frozen=True)
class StatusMessage:
    ok: bool
    summary: str
    command: str = ""

    @classmethod
    def success(cls, text: str, *, command: str = "") -> "StatusMessage":
        return cls(ok=True, summary=text, command=command)

    @classmethod
    def failure(cls, text: str, *, command: str = "") -> "StatusMessage":
        return cls(ok=False, summary=text, command=command)
