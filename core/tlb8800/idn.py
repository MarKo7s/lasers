"""TLB-8800 *IDN? parsing for discovery display labels."""

from __future__ import annotations

from newfocus.tlb8800_utilities.idn import parse_idn


def display_id_from_idn(raw_idn: str) -> str:
    parsed = parse_idn(raw_idn)
    if parsed is not None:
        serial = parsed.get("customer_serial") or parsed.get("nf_serial")
        if serial:
            return serial
        return parsed.get("model", raw_idn[:40])
    text = raw_idn.strip()
    if len(text) > 48:
        return text[:45] + "..."
    return text or "Unknown"
