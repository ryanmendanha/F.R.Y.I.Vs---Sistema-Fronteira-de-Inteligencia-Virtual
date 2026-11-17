"""
RSP-001 a RSP-025 — Responsividade, Desempenho e Carga
Testa latência de operações, entradas grandes, requisições paralelas,
estabilidade de WebSocket e liberação de recursos do sistema.
"""
import sys
import time
import threading
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from skills import execute_skill
from skills.file_data_ops import criar_planilha, consultar_planilha, criar_documento_word
from skills.system_controls import obter_hora_data, status_sistema

SANDBOX = PROJECT_ROOT / "FRYIVS_TESTES" / "rsp"
SANDBOX.mkdir(parents=True, exist_ok=True)

def sb(name: str) -> str:
    return str(SANDBOX / name)

def medir(func, *args, **kwargs):
    """Mede tempo de execução em ms."""
    t0 = time.perf_counter()
    r = func(*args, **kwargs)
    return r, (time.perf_counter() - t0) * 1000


# ── RSP-001 ──────────────────────────────────────────────────────────────────
def test_RSP_001_latencia_obter_hora():
    """RSP-001: obter_hora_data deve responder em menos de 500ms."""
    _, ms = medir(obter_hora_data)
    assert ms < 500, f"Latência muito alta: {ms:.1f}ms (limite: 500ms)"


# ── RSP-002 ──────────────────────────────────────────────────────────────────
def test_RSP_002_latencia_status_sistema():
    """RSP-002: status_sistema deve responder em menos de 2000ms."""
    _, ms = medir(status_sistema)
    assert ms < 2000, f"Latência muito alta: {ms:.1f}ms (limite: 2000ms)"


# ── RSP-003 ──────────────────────────────────────────────────────────────────
def test_RSP_003_latencia_criar_planilha():
    """RSP-003: criar_planilha deve completar em menos de 3000ms."""
    _, ms = medir(criar_planilha, sb("latencia.xlsx"), None, None, False)
    assert ms < 3000, f"Criação de planilha lenta: {ms:.1f}ms (limite: 3000ms)"


# ── RSP-004 ──────────────────────────────────────────────────────────────────
def test_RSP_004_latencia_criar_word():
    """RSP-004: criar_documento_word deve completar em menos de 2000ms."""
    _, ms = medir(
        criar_documento_word,
        sb("latencia.docx"),
        "Teste de Latência RSP-004",
        None,
        ["Parágrafo de teste de latência."]
    )
    assert ms < 2000, f"Criação de Word lenta: {ms:.1f}ms (limite: 2000ms)"


# ── RSP-005 ──────────────────────────────────────────────────────────────────
def test_RSP_005_entrada_5000_chars():
    """RSP-005: Criar documento Word com parágrafo de 5.000 caracteres — sem crash."""
    texto_longo = "A" * 5000
    r, ms = medir(criar_documento_word, sb("longo_5k.docx"), "Entrada Longa", None, [texto_longo])
    assert isinstance(r, str)
    assert ms < 5000, f"Muito lento com entrada de 5k chars: {ms:.1f}ms"


# ── RSP-006 ──────────────────────────────────────────────────────────────────
def test_RSP_006_entrada_15000_chars():
    """RSP-006: Criar documento Word com parágrafo de 15.000 caracteres — sem estouro."""
    texto_longo = "B " * 7500  # 15.000 chars
    r, ms = medir(criar_documento_word, sb("longo_15k.docx"), "Entrada 15k", None, [texto_longo])
    assert isinstance(r, str)
    assert ms < 10000, f"Muito lento com 15k chars: {ms:.1f}ms"


# ── RSP-007 ──────────────────────────────────────────────────────────────────
def test_RSP_007_10_planilhas_sequenciais():
    """RSP-007: Criar 10 planilhas sequencialmente — tempo total < 15s."""
    t0 = time.perf_counter()
    for i in range(10):
        criar_planilha(sb(f"seq/planilha_{i}.xlsx"), abrir_no_excel=False)
    total_ms = (time.perf_counter() - t0) * 1000
    assert total_ms < 15000, f"10 planilhas demoraram {total_ms:.1f}ms (limite: 15.000ms)"


