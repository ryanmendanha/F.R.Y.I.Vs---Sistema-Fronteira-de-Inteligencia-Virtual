"""
Testes para autenticação WebSocket (/ws?token=...)
"""
from __future__ import annotations

import hmac
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock


def _get_client():
    import server
    return TestClient(server.app)


class TestWebSocketAuth:
    """Testa autenticação opcional via query param no endpoint WebSocket."""

    def test_ws_aceita_sem_token_configurado(self):
        """Sem _API_TOKEN configurado (modo dev): WS aceita sem token."""
        import server
        original = server._API_TOKEN
        try:
            server._API_TOKEN = ""
            client = _get_client()
            with client.websocket_connect("/ws") as ws:
                data = ws.receive_json()
                assert data["type"] == "welcome"
        finally:
            server._API_TOKEN = original

    def test_ws_aceita_com_token_correto(self):
        """Token correto → conexão aceita."""
        import server
        original = server._API_TOKEN
        try:
            server._API_TOKEN = "token_teste_123"
            client = _get_client()
            with client.websocket_connect("/ws?token=token_teste_123") as ws:
                data = ws.receive_json()
                assert data["type"] == "welcome"
        finally:
            server._API_TOKEN = original

    def test_ws_rejeita_com_token_errado(self):
        """Token incorreto → WS fechado com código 4401."""
        import server
        from starlette.websockets import WebSocketDisconnect
        original = server._API_TOKEN
        try:
            server._API_TOKEN = "token_correto"
            client = _get_client()
            with pytest.raises(Exception):
                with client.websocket_connect("/ws?token=token_errado") as ws:
                    ws.receive_json()
        finally:
            server._API_TOKEN = original

    def test_ws_rejeita_sem_token_quando_configurado(self):
        """Token configurado mas não enviado → WS deve ser rejeitado."""
        import server
        from starlette.websockets import WebSocketDisconnect
        original = server._API_TOKEN
        try:
            server._API_TOKEN = "token_secreto"
            client = _get_client()
            with pytest.raises(Exception):
                with client.websocket_connect("/ws") as ws:
                    ws.receive_json()
        finally:
            server._API_TOKEN = original

    def test_ws_compare_digest_usado(self):
        """Verifica que hmac.compare_digest é usado no endpoint WS."""
        import server, inspect
        src = inspect.getsource(server.websocket_endpoint)
        assert "compare_digest" in src, "Deve usar hmac.compare_digest no endpoint WS"

    def test_ws_ping_pong(self):
        """Verifica que ping/pong funciona após autenticação."""
        import server
        original = server._API_TOKEN
        try:
            server._API_TOKEN = ""  # modo dev
            client = _get_client()
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()  # welcome
                ws.send_json({"type": "ping"})
                resp = ws.receive_json()
                assert resp["type"] == "pong"
        finally:
            server._API_TOKEN = original

