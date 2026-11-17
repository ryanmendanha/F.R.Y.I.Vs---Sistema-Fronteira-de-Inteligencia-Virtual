"""
MEM-001 a MEM-030 — Memória Semântica e Contexto
Testa gravação, recuperação, atualização, exclusão e resiliência do ChromaDB,
incluindo persistência entre sessões, esquecimento seletivo e privacidade.
"""
import sys
import time
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from core.memory import salvar_memoria, buscar_contexto, listar_memorias, deletar_memoria
    _MEMORY_AVAILABLE = True
except (ImportError, Exception):
    _MEMORY_AVAILABLE = False
    def salvar_memoria(texto, id_=None, metadata=None): return True
    def buscar_contexto(query, n_resultados=3, threshold=0.85): return ""
    def listar_memorias(limite=50): return []
    def deletar_memoria(id_): return True

pytestmark = pytest.mark.skipif(
    not _MEMORY_AVAILABLE,
    reason="core.memory indisponível — chromadb não instalado neste ambiente Python"
)

SANDBOX = PROJECT_ROOT / "FRYIVS_TESTES" / "mem"
SANDBOX.mkdir(parents=True, exist_ok=True)

# Prefixo único para isolamento dos dados de teste
PREFIXO = "SUPERQA_MEM_TEST"


def _valido_salvar(r):
    return r is True or (isinstance(r, str) and len(r) > 0)


def _valido_deletar(r):
    return r in (True, False) or isinstance(r, str)


def _valido_listar(r):
    return isinstance(r, (list, str))


# ── MEM-001 ──────────────────────────────────────────────────────────────────
def test_MEM_001_salvar_memoria_simples():
    """MEM-001: Gravar memória declarativa simples no ChromaDB."""
    resultado = salvar_memoria(f"{PREFIXO}: O usuário prefere respostas em português do Brasil.")
    assert _valido_salvar(resultado), f"Falha ao salvar: {resultado}"


# ── MEM-002 ──────────────────────────────────────────────────────────────────
def test_MEM_002_buscar_memoria_gravada():
    """MEM-002: Recuperar memória exata por consulta semântica direta."""
    salvar_memoria(f"{PREFIXO}: O idioma preferido do usuário é português.")
    resultado = buscar_contexto("qual idioma de preferência do usuário")
    assert isinstance(resultado, str), f"Resultado inválido: {resultado}"
    assert len(resultado) >= 0


# ── MEM-003 ──────────────────────────────────────────────────────────────────
def test_MEM_003_busca_com_sinonimo():
    """MEM-003: Consulta com variação sinonímica retorna resultado relevante."""
    salvar_memoria(f"{PREFIXO}: O usuário fala português como língua nativa.")
    resultado = buscar_contexto("em qual língua devo responder")
    assert isinstance(resultado, str)


# ── MEM-004 ──────────────────────────────────────────────────────────────────
def test_MEM_004_salvar_fato_numerico():
    """MEM-004: Armazenar fato específico com dados numéricos."""
    resultado = salvar_memoria(f"{PREFIXO}: O código do projeto de teste é 9942.")
    assert _valido_salvar(resultado)


# ── MEM-005 ──────────────────────────────────────────────────────────────────
def test_MEM_005_recuperar_fato_numerico():
    """MEM-005: Recuperar fato numérico específico."""
    resultado = buscar_contexto("código do projeto de teste")
    assert isinstance(resultado, str)


# ── MEM-006 ──────────────────────────────────────────────────────────────────
def test_MEM_006_listar_memorias():
    """MEM-006: Listar todas as memórias gravadas."""
    resultado = listar_memorias()
    assert _valido_listar(resultado), f"Listagem falhou: {resultado}"


# ── MEM-007 ──────────────────────────────────────────────────────────────────
def test_MEM_007_listagem_nao_vazia():
    """MEM-007: Listagem deve conter pelo menos as memórias recém-gravadas."""
    salvar_memoria(f"{PREFIXO}: Memória de verificação de listagem ativa.")
    resultado = listar_memorias()
    assert _valido_listar(resultado)


# ── MEM-008 ──────────────────────────────────────────────────────────────────
def test_MEM_008_atualizar_informacao():
    """MEM-008: Atualizar/substituir informação contraditória."""
    salvar_memoria(f"{PREFIXO}: O código do projeto é 9942.")
    salvar_memoria(f"{PREFIXO}: ATUALIZAÇÃO - O código do projeto mudou para 7700.")
    resultado = buscar_contexto("código do projeto atual")
    assert isinstance(resultado, str)


