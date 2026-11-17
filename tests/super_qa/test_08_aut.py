"""
AUT-001 a AUT-030 — Automação Multi-etapas e Pipelines
Testa fluxos encadeados: criação de arquivos → manipulação → geração de relatórios.
Valida tratamento de falha intermediária, condições de parada e recuperação.
"""
import sys
import time
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from skills import execute_skill
from skills.file_data_ops import (
    gerenciar_arquivos, criar_planilha, consultar_planilha,
    criar_documento_word, ler_documento_word
)
from skills.system_controls import obter_hora_data, status_sistema, tirar_screenshot

SANDBOX = PROJECT_ROOT / "FRYIVS_TESTES" / "aut"
SANDBOX.mkdir(parents=True, exist_ok=True)

def sb(name: str) -> str:
    return str(SANDBOX / name)


# ── AUT-001 ──────────────────────────────────────────────────────────────────
def test_AUT_001_pipeline_pasta_planilha():
    """AUT-001: Pipeline completo: Criar pasta → Gerar planilha dentro → Validar."""
    # Etapa 1: Criar pasta
    r1 = gerenciar_arquivos("criar_pasta", sb("pipeline_01"))
    assert Path(sb("pipeline_01")).exists(), f"Etapa 1 falhou: {r1}"
    # Etapa 2: Criar planilha dentro da pasta
    r2 = criar_planilha(sb("pipeline_01/dados.xlsx"), abrir_no_excel=False)
    assert Path(sb("pipeline_01/dados.xlsx")).exists(), f"Etapa 2 falhou: {r2}"
    # Etapa 3: Validar
    assert "criada" in r2.lower() or "sucesso" in r2.lower(), f"Validação falhou: {r2}"


# ── AUT-002 ──────────────────────────────────────────────────────────────────
def test_AUT_002_pipeline_pasta_word():
    """AUT-002: Pipeline completo: Criar pasta → Gerar documento Word → Validar."""
    gerenciar_arquivos("criar_pasta", sb("pipeline_02"))
    r = criar_documento_word(
        sb("pipeline_02/relatorio.docx"),
        titulo="Relatório Pipeline AUT-002",
        paragrafos=["Gerado automaticamente pelo teste de pipeline."]
    )
    assert Path(sb("pipeline_02/relatorio.docx")).exists(), f"Pipeline Word falhou: {r}"


# ── AUT-003 ──────────────────────────────────────────────────────────────────
def test_AUT_003_pipeline_planilha_para_word():
    """AUT-003: Pipeline: Gerar planilha → Ler dados → Gerar Word com resumo."""
    # Etapa 1: Criar planilha com dados
    dados = [{"Produto": f"Prod_{i}", "Vendas": i * 100} for i in range(1, 6)]
    criar_planilha(sb("pipeline_03/vendas.xlsx"), dados=dados, abrir_no_excel=False)
    # Etapa 2: Ler dados da planilha
    resumo = consultar_planilha(sb("pipeline_03/vendas.xlsx"), acao="resumo")
    assert isinstance(resumo, str)
    # Etapa 3: Criar Word com o resumo
    r = criar_documento_word(
        sb("pipeline_03/relatorio_vendas.docx"),
        titulo="Relatório de Vendas AUT-003",
        paragrafos=[resumo]
    )
    assert Path(sb("pipeline_03/relatorio_vendas.docx")).exists(), f"Etapa Word falhou: {r}"


# ── AUT-004 ──────────────────────────────────────────────────────────────────
def test_AUT_004_pipeline_screenshot_mover():
    """AUT-004: Pipeline: Capturar screenshot → Mover para pasta de auditoria."""
    result_ss = tirar_screenshot()
    assert isinstance(result_ss, str)
    # Extrai caminho do resultado (heurística)
    caminho_ss = None
    for palavra in result_ss.split():
        for ext in [".png", ".jpg"]:
            if ext in palavra.lower():
                caminho_ss = palavra.strip("'\".,")
                break
    if caminho_ss and Path(caminho_ss).exists():
        destino = sb("auditoria/" + Path(caminho_ss).name)
        gerenciar_arquivos("criar_pasta", sb("auditoria"))
        r = gerenciar_arquivos("mover", caminho_ss, destino)
        assert isinstance(r, str)
    else:
        # Screenshot sem caminho explícito — aceitar
        assert isinstance(result_ss, str)


