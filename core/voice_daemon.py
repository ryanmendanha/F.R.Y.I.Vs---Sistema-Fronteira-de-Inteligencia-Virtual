"""
Daemon de Escuta Contínua e Wake Word ("FRYIVS / Fraives / Frives") no Servidor Python.

Características:
- Único dono do microfone (`sounddevice.InputStream`), funcionando mesmo com a aba
  do navegador minimizada ou fechada.
- Calibração automática do piso de ruído nos primeiros chunks.
- Máquina de estados:
    DORMINDO -> VERIFICANDO -> SENHOR_Q ("Senhor?") -> OUVINDO_PEDIDO -> PROCESSANDO -> DORMINDO
- Se o usuário disser apenas o nome ("Frives!"), responde imediatamente "Senhor?"
  pelas caixas de som e escuta o pedido.
- Se o usuário disser o nome + pedido na mesma frase ("Frives, crie uma planilha"),
  executa diretamente.
- Half-duplex estrito: ignora o microfone enquanto a FRYIVS estiver falando.
"""

from __future__ import annotations

import asyncio
import collections
import os
import queue
import re
import sys
import threading
import time
from typing import Any, Awaitable, Callable

import numpy as np

from core import audio_player
from core.openwakeword_detector import OpenWakeWordDetector, obter_detector_openwakeword
from core.overlay import status_overlay
from core.stt import CHUNK_SIZE, SAMPLE_RATE, _rms, _trim_silence, eh_alucinacao_whisper, transcrever
from core.tts import AUDIO_CACHE_DIR, falar
from core.wake_word import comando_util, contem_nome
from core import mute_state as _mute_state

WAKE_PROMPT = "Frives, FRYIVS, Fraives."
SENHOR_MP3_PATH = os.path.join(AUDIO_CACHE_DIR, "senhor_ack.mp3")


def _em_teste() -> bool:
    return "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))


def garantir_audio_senhor() -> str:
    """Gera e mantém em cache o áudio curto 'Senhor?' para resposta instantânea (~0ms TTS)."""
    from core.e2ee_auth import is_session_unlocked
    if not is_session_unlocked():
        return ""
    os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
    if os.path.exists(SENHOR_MP3_PATH) and os.path.getsize(SENHOR_MP3_PATH) > 200:
        return SENHOR_MP3_PATH
    gerado = falar("Senhor?", output_path=SENHOR_MP3_PATH)
    return gerado or SENHOR_MP3_PATH


