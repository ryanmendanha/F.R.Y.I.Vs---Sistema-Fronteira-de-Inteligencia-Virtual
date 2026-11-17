"""Cooperative cancellation shared with tool execution threads."""
from contextvars import ContextVar
from dataclasses import dataclass, field
import threading
import uuid


class CommandCancelled(Exception):
    pass


@dataclass
class Command:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    cancelled: threading.Event = field(default_factory=threading.Event)


current_command: ContextVar[Command | None] = ContextVar('command', default=None)


def check_cancelled() -> None:
    command = current_command.get()
    if command is not None and command.cancelled.is_set():
        raise CommandCancelled('Comando cancelado.')
