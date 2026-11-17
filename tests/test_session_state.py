"""
Testes unitários do gerenciador de estado de sessão unificado (`core/session_state.py`).
"""

from core import session_state


class TestSessionState:
    def setup_method(self):
        session_state.limpar()

    def test_registrar_turno_limita_a_oito_mensagens(self):
        for i in range(6):
            session_state.registrar_turno(f"pergunta {i}", f"resposta {i}")

        hist = session_state.obter_historico()
        assert len(hist) == 8
        assert hist[0] == {"role": "user", "content": "pergunta 2"}
        assert hist[-1] == {"role": "assistant", "content": "resposta 5"}

    def test_registrar_e_obter_artefatos_por_tipo(self):
        session_state.registrar_artefato(
            tipo="excel",
            caminho="C:/temp/estoque.xlsx",
            aba="Produtos",
            colunas=["Item", "Qtd"],
        )
        session_state.registrar_artefato(
            tipo="word",
            caminho="C:/temp/relatorio.docx",
            titulo="Relatório Mensal",
        )
        session_state.registrar_artefato(
            tipo="web",
            url="https://github.com",
            titulo="GitHub",
        )

        # Artefato ativo mais recente é web
        ativo = session_state.obter_artefato()
        assert ativo is not None
        assert ativo["tipo"] == "web"
        assert ativo["url"] == "https://github.com"

        # Consulta explícita por tipo retorna cada artefato preservado
        excel = session_state.obter_artefato("excel")
        assert excel is not None
        assert excel["caminho"] == "C:/temp/estoque.xlsx"
        assert excel["aba"] == "Produtos"

        word = session_state.obter_artefato("word")
        assert word is not None
        assert word["caminho"] == "C:/temp/relatorio.docx"

    def test_contexto_para_llm_inclui_artefatos_abertos(self):
        session_state.registrar_artefato(
            tipo="excel",
            caminho="C:/temp/financeiro.xlsx",
            aba="Fluxo",
            colunas=["Data", "Valor"],
        )
        ctx = session_state.contexto_para_llm()
        assert "[Artefatos Abertos em Segundo Plano]" in ctx
        assert "C:/temp/financeiro.xlsx" in ctx
        assert "Fluxo" in ctx

