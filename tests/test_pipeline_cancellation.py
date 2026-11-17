import asyncio
import threading
from unittest.mock import patch

from core.assistant_pipeline import processar_comando
from core.command_control import check_cancelled
from core.command_queue import get_queue


def test_cancellation_reaches_model_thread_and_prevents_audio():
    async def scenario():
        entered, release = threading.Event(), threading.Event()
        audio_calls, events = [], []
        def model(**kwargs):
            entered.set()
            release.wait(5)
            check_cancelled()
            return 'late response', []
        async def broadcast(event):
            events.append(event)
        task = asyncio.create_task(processar_comando(
            texto='teste', use_memory=False,
            buscar_conhecimento_fn=lambda *a, **k: '',
            ask_fryvis_fn=model,
            falar_fn=lambda *a, **k: audio_calls.append(a),
            broadcast_fn=broadcast,
        ))
        assert await asyncio.to_thread(entered.wait, 5)
        assert get_queue().cancel() == 1
        release.set()
        result = await task
        assert result['cancelled'] is True
        assert not audio_calls
        assert events[-1]['state'] == 'idle'
    asyncio.run(scenario())


def test_final_state_published_when_model_fails():
    async def scenario():
        events = []
        async def broadcast(event):
            events.append(event)
        with patch('core.assistant_pipeline.status_overlay'):
            try:
                await processar_comando(
                    texto='teste', use_memory=False, generate_speech=False,
                    buscar_conhecimento_fn=lambda *a, **k: '',
                    ask_fryvis_fn=lambda **k: (_ for _ in ()).throw(ValueError('failure')),
                    broadcast_fn=broadcast,
                )
            except ValueError:
                pass
            else:
                raise AssertionError('Expected model failure')
        assert events[-1]['state'] == 'idle'
        assert not get_queue().commands
    asyncio.run(scenario())
