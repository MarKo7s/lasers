"""Map TLB-8800 command results to shared StatusMessage."""

from __future__ import annotations

from core.models import StatusMessage


def status_from_command_result(result) -> StatusMessage:
    from newfocus.tlb8800_utilities.errors import CommandResult

    if not isinstance(result, CommandResult):
        return StatusMessage.success(str(result))
    if result.ok:
        text = result.message or "OK"
        return StatusMessage.success(text, command=result.command)
    parts = [result.message or "Command failed"]
    if result.error_messages:
        parts.extend(result.error_messages)
    return StatusMessage.failure(" — ".join(parts), command=result.command)
