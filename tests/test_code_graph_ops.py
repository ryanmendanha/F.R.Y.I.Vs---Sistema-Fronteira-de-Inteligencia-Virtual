"""
Testes unitários para as novas habilidades de Grafo Arquitetural (Graphify) da F.R.Y.I.Vs.
"""

import pytest
from skills import execute_skill, SKILLS_REGISTRY
from skills.code_graph_ops import (
    consultar_mapa_codigo,
    explicar_modulo_grafo,
    caminho_entre_componentes,
    resumo_arquitetura_sistema,
)


class TestCodeGraphOps:
    """Valida o funcionamento do mapa mental do código e sua integração com a assistente."""

    def test_skills_registered_in_skills_registry(self):
        """Verifica se todas as novas skills estão devidamente registradas no barramento."""
        novas_skills = [
            "consultar_mapa_codigo",
            "explicar_modulo_grafo",
            "caminho_entre_componentes",
            "resumo_arquitetura_sistema",
            "atualizar_mapa_codigo",
        ]
        for skill in novas_skills:
            assert skill in SKILLS_REGISTRY, f"A skill '{skill}' não está registrada em SKILLS_REGISTRY."

    def test_resumo_arquitetura_sistema(self):
        """Testa o resumo macroscópico da arquitetura."""
        resultado = resumo_arquitetura_sistema()
        assert "Arquitetura Geral da F.R.Y.I.Vs" in resultado
        assert "Total de Elementos Mapeados" in resultado
        assert "Núcleos Centrais do Sistema (God Nodes)" in resultado

    def test_consultar_mapa_codigo_termo_existente(self):
        """Testa a consulta por uma função conhecida no grafo (ex: ask_fryvis)."""
        resultado = consultar_mapa_codigo("ask_fryvis")
        assert "Mapa Arquitetural" in resultado
        assert "ask_fryvis" in resultado
        assert "core/llm.py" in resultado

    def test_consultar_mapa_codigo_termo_vazio(self):
        """Testa o comportamento defensivo para consulta vazia."""
        resultado = consultar_mapa_codigo("")
        assert "informe o termo" in resultado.lower()

    def test_explicar_modulo_grafo(self):
        """Testa a explicação detalhada de um módulo ou função."""
        resultado = explicar_modulo_grafo("server")
        assert "Análise do Componente" in resultado
        assert "Conexões Diretas" in resultado

    def test_caminho_entre_componentes(self):
        """Testa a descoberta do caminho entre dois nós do sistema."""
        resultado = caminho_entre_componentes("server", "core_llm_ask_fryvis")
        assert "Rota Arquitetural" in resultado
        assert "Distância estrutural" in resultado

    def test_execute_skill_dispatch(self):
        """Testa o despacho de ponta a ponta via execute_skill."""
        resp = execute_skill("consultar_mapa_codigo", {"termo": "execute_skill"})
        assert isinstance(resp, str)
        assert "execute_skill" in resp