class VoiceDaemon:
    """
    Motor de escuta contínua por wake-word com máquina de estados determinística.
    Pode operar sobre o microfone real (`iniciar`) ou sobre uma sequência de chunks
    injetados em testes (`processar_chunk`).
    """

    def __init__(
        self,
        transcrever_wake_fn: Callable[[np.ndarray], str] | None = None,
        transcrever_cmd_fn: Callable[[np.ndarray], str] | None = None,
        tocar_senhor_fn: Callable[[], None] | None = None,
        executar_comando_fn: Callable[[str], None] | None = None,
        notificar_fn: Callable[[dict[str, Any]], None] | None = None,
        tocando_fn: Callable[[], bool] | None = None,
        processando_fn: Callable[[], bool] | None = None,
        oww_detector: OpenWakeWordDetector | None = None,
        usar_openwakeword: bool | None = None,
        limiar_inicial: float = 0.045,
        transcrever_interrupcao_fn: Callable[[np.ndarray], str] | None = None,
    ) -> None:
        self.estado: str = "DORMINDO"
        self.historico_estados: list[str] = ["DORMINDO"]
        self.limiar_rms: float = limiar_inicial
        self._ruido_amostras: list[float] = []

        self._wake_fn_custom: bool = transcrever_wake_fn is not None
        self._transcrever_wake = transcrever_wake_fn or self._default_transcrever_wake
        self._transcrever_cmd = transcrever_cmd_fn or self._default_transcrever_cmd
        self._tocar_senhor = tocar_senhor_fn or self._default_tocar_senhor
        self._executar_comando = executar_comando_fn or self._default_executar_comando
        self._notificar = notificar_fn or (lambda _ev: None)
        self._esta_tocando = tocando_fn or audio_player.tocando
        self._esta_processando = processando_fn or _mute_state.is_processing

        if usar_openwakeword is None:
            usar_openwakeword = transcrever_wake_fn is None or oww_detector is not None
        self._usar_oww: bool = bool(usar_openwakeword)
        self._oww_detector: OpenWakeWordDetector | None = (
            oww_detector if oww_detector is not None else (obter_detector_openwakeword() if self._usar_oww else None)
        )
        self._oww_wake_no_segmento: bool = False
        self._oww_max_score_segmento: float = 0.0

        self._chunks_fala: list[np.ndarray] = []
        self._pre_roll: collections.deque[np.ndarray] = collections.deque(maxlen=3)
        self._fala_iniciada: bool = False
        self._chunks_voz_ativa: int = 0
        self._chunks_silencio: int = 0
        self._chunks_espera_pedido: int = 0
        self._warmup_restante: int = 0

        self._ring_lock = threading.Lock()
        self._ring_chunks: collections.deque[np.ndarray] = collections.deque(maxlen=300)

        self._gatilho_manual = threading.Event()
        self._parar_ev = threading.Event()
        self._stream_aberto = False
        self._thread: threading.Thread | None = None

        self._silenciar_ate: float = 0.0
        if _em_teste():
            _mute_state.reset_cooldown()

        self._stop_chunks: list = []
        self._stop_chunk_limit: int = 8
        self._transcrever_interrupcao = transcrever_interrupcao_fn or self._default_transcrever_wake
        self.long_segment_seconds: float = 2.2

        self.min_wake_chunks = 4
        self.min_voz_ativa_chunks = 3
        self.silencio_wake_chunks = 4
        self.max_wake_chunks = 40

        self.timeout_pedido_chunks = 80
        self.min_pedido_chunks = 5
        self.min_voz_ativa_pedido_chunks = 3
        self.silencio_pedido_chunks = 8
        self.max_pedido_chunks = 150

    def _mudar_estado(self, novo: str) -> None:
        if self.estado != novo:
            self.estado = novo
            self.historico_estados.append(novo)

    def _resetar_captura(self) -> None:
        self._chunks_fala.clear()
        self._fala_iniciada = False
        self._chunks_voz_ativa = 0
        self._chunks_silencio = 0
        self._chunks_espera_pedido = 0
        self._oww_wake_no_segmento = False
        self._oww_max_score_segmento = 0.0

    def _default_transcrever_wake(self, audio: np.ndarray) -> str:
        wake_model = os.getenv("WAKE_WORD_MODEL", "base").strip() or "base"
        return transcrever(
            audio,
            fs=SAMPLE_RATE,
            language="pt",
            model_name=wake_model,
            initial_prompt=WAKE_PROMPT,
            vad_filter=True,
        )

    def _default_transcrever_cmd(self, audio: np.ndarray) -> str:
        return transcrever(audio, fs=SAMPLE_RATE, language="pt")

    def _default_tocar_senhor(self) -> None:
        from core.e2ee_auth import is_session_unlocked
        if not is_session_unlocked():
            return
        caminho = garantir_audio_senhor()
        if caminho:
            audio_player.tocar(caminho, bloquear=True)

    def _default_executar_comando(self, texto: str) -> None:
        pass

    def set_muted(self, mutado: bool) -> None:
        """
        Muta ou desmuta todo o sistema de voz.
        Quando mutado: microfone descartado + TTS/áudio bloqueados via mute_state.
        """
        _mute_state.set_muted(mutado)
        if mutado:
            self._resetar_captura()
            self._mudar_estado("DORMINDO")
            self._notificar({"type": "mic_muted", "muted": True})
            status_overlay("Microfone mudo.", ativo=True, duracao=3.0)
        else:
            self._notificar({"type": "mic_muted", "muted": False})
            status_overlay("Microfone ativo.", ativo=True, duracao=2.0)

    def esta_falando(self) -> bool:
        """Retorna True se a IA estiver reproduzindo áudio ou no cooldown anti-eco pós-fala."""
        if self._esta_tocando and self._esta_tocando():
            return True
        if time.time() < self._silenciar_ate:
            return True
        if self.estado == "SENHOR_Q":
            return True
        usar_player_global = (self._esta_tocando == audio_player.tocando)
        if _mute_state.is_speaking(check_audio_player=usar_player_global):
            return True
        return False

    def esta_processando(self) -> bool:
        """Retorna True se a IA estiver processando um comando (inferência, skills, TTS)."""
        if self.estado == "PROCESSANDO":
            return True
        if self._esta_processando and self._esta_processando():
            return True
        if _mute_state.is_processing():
            return True
        if len(_pipeline_futures) > 0:
            return True
        return False

    def escuta_habilitada(self) -> bool:
        """Retorna True somente se a escuta estiver habilitada (desbloqueada via E2EE, não mutada, não falando e não processando)."""
        from core.e2ee_auth import is_session_unlocked
        if not is_session_unlocked():
            return False
        if _mute_state.is_muted():
            return False
        if self.esta_falando():
            return False
        if self.esta_processando():
            return False
        return True

    def acionar_manual(self) -> bool:
        """Acorda a FRYIVS imediatamente (ex.: botão de microfone na interface)."""
        if not self.escuta_habilitada():
            print("[VoiceDaemon] Escuta manual não habilitada: IA bloqueada (E2EE), mutada, falando ou processando.")
            return False
        self._gatilho_manual.set()
        return True

    def _entrar_modo_senhor(self) -> None:
        from core.e2ee_auth import is_session_unlocked
        if not is_session_unlocked():
            self._resetar_captura()
            self._pre_roll.clear()
            self._mudar_estado("DORMINDO")
            return
        self._mudar_estado("SENHOR_Q")
        status_overlay("Senhor? Estou ouvindo...", ativo=True, duracao=10.0)
        self._notificar({"type": "wake_detected", "response": "Senhor?"})
        self._notificar({"type": "state_change", "state": "speaking", "detail": "Senhor?"})
        try:
            self._tocar_senhor()
        except Exception as e:
            print(f"[VoiceDaemon] Aviso ao tocar 'Senhor?': {e}")
        if self._tocar_senhor == self._default_tocar_senhor and not _em_teste():
            self._silenciar_ate = time.time() + 0.45
        self._resetar_captura()
        self._pre_roll.clear()
        self._mudar_estado("OUVINDO_PEDIDO")
        status_overlay("Ouvindo seu pedido, senhor...", ativo=True, duracao=12.0)
        self._notificar({"type": "state_change", "state": "listening", "detail": "Ouvindo seu comando, senhor..."})

    def _executar_pedido(self, texto_comando: str) -> None:
        from core.e2ee_auth import is_session_unlocked
        if not is_session_unlocked():
            self._resetar_captura()
            self._pre_roll.clear()
            self._stop_chunks.clear()
            self._mudar_estado("DORMINDO")
            return
        if not texto_comando or eh_alucinacao_whisper(texto_comando):
            print(f"[VoiceDaemon] Comando ignorado por filtro anti-alucinação: '{texto_comando}'")
            self._resetar_captura()
            self._pre_roll.clear()
            self._mudar_estado("DORMINDO")
            self._notificar({"type": "state_change", "state": "idle", "detail": "Aguardando 'FRYIVS'..."})
            return
        self._mudar_estado("PROCESSANDO")
        self._notificar({"type": "transcription", "transcription": texto_comando})
        self._notificar({"type": "state_change", "state": "thinking", "detail": f"Executando: {texto_comando[:40]}..."})
        self._resetar_captura()
        self._pre_roll.clear()
        self._stop_chunks.clear()
        pending = None
        try:
            pending = self._executar_comando(texto_comando)
        except Exception as e:
            print(f"[VoiceDaemon] Erro ao executar comando '{texto_comando}': {e}")
        finally:
            if pending is None:
                if self._executar_comando == self._default_executar_comando or not _em_teste():
                    self._silenciar_ate = time.time() + 0.80
                self._resetar_captura()
                self._pre_roll.clear()
                self._stop_chunks.clear()
                self._mudar_estado("DORMINDO")
                self._notificar({"type": "state_change", "state": "idle", "detail": "Aguardando 'FRYIVS'..."})

    def finalizar_processamento(self) -> None:
        """Chamado quando o pipeline assíncrono conclui todo o processamento e fala."""
        self._silenciar_ate = time.time() + 0.80
        self._resetar_captura()
        self._pre_roll.clear()
        self._stop_chunks.clear()
        self._mudar_estado("DORMINDO")
        self._notificar({"type": "state_change", "state": "idle", "detail": "Aguardando 'FRYIVS'..."})

    _STOP_WORDS: frozenset = frozenset({
        "pare", "para", "silencio", "silêncio", "chega",
        "stop", "cancela", "cancele", "basta",
    })

    def _limiar_barge_in(self) -> float:
        """Limiar de energia elevado para barge-in durante reprodução (evita falsos positivos por eco)."""
        return max(self.limiar_rms * 2.2, 0.065)

    def _barge_in_ativo(self) -> bool:
        """Retorna True quando a IA está reproduzindo fala ativamente, desbloqueada (E2EE) e não mutada."""
        from core.e2ee_auth import is_session_unlocked
        if not is_session_unlocked():
            return False
        if _mute_state.is_muted():
            return False
        if self.estado == "SENHOR_Q":
            return False
        if not self.esta_falando():
            return False
        usar_player_global = (self._esta_tocando == audio_player.tocando)
        return bool(
            (self._esta_tocando and self._esta_tocando())
            or _mute_state.is_speaking(check_audio_player=usar_player_global)
        )

    def _processar_chunk_barge_in(self, flat: np.ndarray) -> None:
        """Acumula chunks acima do limiar elevado durante fala para acionar `_verificar_interrupcao`."""
        limiar = self._limiar_barge_in()
        if _rms(flat) >= limiar:
            self._stop_chunks.append(flat)
            if len(self._stop_chunks) >= self._stop_chunk_limit:
                self._verificar_interrupcao()
                self._stop_chunks.clear()
        elif self._stop_chunks:
            if len(self._stop_chunks) >= 3:
                self._verificar_interrupcao()
            self._stop_chunks.clear()

    def _verificar_interrupcao(self) -> None:
        """Verifica se chunks acumulados durante reprodução contêm palavra de parada (barge-in).

        Usa limiar elevado (`max(limiar_rms * 2.2, 0.065)`) para rejeitar eco das caixas de som
        enquanto permite interromper a fala com 'pare', 'chega', 'stop', etc.
        Nunca chamado de dentro do callback sounddevice.
        """
        if not self._stop_chunks:
            return
        try:
            audio_seg = np.concatenate(self._stop_chunks)
            if _rms(audio_seg) < self._limiar_barge_in():
                return
            # Em testes unitários que mockaram apenas `transcrever_wake_fn` sem mockar
            # `_transcrever_interrupcao` nem `transcrever`, evita carregar Whisper real do disco.
            if (
                _em_teste()
                and self._wake_fn_custom
                and self._transcrever_interrupcao == self._default_transcrever_wake
                and getattr(transcrever, "__module__", "") == "core.stt"
            ):
                return
            texto = self._transcrever_interrupcao(audio_seg)
            if not texto:
                return
            tokens = set(re.sub(r"[^\w\s]", " ", texto.lower()).split())
            if tokens & self._STOP_WORDS:
                print(f"[VoiceDaemon] Interrupção por voz (barge-in) detectada: '{texto}'")
                from core import audio_player as _ap
                _ap.parar()
                self._notificar({"type": "barge_in", "text": texto})
                try:
                    if _event_loop is not None:
                        asyncio.run_coroutine_threadsafe(
                            _cancel_active_command_async(), _event_loop
                        )
                except Exception as _exc_c:
                    print(f"[VoiceDaemon] Aviso ao cancelar via fila: {_exc_c}")
        except Exception as exc:
            print(f"[VoiceDaemon] Erro em _verificar_interrupcao: {exc}")

    def processar_chunk(self, chunk: np.ndarray) -> None:
        """Processa um único bloco de 100ms (1600 amostras float32) de áudio."""
        flat = np.asarray(chunk, dtype="float32").flatten()
        if len(flat) == 0:
            return

        if not self.escuta_habilitada():
            self._resetar_captura()
            self._pre_roll.clear()
            if self._barge_in_ativo():
                self._processar_chunk_barge_in(flat)
            else:
                self._stop_chunks.clear()
            return
        if self._stop_chunks:
            self._stop_chunks.clear()

        with self._ring_lock:
            self._ring_chunks.append(flat)

        if self._gatilho_manual.is_set():
            self._gatilho_manual.clear()
            self._entrar_modo_senhor()
            return

        energia = _rms(flat)

        if self._warmup_restante > 0:
            self._warmup_restante -= 1
            if energia < 0.08:
                self._ruido_amostras.append(energia)
                piso = float(np.median(self._ruido_amostras))
                self.limiar_rms = max(0.040, min(0.085, piso * 3.8))
            self._resetar_captura()
            self._pre_roll.clear()
            return

        if self.estado == "DORMINDO" and not self._fala_iniciada and energia < self.limiar_rms:
            if len(self._ruido_amostras) < 40:
                self._ruido_amostras.append(energia)
                piso = float(np.median(self._ruido_amostras))
                self.limiar_rms = max(0.040, min(0.085, piso * 3.8))

        if self.estado == "DORMINDO":
            oww_ativou = False
            oww_score = 0.0
            if self._oww_detector is not None and self._oww_detector.disponivel:
                oww_ativou, oww_score = self._oww_detector.processar_chunk(flat)
                if oww_score > self._oww_max_score_segmento:
                    self._oww_max_score_segmento = oww_score
                if oww_ativou:
                    self._oww_wake_no_segmento = True

            if energia > self.limiar_rms:
                if not self._fala_iniciada:
                    self._fala_iniciada = True
                    self._chunks_fala.extend(self._pre_roll)
                    self._pre_roll.clear()
                self._chunks_fala.append(flat)
                self._chunks_voz_ativa += 1
                self._chunks_silencio = 0
            elif self._fala_iniciada:
                self._chunks_fala.append(flat)
                self._chunks_silencio += 1
            else:
                self._pre_roll.append(flat)

            if self._fala_iniciada and (
                self._chunks_silencio >= self.silencio_wake_chunks
                or len(self._chunks_fala) >= self.max_wake_chunks
            ):
                voz_ativa = self._chunks_voz_ativa
                total_chunks = len(self._chunks_fala)
                oww_confirmou = self._oww_wake_no_segmento
                oww_max_score = self._oww_max_score_segmento
                audio_seg = np.concatenate(self._chunks_fala)
                self._resetar_captura()

                if total_chunks < self.min_wake_chunks or voz_ativa < self.min_voz_ativa_chunks:
                    return

                if (
                    not oww_confirmou
                    and self._oww_detector is not None
                    and self._oww_detector.disponivel
                ):
                    oww_seg_ok, oww_seg_score = self._oww_detector.detectar_em_segmento(audio_seg)
                    oww_max_score = max(oww_max_score, oww_seg_score)
                    if oww_seg_ok:
                        oww_confirmou = True

                if (
                    self._oww_detector is not None
                    and self._oww_detector.disponivel
                    and not oww_confirmou
                    and oww_max_score < 0.25
                    and len(audio_seg) <= SAMPLE_RATE * 1.6
                ):
                    return

                self._mudar_estado("VERIFICANDO")
                duracao_seg = len(audio_seg) / float(SAMPLE_RATE)
                usou_transcricao_completa = False
                if duracao_seg > self.long_segment_seconds and not self._wake_fn_custom:
                    texto = self._transcrever_cmd(audio_seg)
                    usou_transcricao_completa = True
                else:
                    texto = self._transcrever_wake(audio_seg)
                if eh_alucinacao_whisper(texto):
                    if self._oww_detector is not None:
                        self._oww_detector.reset()
                    self._mudar_estado("DORMINDO")
                    return
                chamou, resto = contem_nome(texto)

                if not chamou:
                    if self._oww_detector is not None:
                        self._oww_detector.reset()
                    self._mudar_estado("DORMINDO")
                    return

                print(
                    f"[VoiceDaemon] Wake word detectada (openWakeWord={oww_max_score:.2f}, "
                    f"STT='{texto}', resto='{resto}', dur={duracao_seg:.2f}s)"
                )
                if self._oww_detector is not None:
                    self._oww_detector.reset()

                if comando_util(resto):
                    if usou_transcricao_completa:
                        pedido_final = resto
                    else:
                        texto_completo = self._transcrever_cmd(audio_seg) or texto
                        _, resto_refinado = contem_nome(texto_completo)
                        pedido_final = resto_refinado if comando_util(resto_refinado) else resto
                    self._executar_pedido(pedido_final)
                else:
                    self._entrar_modo_senhor()

        elif self.estado == "OUVINDO_PEDIDO":
            self._chunks_espera_pedido += 1
            if energia > self.limiar_rms:
                if not self._fala_iniciada:
                    self._fala_iniciada = True
                    self._chunks_fala.extend(self._pre_roll)
                    self._pre_roll.clear()
                self._chunks_fala.append(flat)
                self._chunks_voz_ativa += 1
                self._chunks_silencio = 0
            elif self._fala_iniciada:
                self._chunks_fala.append(flat)
                self._chunks_silencio += 1
            else:
                self._pre_roll.append(flat)
                if self._chunks_espera_pedido >= self.timeout_pedido_chunks:
                    print("[VoiceDaemon] Tempo esgotado aguardando comando após 'Senhor?'. Voltando a dormir.")
                    self._resetar_captura()
                    self._mudar_estado("DORMINDO")
                    status_overlay("", ativo=False)
                    self._notificar({"type": "state_change", "state": "idle", "detail": "Pronta"})
                    return

            if self._fala_iniciada and (
                (self._chunks_silencio >= self.silencio_pedido_chunks and len(self._chunks_fala) >= self.min_pedido_chunks)
                or len(self._chunks_fala) >= self.max_pedido_chunks
            ):
                voz_ativa_cmd = self._chunks_voz_ativa
                audio_cmd = _trim_silence(
                    np.concatenate(self._chunks_fala), SAMPLE_RATE, threshold=self.limiar_rms * 0.7
                )
                self._resetar_captura()
                if voz_ativa_cmd < self.min_voz_ativa_pedido_chunks:
                    self._mudar_estado("DORMINDO")
                    status_overlay("", ativo=False)
                    self._notificar({"type": "state_change", "state": "idle", "detail": "Pronta"})
                    return
                texto_cmd = self._transcrever_cmd(audio_cmd)
                if not texto_cmd or not texto_cmd.strip() or eh_alucinacao_whisper(texto_cmd):
                    self._mudar_estado("DORMINDO")
                    status_overlay("", ativo=False)
                    self._notificar({"type": "state_change", "state": "idle", "detail": "Pronta"})
                    return
                chamou_novamente, resto_cmd = contem_nome(texto_cmd)
                if chamou_novamente:
                    if comando_util(resto_cmd):
                        texto_cmd = resto_cmd
                    else:
                        self._mudar_estado("DORMINDO")
                        status_overlay("", ativo=False)
                        self._notificar({"type": "state_change", "state": "idle", "detail": "Pronta"})
                        return
                self._executar_pedido(texto_cmd.strip())


