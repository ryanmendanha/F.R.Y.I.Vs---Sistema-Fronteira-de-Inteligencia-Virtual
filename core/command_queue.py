"""Bounded serial execution; a cancelled caller never releases a running tool."""
import asyncio
from weakref import WeakKeyDictionary

from core.command_control import Command, CommandCancelled, current_command


class CommandQueue:
    def __init__(self, capacity=8):
        self.capacity = capacity
        self.commands = {}
        self.lock = asyncio.Lock()
        self.active_id = None
        self.closed = False

    async def run(self, operation, command=None):
        if self.closed:
            raise RuntimeError('Executor encerrando.')
        if len(self.commands) >= self.capacity:
            raise RuntimeError('Fila de comandos cheia. Tente novamente em instantes.')
        command = command or Command()
        self.commands[command.id] = command
        try:
            async with self.lock:
                if command.cancelled.is_set():
                    raise CommandCancelled('Comando cancelado antes de executar.')
                token = current_command.set(command)
                self.active_id = command.id
                try:
                    task = asyncio.create_task(operation())
                    try:
                        return await asyncio.shield(task)
                    except asyncio.CancelledError:
                        command.cancelled.set()
                        await asyncio.gather(task, return_exceptions=True)
                        raise
                finally:
                    self.active_id = None
                    current_command.reset(token)
        finally:
            self.commands.pop(command.id, None)

    def cancel(self, command_id=None):
        matched = [c for c in self.commands.values() if command_id is None or c.id == command_id]
        for command in matched:
            command.cancelled.set()
        return len(matched)

    async def close(self):
        self.closed = True
        self.cancel()
        async with self.lock:
            pass


_queues = WeakKeyDictionary()


def get_queue():
    loop = asyncio.get_running_loop()
    if loop not in _queues:
        _queues[loop] = CommandQueue()
    return _queues[loop]
