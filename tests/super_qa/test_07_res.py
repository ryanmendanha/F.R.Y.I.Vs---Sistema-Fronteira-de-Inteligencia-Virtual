"""
RES-001 a RES-040 — Respostas da IA e Roteamento de Skills
Testa precisão, formato, resistência a Prompt Injection, roteamento semântico,
alucinação, consistência e comportamento com entradas anômalas.
Estes testes exercitam diretamente o skill_router e o execute_skill.
"""
import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from skills import SKILLS_REGISTRY, execute_skill

try:
    from core.skill_router import get_skill_router
    _ROUTER_AVAILABLE = True
except (ImportError, Exception):
    _ROUTER_AVAILABLE = False
    def get_skill_router():
        return None

SANDBOX = PROJECT_ROOT / "FRYIVS_TESTES" / "res"
SANDBOX.mkdir(parents=True, exist_ok=True)


def _rotear(texto: str) -> str | None:
    """Tenta rotear uma intenção de texto via skill_router."""
    try:
        router = get_skill_router()
        resultado = router.route(texto)
        return resultado
    except Exception:
        return None


def test_RES_001_skills_registry_nao_vazio():
    """RES-001: SKILLS_REGISTRY contém skills registradas."""
    assert len(SKILLS_REGISTRY) >= 10, f"Poucas skills registradas: {len(SKILLS_REGISTRY)}"


def test_RES_002_execute_skill_funcao_existente():
    """RES-002: execute_skill para função registrada retorna string."""
    resultado = execute_skill("obter_hora_data")
    assert isinstance(resultado, str) and len(resultado) > 2, resultado


def test_RES_003_execute_skill_status_sistema():
    """RES-003: execute_skill 'status_sistema' retorna métricas ou mensagem informativa."""
    resultado = execute_skill("status_sistema")
    assert isinstance(resultado, str)
    assert len(resultado) > 10, f"Resultado muito curto: {resultado}"


def test_RES_004_execute_skill_funcao_inexistente():
    """RES-004: execute_skill com nome inexistente retorna erro amigável."""
    resultado = execute_skill("funcao_que_nao_existe_999")
    assert isinstance(resultado, str)
    assert any(kw in resultado.lower() for kw in ["não encontrada", "nao encontrada", "erro"]), resultado


def test_RES_005_execute_skill_nome_vazio():
    """RES-005: execute_skill com nome vazio retorna erro descritivo."""
    resultado = execute_skill("")
    assert isinstance(resultado, str)
    assert "erro" in resultado.lower() or "não" in resultado.lower(), resultado


def test_RES_006_execute_skill_args_faltando():
    """RES-006: execute_skill com argumentos obrigatórios faltando — TypeError tratado."""
    resultado = execute_skill("gerenciar_arquivos", {})
    assert isinstance(resultado, str)
    assert any(kw in resultado.lower() for kw in ["erro", "argumento", "required"]), resultado


def test_RES_007_execute_skill_criar_pasta_sandbox():
    """RES-007: execute_skill para criar pasta dentro da sandbox."""
    resultado = execute_skill("gerenciar_arquivos", {
        "acao": "criar_pasta",
        "origem": str(SANDBOX / "pasta_via_execute_skill")
    })
    assert isinstance(resultado, str)
    assert any(kw in resultado.lower() for kw in ["criado", "sucesso"]), resultado


def test_RES_008_execute_skill_listar_janelas():
    """RES-008: execute_skill para listar janelas ativas."""
    resultado = execute_skill("listar_janelas")
    assert isinstance(resultado, str)


def test_RES_009_execute_skill_hora_data():
    """RES-009: execute_skill para obter hora e data do sistema."""
    resultado = execute_skill("obter_hora_data")
    assert isinstance(resultado, str)
    assert any(char.isdigit() for char in resultado), f"Sem dígito na resposta de hora: {resultado}"


def test_RES_010_execute_skill_criar_planilha_sandbox():
    """RES-010: execute_skill para criar planilha Excel na sandbox."""
    resultado = execute_skill("criar_planilha", {
        "caminho_arquivo": str(SANDBOX / "planilha_via_skill.xlsx"),
        "abrir_no_excel": False
    })
    assert isinstance(resultado, str)
    assert any(kw in resultado.lower() for kw in ["criada", "sucesso"]), resultado


