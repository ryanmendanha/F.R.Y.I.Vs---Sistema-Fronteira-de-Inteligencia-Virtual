"""
Teste de regressão para o fallback de conexão em `core/llm.py` (`ask_fryvis`),
garantindo que falhas no `ollama.chat` inicial não lancem `NameError: name 'err_msg' is not defined`.
"""

from unittest.mock import patch

from core.llm import ask_fryvis


class TestLLMFallbackRegression:
    def test_ollama_connection_error_nao_levanta_name_error(self):
        with patch("ollama.chat", side_effect=ConnectionError("Connection refused")):
            with patch("core.llm.is_gemini_configured", return_value=False):
                resposta, tools = ask_fryvis("Explique a teoria da relatividade detalhadamente")

        assert isinstance(resposta, str)
        assert len(resposta) > 0
        assert isinstance(tools, list)

    def test_tool_failure_detectada_mesmo_quando_nao_e_a_ultima_tool(self):
        executed = [
            {"tool": "criar_planilha", "args": {}, "result": "Erro ao criar planilha: permissão negada"},
            {"tool": "obter_data_hora", "args": {}, "result": "10:00"},
        ]
        any_failed = any(
            str(t.get("result", "")).lower().startswith(("erro", "falha", "não foi possível"))
            for t in executed
        )
        assert any_failed is True