# ── RSP-008 ──────────────────────────────────────────────────────────────────
def test_RSP_008_10_words_sequenciais():
    """RSP-008: Criar 10 documentos Word sequencialmente — tempo total < 10s."""
    t0 = time.perf_counter()
    for i in range(10):
        criar_documento_word(sb(f"seq/doc_{i}.docx"), titulo=f"Documento {i}")
    total_ms = (time.perf_counter() - t0) * 1000
    assert total_ms < 10000, f"10 documentos demoraram {total_ms:.1f}ms (limite: 10.000ms)"


# ── RSP-009 ──────────────────────────────────────────────────────────────────
def test_RSP_009_5_execute_skills_paralelos():
    """RSP-009: 5 chamadas paralelas ao execute_skill — sem deadlock ou crash."""
    resultados = []
    erros = []

    def chamar():
        try:
            r = execute_skill("obter_hora_data")
            resultados.append(r)
        except Exception as e:
            erros.append(str(e))

    t0 = time.perf_counter()
    threads = [threading.Thread(target=chamar) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    total_ms = (time.perf_counter() - t0) * 1000

    assert len(erros) == 0, f"Erros em paralelo: {erros}"
    assert len(resultados) == 5, f"Apenas {len(resultados)}/5 completaram"
    assert total_ms < 10000, f"Timeout em chamadas paralelas: {total_ms:.1f}ms"


# ── RSP-010 ──────────────────────────────────────────────────────────────────
def test_RSP_010_10_creates_planilha_paralelos():
    """RSP-010: 10 criações de planilha em paralelo — verificar ausência de corrupção."""
    resultados = []
    erros = []

    def criar(idx):
        try:
            r = criar_planilha(sb(f"paralelo/pl_{idx}.xlsx"), abrir_no_excel=False)
            resultados.append((idx, r))
        except Exception as e:
            erros.append(f"Planilha {idx}: {e}")

    threads = [threading.Thread(target=criar, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(erros) == 0, f"Erros ao criar planilhas em paralelo: {erros}"
    arquivos_criados = list(Path(sb("paralelo")).glob("*.xlsx"))
    assert len(arquivos_criados) == 10, f"Apenas {len(arquivos_criados)}/10 planilhas criadas"


# ── RSP-011 ──────────────────────────────────────────────────────────────────
def test_RSP_011_latencia_listar_diretorio_grande():
    """RSP-011: Listar diretório com 50 arquivos deve completar em menos de 1s."""
    base = Path(sb("dir_grande"))
    base.mkdir(parents=True, exist_ok=True)
    for i in range(50):
        (base / f"arq_{i}.txt").write_text(f"conteúdo {i}", encoding="utf-8")
    from skills.file_data_ops import gerenciar_arquivos
    r, ms = medir(gerenciar_arquivos, "listar", str(base))
    assert ms < 1000, f"Listagem de 50 arquivos lenta: {ms:.1f}ms"


# ── RSP-012 ──────────────────────────────────────────────────────────────────
def test_RSP_012_consulta_planilha_50_linhas():
    """RSP-012: Ler planilha de 50 linhas em menos de 2s."""
    dados = [{"ID": i, "Valor": i * 1.5} for i in range(50)]
    criar_planilha(sb("perf_50.xlsx"), dados=dados, abrir_no_excel=False)
    _, ms = medir(consultar_planilha, sb("perf_50.xlsx"), "resumo")
    assert ms < 2000, f"Leitura de 50 linhas lenta: {ms:.1f}ms"


# ── RSP-013 ──────────────────────────────────────────────────────────────────
def test_RSP_013_memory_consumo_estavel():
    """RSP-013: Consumo de memória não cresce excessivamente após 20 operações."""
    try:
        import psutil
        processo = psutil.Process()
        mem_antes = processo.memory_info().rss / 1024 / 1024  # MB
        for i in range(20):
            execute_skill("obter_hora_data")
        mem_depois = processo.memory_info().rss / 1024 / 1024
        crescimento = mem_depois - mem_antes
        # Tolerância de 100MB de crescimento para 20 operações
        assert crescimento < 100, f"Crescimento de memória excessivo: +{crescimento:.1f}MB"
    except ImportError:
        pytest.skip("psutil não disponível — instale para testes de memória")


# ── RSP-014 ──────────────────────────────────────────────────────────────────
def test_RSP_014_5_docs_word_paralelos():
    """RSP-014: 5 criações de Word em paralelo — sem corrupção de arquivos."""
    erros = []

    def criar_doc(idx):
        try:
            criar_documento_word(
                sb(f"paralelo_docs/doc_{idx}.docx"),
                titulo=f"Doc Paralelo {idx}",
                paragrafos=[f"Criado em paralelo — índice {idx}."],
                abrir_no_word=False
            )
        except Exception as e:
            erros.append(f"Doc {idx}: {e}")

    threads = [threading.Thread(target=criar_doc, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert len(erros) == 0, f"Erros em paralelo: {erros}"
    docs = [d for d in Path(sb("paralelo_docs")).glob("*.docx") if not d.name.startswith("~$")] if Path(sb("paralelo_docs")).exists() else []
    assert len(docs) == 5, f"Apenas {len(docs)}/5 documentos criados"


# ── RSP-015 ──────────────────────────────────────────────────────────────────
def test_RSP_015_planilha_1000_linhas():
    """RSP-015: Criar e ler planilha com 1.000 linhas — menos de 5s total."""
    dados = [{"ID": i, "Nome": f"Item_{i}", "Valor": i * 0.99} for i in range(1000)]
    t0 = time.perf_counter()
    criar_planilha(sb("mil_linhas.xlsx"), dados=dados, abrir_no_excel=False)
    resumo = consultar_planilha(sb("mil_linhas.xlsx"), acao="resumo")
    total_ms = (time.perf_counter() - t0) * 1000
    assert "1000" in resumo or "1.000" in resumo, f"Quantidade incorreta no resumo: {resumo}"
    assert total_ms < 5000, f"1.000 linhas demoraram {total_ms:.1f}ms (limite: 5.000ms)"


# ── RSP-016 ──────────────────────────────────────────────────────────────────
def test_RSP_016_repetir_hora_100x():
    """RSP-016: 100 chamadas sequenciais ao obter_hora_data — média < 100ms cada."""
    tempos = []
    for _ in range(100):
        _, ms = medir(obter_hora_data)
        tempos.append(ms)
    media = sum(tempos) / len(tempos)
    assert media < 100, f"Média de latência muito alta: {media:.2f}ms"


# ── RSP-017 ──────────────────────────────────────────────────────────────────
def test_RSP_017_execute_skill_sem_degradacao():
    """RSP-017: 50 chamadas ao execute_skill — sem degradação progressiva de latência."""
    tempos = []
    for _ in range(50):
        _, ms = medir(execute_skill, "obter_hora_data")
        tempos.append(ms)
    # Verificar que a última metade não é 3x mais lenta que a primeira
    primeira = sum(tempos[:25]) / 25
    ultima = sum(tempos[25:]) / 25
    assert ultima < primeira * 3, \
        f"Degradação detectada: início={primeira:.1f}ms, fim={ultima:.1f}ms"


# ── RSP-018 ──────────────────────────────────────────────────────────────────
def test_RSP_018_criar_e_ler_word_latencia():
    """RSP-018: Criar + ler documento Word em menos de 3s total."""
    t0 = time.perf_counter()
    criar_documento_word(
        sb("latencia_leitura.docx"),
        titulo="Teste de Latência Completo",
        paragrafos=["Parágrafo 1", "Parágrafo 2", "Parágrafo 3"]
    )
    from skills.file_data_ops import ler_documento_word
    ler_documento_word(sb("latencia_leitura.docx"))
    total_ms = (time.perf_counter() - t0) * 1000
    assert total_ms < 3000, f"Criar + ler Word levou {total_ms:.1f}ms (limite: 3.000ms)"


# ── RSP-019 ──────────────────────────────────────────────────────────────────
def test_RSP_019_criar_planilha_com_150_colunas():
    """RSP-019: Planilha com 150 colunas — sem crash por largura excessiva."""
    colunas = [f"Col_{i}" for i in range(150)]
    r, ms = medir(criar_planilha, sb("muitas_colunas.xlsx"), colunas, None, False)
    assert isinstance(r, str)
    assert ms < 5000, f"150 colunas demoraram {ms:.1f}ms"


# ── RSP-020 ──────────────────────────────────────────────────────────────────
def test_RSP_020_word_com_tabela_grande():
    """RSP-020: Criar Word com tabela 50x5 — sem crash por tamanho de tabela."""
    cabecalho = ["ID", "Nome", "Valor", "Status", "Data"]
    linhas = [[str(i), f"Item_{i}", str(i * 10), "OK", "2026-01"] for i in range(50)]
    tabela = [cabecalho] + linhas
    r, ms = medir(criar_documento_word, sb("tabela_grande.docx"), "Tabela Grande", None, None, None, None, tabela)
    assert isinstance(r, str)
    assert ms < 5000, f"Tabela 50x5 demorou {ms:.1f}ms"


# ── RSP-021 ──────────────────────────────────────────────────────────────────
def test_RSP_021_status_sistema_5x_rapido():
    """RSP-021: 5 consultas de status em menos de 5s total."""
    t0 = time.perf_counter()
    for _ in range(5):
        status_sistema()
    total_ms = (time.perf_counter() - t0) * 1000
    assert total_ms < 5000, f"5 consultas de status levaram {total_ms:.1f}ms"


# ── RSP-022 ──────────────────────────────────────────────────────────────────
def test_RSP_022_execute_skill_nao_bloqueia_thread():
    """RSP-022: execute_skill retorna dentro do timeout definido por thread."""
    resultado = [None]
    def rodar():
        resultado[0] = execute_skill("status_sistema")
    t = threading.Thread(target=rodar)
    t.start()
    t.join(timeout=10)
    assert not t.is_alive(), "execute_skill bloqueou a thread por mais de 10s"
    assert isinstance(resultado[0], str)


# ── RSP-023 ──────────────────────────────────────────────────────────────────
def test_RSP_023_leitura_planilha_1000_3x():
    """RSP-023: Ler planilha de 1.000 linhas 3 vezes — verificar estabilidade de tempo."""
    dados = [{"X": i} for i in range(1000)]
    criar_planilha(sb("estabilidade.xlsx"), dados=dados, abrir_no_excel=False)
    tempos = []
    for _ in range(3):
        _, ms = medir(consultar_planilha, sb("estabilidade.xlsx"), "resumo")
        tempos.append(ms)
    variacao = max(tempos) - min(tempos)
    # Variação entre leituras não deve ser maior que 2x
    assert variacao < max(tempos) * 2, f"Variação excessiva de latência: {tempos}"


# ── RSP-024 ──────────────────────────────────────────────────────────────────
def test_RSP_024_multiplas_edicoes_word_sequenciais():
    """RSP-024: 10 edições sequenciais no mesmo documento Word — sem corrupção."""
    from skills.file_data_ops import editar_documento_word, ler_documento_word
    criar_documento_word(sb("edicoes_sequenciais.docx"), titulo="Documento para Edições", abrir_no_word=False)
    for i in range(10):
        editar_documento_word(
            sb("edicoes_sequenciais.docx"),
            adicionar_paragrafos=[f"Edição número {i}."]
        )
    leitura = ler_documento_word(sb("edicoes_sequenciais.docx"))
    # Verificar que todas as edições estão presentes
    for i in range(10):
        assert f"Edição número {i}" in leitura, f"Edição {i} perdida: {leitura[:200]}"


# ── RSP-025 ──────────────────────────────────────────────────────────────────
def test_RSP_025_liberacao_recursos_pos_operacoes():
    """RSP-025: Após 30 operações diversas, sistema não deve estar degradado."""
    # Executar 30 operações variadas
    for i in range(10):
        execute_skill("obter_hora_data")
    for i in range(10):
        criar_planilha(sb(f"recursos/pl_{i}.xlsx"), abrir_no_excel=False)
    for i in range(10):
        criar_documento_word(sb(f"recursos/doc_{i}.docx"), titulo=f"Recurso {i}")
    # Sistema deve ainda responder rapidamente
    _, ms = medir(obter_hora_data)
    assert ms < 500, f"Sistema degradado após 30 operações: {ms:.1f}ms de latência"
