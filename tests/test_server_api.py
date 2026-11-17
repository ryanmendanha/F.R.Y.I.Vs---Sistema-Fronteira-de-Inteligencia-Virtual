"""
Suíte de testes de depuração e validação para os endpoints do servidor FastAPI da F.R.Y.I.Vs.
Cobre: /api/status, /api/skills, /api/skills/search, /api/skills/execute, /api/memory, /api/chat e /api/audio/last.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Garante que o diretório raiz esteja no path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient
import server


class TestServerStatusEndpoint(unittest.TestCase):
    """Testes para o endpoint /api/status."""

    def setUp(self):
        self.client = TestClient(server.app)

    @patch("requests.get")
    def test_status_when_ollama_online(self, mock_requests_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests_get.return_value = mock_response

        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "online")
        self.assertEqual(data["assistant_name"], "F.R.Y.I.Vs")
        self.assertTrue(data["ollama_online"])
        self.assertIsNone(data["ollama_error"])
        self.assertIn("abrir_programa", data["available_skills"])
        self.assertEqual(data["default_profile"], "fryvis_1.0")
        profiles_by_id = {p["id"]: p for p in data["available_profiles"]}
        self.assertEqual(profiles_by_id["fryvis_beta"]["tokens"], 40)
        self.assertEqual(profiles_by_id["fryvis_1.0"]["tokens"], 50)
        self.assertEqual(profiles_by_id["fryvis_recursive"]["tokens"], 80)
        self.assertEqual(profiles_by_id["fryvis_beta"]["name"], "Fryivs Beta")
        self.assertEqual(profiles_by_id["fryvis_1.0"]["name"], "Fryivs 1.0")
        self.assertEqual(profiles_by_id["fryvis_recursive"]["name"], "Fryivs Recursive 1.1")

    @patch("requests.get")
    def test_status_when_ollama_offline(self, mock_requests_get):
        mock_requests_get.side_effect = Exception("Connection refused")

        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["ollama_online"])
        self.assertIsNotNone(data["ollama_error"])


class TestServerSkillsEndpoints(unittest.TestCase):
    """Testes para listagem, busca semântica e execução direta de skills."""

    def setUp(self):
        self.client = TestClient(server.app)

    def test_list_skills_returns_all_registered(self):
        response = self.client.get("/api/skills")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("skills", data)
        self.assertIn("schemas", data)
        self.assertIn("abrir_programa", data["skills"])
        self.assertIn("tirar_screenshot", data["skills"])
        self.assertGreaterEqual(len(data["schemas"]), 10)

    def test_search_skills_valid_query(self):
        response = self.client.get("/api/skills/search?q=ajustar+volume")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["query"], "ajustar volume")
        self.assertIn("matched_count", data)
        self.assertIn("matched_skills", data)

    def test_search_skills_missing_query_returns_validation_error(self):
        response = self.client.get("/api/skills/search")
        self.assertEqual(response.status_code, 422)

    def test_execute_skill_direct_success(self):
        with patch("server.execute_skill", return_value="Volume aumentado em 10%") as mock_exec:
            payload = {"skill": "controlar_volume", "arguments": {"acao": "aumentar"}}
            response = self.client.post("/api/skills/execute", json=payload)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["skill"], "controlar_volume")
            self.assertEqual(data["result"], "Volume aumentado em 10%")
            mock_exec.assert_called_once_with("controlar_volume", {"acao": "aumentar"})

    def test_execute_skill_unknown_returns_error_result(self):
        payload = {"skill": "skill_inexistente_xyz", "arguments": {}}
        response = self.client.post("/api/skills/execute", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Erro: Skill", data["result"])


class TestServerMemoryEndpoints(unittest.TestCase):
    """Testes para gerenciamento de memória semântica (/api/memory)."""

    def setUp(self):
        self.client = TestClient(server.app)

    @patch("server.listar_memorias")
    def test_get_memories_returns_list(self, mock_list):
        mock_list.return_value = [
            {"id": "mem-1", "texto": "Usuário gosta de tecnologia", "distancia": 0.0}
        ]
        response = self.client.get("/api/memory")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("memories", data)
        self.assertEqual(len(data["memories"]), 1)
        self.assertEqual(data["memories"][0]["id"], "mem-1")

    @patch("server.deletar_memoria")
    def test_delete_memory_endpoint(self, mock_delete):
        mock_delete.return_value = True
        response = self.client.delete("/api/memory/mem-123")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        mock_delete.assert_called_once_with("mem-123")


class TestServerChatEndpoint(unittest.TestCase):
    """Testes para o endpoint /api/chat e processamento com IA."""

    def setUp(self):
        self.client = TestClient(server.app)

    @patch("server.buscar_contexto")
    @patch("server.ask_fryvis")
    @patch("server.salvar_memoria")
    @patch("server.falar")
    def test_process_chat_success(self, mock_falar, mock_salvar, mock_ask, mock_buscar):
        mock_buscar.return_value = "Contexto relevante prévio"
        mock_ask.return_value = ("Olá! Como posso ajudar?", [])
        mock_falar.return_value = ""

        payload = {
            "message": "Olá FRYVIS",
            "use_memory": True,
            "generate_speech": False,
            "history": []
        }
        response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["user_message"], "Olá FRYVIS")
        self.assertEqual(data["response"], "Olá! Como posso ajudar?")
        self.assertEqual(data["context_used"], "Contexto relevante prévio")
        self.assertEqual(data["tools_executed"], [])
        self.assertFalse(data["has_audio"])
        mock_salvar.assert_called_once()

    @patch("server.buscar_contexto", return_value="")
    @patch("server.ask_fryvis", return_value=("Resposta de teste", []))
    @patch("server.salvar_memoria")
    @patch("server.falar")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=1234)
    def test_process_chat_with_speech_generation_synchronous(self, mock_size, mock_exists, mock_falar, mock_salvar, mock_ask, mock_buscar):
        mock_falar.return_value = "resposta.mp3"
        payload = {
            "message": "Fale comigo",
            "use_memory": False,
            "generate_speech": True,
            "history": []
        }
        response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["has_audio"])
        self.assertIn("audio_url", data)
        self.assertIn("/api/audio/last", data["audio_url"])
        mock_falar.assert_called_once()

    def test_process_chat_empty_message_validation_error(self):
        payload = {"message": ""}
        response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 422)

    @patch("server.buscar_contexto", return_value="")
    @patch("server.ask_fryvis", return_value=("Resposta concisa, senhor.", []))
    def test_process_chat_with_custom_model_profile(self, mock_ask, mock_buscar):
        expected_history = []
        for profile in ["fryvis_beta", "fryvis_1.0", "fryvis_recursive"]:
            payload = {
                "message": "Teste perfil",
                "model_profile": profile,
                "generate_speech": False
            }
            response = self.client.post("/api/chat", json=payload)
            self.assertEqual(response.status_code, 200)
            mock_ask.assert_called_with(
                prompt="Teste perfil",
                context="",
                conversation_history=expected_history,
                enable_semantic_skill_routing=True,
                profile=profile,
                provider=None
            )

            expected_history.extend([
                {"role": "user", "content": "Teste perfil"},
                {"role": "assistant", "content": "Resposta concisa, senhor."},
            ])

        # Testa envio com provider='gemini'
        payload_gemini = {
            "message": "Teste gemini cloud",
            "provider": "gemini",
            "generate_speech": False
        }
        res_gemini = self.client.post("/api/chat", json=payload_gemini)
        self.assertEqual(res_gemini.status_code, 200)
        mock_ask.assert_called_with(
            prompt="Teste gemini cloud",
            context="",
            conversation_history=expected_history,
            enable_semantic_skill_routing=True,
            profile="fryvis_1.0",
            provider="gemini"
        )


class TestServerAudioLastEndpoint(unittest.TestCase):
    """Testes para o endpoint /api/audio/last."""

    def setUp(self):
        self.client = TestClient(server.app)

    def test_get_last_audio_404_when_file_not_found(self):
        with patch("os.path.exists", return_value=False):
            response = self.client.get("/api/audio/last")
            self.assertEqual(response.status_code, 404)

    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=2048)
    def test_get_last_audio_success_returns_no_cache_headers(self, mock_size, mock_exists):
        # Cria arquivo temporário real ou mock de FileResponse
        temp_audio = os.path.join(ROOT, "resposta.mp3")
        already_existed = os.path.exists(temp_audio)
        if not already_existed:
            with open(temp_audio, "wb") as f:
                f.write(b"ID3FakeMp3Content")
        try:
            response = self.client.get("/api/audio/last")
            self.assertEqual(response.status_code, 200)
            self.assertIn("no-cache", response.headers.get("cache-control", ""))
        finally:
            if not already_existed and os.path.exists(temp_audio):
                try:
                    os.remove(temp_audio)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