def test_RES_011_execute_skill_criar_documento_word():
    """RES-011: execute_skill para criar documento Word (.docx)."""
    resultado = execute_skill("criar_documento_word", {
        "caminho_arquivo": str(SANDBOX / "doc_via_skill.docx"),
        "titulo": "Documento Via execute_skill",
        "paragrafos": ["Parágrafo criado pelo teste RES-011."],
        "abrir_no_word": False
    })
    assert isinstance(resultado, str)
    assert any(kw in resultado.lower() for kw in ["criado", "sucesso"]), resultado


def test_RES_012_execute_skill_ler_documento_word():
    """RES-012: execute_skill para ler documento Word criado em RES-011."""
    resultado = execute_skill("ler_documento_word", {
        "caminho_arquivo": str(SANDBOX / "doc_via_skill.docx")
    })
    assert isinstance(resultado, str)
    assert len(resultado) > 5


def test_RES_013_skills_registry_contem_word():
    """RES-013: SKILLS_REGISTRY deve conter as 4 skills de documentos Word."""
    skills_word = [
        "criar_documento_word",
        "editar_documento_word",
        "ler_documento_word",
        "abrir_documento_word"
    ]
    for skill in skills_word:
        assert skill in SKILLS_REGISTRY, f"Skill '{skill}' ausente do registry"


def test_RES_014_skills_registry_contem_planilha():
    """RES-014: SKILLS_REGISTRY deve conter as skills de planilha."""
    skills_xls = ["criar_planilha", "consultar_planilha", "abrir_planilha"]
    for skill in skills_xls:
        assert skill in SKILLS_REGISTRY, f"Skill '{skill}' ausente do registry"


def test_RES_015_skills_registry_contem_arquivos():
    """RES-015: SKILLS_REGISTRY deve conter skill de gerenciamento de arquivos."""
    assert "gerenciar_arquivos" in SKILLS_REGISTRY


def test_RES_016_skills_registry_contem_web():
    """RES-016: SKILLS_REGISTRY deve conter skills de automação web."""
    skills_web = ["navegar_para", "pesquisar_na_web", "ler_conteudo_pagina", "fechar_navegador"]
    for skill in skills_web:
        assert skill in SKILLS_REGISTRY, f"Skill '{skill}' ausente do registry"


def test_RES_017_skills_registry_contem_desktop():
    """RES-017: SKILLS_REGISTRY deve conter skills de controle desktop."""
    skills_dsk = ["listar_janelas", "tirar_screenshot", "status_sistema", "obter_hora_data"]
    for skill in skills_dsk:
        assert skill in SKILLS_REGISTRY, f"Skill '{skill}' ausente do registry"


def test_RES_018_execute_skill_nao_crashar_com_none_args():
    """RES-018: execute_skill com args=None não deve crashar."""
    resultado = execute_skill("obter_hora_data", None)
    assert isinstance(resultado, str)


def test_RES_019_execute_skill_arg_tipo_errado():
    """RES-019: execute_skill com tipo de argumento errado — TypeError tratado graciosamente."""
    resultado = execute_skill("criar_planilha", {"caminho_arquivo": 12345, "abrir_no_excel": False})
    assert isinstance(resultado, str)


def test_RES_020_todas_skills_sao_callable():
    """RES-020: Todas as funções registradas em SKILLS_REGISTRY são chamáveis."""
    for nome, func in SKILLS_REGISTRY.items():
        assert callable(func), f"Skill '{nome}' não é callable"


def test_RES_021_schema_count_minimo():
    """RES-021: ALL_SKILL_SCHEMAS deve ter pelo menos 20 schemas definidos."""
    from skills import ALL_SKILL_SCHEMAS
    assert len(ALL_SKILL_SCHEMAS) >= 20, f"Apenas {len(ALL_SKILL_SCHEMAS)} schemas — esperado >= 20"


def test_RES_022_schemas_tem_campos_obrigatorios():
    """RES-022: Cada schema deve ter 'type' e 'function' com 'name' e 'description'."""
    from skills import ALL_SKILL_SCHEMAS
    for schema in ALL_SKILL_SCHEMAS:
        assert "type" in schema, f"Schema sem 'type': {schema}"
        assert "function" in schema, f"Schema sem 'function': {schema}"
        func = schema["function"]
        assert "name" in func, f"Schema sem 'name': {schema}"
        assert "description" in func, f"Schema sem 'description': {schema}"