_pipeline_futures: set = set()
_daemon_instance: VoiceDaemon | None = None
_daemon_lock = threading.Lock()
_event_loop: asyncio.AbstractEventLoop | None = None
_broadcast_cb: Callable[[dict[str, Any]], Awaitable[None]] | None = None


async def _cancel_active_command_async() -> None:
    """Cancela o comando ativo na fila (chamado via run_coroutine_threadsafe)."""
    from core.command_queue import get_queue
    get_queue().cancel()


def _notificar_ws(evento: dict[str, Any]) -> None:
    if _event_loop is not None and _broadcast_cb is not None:
        try:
            asyncio.run_coroutine_threadsafe(_broadcast_cb(evento), _event_loop)
        except Exception:
            pass


def _executar_no_pipeline(texto: str):
    if _event_loop is None:
        return
    from core.assistant_pipeline import processar_comando
    from core.llm import DEFAULT_PROFILE

    fut = asyncio.run_coroutine_threadsafe(
        processar_comando(
            texto=texto,
            origem="daemon",
            profile=DEFAULT_PROFILE,
            provider=None,
            use_memory=True,
            generate_speech=True,
            tocar_local=True,
            broadcast_fn=_broadcast_cb,
        ),
        _event_loop,
    )
    _pipeline_futures.add(fut)
    def finished(done):
        _pipeline_futures.discard(done)
        try:
            done.result()
        except Exception as exc:
            print(f"[VoiceDaemon] Pipeline finalizado com erro: {exc}")
        if _daemon_instance is not None:
            _daemon_instance.finalizar_processamento()
    fut.add_done_callback(finished)
    return fut


