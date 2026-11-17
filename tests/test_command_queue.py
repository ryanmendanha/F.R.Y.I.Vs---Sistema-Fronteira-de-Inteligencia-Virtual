import asyncio
import pytest
from core.command_control import Command, CommandCancelled, check_cancelled
from core.command_queue import CommandQueue


def test_cancelled_waiting_command_never_executes():
    async def scenario():
        queue = CommandQueue()
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def first():
            started.set()
            await release.wait()
        async def second():
            calls.append('unexpected')
        active = asyncio.create_task(queue.run(first))
        await started.wait()
        command = Command()
        pending = asyncio.create_task(queue.run(second, command))
        await asyncio.sleep(0)
        assert queue.cancel(command.id) == 1
        release.set()
        await active
        with pytest.raises(CommandCancelled):
            await pending
        assert calls == []
        assert not queue.commands
    asyncio.run(scenario())


def test_cancelled_caller_drains_operation_before_next():
    async def scenario():
        queue = CommandQueue(capacity=1)
        started, release = asyncio.Event(), asyncio.Event()
        async def operation():
            started.set()
            await release.wait()
            await asyncio.to_thread(check_cancelled)
        task = asyncio.create_task(queue.run(operation))
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        with pytest.raises(RuntimeError, match='cheia'):
            await queue.run(operation)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not queue.commands
    asyncio.run(scenario())


def test_shutdown_cancels_waiters_and_rejects_new_work():
    async def scenario():
        queue = CommandQueue()
        entered, release = asyncio.Event(), asyncio.Event()
        async def operation():
            entered.set()
            await release.wait()
        active = asyncio.create_task(queue.run(operation))
        await entered.wait()
        closing = asyncio.create_task(queue.close())
        await asyncio.sleep(0)
        assert not closing.done()
        with pytest.raises(RuntimeError, match='encerrando'):
            await queue.run(operation)
        release.set()
        await active
        await closing
        assert not queue.commands
    asyncio.run(scenario())