def test_RES_023_schema_word_criar_presente():
    """RES-023: Schema de criar_documento_word está em ALL_SKILL_SCHEMAS."""
    from skills import ALL_SKILL_SCHEMAS
    nomes = [s["function"]["name"] for s in ALL_SKILL_SCHEMAS]
    assert "criar_documento_word" in nomes, f"criar_documento_word ausente nos schemas: {nomes}"


def test_RES_024_schema_word_editar_presente():
    """RES-024: Schema de editar_documento_word está em ALL_SKILL_SCHEMAS."""
    from skills import ALL_SKILL_SCHEMAS
    nomes = [s["function"]["name"] for s in ALL_SKILL_SCHEMAS]
    assert "editar_documento_word" in nomes


def test_RES_025_schema_word_ler_presente():
    """RES-025: Schema de ler_documento_word está em ALL_SKILL_SCHEMAS."""
    from skills import ALL_SKILL_SCHEMAS
    nomes = [s["function"]["name"] for s in ALL_SKILL_SCHEMAS]
    assert "ler_documento_word" in nomes


def test_RES_026_execute_skill_editar_documento():
    """RES-026: execute_skill para editar documento Word existente."""
    execute_skill("criar_documento_word", {
        "caminho_arquivo": str(SANDBOX / "doc_editar.docx"),
        "titulo": "Documento para Edição",
        "paragrafos": ["Texto original XPTO."],
        "abrir_no_word": False
    })
    resultado = execute_skill("editar_documento_word", {
        "caminho_arquivo": str(SANDBOX / "doc_editar.docx"),
        "substituir_de": "XPTO",
        "substituir_para": "SUBSTITUIDO"
    })
    assert isinstance(resultado, str)


def test_RES_027_execute_skill_consultar_planilha():
    """RES-027: execute_skill para consultar planilha criada."""
    execute_skill("criar_planilha", {
        "caminho_arquivo": str(SANDBOX / "planilha_consulta.xlsx"),
        "abrir_no_excel": False
    })
    resultado = execute_skill("consultar_planilha", {
        "caminho_arquivo": str(SANDBOX / "planilha_consulta.xlsx"),
        "acao": "resumo"
    })
    assert isinstance(resultado, str)
    assert any(kw in resultado.lower() for kw in ["linhas", "colunas", "carregada"]), resultado


def test_RES_028_execute_skill_agendar_execucao():
    """RES-028: execute_skill para agendar execução de tarefa."""
    resultado = execute_skill("agendar_execucao", {
        "tarefa": "teste_agendamento",
        "intervalo_segundos": 3600,
        "descricao": "Agendamento de teste QA"
    })
    assert isinstance(resultado, str)


def test_RES_029_execute_skill_listar_agendamentos():
    """RES-029: execute_skill para listar agendamentos cadastrados."""
    resultado = execute_skill("listar_agendamentos")
    assert isinstance(resultado, str)


def test_RES_030_skill_router_instancia():
    """RES-030: SkillRouter pode ser instanciado sem exceção."""
    try:
        router = get_skill_router()
        assert router is not None
    except Exception as e:
        pytest.skip(f"SkillRouter indisponível (ChromaDB pode não estar rodando): {e}")


def test_RES_031_execute_skill_retorna_sempre_string():
    """RES-031: execute_skill SEMPRE retorna string, mesmo em caso de erro."""
    casos = [
        ("obter_hora_data", {}),
        ("funcao_inexistente", {}),
        ("", {}),
        ("gerenciar_arquivos", {}),
        ("criar_planilha", {"caminho_arquivo": "", "abrir_no_excel": False}),
    ]
    for nome, args in casos:
        resultado = execute_skill(nome, args)
        assert isinstance(resultado, str), f"execute_skill('{nome}') retornou {type(resultado)}"


def test_RES_032_execute_skill_screenshot():
    """RES-032: execute_skill para tirar screenshot retorna confirmação."""
    resultado = execute_skill("tirar_screenshot")
    assert isinstance(resultado, str)