def _loop_microfone(daemon: VoiceDaemon) -> None:
    import sounddevice as sd

    q_audio: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=200)

    def _callback(indata: np.ndarray, _frames: int, _time_info: Any, _status: Any) -> None:
        try:
            q_audio.put_nowait((time.monotonic(), indata.copy().flatten()))
        except queue.Full:
            pass

    backoff = 1.0
    while not daemon._parar_ev.is_set():
        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=CHUNK_SIZE,
                callback=_callback,
            ):
                daemon._stream_aberto = True
                daemon._warmup_restante = 18
                daemon._resetar_captura()
                backoff = 1.0
                print("[VoiceDaemon] Escuta contínua em standby — aguardando exclusivamente 'FRYIVS / Fraives / Frives'.")
                while not daemon._parar_ev.is_set():
                    try:
                        captured_at, bloco = q_audio.get(timeout=0.25)
                        if time.monotonic() - captured_at <= 0.5:
                            daemon.processar_chunk(bloco)
                    except queue.Empty:
                        if daemon._gatilho_manual.is_set():
                            daemon.processar_chunk(np.zeros(CHUNK_SIZE, dtype="float32"))
        except Exception as e:
            daemon._stream_aberto = False
            if daemon._parar_ev.is_set():
                break
            print(f"[VoiceDaemon] Aviso no stream de microfone ({e}). Reconectando em {backoff:.0f}s...")
            time.sleep(backoff)
            backoff = min(10.0, backoff * 2)
        finally:
            daemon._stream_aberto = False


