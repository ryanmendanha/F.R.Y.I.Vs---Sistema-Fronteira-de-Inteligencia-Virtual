"""
Estado global de mute e execução da F.R.Y.I.Vs.

Módulo singleton sem dependências internas, para evitar importações circulares.
Gerencia:
  - Mute manual do usuário
  - Estado de processamento (thinking / pipeline ativo)
  - Estado de fala (speaking / reprodução de áudio)
  - Regra: quando a IA estiver falando ou processando, a escuta é estritamente desabilitada.
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_muted: bool = False
_processing_count: int = 0
_speaking: bool = False
_cooldown_ate: float = 0.0


def set_muted(muted: bool) -> None:
    """Define o estado global de mute do sistema."""
    global _muted
    with _lock:
        _muted = muted


def is_muted() -> bool:
    """Retorna True se o sistema estiver com voz e microfone bloqueados."""
    with _lock:
        return _muted


def iniciar_processamento() -> None:
    """Marca início de processamento de comando na IA."""
    global _processing_count
    with _lock:
        _processing_count += 1


def finalizar_processamento() -> None:
    """Marca término de processamento de comando na IA."""
    global _processing_count
    with _lock:
        if _processing_count > 0:
            _processing_count -= 1


def is_processing() -> bool:
    """Retorna True se a IA estiver processando algum comando."""
    with _lock:
        return _processing_count > 0


def definir_falando(falando: bool, cooldown: float = 0.8) -> None:
    """Define se a IA está emitindo fala."""
    global _speaking, _cooldown_ate
    with _lock:
        _speaking = falando
        if not falando and cooldown > 0:
            _cooldown_ate = time.time() + cooldown


def is_speaking(check_audio_player: bool = True) -> bool:
    """Retorna True se a IA estiver falando ou em cooldown pós-fala (anti-eco)."""
    with _lock:
        if _speaking:
            return True
        if time.time() < _cooldown_ate:
            return True
    if check_audio_player:
        try:
            from core import audio_player
            if audio_player.tocando(margem=0.5):
                return True
        except Exception:
            pass
    return False


def reset_cooldown() -> None:
    """Limpa o cooldown pós-fala (usado ao instanciar novo VoiceDaemon em testes)."""
    global _cooldown_ate
    with _lock:
        _cooldown_ate = 0.0


def escuta_permitida() -> bool:
    """Retorna True SOMENTE se a IA estiver em repouso (não mutada, não processando e não falando)."""
    if is_muted():
        return False
    if is_processing():
        return False
    if is_speaking():
        return False
    return True