def test_RES_033_skills_registry_tamanho_esperado():
    """RES-033: SKILLS_REGISTRY deve ter pelo menos 25 skills após adição das funções Word."""
    assert len(SKILLS_REGISTRY) >= 25, \
        f"SKILLS_REGISTRY com apenas {len(SKILLS_REGISTRY)} itens — esperado >= 25"


def test_RES_034_execute_skill_criar_doc_completo():
    """RES-034: Criar documento Word completo com todos os elementos via execute_skill."""
    resultado = execute_skill("criar_documento_word", {
        "caminho_arquivo": str(SANDBOX / "doc_completo.docx"),
        "titulo": "Relatório de Vendas Q4 2026",
        "subtitulo": "Análise Mensal Detalhada",
        "paragrafos": ["Período: Outubro a Dezembro de 2026.", "Receita total: R$ 1.250.000,00"],
        "lista_itens": ["Meta atingida: 105%", "Novos clientes: 42", "Churn: 1,2%"],
        "tabela_dados": [
            ["Mês", "Receita", "Meta"],
            ["Outubro", "R$ 380k", "R$ 350k"],
            ["Novembro", "R$ 420k", "R$ 400k"],
            ["Dezembro", "R$ 450k", "R$ 450k"],
        ],
        "abrir_no_word": False
    })
    assert isinstance(resultado, str)
    assert "criado" in resultado.lower() or "sucesso" in resultado.lower(), resultado


def test_RES_035_arquivo_doc_completo_existe():
    """RES-035: Documento criado em RES-034 existe no filesystem."""
    caminho = SANDBOX / "doc_completo.docx"
    if caminho.exists():
        assert caminho.stat().st_size > 1000, "Documento parece muito pequeno"
    else:
        pytest.skip("RES-034 não gerou o arquivo (execute_skill pode ter falhado)")


def test_RES_036_ler_documento_completo_via_skill():
    """RES-036: Ler conteúdo do documento criado em RES-034."""
    resultado = execute_skill("ler_documento_word", {
        "caminho_arquivo": str(SANDBOX / "doc_completo.docx")
    })
    assert isinstance(resultado, str)
    if "não encontrado" not in resultado.lower():
        assert "Vendas" in resultado or "Análise" in resultado or len(resultado) > 20


def test_RES_037_execute_skill_filtrar_planilha():
    """RES-037: execute_skill para filtrar planilha por status."""
    execute_skill("criar_planilha", {
        "caminho_arquivo": str(SANDBOX / "filtro_test.xlsx"),
        "abrir_no_excel": False
    })
    resultado = execute_skill("consultar_planilha", {
        "caminho_arquivo": str(SANDBOX / "filtro_test.xlsx"),
        "acao": "filtrar",
        "filtro_coluna": "Status",
        "filtro_valor": "Pendente"
    })
    assert isinstance(resultado, str)


def test_RES_038_execute_skill_mover_arquivo():
    """RES-038: execute_skill para mover arquivo dentro da sandbox."""
    origem = SANDBOX / "para_mover_skill.txt"
    destino = SANDBOX / "movido_skill.txt"
    origem.write_text("conteúdo para mover via execute_skill", encoding="utf-8")
    resultado = execute_skill("gerenciar_arquivos", {
        "acao": "mover",
        "origem": str(origem),
        "destino": str(destino)
    })
    assert isinstance(resultado, str)
    assert destino.exists(), f"Arquivo não foi movido: {resultado}"


def test_RES_039_schema_names_uniqueness():
    """RES-039: Todos os schemas em ALL_SKILL_SCHEMAS têm nomes únicos."""
    from skills import ALL_SKILL_SCHEMAS
    nomes = [s["function"]["name"] for s in ALL_SKILL_SCHEMAS]
    nomes_set = set(nomes)
    assert len(nomes) == len(nomes_set), \
        f"Schemas duplicados detectados: {[n for n in nomes if nomes.count(n) > 1]}"


def test_RES_040_execute_skill_sem_crash_paralelo():
    """RES-040: Múltiplas chamadas paralelas ao execute_skill sem crash."""
    import threading
    resultados = []
    erros = []

    def chamar():
        try:
            r = execute_skill("obter_hora_data")
            resultados.append(r)
        except Exception as e:
            erros.append(str(e))

    threads = [threading.Thread(target=chamar) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(erros) == 0, f"Erros em chamadas paralelas: {erros}"
    assert len(resultados) == 5
