"""
Testes unitários para o módulo core.gemini_client e para o failover híbrido em core.llm.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from core.gemini_client import (
    _format_history_for_gemini,
    ask_gemini,
    is_gemini_configured,
)
from core.llm import ask_fryvis


class TestGeminiClient(unittest.TestCase):
    """Testes de formatação, configuração e chamadas do cliente Gemini."""

    def test_is_gemini_configured(self):
        with patch("core.gemini_client.GEMINI_API_KEY", "test-key-123"):
            self.assertTrue(is_gemini_configured())
        with patch("core.gemini_client.GEMINI_API_KEY", ""):
            self.assertFalse(is_gemini_configured())

    def test_format_history_for_gemini(self):
        raw_history = [
            {"role": "user", "content": "Olá"},
            {"role": "assistant", "content": "Olá, senhor."},
            {"role": "user", "content": "Como vai?"},
        ]
        formatted = _format_history_for_gemini(raw_history)
        self.assertEqual(len(formatted), 3)
        self.assertEqual(formatted[0]["role"], "user")
        self.assertEqual(formatted[1]["role"], "model")
        self.assertEqual(formatted[2]["role"], "user")
        self.assertEqual(formatted[0]["parts"][0]["text"], "Olá")

    @patch("urllib.request.urlopen")
    def test_ask_gemini_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "candidates": [{
                "content": {
                    "parts": [{"text": "Sim, senhor. Todos os protocolos operando perfeitamente."}]
                }
            }]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch("core.gemini_client.GEMINI_API_KEY", "fake-key"):
            text, tools = ask_gemini("Status do sistema?", max_tokens=50)
            self.assertIn("Sim, senhor", text)
            self.assertEqual(tools, [])

    @patch("core.llm.ask_gemini")
    def test_ask_fryvis_direct_gemini_provider(self, mock_gemini):
        mock_gemini.return_value = ("Resposta vinda da nuvem Google Gemini, senhor.", [])
        resp, tools = ask_fryvis("Qual a resposta?", provider="gemini", profile="fryvis_1.0")
        self.assertIn("Gemini", resp)
        self.assertIn("senhor.", resp)
        mock_gemini.assert_called_once()

    @patch("core.llm.ask_gemini")
    @patch("ollama.chat")
    def test_ask_fryvis_hybrid_fallback_on_ollama_offline(self, mock_ollama, mock_gemini):
        mock_ollama.side_effect = Exception("Failed to connect to Ollama: connection refused")
        mock_gemini.return_value = ("Resposta de fallback do Gemini Flash, senhor.", [])

        with patch("core.llm.is_gemini_configured", return_value=True):
            resp, tools = ask_fryvis("Comando teste", provider="hybrid", profile="fryvis_beta")
            self.assertIn("Gemini Flash", resp)
            self.assertIn("senhor.", resp)
            mock_gemini.assert_called_once()


if __name__ == "__main__":
    unittest.main()
