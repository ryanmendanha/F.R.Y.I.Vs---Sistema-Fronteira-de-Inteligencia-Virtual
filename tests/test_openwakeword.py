"""
Testes de integração do motor `openWakeWord` (https://github.com/dscripka/openWakeWord)
com o modelo customizado `models/openwakeword/fryivs.onnx` e `VoiceDaemon`.
"""

from pathlib import Path

import numpy as np
import pytest
from faster_whisper.audio import decode_audio

from core.openwakeword_detector import (
    FRYIVS_ONNX_PATH,
    FRYIVS_VERIFIER_PATH,
    OpenWakeWordDetector,
    garantir_modelos_openwakeword,
)
from core.stt import CHUNK_SIZE, SAMPLE_RATE
from core.voice_daemon import VoiceDaemon
from scripts.train_fryivs_openwakeword import extrair_segmentos_voz_m4a

VOZ_M4A = Path(__file__).resolve().parents[1] / "voz-capta" / "voz.m4a"


class TestOpenWakeWordEngine:
    """Valida o modelo ONNX do openWakeWord, o verificador de voz e a integração com o VoiceDaemon."""

    def test_modelos_openwakeword_presentes_e_carregados(self):
        assert garantir_modelos_openwakeword() is True
        assert FRYIVS_ONNX_PATH.exists()
        assert FRYIVS_VERIFIER_PATH.exists()

        detector = OpenWakeWordDetector()
        assert detector.disponivel is True
        st = detector.status()
        assert st["engine"] == "openWakeWord (ONNX)"
        assert st["available"] is True
        assert st["verifier_enabled"] is True

    @pytest.mark.skipif(not VOZ_M4A.exists(), reason="Arquivo voz-capta/voz.m4a não encontrado")
    def test_openwakeword_detecta_5_de_5_no_audio_real_voz_m4a(self):
        detector = OpenWakeWordDetector(threshold=0.55)
        audio = decode_audio(str(VOZ_M4A), sampling_rate=SAMPLE_RATE).astype(np.float32)
        segmentos = extrair_segmentos_voz_m4a(audio)
        assert len(segmentos) == 5

        scores = []
        detectados = 0
        for seg in segmentos:
            ok, score = detector.detectar_em_segmento(seg)
            scores.append(round(score, 4))
            if ok:
                detectados += 1

        assert detectados == 5, f"Esperado 5/5 pelo openWakeWord em voz.m4a, obtido {detectados}/5 (scores={scores})"

    def test_openwakeword_rejeita_silencio_e_ruido_ambiente(self):
        detector = OpenWakeWordDetector(threshold=0.55)
        rng = np.random.default_rng(123)

        # Silêncio puro
        ok_sil, score_sil = detector.detectar_em_segmento(np.zeros(SAMPLE_RATE, dtype=np.float32))
        assert not ok_sil and score_sil < 0.25

        # Ruído branco/ambiente em diferentes amplitudes
        for amp in (0.005, 0.02, 0.05):
            ruido = rng.normal(0.0, amp, SAMPLE_RATE).astype(np.float32)
            ok_r, score_r = detector.detectar_em_segmento(ruido)
            assert not ok_r, f"Falso positivo do openWakeWord em ruído amp={amp}: score={score_r}"

    @pytest.mark.skipif(not VOZ_M4A.exists(), reason="Arquivo voz-capta/voz.m4a não encontrado")
    def test_voice_daemon_com_openwakeword_acorda_com_voz_real_e_liga_microfone(self):
        detector = OpenWakeWordDetector(threshold=0.55)
        senhor_tocado = []
        comandos = []

        daemon = VoiceDaemon(
            transcrever_wake_fn=lambda _a: "Frives",
            transcrever_cmd_fn=lambda _a: "abra o primeiro link",
            tocar_senhor_fn=lambda: senhor_tocado.append(True),
            executar_comando_fn=lambda cmd: comandos.append(cmd),
            tocando_fn=lambda: False,
            oww_detector=detector,
            usar_openwakeword=True,
        )

        audio = decode_audio(str(VOZ_M4A), sampling_rate=SAMPLE_RATE).astype(np.float32)
        seg_voz = extrair_segmentos_voz_m4a(audio)[0]

        # Pre-roll de silêncio + segmento real da voz do usuário + silêncio pós-fala
        stream_audio = np.concatenate([
            np.zeros(CHUNK_SIZE * 5, dtype=np.float32),
            seg_voz,
            np.zeros(CHUNK_SIZE * 6, dtype=np.float32),
        ])
        for idx in range(0, len(stream_audio) - CHUNK_SIZE + 1, CHUNK_SIZE):
            daemon.processar_chunk(stream_audio[idx : idx + CHUNK_SIZE])

        assert len(senhor_tocado) == 1
        assert daemon.estado == "OUVINDO_PEDIDO"

        # Agora envia o comando de voz com o microfone ativo em OUVINDO_PEDIDO
        for _ in range(6):
            daemon.processar_chunk(np.full(CHUNK_SIZE, 0.15, dtype=np.float32))
        for _ in range(8):
            daemon.processar_chunk(np.zeros(CHUNK_SIZE, dtype=np.float32))

        assert comandos == ["abra o primeiro link"]
        assert daemon.estado == "DORMINDO"