def iniciar(
    loop: asyncio.AbstractEventLoop,
    broadcast_fn: Callable[[dict[str, Any]], Awaitable[None]],
) -> bool:
    """Inicia a thread do VoiceDaemon no startup do servidor."""
    global _daemon_instance, _event_loop, _broadcast_cb
    if _em_teste():
        return False
    enabled = os.getenv("WAKE_WORD_ENABLED", "true").strip().lower()
    if enabled in ("false", "0", "no", "nao", "não"):
        print("[VoiceDaemon] Desativado via WAKE_WORD_ENABLED=false.")
        return False

    with _daemon_lock:
        _event_loop = loop
        _broadcast_cb = broadcast_fn
        if _daemon_instance is not None and _daemon_instance._thread is not None and _daemon_instance._thread.is_alive():
            return True

        try:
            garantir_audio_senhor()
        except Exception as e:
            print(f"[VoiceDaemon] Aviso ao pré-gerar senhor.mp3: {e}")

        daemon = VoiceDaemon(
            executar_comando_fn=_executar_no_pipeline,
            notificar_fn=_notificar_ws,
        )
        t = threading.Thread(target=_loop_microfone, args=(daemon,), name="FryivsVoiceDaemon", daemon=True)
        daemon._thread = t
        _daemon_instance = daemon
        t.start()
        return True