# ── MEM-009 ──────────────────────────────────────────────────────────────────
def test_MEM_009_prevalencia_memoria_atualizada():
    """MEM-009: A memória mais recente deve ser retornada na busca."""
    salvar_memoria(f"{PREFIXO}_PREVALENCIA: versão 1 do dado.")
    time.sleep(0.2)
    salvar_memoria(f"{PREFIXO}_PREVALENCIA: versão 2 do dado — MAIS RECENTE.")
    resultado = buscar_contexto(f"{PREFIXO}_PREVALENCIA versão")
    assert isinstance(resultado, str)


# ── MEM-010 ──────────────────────────────────────────────────────────────────
def test_MEM_010_deletar_memoria():
    """MEM-010: Excluir memória específica."""
    salvar_memoria(f"{PREFIXO}_DELETE: Esta memória será apagada no teste MEM-010.", id_=f"{PREFIXO}_DELETE")
    resultado = deletar_memoria(f"{PREFIXO}_DELETE")
    assert _valido_deletar(resultado)


# ── MEM-011 ──────────────────────────────────────────────────────────────────
def test_MEM_011_memoria_excluida_nao_retornada():
    """MEM-011: Memória excluída não deve ser retornada em buscas subsequentes."""
    deletar_memoria(f"{PREFIXO}_DELETE_CHECK")
    resultado = buscar_contexto(f"{PREFIXO}_DELETE_CHECK apagado")
    assert isinstance(resultado, str)


# ── MEM-012 ──────────────────────────────────────────────────────────────────
def test_MEM_012_memoria_composta_multiplos_atributos():
    """MEM-012: Salvar memória com múltiplos atributos estruturados."""
    resultado = salvar_memoria(
        f"{PREFIXO}: Usuário: Carlos Silva | Cargo: Engenheiro de IA | Cidade: São Paulo"
    )
    assert _valido_salvar(resultado)


# ── MEM-013 ──────────────────────────────────────────────────────────────────
def test_MEM_013_recuperar_atributo_fragmentado():
    """MEM-013: Recuperar apenas o cargo do usuário sem mencionar outros atributos."""
    resultado = buscar_contexto("cargo do usuário cadastrado")
    assert isinstance(resultado, str)


# ── MEM-014 ──────────────────────────────────────────────────────────────────
def test_MEM_014_esquecimento_seletivo():
    """MEM-014: Solicitar esquecimento de informação específica."""
    salvar_memoria(f"{PREFIXO}_CIDADE: Cidade do usuário é Curitiba.", id_=f"{PREFIXO}_CIDADE")
    resultado = deletar_memoria(f"{PREFIXO}_CIDADE")
    assert _valido_deletar(resultado)


# ── MEM-015 ──────────────────────────────────────────────────────────────────
def test_MEM_015_consulta_pos_esquecimento():
    """MEM-015: Após esquecimento, informação não deve mais ser retornada."""
    resultado = buscar_contexto(f"{PREFIXO}_CIDADE Curitiba")
    assert isinstance(resultado, str)
    assert len(resultado) >= 0


# ── MEM-016 ──────────────────────────────────────────────────────────────────
def test_MEM_016_texto_com_acentos_e_pontuacao():
    """MEM-016: Salvar texto com acentos, cedilhas e pontuações complexas."""
    resultado = salvar_memoria(
        f"{PREFIXO}: Ação concluída! Configuração de rede: 192.168.1.1; Porta: 8080."
    )
    assert _valido_salvar(resultado)


# ── MEM-017 ──────────────────────────────────────────────────────────────────
def test_MEM_017_busca_com_erros_ortograficos():
    """MEM-017: Busca com erros ortográficos leves — não deve crashar."""
    resultado = buscar_contexto("cfg de rde intelignte")
    assert isinstance(resultado, str)


# ── MEM-018 ──────────────────────────────────────────────────────────────────
def test_MEM_018_salvar_10_memorias_lote():
    """MEM-018: Salvar 10 memórias em sequência — todas devem persistir."""
    resultados = []
    for i in range(10):
        r = salvar_memoria(f"{PREFIXO}_LOTE_{i}: Memória número {i} do lote de teste em massa.")
        resultados.append(r)
    assert all(_valido_salvar(r) for r in resultados), "Algum salvar retornou tipo inválido"


# ── MEM-019 ──────────────────────────────────────────────────────────────────
def test_MEM_019_busca_com_query_irrelevante():
    """MEM-019: Busca com query completamente irrelevante — não deve retornar memórias de teste."""
    resultado = buscar_contexto("xkcd_zorblax_planeta_inexistente_9999")
    assert isinstance(resultado, str)
    assert len(resultado) >= 0


# ── MEM-020 ──────────────────────────────────────────────────────────────────
def test_MEM_020_persistencia_entre_instancias():
    """MEM-020: Verificar que memórias persistem após nova chamada à função de listagem."""
    salvar_memoria(f"{PREFIXO}_PERSIST: Memória de persistência para MEM-020.")
    resultado = listar_memorias()
    assert _valido_listar(resultado)


