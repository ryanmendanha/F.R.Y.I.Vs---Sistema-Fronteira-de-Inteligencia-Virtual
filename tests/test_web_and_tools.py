"""
Testes automatizados para as novas ferramentas de automação web,
visão computacional, processamento de arquivos/planilhas e agendamento na F.R.Y.I.Vs.
"""

import os
from pathlib import Path
import pytest
from skills import SKILLS_REGISTRY, ALL_SKILL_SCHEMAS, execute_skill


def test_registry_contains_new_skills():
    novas_skills = [
        "navegar_para",
        "pesquisar_na_web",
        "clicar_elemento_web",
        "digitar_campo_web",
        "ler_conteudo_pagina",
        "capturar_tela_web",
        "fechar_navegador",
        "localizar_e_clicar_imagem",
        "ler_texto_da_tela",
        "gerenciar_arquivos",
        "consultar_planilha",
        "agendar_execucao",
        "listar_agendamentos",
        "enviar_alerta_webhook"
    ]
    for skill_name in novas_skills:
        assert skill_name in SKILLS_REGISTRY, f"Skill '{skill_name}' deve estar no SKILLS_REGISTRY"


def test_schemas_validity():
    assert len(ALL_SKILL_SCHEMAS) >= 29
    schema_names = [s.get("function", {}).get("name") for s in ALL_SKILL_SCHEMAS if "function" in s]
    assert "navegar_para" in schema_names
    assert "pesquisar_na_web" in schema_names
    assert "gerenciar_arquivos" in schema_names
    assert "consultar_planilha" in schema_names
    assert "agendar_execucao" in schema_names


def test_gerenciar_arquivos_seguranca():
    res = execute_skill("gerenciar_arquivos", {"acao": "deletar", "origem": "C:\\Windows"})
    assert "bloqueada por segurança" in res.lower()

    res_list = execute_skill("gerenciar_arquivos", {"acao": "listar", "origem": "."})
    assert "conteúdo do diretório" in res_list.lower() or "diretório" in res_list.lower()


def test_agendamento_e_listagem():
    res_add = execute_skill("agendar_execucao", {"horario": "10:00", "comando": "Rotina de teste", "tipo": "diario"})
    assert "agendada" in res_add.lower() or "sucesso" in res_add.lower(), f"Resposta inesperada: {res_add!r}"

    res_list = execute_skill("listar_agendamentos", {})
    assert "Rotina de teste" in res_list