def parar() -> None:
    """Encerra a escuta contínua do VoiceDaemon."""
    global _daemon_instance
    with _daemon_lock:
        if _daemon_instance is not None:
            _daemon_instance._parar_ev.set()
            _daemon_instance._stream_aberto = False
            _daemon_instance = None


def ativo() -> bool:
    return (
        _daemon_instance is not None
        and not _daemon_instance._parar_ev.is_set()
        and _daemon_instance._thread is not None
        and _daemon_instance._thread.is_alive()
    )


def stream_aberto() -> bool:
    return bool(_daemon_instance is not None and _daemon_instance._stream_aberto)


def status() -> dict[str, Any]:
    from core.e2ee_auth import is_session_unlocked
    oww_info = (
        _daemon_instance._oww_detector.status()
        if (_daemon_instance is not None and _daemon_instance._oww_detector is not None)
        else obter_detector_openwakeword().status()
    )
    return {
        "active": ativo(),
        "stream_open": stream_aberto(),
        "muted": is_muted(),
        "e2ee_locked": not is_session_unlocked(),
        "state": _daemon_instance.estado if _daemon_instance else "INATIVO",
        "threshold_rms": round(_daemon_instance.limiar_rms, 4) if _daemon_instance else 0.0,
        "openwakeword": oww_info,
    }