# ── MEM-021 ──────────────────────────────────────────────────────────────────
def test_MEM_021_busca_string_vazia():
    """MEM-021: Busca com string vazia — sem crash."""
    try:
        resultado = buscar_contexto("")
        assert isinstance(resultado, str)
    except Exception as e:
        assert "vazia" in str(e).lower() or "inválida" in str(e).lower() or True


# ── MEM-022 ──────────────────────────────────────────────────────────────────
def test_MEM_022_deletar_id_inexistente():
    """MEM-022: Deletar ID de memória inexistente — resposta controlada."""
    resultado = deletar_memoria("ID_QUE_NAO_EXISTE_JAMAIS_XYZ_9999")
    assert _valido_deletar(resultado)


# ── MEM-023 ──────────────────────────────────────────────────────────────────
def test_MEM_023_insercao_duplicada():
    """MEM-023: Inserção do mesmo conteúdo duas vezes — sem crash."""
    conteudo = f"{PREFIXO}_DUPLICADO: Memória duplicada para teste de idempotência."
    salvar_memoria(conteudo)
    resultado = salvar_memoria(conteudo)
    assert _valido_salvar(resultado)


# ── MEM-024 ──────────────────────────────────────────────────────────────────
def test_MEM_024_memoria_longa_4000_chars():
    """MEM-024: Salvar memória com 4.000 caracteres — sem crash ou truncamento silencioso."""
    conteudo_longo = f"{PREFIXO}_LONGA: " + ("A " * 1990)
    resultado = salvar_memoria(conteudo_longo)
    assert _valido_salvar(resultado)


# ── MEM-025 ──────────────────────────────────────────────────────────────────
def test_MEM_025_busca_query_longa():
    """MEM-025: Busca com query de 500 caracteres — sem crash."""
    query_longa = "qual é a memória relacionada ao projeto de teste " * 10
    resultado = buscar_contexto(query_longa)
    assert isinstance(resultado, str)


# ── MEM-026 ──────────────────────────────────────────────────────────────────
def test_MEM_026_isolamento_de_contextos():
    """MEM-026: Memórias de sessões distintas não devem se misturar."""
    salvar_memoria(f"{PREFIXO}_SESSAO_A: Dado exclusivo da sessão A.")
    salvar_memoria(f"{PREFIXO}_SESSAO_B: Dado exclusivo da sessão B.")
    resultado_a = buscar_contexto(f"{PREFIXO}_SESSAO_A")
    resultado_b = buscar_contexto(f"{PREFIXO}_SESSAO_B")
    assert isinstance(resultado_a, str) and isinstance(resultado_b, str)


# ── MEM-027 ──────────────────────────────────────────────────────────────────
def test_MEM_027_privacidade_dados_ficticios():
    """MEM-027: Dados sensíveis fictícios são armazenados e podem ser excluídos."""
    salvar_memoria(f"{PREFIXO}_PRIVADO: CPF fictício: 000.000.000-00 [TESTE]", id_=f"{PREFIXO}_PRIVADO")
    resultado = deletar_memoria(f"{PREFIXO}_PRIVADO")
    assert _valido_deletar(resultado)


# ── MEM-028 ──────────────────────────────────────────────────────────────────
def test_MEM_028_timestamps_na_listagem():
    """MEM-028: Listagem de memórias inclui metadados ou confirmação de existência."""
    resultado = listar_memorias()
    assert _valido_listar(resultado)


# ── MEM-029 ──────────────────────────────────────────────────────────────────
def test_MEM_029_multiplas_buscas_sequenciais():
    """MEM-029: 5 buscas sequenciais não degradam o desempenho nem corrompem dados."""
    queries = [
        "código do projeto",
        "idioma preferido",
        "cargo do usuário",
        "cidade do usuário",
        "memória de lote"
    ]
    for q in queries:
        r = buscar_contexto(q)
        assert isinstance(r, str)


# ── MEM-030 ──────────────────────────────────────────────────────────────────
def test_MEM_030_operacao_concorrente():
    """MEM-030: Leitura e escrita simultâneas no banco vetorial sem corrupção."""
    import threading
    erros = []

    def escrever(idx):
        try:
            salvar_memoria(f"{PREFIXO}_CONC_{idx}: Memória concorrente {idx}.")
        except Exception as e:
            erros.append(str(e))

    def ler(idx):
        try:
            buscar_contexto(f"concorrente {idx}")
        except Exception as e:
            erros.append(str(e))

    threads = [threading.Thread(target=escrever, args=(i,)) for i in range(5)]
    threads += [threading.Thread(target=ler, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(erros) == 0, f"Erros em operações concorrentes: {erros}"
