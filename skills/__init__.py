"""
Ponto central de registro e despacho de Skills para a assistente F.R.Y.I.Vs.
Implementa tipagem estrita (Python 3.12+), mapeamento de funções e despacho resiliente.
"""

from __future__ import annotations

from typing import Any, Callable, Final
from .open_app import abrir_programa, SKILL_SCHEMA as SKILL_SCHEMA_OPEN_APP
from .system_controls import (
    listar_janelas,
    focar_janela,
    minimizar_janela,
    maximizar_janela,
    fechar_janela,
    digitar_texto,
    pressionar_atalho,
    controlar_volume,
    tirar_screenshot,
    obter_hora_data,
    pesquisar_google,
    pesquisar_informacao_web,
    pesquisar_youtube,
    status_sistema,
    bloquear_tela,
    SYSTEM_TOOLS_SCHEMAS,
)
from .web_automation import (
    navegar_para,
    pesquisar_na_web,
    clicar_elemento_web,
    interagir_pagina_web,
    digitar_campo_web,
    ler_conteudo_pagina,
    capturar_tela_web,
    fechar_navegador,
    WEB_TOOLS_SCHEMAS,
)
from .visual_ocr import (
    localizar_e_clicar_imagem,
    ler_texto_da_tela,
    VISUAL_OCR_SCHEMAS,
)
from .file_data_ops import (
    gerenciar_arquivos,
    consultar_planilha,
    criar_planilha,
    abrir_planilha,
    editar_planilha,
    FILE_DATA_SCHEMAS,
    criar_documento_word,
    editar_documento_word,
    ler_documento_word,
    abrir_documento_word,
    WORD_DOC_SCHEMAS,
)
from .scheduler_ops import (
    agendar_execucao,
    listar_agendamentos,
    enviar_alerta_webhook,
    SCHEDULER_SCHEMAS,
)
from .code_graph_ops import (
    consultar_mapa_codigo,
    explicar_modulo_grafo,
    caminho_entre_componentes,
    resumo_arquitetura_sistema,
    atualizar_mapa_codigo,
    CODE_GRAPH_SCHEMAS,
)
from .n8n_ops import (
    disparar_workflow_n8n,
    listar_workflows_n8n,
    consultar_execucoes_n8n,
    N8N_SCHEMAS,
)
from .hermes_ops import (
    delegar_missao_hermes,
    consultar_status_agentes,
    cancelar_missao_agente,
    listar_perfis_hermes,
    HERMES_SCHEMAS,
)

SKILLS_REGISTRY: Final[dict[str, Callable[..., str]]] = {
    "abrir_programa": abrir_programa,
    "listar_janelas": listar_janelas,
    "focar_janela": focar_janela,
    "minimizar_janela": minimizar_janela,
    "maximizar_janela": maximizar_janela,
    "fechar_janela": fechar_janela,
    "digitar_texto": digitar_texto,
    "pressionar_atalho": pressionar_atalho,
    "controlar_volume": controlar_volume,
    "tirar_screenshot": tirar_screenshot,
    "obter_hora_data": obter_hora_data,
    "pesquisar_google": pesquisar_google,
    "pesquisar_informacao_web": pesquisar_informacao_web,
    "pesquisar_youtube": pesquisar_youtube,
    "status_sistema": status_sistema,
    "bloquear_tela": bloquear_tela,
    "navegar_para": navegar_para,
    "pesquisar_na_web": pesquisar_na_web,
    "clicar_elemento_web": clicar_elemento_web,
    "interagir_pagina_web": interagir_pagina_web,
    "digitar_campo_web": digitar_campo_web,
    "ler_conteudo_pagina": ler_conteudo_pagina,
    "capturar_tela_web": capturar_tela_web,
    "fechar_navegador": fechar_navegador,
    "localizar_e_clicar_imagem": localizar_e_clicar_imagem,
    "ler_texto_da_tela": ler_texto_da_tela,
    "gerenciar_arquivos": gerenciar_arquivos,
    "consultar_planilha": consultar_planilha,
    "criar_planilha": criar_planilha,
    "abrir_planilha": abrir_planilha,
    "editar_planilha": editar_planilha,
    "criar_documento_word": criar_documento_word,
    "editar_documento_word": editar_documento_word,
    "ler_documento_word": ler_documento_word,
    "abrir_documento_word": abrir_documento_word,
    "agendar_execucao": agendar_execucao,
    "listar_agendamentos": listar_agendamentos,
    "enviar_alerta_webhook": enviar_alerta_webhook,
    "consultar_mapa_codigo": consultar_mapa_codigo,
    "explicar_modulo_grafo": explicar_modulo_grafo,
    "caminho_entre_componentes": caminho_entre_componentes,
    "resumo_arquitetura_sistema": resumo_arquitetura_sistema,
    "atualizar_mapa_codigo": atualizar_mapa_codigo,
    "disparar_workflow_n8n": disparar_workflow_n8n,
    "listar_workflows_n8n": listar_workflows_n8n,
    "consultar_execucoes_n8n": consultar_execucoes_n8n,
    "delegar_missao_hermes": delegar_missao_hermes,
    "consultar_status_agentes": consultar_status_agentes,
    "cancelar_missao_agente": cancelar_missao_agente,
    "listar_perfis_hermes": listar_perfis_hermes,
}

ALL_SKILL_SCHEMAS: Final[list[dict[str, Any]]] = [
    SKILL_SCHEMA_OPEN_APP,
    *SYSTEM_TOOLS_SCHEMAS,
    *WEB_TOOLS_SCHEMAS,
    *VISUAL_OCR_SCHEMAS,
    *FILE_DATA_SCHEMAS,
    *WORD_DOC_SCHEMAS,
    *SCHEDULER_SCHEMAS,
    *CODE_GRAPH_SCHEMAS,
    *N8N_SCHEMAS,
    *HERMES_SCHEMAS,
]


def execute_skill(function_name: str, arguments: dict[str, Any] | None = None) -> str:
    """
    Executa uma skill registrada pelo nome com validação defensiva de argumentos.
    Retorna sempre uma string informativa com o resultado ou o erro capturado.
    """
    from core.command_control import check_cancelled
    check_cancelled()

    if not function_name:
        return "Erro: Nome da skill não especificado."

    if function_name not in SKILLS_REGISTRY:
        return f"Erro: Skill '{function_name}' não encontrada no registro de habilidades."

    func = SKILLS_REGISTRY[function_name]
    args = arguments or {}

    try:
        from core.overlay import status_overlay
        detalhe = next((str(v) for v in args.values() if isinstance(v, str) and v.strip()), "")
        status_overlay(f"{function_name.replace('_', ' ').capitalize()}" + (f": {detalhe}" if detalhe else ""))
    except Exception:
        pass

    try:
        if not args:
            return str(func())
        return str(func(**args))
    except TypeError as te:
        return f"Erro nos argumentos para a skill '{function_name}': {te}"
    except Exception as e:
        return f"Erro ao executar a skill '{function_name}': {e}"
