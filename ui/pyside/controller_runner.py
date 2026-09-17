"""Background job runner for PySide6.

Runs Python callables on a single background thread and reports:
- the action name
- a `StatusMessage` indicating success/failure
- an optional payload (e.g., telemetry snapshot, discovery results)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt

from laser.core.models import StatusMessage


@dataclass(frozen=True)
class Job:
    action: str
    fn: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


class ControllerRunner(QObject):
    """Executes jobs serially on a dedicated QThread."""

    request_run = Signal(object)  # Job
    finished = Signal(str, object, object)  # action, StatusMessage, payload

    def __init__(self) -> None:
        super().__init__()
        self._thread = QThread()
        self.moveToThread(self._thread)
        self.request_run.connect(self.run_job, Qt.ConnectionType.QueuedConnection)  # type: ignore[name-defined]
        self._thread.start()

    def shutdown(self) -> None:
        """Stop the background thread."""
        try:
            self._thread.quit()
            self._thread.wait(2000)
        except Exception:
            # Best-effort shutdown; Qt may already be tearing down.
            pass

    @Slot(object)
    def run_job(self, job: Job) -> None:
        """Run a job and emit the result back to the UI thread."""
        try:
            result = job.fn(*job.args, **job.kwargs)
            if isinstance(result, StatusMessage):
                status = result
                payload = None
            else:
                status = StatusMessage.success("OK")
                payload = result
            self.finished.emit(job.action, status, payload)
        except Exception as exc:  # pragma: no cover (runtime only)
            status = StatusMessage.failure(str(exc))
            self.finished.emit(job.action, status, None)

