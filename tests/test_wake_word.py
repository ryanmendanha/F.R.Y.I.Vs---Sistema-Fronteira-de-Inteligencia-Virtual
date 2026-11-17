"""
Testes de detecção fonética de Wake Word ("FRYIVS / Fraives / Frives") e validação
contra a amostra real de voz do usuário (`voz-capta/voz.m4a`).
"""

import os
from pathlib import Path

import numpy as np
import pytest

from core.stt import SAMPLE_RATE, _rms, transcrever
from core.voice_daemon import WAKE_PROMPT
from core.wake_word import comando_util, contem_nome, normalizar

ROOT_DIR = Path(__file__).resolve().parent.parent
VOZ_M4A = ROOT_DIR / "voz-capta" / "voz.m4a"


class TestWakeWordPhonetics:
    """Valida todas as variações fonéticas positivas e negativas."""

    @pytest.mark.parametrize(
        "frase",
        [
            "FRYIVS",
            "Fryvis",
            "Fraives",
            "Frives",
            "Frive",
            "Frivis",
            "Fraive",
            "Frayvis",
            "Fra ives",
            "Oi Frives!",
            "Olá Fraives",
        ],
    )
    def test_detecta_variacoes_do_nome_isolado(self, frase: str):
        chamou, resto = contem_nome(frase)
        assert chamou is True, f"Deveria detectar wake word em: {frase!r}"
        assert comando_util(resto) is False, f"Resto deveria ser vazio/saudação em {frase!r}, obtido {resto!r}"

    def test_extrai_comando_apos_wake_word(self):
        chamou, resto = contem_nome("Frives, crie uma planilha de estoque agora")
        assert chamou is True
        assert resto == "crie uma planilha de estoque agora"
        assert comando_util(resto) is True

    def test_extrai_comando_apos_token_dividido(self):
        chamou, resto = contem_nome("Fra ives abra o navegador no google")
        assert chamou is True
        assert resto == "abra o navegador no google"
        assert comando_util(resto) is True

    @pytest.mark.parametrize(
        "frase_negativa",
        [
            "",
            "drive",
            "google drive",
            "está frio hoje",
            "Ai, me liberto de isso agora",
            "batata frita",
            "five",
            "fries",
            "bom dia tudo bem",
            "qual é a previsão do tempo",
            "livre para sair",
        ],
    )
    def test_rejeita_falsos_positivos(self, frase_negativa: str):
        chamou, resto = contem_nome(frase_negativa)
        assert chamou is False, f"Falso positivo indevido para: {frase_negativa!r}"
        assert resto == ""

    def test_normalizar_remove_acentos_e_pontuacao(self):
        assert normalizar("Olá, F.R.Y.I.Vs!") == "ola fryivs"


class TestWakeWordAudioSample:
    """Valida 5/5 ativações na gravação real `voz-capta/voz.m4a`."""

    @pytest.mark.skipif(not VOZ_M4A.exists(), reason="Arquivo voz-capta/voz.m4a não encontrado")
    def test_cinco_de_cinco_no_audio_real_voz_m4a(self):
        from faster_whisper.audio import decode_audio

        audio = decode_audio(str(VOZ_M4A), sampling_rate=SAMPLE_RATE)
        assert len(audio) > SAMPLE_RATE * 5

        chunk_len = 1600
        limiar = 0.025
        segmentos: list[np.ndarray] = []
        atual: list[np.ndarray] = []
        silencio = 0

        for idx in range(0, len(audio), chunk_len):
            bloco = audio[idx : idx + chunk_len]
            energia = _rms(bloco)
            if energia > limiar:
                if not atual and idx >= chunk_len:
                    atual.append(audio[idx - chunk_len : idx])
                atual.append(bloco)
                silencio = 0
            elif atual:
                atual.append(bloco)
                silencio += 1
                if silencio >= 4:
                    seg = np.concatenate(atual)
                    if len(seg) >= chunk_len * 3:
                        segmentos.append(seg)
                    atual = []
                    silencio = 0

        if atual:
            seg = np.concatenate(atual)
            if len(seg) >= chunk_len * 3:
                segmentos.append(seg)

        assert len(segmentos) == 5, f"Esperados 5 segmentos em voz.m4a, encontrados {len(segmentos)}"

        detectados = 0
        transcricoes = []
        for seg in segmentos:
            texto = transcrever(
                seg,
                fs=SAMPLE_RATE,
                language="pt",
                model_name="base",
                initial_prompt=WAKE_PROMPT,
                vad_filter=False,
            )
            transcricoes.append(texto)
            chamou, _ = contem_nome(texto)
            if chamou:
                detectados += 1

        assert detectados == 5, f"Esperado 5/5 detecções em voz.m4a, obtido {detectados}/5 ({transcricoes})"

    def test_ruido_ambiente_nao_alucina_wake_word(self):
        rng = np.random.default_rng(42)
        for amp in (0.01, 0.03, 0.06):
            ruido = rng.normal(0.0, amp, SAMPLE_RATE).astype("float32")
            texto = transcrever(
                ruido,
                fs=SAMPLE_RATE,
                language="pt",
                model_name="base",
                initial_prompt=WAKE_PROMPT,
                vad_filter=True,
            )
            chamou, _ = contem_nome(texto)
            assert not chamou, f"Ruído (amp={amp}) alucinou wake word: {texto!r}"


