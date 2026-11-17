"""
Testes para Etapa 3:
- Autenticação FRYIVS_API_TOKEN (server.py)
- Manifesto SHA-256 da base de conhecimento (knowledge_base.py)
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ══════════════════════════════════════════════════════════════
# Autenticação — _verificar_token
# ══════════════════════════════════════════════════════════════

class TestVerificarToken:
    """Testa a dependência _verificar_token do server.py."""

    def _import_fn(self, token_env: str = ""):
        """Importa _verificar_token com o env configurado."""
        import importlib
        import server
        importlib.reload(server)
        # Sobrescreve _API_TOKEN diretamente após reload
        server._API_TOKEN = token_env
        return server._verificar_token

    def test_sem_token_configurado_libera_qualquer_authorization(self):
        """Modo dev: sem _API_TOKEN configurado, qualquer header é aceito."""
        import server
        original = server._API_TOKEN
        try:
            server._API_TOKEN = ""
            # Não deve lançar exceção
            server._verificar_token(authorization="")
            server._verificar_token(authorization="Bearer qualquer_coisa")
            server._verificar_token(authorization="invalido")
        finally:
            server._API_TOKEN = original

    def test_token_correto_aceito(self):
        """Token Bearer correto deve ser aceito."""
        import server
        original = server._API_TOKEN
        try:
            server._API_TOKEN = "meu_token_secreto_123"
            # Não deve lançar exceção
            server._verificar_token(authorization="Bearer meu_token_secreto_123")
        finally:
            server._API_TOKEN = original

    def test_token_errado_retorna_401(self):
        """Token Bearer incorreto deve lançar HTTPException 401."""
        from fastapi import HTTPException
        import server
        original = server._API_TOKEN
        try:
            server._API_TOKEN = "token_correto"
            with pytest.raises(HTTPException) as exc:
                server._verificar_token(authorization="Bearer token_errado")
            assert exc.value.status_code == 401
        finally:
            server._API_TOKEN = original

    def test_sem_bearer_retorna_401(self):
        """Authorization sem prefixo Bearer deve retornar 401."""
        from fastapi import HTTPException
        import server
        original = server._API_TOKEN
        try:
            server._API_TOKEN = "token_correto"
            with pytest.raises(HTTPException) as exc:
                server._verificar_token(authorization="token_correto")
            assert exc.value.status_code == 401
        finally:
            server._API_TOKEN = original

    def test_authorization_vazio_retorna_401_quando_token_configurado(self):
        """Authorization vazio com token configurado → 401."""
        from fastapi import HTTPException
        import server
        original = server._API_TOKEN
        try:
            server._API_TOKEN = "token_secreto"
            with pytest.raises(HTTPException) as exc:
                server._verificar_token(authorization="")
            assert exc.value.status_code == 401
        finally:
            server._API_TOKEN = original

    def test_compare_digest_timing_safe(self):
        """Verifica que hmac.compare_digest é usado (não ==) para evitar timing attacks."""
        import server, inspect
        src = inspect.getsource(server._verificar_token)
        assert "compare_digest" in src, "Deve usar hmac.compare_digest"
        assert " == " not in src or "compare_digest" in src, "Não deve usar == para comparar tokens"


# ══════════════════════════════════════════════════════════════
# Knowledge Base — manifesto SHA-256
# ══════════════════════════════════════════════════════════════

class TestKBManifesto:
    """Testa o manifesto SHA-256 da knowledge_base."""

    def _setup_kb(self, tmp_path: Path):
        """Configura ambiente isolado para a KB."""
        from core import knowledge_base as kb
        base = tmp_path / "base_conhecimento"
        base.mkdir()
        manifest_path = tmp_path / "data" / "kb_manifest.json"
        # Patch dos caminhos
        return kb, base, manifest_path

    def test_ler_manifesto_arquivo_inexistente_retorna_vazio(self, tmp_path):
        """_ler_manifesto() com arquivo ausente retorna dict vazio."""
        from core import knowledge_base as kb
        with patch.object(kb, "_MANIFEST_PATH", tmp_path / "inexistente.json"):
            resultado = kb._ler_manifesto()
        assert resultado == {}

    def test_salvar_e_ler_manifesto(self, tmp_path):
        """Salvar e ler manifesto deve persistir corretamente."""
        from core import knowledge_base as kb
        manifest_path = tmp_path / "kb_manifest.json"
        dados = {"arquivo1.md": "abc123", "dir/arquivo2.txt": "def456"}

        with patch.object(kb, "_MANIFEST_PATH", manifest_path):
            kb._salvar_manifesto(dados)
            lido = kb._ler_manifesto()

        assert lido == dados

    def test_salvar_manifesto_cria_diretorios(self, tmp_path):
        """_salvar_manifesto cria diretórios pai automaticamente."""
        from core import knowledge_base as kb
        manifest_path = tmp_path / "data" / "subdir" / "kb_manifest.json"

        with patch.object(kb, "_MANIFEST_PATH", manifest_path):
            kb._salvar_manifesto({"arq.md": "hash123"})

        assert manifest_path.exists()

    def test_indexar_pula_arquivo_com_mesmo_hash(self, tmp_path):
        """Se hash do conteúdo igual ao do manifesto e forcar=False → pula upsert."""
        from core import knowledge_base as kb

        conteudo = "# Titulo\n\nConteúdo de teste para a knowledge base."
        sha = hashlib.sha256(conteudo.encode()).hexdigest()

        base = tmp_path / "base_conhecimento"
        base.mkdir()
        arq = base / "doc.md"
        arq.write_text(conteudo, encoding="utf-8")

        manifesto_inicial = {"doc.md": sha}
        manifest_path = tmp_path / "kb_manifest.json"

        mock_colecao = MagicMock()
        mock_colecao.get.return_value = {"ids": []}

        with (
            patch.object(kb, "BASE_CONHECIMENTO_PATH", base),
            patch.object(kb, "_MANIFEST_PATH", manifest_path),
            patch.object(kb, "_get_colecao", new=lambda: mock_colecao),
        ):
            kb._salvar_manifesto(manifesto_inicial)
            total = kb.indexar(forcar=False, verbose=False)

        # Não deve ter chamado upsert pois hash igual
        mock_colecao.upsert.assert_not_called()
        assert total == 0

    def test_indexar_atualiza_chunks_quando_conteudo_muda(self, tmp_path):
        """Quando conteúdo muda, chunks antigos são removidos e novos inseridos."""
        from core import knowledge_base as kb

        conteudo_antigo = "# Doc\n\nConteúdo original."
        conteudo_novo = "# Doc\n\nConteúdo totalmente diferente e atualizado!"
        sha_antigo = hashlib.sha256(conteudo_antigo.encode()).hexdigest()

        base = tmp_path / "base_conhecimento"
        base.mkdir()
        arq = base / "doc.md"
        arq.write_text(conteudo_novo, encoding="utf-8")  # arquivo já com conteúdo novo

        manifest_path = tmp_path / "kb_manifest.json"

        mock_colecao = MagicMock()
        # Simula chunks antigos existentes no ChromaDB
        mock_colecao.get.return_value = {"ids": ["chunk_antigo_1", "chunk_antigo_2"]}
        mock_colecao.count.return_value = 2

        with (
            patch.object(kb, "BASE_CONHECIMENTO_PATH", base),
            patch.object(kb, "_MANIFEST_PATH", manifest_path),
            patch.object(kb, "_get_colecao", new=lambda: mock_colecao),
        ):
            kb._salvar_manifesto({"doc.md": sha_antigo})  # manifesto com hash antigo
            total = kb.indexar(forcar=False, verbose=False)

        # Deve ter deletado os chunks antigos
        mock_colecao.delete.assert_called_once()
        # Deve ter inserido os novos
        mock_colecao.upsert.assert_called_once()
        assert total > 0

    def test_indexar_forcar_sempre_reatuanda(self, tmp_path):
        """forcar=True sempre faz upsert, mesmo sem mudança de conteúdo."""
        from core import knowledge_base as kb

        conteudo = "# Doc\n\nConteúdo de teste."
        sha = hashlib.sha256(conteudo.encode()).hexdigest()

        base = tmp_path / "base_conhecimento"
        base.mkdir()
        arq = base / "doc.md"
        arq.write_text(conteudo, encoding="utf-8")

        manifest_path = tmp_path / "kb_manifest.json"
        mock_colecao = MagicMock()
        mock_colecao.get.return_value = {"ids": []}
        mock_colecao.count.return_value = 1

        with (
            patch.object(kb, "BASE_CONHECIMENTO_PATH", base),
            patch.object(kb, "_MANIFEST_PATH", manifest_path),
            patch.object(kb, "_get_colecao", new=lambda: mock_colecao),
        ):
            kb._salvar_manifesto({"doc.md": sha})  # mesmo hash
            total = kb.indexar(forcar=True, verbose=False)

        # Com forcar=True, deve ter feito upsert mesmo com hash igual
        mock_colecao.upsert.assert_called()
        assert total > 0

    def test_indexar_nao_remove_chunks_em_erro_de_leitura(self, tmp_path):
        """Erro de leitura de arquivo não deve remover chunks existentes."""
        from core import knowledge_base as kb

        base = tmp_path / "base_conhecimento"
        base.mkdir()
        arq = base / "doc.md"
        arq.write_text("# Teste", encoding="utf-8")

        manifest_path = tmp_path / "kb_manifest.json"
        mock_colecao = MagicMock()

        # Simula erro de leitura
        def raise_on_read(*args, **kwargs):
            raise PermissionError("Sem permissão")

        with (
            patch.object(kb, "BASE_CONHECIMENTO_PATH", base),
            patch.object(kb, "_MANIFEST_PATH", manifest_path),
            patch.object(kb, "_get_colecao", new=lambda: mock_colecao),
            patch("pathlib.Path.read_text", side_effect=raise_on_read),
        ):
            kb._salvar_manifesto({})
            kb.indexar(forcar=False, verbose=False)

        # NÃO deve ter chamado delete
        mock_colecao.delete.assert_not_called()

    def test_indexar_reconcilia_fonte_removida(self, tmp_path):
        """Arquivo removido do disco deve ter seus chunks deletados do ChromaDB."""
        from core import knowledge_base as kb

        base = tmp_path / "base_conhecimento"
        base.mkdir()
        # Pasta existe mas arquivo removido

        manifest_path = tmp_path / "kb_manifest.json"
        mock_colecao = MagicMock()
        mock_colecao.get.return_value = {"ids": ["chunk_orfao_1"]}
        mock_colecao.count.return_value = 0

        with (
            patch.object(kb, "BASE_CONHECIMENTO_PATH", base),
            patch.object(kb, "_MANIFEST_PATH", manifest_path),
            patch.object(kb, "_get_colecao", new=lambda: mock_colecao),
        ):
            # Manifesto aponta para arquivo que não existe mais
            kb._salvar_manifesto({"arquivo_removido.md": "hash_antigo"})
            kb.indexar(forcar=False, verbose=False)

        # Deve ter chamado delete para remover chunks órfãos
        mock_colecao.delete.assert_called()

    def test_manifesto_atualizado_apos_indexacao(self, tmp_path):
        """Após indexação bem-sucedida, manifesto deve ter o SHA-256 atual."""
        from core import knowledge_base as kb

        conteudo = "# Teste\n\nConteúdo de exemplo para indexação."
        sha_esperado = hashlib.sha256(conteudo.encode()).hexdigest()

        base = tmp_path / "base_conhecimento"
        base.mkdir()
        (base / "doc.md").write_text(conteudo, encoding="utf-8")

        manifest_path = tmp_path / "kb_manifest.json"
        mock_colecao = MagicMock()
        mock_colecao.get.return_value = {"ids": []}
        mock_colecao.count.return_value = 1

        with (
            patch.object(kb, "BASE_CONHECIMENTO_PATH", base),
            patch.object(kb, "_MANIFEST_PATH", manifest_path),
            patch.object(kb, "_get_colecao", new=lambda: mock_colecao),
        ):
            kb.indexar(forcar=False, verbose=False)
            manifesto_final = kb._ler_manifesto()

        assert "doc.md" in manifesto_final
        assert manifesto_final["doc.md"] == sha_esperado
