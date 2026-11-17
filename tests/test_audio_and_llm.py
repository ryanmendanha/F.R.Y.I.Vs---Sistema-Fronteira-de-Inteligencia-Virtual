"""
Suíte de testes de depuração e robustez para os módulos de áudio (STT, TTS) e LLM.
Cobre: VAD, tratamento de exceções de API, timeouts, fallback de transcrição e chamadas de ferramentas.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

# Garante que o diretório raiz esteja no path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from core.stt import _rms, transcrever
from core.tts import falar, limpar_texto_para_fala


class TestAudioSTT(unittest.TestCase):
    """Testes unitários para detecção de silêncio (RMS) e transcrição com Faster-Whisper."""

    def test_rms_calculation_silent_array(self):
        silent_audio = np.zeros(1600, dtype=np.float32)
        rms_val = _rms(silent_audio)
        self.assertEqual(rms_val, 0.0)

    def test_rms_calculation_signal_array(self):
        signal_audio = np.ones(1600, dtype=np.float32) * 0.5
        rms_val = _rms(signal_audio)
        self.assertAlmostEqual(rms_val, 0.5, places=4)

    def test_transcribe_empty_audio_returns_empty_string(self):
        empty_audio = np.array([], dtype=np.float32)
        result = transcrever(empty_audio, 16000)
        self.assertEqual(result, "")

    @patch("core.stt._get_whisper_model")
    def test_transcribe_success_with_mock_model(self, mock_get_model):
        mock_segment = MagicMock()
        mock_segment.text = " Abrir bloco de notas"

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_get_model.return_value = mock_model

        audio_data = np.random.randn(16000).astype(np.float32)
        text = transcrever(audio_data, 16000)
        self.assertEqual(text, "Abrir bloco de notas")

    @patch("faster_whisper.WhisperModel")
    def test_whisper_model_selection_defaults_to_small(self, mock_whisper_cls):
        import core.stt
        core.stt._whisper_model = None
        with patch.dict(os.environ, {"WHISPER_MODEL": ""}):
            model = core.stt._get_whisper_model()
            args, kwargs = mock_whisper_cls.call_args
            self.assertEqual(args, ("small",))
            self.assertEqual(kwargs.get("device"), "cpu")
            self.assertEqual(kwargs.get("compute_type"), "int8")
        core.stt._whisper_model = None


class TestAudioTTS(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._audio_dir = tempfile.TemporaryDirectory(prefix="fryivs_tts_test_")
        self.addCleanup(self._audio_dir.cleanup)
        for replacement in (
            patch.dict(os.environ, {"TTS_PROVIDER": "auto"}),
            patch("core.tts._openai_quota_exhausted", False),
            patch("core.tts.AUDIO_CACHE_DIR", self._audio_dir.name),
            patch("core.tts.voicestudio_disponivel", return_value=False),
            patch("core.tts._falar_edge_tts", return_value=""),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)

    """Testes unitários para Text-to-Speech via OpenAI API."""

    @patch("core.tts._falar_edge_tts", return_value="resposta.mp3")
    @patch("core.tts._falar_openai")
    def test_falar_with_tts_provider_edge_calls_edge_directly(self, mock_openai, mock_edge):
        with patch.dict(os.environ, {"TTS_PROVIDER": "edge"}):
            res = falar("Mensagem direta via Edge")
            self.assertEqual(res, "resposta.mp3")
            mock_edge.assert_called_once()
            mock_openai.assert_not_called()

    def test_limpar_texto_para_fala_removes_markdown_and_asterisks(self):
        """Verifica se asteriscos e caracteres de formatação são removidos para evitar que o TTS pronuncie 'asterisco'."""
        texto_com_marcadores = "**Sim, Senhor!** Os dados são: *CPU* a 50%. Lista:\n* Item 1\n* Item 2\nVeja [link](https://exemplo.com) e `código`."
        limpo = limpar_texto_para_fala(texto_com_marcadores)
        self.assertNotIn("*", limpo)
        self.assertNotIn("`", limpo)
        self.assertNotIn("[link]", limpo)
        self.assertIn("Sim, Senhor! Os dados são: CPU a 50%", limpo)
        self.assertIn("Item 1 Item 2", limpo)
        self.assertIn("Veja link e código.", limpo)

    def test_limpar_texto_para_fala_normalizes_frayvis(self):
        """Verifica se F.R.Y.I.Vs e variantes são convertidos para Frayvis e marcas redundantes removidas."""
        texto = "Eu sou F.R.Y.I.Vs (pronuncia-se Frayvis), às suas ordens."
        limpo = limpar_texto_para_fala(texto)
        self.assertIn("Frayvis", limpo)
        self.assertNotIn("F.R.Y.I.Vs", limpo)
        self.assertNotIn("pronuncia-se", limpo)

        texto_sigla = "FRYIVs pronta para o trabalho."
        limpo_sigla = limpar_texto_para_fala(texto_sigla)
        self.assertEqual(limpo_sigla, "Frayvis pronta para o trabalho.")

    def test_limpar_texto_para_fala_empty_or_none(self):
        self.assertEqual(limpar_texto_para_fala(""), "")
        self.assertEqual(limpar_texto_para_fala("   ***   "), "")

    def test_falar_empty_text_returns_empty(self):
        result = falar("")
        self.assertEqual(result, "")
        result_spaces = falar("   ")
        self.assertEqual(result_spaces, "")

    @patch("core.tts._falar_edge_tts", return_value="")
    @patch.dict(os.environ, {"OPENAI_API_KEY": ""})
    def test_falar_without_api_key_returns_empty(self, mock_edge):
        result = falar("Olá mundo")
        self.assertEqual(result, "")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-mock-key"})
    @patch("requests.post")
    def test_falar_success_writes_file(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [b"audio-data-chunk-1", b"chunk-2"]
        mock_post.return_value = mock_response

        test_output = "test_output_audio.mp3"
        try:
            result = falar("Teste de áudio", output_path=test_output)
            self.assertEqual(result, test_output)
            self.assertTrue(os.path.exists(test_output))
        finally:
            if os.path.exists(test_output):
                os.remove(test_output)

    @patch("core.tts._falar_edge_tts", return_value="")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-mock-key"})
    @patch("requests.post")
    def test_falar_api_error_handled_gracefully(self, mock_post, mock_edge):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": {"message": "Invalid API key"}}
        mock_post.return_value = mock_response

        result = falar("Teste", output_path="non_existent.mp3")
        self.assertEqual(result, "")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-mock-key"})
    @patch("requests.post")
    def test_falar_multi_user_unique_file(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [b"unique-audio-stream"]
        mock_post.return_value = mock_response

        # Modo multi-usuário: gera arquivos separados para usuários simultâneos
        path1 = falar("Resposta usuário 1", unique_file=True)
        path2 = falar("Resposta usuário 2", unique_file=True)
        try:
            self.assertTrue(bool(path1))
            self.assertTrue(bool(path2))
            self.assertNotEqual(path1, path2)
            self.assertEqual(os.path.dirname(path1), self._audio_dir.name)
            self.assertEqual(os.path.dirname(path2), self._audio_dir.name)
            self.assertTrue(os.path.exists(path1))
            self.assertTrue(os.path.exists(path2))
        finally:
            for p in (path1, path2):
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-mock-key"})
    @patch("requests.post")
    def test_falar_concurrent_threads_safety(self, mock_post):
        import concurrent.futures

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [b"concurrent-bytes"]
        mock_post.return_value = mock_response

        # Dispara 10 requisições simultâneas
        def _task(i):
            return falar(f"Mensagem simultanea {i}", unique_file=True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(_task, i) for i in range(10)]
            paths = [f.result(timeout=10) for f in futures]

        # Todos devem ter gerado arquivos válidos e distintos sem conflito
        self.assertEqual(len(paths), 10)
        self.assertEqual(len(set(paths)), 10)
        for p in paths:
            self.assertTrue(os.path.exists(p))
            try:
                os.remove(p)
            except Exception:
                pass


class TestLLMProfiles(unittest.TestCase):
    """Testes para os perfis de tokens configuráveis (Beta: 40, 1.0: 50, Recursive 1.1: 80)."""

    def test_model_profiles_definitions(self):
        from core.llm import MODEL_PROFILES
        self.assertEqual(MODEL_PROFILES["fryvis_beta"]["tokens"], 40)
        self.assertEqual(MODEL_PROFILES["fryvis_1.0"]["tokens"], 50)
        self.assertEqual(MODEL_PROFILES["fryvis_recursive"]["tokens"], 80)
        self.assertEqual(MODEL_PROFILES["fryvis_beta"]["name"], "Fryivs Beta")
        self.assertEqual(MODEL_PROFILES["fryvis_1.0"]["name"], "Fryivs 1.0")
        self.assertEqual(MODEL_PROFILES["fryvis_recursive"]["name"], "Fryivs Recursive 1.1")

    @patch("ollama.chat")
    def test_ask_fryvis_passes_correct_num_predict(self, mock_chat):
        from core.llm import ask_fryvis
        mock_response = MagicMock()
        mock_response.message.content = "Sim, senhor."
        mock_response.message.tool_calls = None
        mock_chat.return_value = mock_response

        # Testa Fryivs Beta (40 tokens)
        ask_fryvis("Olá", profile="fryvis_beta", provider="ollama")
        _, kwargs = mock_chat.call_args
        self.assertEqual(kwargs["options"]["num_predict"], 40)

        # Testa Fryivs 1.0 (50 tokens)
        ask_fryvis("Olá", profile="fryvis_1.0", provider="ollama")
        _, kwargs = mock_chat.call_args
        self.assertEqual(kwargs["options"]["num_predict"], 50)

        # Testa Fryivs Recursive 1.1 (80 tokens)
        ask_fryvis("Olá", profile="fryvis_recursive", provider="ollama")
        _, kwargs = mock_chat.call_args
        self.assertEqual(kwargs["options"]["num_predict"], 80)


if __name__ == "__main__":
    unittest.main()