def acionar_manual() -> bool:
    if _daemon_instance is not None and ativo():
        return _daemon_instance.acionar_manual()
    return False


def set_muted(mutado: bool) -> bool:
    """Define o estado global de mute (entrada + saída de voz). Retorna True se daemon ativo."""
    _mute_state.set_muted(mutado)
    if _daemon_instance is not None:
        _daemon_instance.set_muted(mutado)
        return True
    return False


def is_muted() -> bool:
    """Retorna True se o sistema estiver mutado."""
    return _mute_state.is_muted()


def capturar_audio_do_buffer(duracao: int = 5, fs: int = SAMPLE_RATE) -> tuple[np.ndarray, int]:
    """
    Permite que chamadas diretas a `gravar_audio` capturem áudio sem abrir um 2º InputStream
    concorrente quando o daemon já está com o microfone aberto.
    """
    from core.e2ee_auth import is_session_unlocked
    if not is_session_unlocked() or _daemon_instance is None:
        return np.array([], dtype="float32"), fs
    max_s = min(float(duracao), 15.0)
    inicio = time.time()
    coletados: list[np.ndarray] = []
    fala = False
    silencio = 0
    limiar = _daemon_instance.limiar_rms
    ultimo_len = 0

    while time.time() - inicio < max_s:
        time.sleep(0.1)
        with _daemon_instance._ring_lock:
            if not _daemon_instance._ring_chunks:
                continue
            bloco = _daemon_instance._ring_chunks[-1]
        coletados.append(bloco)
        if _rms(bloco) > limiar:
            fala = True
            silencio = 0
        elif fala:
            silencio += 1
        if fala and silencio >= 7 and len(coletados) >= 8:
            break
        ultimo_len = len(coletados)
        if ultimo_len >= int(max_s * 10):
            break

    if not coletados:
        return np.array([], dtype="float32"), fs
    arr = _trim_silence(np.concatenate(coletados), fs, threshold=limiar * 0.8)
    return arr, fs

