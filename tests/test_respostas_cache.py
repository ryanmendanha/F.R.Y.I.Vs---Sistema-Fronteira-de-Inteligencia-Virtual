"""
Testes para o cache de respostas pré-indexadas e integração com o pipeline e KB.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

from core.respostas_cache import (
    buscar_resposta_cache,
    normalizar_chave,
    carregar_cache,
)


class TestNormalizarChave:
    def test_remove_pontuacao_acentos_e_casing(self):
        assert normalizar_chave("Quem é Você???") == "quem e voce"
        assert normalizar_chave("  OLÁ,   Mundo!  ") == "ola mundo"
        assert normalizar_chave("") == ""
        assert normalizar_chave(None) == ""


class TestRespostasCache:
    def test_cache_carrega_com_sucesso(self):
        dados = carregar_cache()
        assert dados is not None
        assert dados.get("total_respostas") == 65
        assert dados.get("total_perguntas") == 264
        assert "lookup_exato" in dados
        assert len(dados.get("itens", [])) == 264

    def test_busca_exata_identidade(self):
        res = buscar_resposta_cache("quem é você")
        assert res is not None
        assert res["match_type"] == "exato"
        assert res["score"] == 1.0
        assert "FRYIVS" in res["resposta"]
        assert "Senhor" in res["resposta"]

    def test_busca_exata_com_variacao_acentos_e_pontuacao(self):
        res = buscar_resposta_cache("quem e voce?")
        assert res is not None
        assert "FRYIVS" in res["resposta"]

    def test_busca_com_cortesia_e_ativacao(self):
        res = buscar_resposta_cache("olá fryivs quem é você por favor")
        assert res is not None
        assert res["score"] >= 0.99
        assert "FRYIVS" in res["resposta"]

    def test_busca_nome_e_significado(self):
        res = buscar_resposta_cache("o que significa seu nome")
        assert res is not None
        assert "Fronteira de Inteligência Virtual" in res["resposta"]

    def test_busca_capacidades_e_programas(self):
        res = buscar_resposta_cache("você abre programas")
        assert res is not None
        assert "trinta e cinco" in res["resposta"].lower() or "calculadora" in res["resposta"].lower()

    def test_busca_semantica_humano(self):
        res = buscar_resposta_cache("você é um ser humano?")
        assert res is not None
        assert res["match_type"] == "semantico"
        assert res["score"] >= 0.82
        assert "inteligência artificial" in res["resposta"].lower() or "não" in res["resposta"].lower()

    def test_busca_semantica_sentimentos(self):
        res = buscar_resposta_cache("você tem sentimentos de verdade")
        assert res is not None
        assert res["match_type"] == "semantico"
        assert res["score"] >= 0.82
        assert "emoções" in res["resposta"].lower()

    def test_comandos_de_acao_e_consultas_dinamicas_sao_rejeitados_pelo_cache(self):
        assert buscar_resposta_cache("abre a calculadora") is None
        assert buscar_resposta_cache("crie uma pasta no desktop") is None
        assert buscar_resposta_cache("feche a janela do chrome") is None
        assert buscar_resposta_cache("aumente o volume para cinquenta") is None
        assert buscar_resposta_cache("crie uma planilha de vendas") is None
        assert buscar_resposta_cache("bloqueia a tela para mim") is None
        assert buscar_resposta_cache("cria um relatório no word") is None

        assert buscar_resposta_cache("que horas são") is None
        assert buscar_resposta_cache("me diga que horas são") is None
        assert buscar_resposta_cache("que dia é hoje") is None
        assert buscar_resposta_cache("qual a data de hoje") is None
        assert buscar_resposta_cache("como está a cpu") is None

    def test_perguntas_estranhas_retornam_none(self):
        assert buscar_resposta_cache("quanto é a raiz quadrada de 98234") is None
        assert buscar_resposta_cache("qual o resultado do jogo de ontem") is None
        assert buscar_resposta_cache("") is None
        assert buscar_resposta_cache("   ") is None


class TestPipelineIntegration:
    def test_pipeline_usa_cache_sem_chamar_llm(self):
        import asyncio
        from core.assistant_pipeline import processar_comando

        async def scenario():
            mock_ask = MagicMock(return_value=("Resposta mock do LLM", []))
            mock_falar = MagicMock(return_value="")

            resultado = await processar_comando(
                texto="quem é você",
                origem="chat",
                ask_fryvis_fn=mock_ask,
                falar_fn=mock_falar,
                generate_speech=False,
                use_memory=False,
            )

            mock_ask.assert_not_called()
            assert resultado["from_cache"] is True
            assert "FRYIVS" in resultado["response"]

        asyncio.run(scenario())

    def test_pipeline_chama_llm_quando_cache_da_miss(self):
        import asyncio
        from core.assistant_pipeline import processar_comando

        async def scenario():
            mock_ask = MagicMock(return_value=("Aqui está sua resposta gerada.", []))
            mock_falar = MagicMock(return_value="")

            resultado = await processar_comando(
                texto="qual a capital da Mongólia?",
                origem="chat",
                ask_fryvis_fn=mock_ask,
                falar_fn=mock_falar,
                generate_speech=False,
                use_memory=False,
            )

            mock_ask.assert_called_once()
            assert resultado["from_cache"] is False
            assert resultado["response"] == "Aqui está sua resposta gerada."

        asyncio.run(scenario())


class TestOfficeSkillsInKB:
    def test_arquivos_office_existem_na_base_conhecimento(self):
        base_path = Path("oragnizacoes_ideias/base_conhecimento/habilidades")
        assert (base_path / "office-excel.md").exists()
        assert (base_path / "office-word.md").exists()
        assert (base_path / "office-powerpoint.md").exists()

    def test_busca_kb_retorna_conteudo_office(self):
        from core.knowledge_base import buscar_conhecimento

        res_excel = buscar_conhecimento("como criar planilha com openpyxl", k=1)
        assert "office-excel" in res_excel.lower() or "openpyxl" in res_excel.lower()

        res_ppt = buscar_conhecimento("como montar slides com python-pptx", k=1)
        assert "powerpoint" in res_ppt.lower() or "pptx" in res_ppt.lower()

        res_word = buscar_conhecimento("como formatar documento docx python-docx", k=1)
        assert "word" in res_word.lower() or "docx" in res_word.lower()
