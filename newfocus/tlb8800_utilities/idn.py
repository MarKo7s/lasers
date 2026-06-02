"""Parse New Focus Legacy *IDN? / id? responses."""

from __future__ import annotations

import re
from typing import Optional

NEWFOCUS_MANUFACTURER = "New Focus"

_IDN_PATTERN = re.compile(
    r"^(?P<manufacturer>[^;]+);\s*"
    r"(?P<model>[^;]+);\s*"
    r"(?P<customer_serial>[^;]+);\s*"
    r"(?P<nf_serial>[^;]+);\s*"
    r"(?P<firmware>[^;]+);\s*"
    r"(?P<fpga>[^;]+)\s*$",
    re.IGNORECASE,
)


def parse_idn(raw_idn: str) -> Optional[dict[str, str]]:
    """Parse a Legacy identity response. Returns None if not a valid New Focus IDN."""
    text = raw_idn.strip()
    match = _IDN_PATTERN.match(text)
    if not match:
        return None
    manufacturer = match.group("manufacturer").strip()
    if manufacturer.lower() != NEWFOCUS_MANUFACTURER.lower():
        return None
    return {
        "manufacturer": manufacturer,
        "model": match.group("model").strip(),
        "customer_serial": match.group("customer_serial").strip(),
        "nf_serial": match.group("nf_serial").strip(),
        "firmware_version": match.group("firmware").strip(),
        "fpga_version": match.group("fpga").strip(),
        "raw_idn": text,
    }
