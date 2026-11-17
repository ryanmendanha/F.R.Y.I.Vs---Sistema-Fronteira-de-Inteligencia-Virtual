"""Reset conversation state without changing application business logic."""
import os
import pytest

os.environ['WAKE_WORD_ENABLED'] = 'false'
os.environ['VOICE_LOCAL_PLAYBACK'] = 'false'


@pytest.fixture(autouse=True)
def isolated_conversation():
    from core.session_state import limpar_sessao
    limpar_sessao()
    yield
    limpar_sessao()