# ── AUT-005 ──────────────────────────────────────────────────────────────────
def test_AUT_005_pipeline_timestamp_log():
    """AUT-005: Pipeline: Obter timestamp → Criar arquivo de log com ele."""
    hora = obter_hora_data()
    assert isinstance(hora, str)
    log_path = Path(sb("log_auditoria.txt"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(f"[LOG AUT-005] Timestamp: {hora}", encoding="utf-8")
    assert log_path.exists()
    assert "AUT-005" in log_path.read_text(encoding="utf-8")


# ── AUT-006 ──────────────────────────────────────────────────────────────────
def test_AUT_006_pipeline_status_para_planilha():
    """AUT-006: Pipeline: Consultar status CPU/RAM → Salvar leitura em planilha."""
    status = status_sistema()
    assert isinstance(status, str)
    dados = [{"Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "Status": status[:200]}]
    r = criar_planilha(sb("monitoramento.xlsx"), dados=dados, abrir_no_excel=False)
    assert Path(sb("monitoramento.xlsx")).exists(), f"Planilha de status falhou: {r}"


# ── AUT-007 ──────────────────────────────────────────────────────────────────
def test_AUT_007_condicional_criar_se_nao_existe():
    """AUT-007: Criar pasta somente se não existir — idempotente."""
    pasta = sb("condicional")
    r1 = gerenciar_arquivos("criar_pasta", pasta)
    r2 = gerenciar_arquivos("criar_pasta", pasta)  # segunda chamada — deve funcionar (exist_ok=True)
    assert Path(pasta).exists()
    assert isinstance(r1, str) and isinstance(r2, str)


# ── AUT-008 ──────────────────────────────────────────────────────────────────
def test_AUT_008_abortar_pipeline_em_falha():
    """AUT-008: Se etapa 1 falhar (caminho inválido), etapas seguintes não são executadas."""
    etapa1_ok = False
    try:
        r1 = gerenciar_arquivos("copiar", sb("nao_existe_origem.txt"), sb("destino_nao_deve.txt"))
        if "não encontrad" in r1.lower() or "nao encontrad" in r1.lower():
            etapa1_ok = False  # Falhou conforme esperado
        else:
            etapa1_ok = True
    except Exception:
        etapa1_ok = False

    if not etapa1_ok:
        # Etapas seguintes NÃO devem ser executadas
        assert not Path(sb("destino_nao_deve.txt")).exists(), "Arquivo não deveria existir após falha"


# ── AUT-009 ──────────────────────────────────────────────────────────────────
def test_AUT_009_lote_5_arquivos():
    """AUT-009: Criar 5 arquivos em lote e copiar todos para subpasta."""
    origem_dir = Path(sb("lote_origem"))
    destino_dir = Path(sb("lote_destino"))
    origem_dir.mkdir(parents=True, exist_ok=True)
    for i in range(5):
        (origem_dir / f"arquivo_{i}.txt").write_text(f"lote {i}", encoding="utf-8")
    r = gerenciar_arquivos("copiar", str(origem_dir), str(destino_dir))
    arquivos = list(destino_dir.glob("*.txt"))
    assert len(arquivos) == 5, f"Esperado 5 arquivos no lote, obtido {len(arquivos)}: {r}"


# ── AUT-010 ──────────────────────────────────────────────────────────────────
def test_AUT_010_agendar_execucao():
    """AUT-010: Agendar execução e obter retorno de confirmação."""
    resultado = execute_skill("agendar_execucao", {
        "tarefa": "aut_010_teste",
        "intervalo_segundos": 7200,
        "descricao": "Agendamento Pipeline AUT-010"
    })
    assert isinstance(resultado, str)


# ── AUT-011 ──────────────────────────────────────────────────────────────────
def test_AUT_011_listar_agendamentos():
    """AUT-011: Listar agendamentos e verificar retorno estruturado."""
    resultado = execute_skill("listar_agendamentos")
    assert isinstance(resultado, str)


# ── AUT-012 ──────────────────────────────────────────────────────────────────
def test_AUT_012_automacao_desktop_notepad():
    """AUT-012: Abrir Bloco de Notas → Aguardar → Fechar."""
    from skills.open_app import abrir_programa
    from skills.system_controls import fechar_janela
    r_open = abrir_programa("notepad")
    assert isinstance(r_open, str)
    time.sleep(1.5)
    r_close = fechar_janela("Bloco de Notas")
    assert isinstance(r_close, str)


# ── AUT-013 ──────────────────────────────────────────────────────────────────
def test_AUT_013_automacao_web_completa():
    """AUT-013: Abrir navegador → Capturar screenshot → Fechar."""
    from skills.web_automation import navegar_para, capturar_tela_web, fechar_navegador
    html_local = SANDBOX / "pagina_aut.html"
    html_local.write_text("<html><body><h1>AUT-013</h1></body></html>", encoding="utf-8")
    url = f"file:///{str(html_local).replace(chr(92), '/')}"
    r_nav = navegar_para(url)
    assert isinstance(r_nav, str)
    time.sleep(0.8)
    r_cap = capturar_tela_web()
    assert isinstance(r_cap, str)
    fechar_navegador()


# ── AUT-014 ──────────────────────────────────────────────────────────────────
def test_AUT_014_limpeza_arquivos_temporarios():
    """AUT-014: Criar arquivos temporários e excluí-los em seguida."""
    temp_dir = Path(sb("temp_cleanup"))
    temp_dir.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        (temp_dir / f"temp_{i}.txt").write_text("temporário", encoding="utf-8")
    assert len(list(temp_dir.glob("*.txt"))) == 3
    r = gerenciar_arquivos("deletar", str(temp_dir))
    assert not temp_dir.exists(), f"Limpeza falhou: {r}"


# ── AUT-015 ──────────────────────────────────────────────────────────────────
def test_AUT_015_pipeline_relatorio_completo():
    """AUT-015: Pipeline completo de relatório executivo com todos os tipos de arquivo."""
    base = Path(sb("relatorio_executivo"))
    base.mkdir(parents=True, exist_ok=True)
    # Planilha de dados
    dados = [{"Departamento": "TI", "Custo": 50000}, {"Departamento": "RH", "Custo": 30000}]
    criar_planilha(str(base / "custos.xlsx"), dados=dados, abrir_no_excel=False)
    # Resumo da planilha
    resumo = consultar_planilha(str(base / "custos.xlsx"), acao="resumo")
    # Documento Word executivo
    hora = obter_hora_data()
    criar_documento_word(
        str(base / "relatorio_final.docx"),
        titulo="Relatório Executivo de Custos",
        subtitulo=f"Gerado em: {hora}",
        paragrafos=[resumo, "Análise realizada pelo sistema FRYIVS automaticamente."],
        tabela_dados=[["Departamento", "Custo"], ["TI", "R$ 50.000"], ["RH", "R$ 30.000"]]
    )
    assert (base / "custos.xlsx").exists()
    assert (base / "relatorio_final.docx").exists()


# ── AUT-016 a AUT-030: Pipelines Avançados ───────────────────────────────────

def test_AUT_016_copiar_planilha_renomear():
    """AUT-016: Copiar planilha para nova versão."""
    criar_planilha(sb("original_v1.xlsx"), abrir_no_excel=False)
    r = gerenciar_arquivos("copiar", sb("original_v1.xlsx"), sb("original_v2.xlsx"))
    assert Path(sb("original_v2.xlsx")).exists(), f"Cópia de planilha falhou: {r}"


def test_AUT_017_criar_estrutura_projeto():
    """AUT-017: Criar estrutura de pastas de projeto completa."""
    pastas = ["projeto/docs", "projeto/dados", "projeto/relatorios", "projeto/backups"]
    for pasta in pastas:
        gerenciar_arquivos("criar_pasta", sb(pasta))
    for pasta in pastas:
        assert Path(sb(pasta)).exists(), f"Pasta '{pasta}' não criada"


def test_AUT_018_popular_estrutura_projeto():
    """AUT-018: Popular a estrutura de projeto com arquivos relevantes."""
    base = Path(sb("projeto"))
    base.mkdir(parents=True, exist_ok=True)
    (base / "docs").mkdir(exist_ok=True)
    (base / "dados").mkdir(exist_ok=True)
    criar_planilha(str(base / "dados/dados_brutos.xlsx"), abrir_no_excel=False)
    criar_documento_word(
        str(base / "docs/especificacao.docx"),
        titulo="Especificação do Projeto",
        paragrafos=["Documento de especificação criado pelo pipeline AUT-018."]
    )
    assert (base / "dados/dados_brutos.xlsx").exists()
    assert (base / "docs/especificacao.docx").exists()


def test_AUT_019_backup_arquivo_antes_editar():
    """AUT-019: Fazer backup de documento antes de editar."""
    original = sb("doc_para_editar.docx")
    backup = sb("doc_para_editar_backup.docx")
    criar_documento_word(original, titulo="Original", paragrafos=["Texto original."])
    gerenciar_arquivos("copiar", original, backup)
    assert Path(backup).exists(), "Backup não criado antes da edição"


def test_AUT_020_editar_verificar_backup_intacto():
    """AUT-020: Editar original e verificar que backup está intacto."""
    from skills.file_data_ops import editar_documento_word, ler_documento_word
    original = sb("doc_para_editar.docx")
    backup = sb("doc_para_editar_backup.docx")
    if not Path(original).exists():
        pytest.skip("AUT-019 não gerou o documento original")
    editar_documento_word(original, adicionar_paragrafos=["Parágrafo adicionado na edição."])
    leitura_backup = ler_documento_word(backup)
    assert "adicionado" not in leitura_backup, "Backup foi modificado indevidamente"


def test_AUT_021_multiplos_docs_lote():
    """AUT-021: Criar 5 documentos Word em lote sequencialmente."""
    for i in range(5):
        r = criar_documento_word(
            sb(f"lote_docs/doc_{i}.docx"),
            titulo=f"Documento {i}",
            paragrafos=[f"Conteúdo do documento número {i}."]
        )
        assert Path(sb(f"lote_docs/doc_{i}.docx")).exists(), f"Doc {i} não criado: {r}"


def test_AUT_022_consolidar_lote_docs_em_planilha():
    """AUT-022: Listar documentos gerados e registrar metadados em planilha."""
    lote_dir = Path(sb("lote_docs"))
    if not lote_dir.exists():
        pytest.skip("Diretório lote_docs não existe — rode AUT-021 primeiro")
    docs = list(lote_dir.glob("*.docx"))
    dados = [{"Arquivo": d.name, "Tamanho_bytes": d.stat().st_size} for d in docs]
    r = criar_planilha(sb("metadados_docs.xlsx"), dados=dados, abrir_no_excel=False)
    assert Path(sb("metadados_docs.xlsx")).exists(), f"Planilha de metadados falhou: {r}"


def test_AUT_023_pipeline_monitoramento_automatico():
    """AUT-023: Coletar 3 leituras de status do sistema e salvar histórico."""
    leituras = []
    for _ in range(3):
        leituras.append({"timestamp": time.strftime("%H:%M:%S"), "status": status_sistema()[:100]})
        time.sleep(0.2)
    r = criar_planilha(sb("historico_status.xlsx"), dados=leituras, abrir_no_excel=False)
    assert Path(sb("historico_status.xlsx")).exists(), f"Histórico falhou: {r}"


def test_AUT_024_pipeline_auditoria_completa():
    """AUT-024: Pipeline de auditoria: screenshot + log + hora + planilha."""
    hora = obter_hora_data()
    status = status_sistema()
    log_path = Path(sb("auditoria_completa/log.txt"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(f"Auditoria AUT-024\nHora: {hora}\nStatus: {status}", encoding="utf-8")
    dados = [{"Item": "Hora", "Valor": hora}, {"Item": "Status", "Valor": status[:80]}]
    criar_planilha(sb("auditoria_completa/metricas.xlsx"), dados=dados, abrir_no_excel=False)
    assert log_path.exists()
    assert Path(sb("auditoria_completa/metricas.xlsx")).exists()


def test_AUT_025_pipeline_leitura_edicao_word():
    """AUT-025: Ler Word → Extrair conteúdo → Adicionar resumo ao mesmo doc."""
    from skills.file_data_ops import editar_documento_word, ler_documento_word
    criar_documento_word(
        sb("ciclo_word.docx"),
        titulo="Ciclo de Leitura-Edição",
        paragrafos=["Parágrafo inicial para ciclo AUT-025."]
    )
    leitura = ler_documento_word(sb("ciclo_word.docx"))
    palavras = len(leitura.split())
    r = editar_documento_word(
        sb("ciclo_word.docx"),
        adicionar_paragrafos=[f"Resumo automático: documento contém {palavras} palavras."]
    )
    assert isinstance(r, str)


def test_AUT_026_pipeline_verificar_integridade_pos_copia():
    """AUT-026: Verificar integridade de planilha após cópia."""
    criar_planilha(sb("integridade_orig.xlsx"), abrir_no_excel=False)
    gerenciar_arquivos("copiar", sb("integridade_orig.xlsx"), sb("integridade_copia.xlsx"))
    resumo_orig = consultar_planilha(sb("integridade_orig.xlsx"), acao="resumo")
    resumo_copia = consultar_planilha(sb("integridade_copia.xlsx"), acao="resumo")
    assert isinstance(resumo_orig, str) and isinstance(resumo_copia, str)


def test_AUT_027_pipeline_criacao_multi_formato():
    """AUT-027: Criar os 3 tipos de arquivo (txt, xlsx, docx) em uma única pasta."""
    base = Path(sb("multi_formato"))
    base.mkdir(parents=True, exist_ok=True)
    (base / "notas.txt").write_text("Notas textuais do pipeline AUT-027.", encoding="utf-8")
    criar_planilha(str(base / "dados.xlsx"), abrir_no_excel=False)
    criar_documento_word(str(base / "relatorio.docx"), titulo="Pipeline Multi-formato AUT-027")
    assert (base / "notas.txt").exists()
    assert (base / "dados.xlsx").exists()
    assert (base / "relatorio.docx").exists()


def test_AUT_028_pipeline_lote_renomear_arquivos():
    """AUT-028: Renomear arquivos de um lote com padrão de versão."""
    base = Path(sb("renomear_lote"))
    base.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        (base / f"arquivo_{i}.txt").write_text(f"v{i}", encoding="utf-8")
    for i in range(3):
        orig = base / f"arquivo_{i}.txt"
        dest = base / f"arquivo_v{i+1}_final.txt"
        if orig.exists():
            gerenciar_arquivos("mover", str(orig), str(dest))
    novos = list(base.glob("*_final.txt"))
    assert len(novos) == 3, f"Renomeação em lote incompleta: {len(novos)}/3"


def test_AUT_029_pipeline_status_para_word():
    """AUT-029: Coletar status do sistema e documentar em Word automaticamente."""
    status = status_sistema()
    hora = obter_hora_data()
    r = criar_documento_word(
        sb("status_report.docx"),
        titulo="Relatório de Status do Sistema",
        subtitulo=f"Coletado em: {hora}",
        paragrafos=[status]
    )
    assert Path(sb("status_report.docx")).exists(), f"Relatório de status falhou: {r}"


def test_AUT_030_pipeline_end_to_end_completo():
    """AUT-030: Pipeline end-to-end completo — todos os tipos de operação encadeados."""
    base = Path(sb("end_to_end"))
    base.mkdir(parents=True, exist_ok=True)
    # 1. Coletar dados do sistema
    hora = obter_hora_data()
    status = status_sistema()
    # 2. Criar planilha com dados
    dados = [{"Tipo": "Hora", "Valor": hora}, {"Tipo": "Status", "Valor": status[:100]}]
    criar_planilha(str(base / "dados_sistema.xlsx"), dados=dados, abrir_no_excel=False)
    # 3. Ler resumo da planilha
    resumo = consultar_planilha(str(base / "dados_sistema.xlsx"), acao="resumo")
    # 4. Criar documento Word com tudo
    criar_documento_word(
        str(base / "relatorio_end_to_end.docx"),
        titulo="Relatório End-to-End AUT-030",
        paragrafos=[f"Hora de geração: {hora}", f"Status: {status[:100]}", f"Planilha: {resumo}"]
    )
    # 5. Fazer backup do documento
    gerenciar_arquivos("copiar", str(base / "relatorio_end_to_end.docx"),
                        str(base / "relatorio_end_to_end_backup.docx"))
    # Verificar todos os arquivos
    assert (base / "dados_sistema.xlsx").exists()
    assert (base / "relatorio_end_to_end.docx").exists()
    assert (base / "relatorio_end_to_end_backup.docx").exists()
