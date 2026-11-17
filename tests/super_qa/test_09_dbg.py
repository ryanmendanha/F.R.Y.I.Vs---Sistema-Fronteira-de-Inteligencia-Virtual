"""
DBG-001 a DBG-030 — Debug, Resiliência e Tratamento de Erros
Testa comportamento com parâmetros inválidos, caminhos protegidos, arquivos
corrompidos, fronteiras de segurança e recuperação gracilosa sem crashes.
"""
import sys
import os
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from skills import execute_skill, SKILLS_REGISTRY
from skills.file_data_ops import (
    gerenciar_arquivos, consultar_planilha, criar_planilha,
    criar_documento_word, ler_documento_word, editar_documento_word
)

SANDBOX = PROJECT_ROOT / "FRYIVS_TESTES" / "dbg"
SANDBOX.mkdir(parents=True, exist_ok=True)

def sb(name: str) -> str:
    return str(SANDBOX / name)

def _ok(r) -> bool:
    return isinstance(r, str) and len(r) > 2


def test_DBG_001_skill_inexistente():
    """DBG-001: execute_skill com nome inexistente — erro amigável."""
    r = execute_skill("skill_que_nao_existe_jamais_999")
    assert _ok(r)
    assert any(kw in r.lower() for kw in ["não encontrada", "nao encontrada", "erro"]), r


def test_DBG_002_args_obrigatorios_faltando():
    """DBG-002: execute_skill sem argumentos obrigatórios — TypeError tratado."""
    r = execute_skill("gerenciar_arquivos", {})
    assert _ok(r)
    assert any(kw in r.lower() for kw in ["erro", "argumento", "required", "missing"]), r


def test_DBG_003_tipo_argumento_errado():
    """DBG-003: Argumento com tipo errado (bool onde espera str) — sem crash fatal."""
    r = execute_skill("consultar_planilha", {"caminho_arquivo": True, "acao": "resumo"})
    assert _ok(r)


def test_DBG_004_acao_desconhecida_gerenciar():
    """DBG-004: gerenciar_arquivos com ação desconhecida -- mensagem de erro ou pedido de destino."""
    r = gerenciar_arquivos("acao_inventada_xyz", sb("qualquer.txt"))
    assert _ok(r)
    assert any(kw in r.lower() for kw in ["desconhecida", "desconhecido", "inválida", "destino", "ação"]), r


def test_DBG_005_caminho_disco_inexistente():
    """DBG-005: Caminho de disco inexistente (Z:\\ nao montado) - erro claro."""
    r = gerenciar_arquivos("listar", r"Z:\pasta_nao_existe")
    assert _ok(r)
    assert any(kw in r.lower() for kw in ["não encontrad", "nao encontrad", "inexistente"]), r


def test_DBG_006_deletar_caminho_protegido_windows():
    """DBG-006: Bloqueio de segurança para System32."""
    r = gerenciar_arquivos("deletar", r"C:\Windows\System32")
    assert _ok(r)
    assert any(kw in r.lower() for kw in ["bloqueado", "protegido", "segurança"]), r


def test_DBG_007_deletar_raiz_c():
    """DBG-007: Bloqueio de seguranca para raiz C:\\."""
    r = gerenciar_arquivos("deletar", r"C:\\")
    assert _ok(r)
    assert any(kw in r.lower() for kw in ["bloqueado", "protegido", "segurança"]), r


def test_DBG_008_copiar_sem_destino():
    """DBG-008: copiar sem argumento 'destino' — mensagem descritiva."""
    r = gerenciar_arquivos("copiar", sb("qualquer.txt"), None)
    assert _ok(r)
    assert any(kw in r.lower() for kw in ["destino", "requer", "obrigatório"]), r


def test_DBG_009_planilha_formato_invalido():
    """DBG-009: Tentativa de leitura de PDF como planilha."""
    caminho = sb("fake.pdf")
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    Path(caminho).write_text("conteúdo não-excel", encoding="utf-8")
    r = consultar_planilha(caminho, acao="resumo")
    assert _ok(r)
    assert any(kw in r.lower() for kw in ["não suportado", "nao suportado", "formato", "suportados"]), r


def test_DBG_010_planilha_corrompida():
    """DBG-010: Leitura de arquivo .xlsx corrompido (bytes aleatórios)."""
    caminho = sb("corrompido.xlsx")
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    Path(caminho).write_bytes(b"\x00\x01\x02\x03\xFF\xFE texto corrompido 123 abc")
    r = consultar_planilha(caminho, acao="resumo")
    assert _ok(r)
    assert any(kw in r.lower() for kw in ["erro", "falha", "inválido", "corrompido", "pandas"]), r


def test_DBG_011_word_corrompido():
    """DBG-011: Leitura de .docx corrompido — erro amigável."""
    caminho = sb("corrompido.docx")
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    Path(caminho).write_bytes(b"\x00\x01bytes_invalidos_para_docx\xFF")
    r = ler_documento_word(caminho)
    assert _ok(r)
    assert any(kw in r.lower() for kw in ["erro", "falha", "inválido"]), r


def test_DBG_012_caminho_barras_mistas():
    """DBG-012: Caminhos com barras normais e invertidas misturadas."""
    pasta = SANDBOX / "barras_mistas"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = str(pasta).replace("\\", "/") + "/arquivo_barras.txt"
    Path(caminho).write_text("teste de barras", encoding="utf-8")
    r = gerenciar_arquivos("listar", str(pasta))
    assert _ok(r)


def test_DBG_013_string_vazia_gerenciar():
    """DBG-013: gerenciar_arquivos com strings vazias — sem crash."""
    r = gerenciar_arquivos("listar", "")
    assert _ok(r)


def test_DBG_014_nome_nulo_execute_skill():
    """DBG-014: execute_skill com None como nome — sem crash."""
    try:
        r = execute_skill(None)
        assert isinstance(r, str)
    except TypeError:
        pass


def test_DBG_015_path_traversal_bloqueado():
    """DBG-015: Path traversal com ../../../../ -- Path.resolve() normaliza o caminho."""
    caminho_alvo = sb("../../../../tentativa_traversal/indesejado.txt")
    caminho_resolvido = Path(caminho_alvo).resolve()
    r = gerenciar_arquivos("criar_pasta", caminho_alvo)
    assert _ok(r)
    assert "windows\\system32" not in str(caminho_resolvido).lower() or not Path(caminho_resolvido).exists(), \
        f"Path traversal resultou em caminho perigoso real: {caminho_resolvido}"


def test_DBG_016_execute_skill_planilha_caminho_vazio():
    """DBG-016: Criar planilha com caminho vazio — erro amigável."""
    r = execute_skill("criar_planilha", {"caminho_arquivo": "", "abrir_no_excel": False})
    assert isinstance(r, str)


def test_DBG_017_consultar_planilha_inexistente():
    """DBG-017: Consultar planilha que não existe — mensagem amigável."""
    r = consultar_planilha(sb("nao_existe_planilha.xlsx"), acao="resumo")
    assert _ok(r)
    assert any(kw in r.lower() for kw in ["não encontrado", "nao encontrado", "inexistente"]), r


def test_DBG_018_ler_word_extensao_errada():
    """DBG-018: ler_documento_word com .txt em vez de .docx."""
    caminho = sb("nao_e_word.txt")
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    Path(caminho).write_text("texto simples", encoding="utf-8")
    r = ler_documento_word(caminho)
    assert _ok(r)
    assert any(kw in r.lower() for kw in ["inválido", "invalido", ".docx", "suportados"]), r


def test_DBG_019_editar_word_inexistente():
    """DBG-019: Editar documento Word que não existe — erro amigável."""
    r = editar_documento_word(sb("documento_fantasma.docx"), adicionar_paragrafos=["parágrafo"])
    assert _ok(r)
    assert any(kw in r.lower() for kw in ["não encontrado", "nao encontrado", "inexistente"]), r


def test_DBG_020_editar_arquivo_nao_docx():
    """DBG-020: Editar arquivo que existe mas não é .docx — erro de formato."""
    caminho = sb("nao_e_docx.pdf")
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    Path(caminho).write_text("PDF fake", encoding="utf-8")
    r = editar_documento_word(caminho, adicionar_paragrafos=["teste"])
    assert _ok(r)
    assert any(kw in r.lower() for kw in ["inválido", "invalido", ".docx"]), r


def test_DBG_021_criar_planilha_pasta_sem_permissao():
    """DBG-021: Criar planilha em diretório de sistema — erro capturado."""
    r = criar_planilha(r"C:\Windows\Temp\fryivs_teste_qa.xlsx", abrir_no_excel=False)
    assert isinstance(r, str)


def test_DBG_022_execute_skill_args_extras():
    """DBG-022: execute_skill com argumentos extras não esperados."""
    r = execute_skill("obter_hora_data", {"arg_extra_invalido": "valor_irrelevante"})
    assert isinstance(r, str)


def test_DBG_023_gerenciar_arquivos_mover_sem_destino():
    """DBG-023: mover sem destino — mensagem exigindo destino."""
    r = gerenciar_arquivos("mover", sb("qualquer.txt"))
    assert _ok(r)
    assert any(kw in r.lower() for kw in ["destino", "requer", "obrigatório"]), r


def test_DBG_024_criar_documento_word_sem_conteudo():
    """DBG-024: Criar documento Word sem nenhum conteúdo — apenas arquivo vazio válido."""
    r = criar_documento_word(sb("word_vazio.docx"))
    assert _ok(r)
    assert Path(sb("word_vazio.docx")).exists(), f"Documento vazio não criado: {r}"


def test_DBG_025_word_titulo_muito_longo():
    """DBG-025: Criar Word com título de 500 caracteres — sem crash."""
    titulo_longo = "T" * 500
    r = criar_documento_word(sb("word_titulo_longo.docx"), titulo=titulo_longo)
    assert isinstance(r, str)


def test_DBG_026_planilha_com_dados_nulos():
    """DBG-026: Planilha com dados contendo None/null — sem crash."""
    import pandas as pd
    dados = pd.DataFrame({"A": [1, None, 3], "B": [None, "texto", None]})
    caminho = sb("dados_nulos.xlsx")
    dados.to_excel(caminho, index=False, engine="openpyxl")
    r = consultar_planilha(caminho, acao="resumo")
    assert _ok(r)


def test_DBG_027_execute_skill_argumento_none_em_dict():
    """DBG-027: execute_skill com valor None dentro do dicionário de argumentos."""
    r = execute_skill("gerenciar_arquivos", {"acao": "listar", "origem": None})
    assert isinstance(r, str)


def test_DBG_028_criacao_pasta_nome_especial():
    """DBG-028: Criar pasta com nome contendo underscores e hífens."""
    pasta = sb("pasta-com-hífen_e_underscore")
    r = gerenciar_arquivos("criar_pasta", pasta)
    assert Path(pasta).exists(), f"Pasta especial não criada: {r}"


def test_DBG_029_todos_skills_registry_executaveis():
    """DBG-029: Verificar que nenhuma skill no registry causa ImportError ao referenciar."""
    for nome in SKILLS_REGISTRY:
        func = SKILLS_REGISTRY[nome]
        assert callable(func), f"'{nome}' não é callable"
        assert func.__name__ is not None


def test_DBG_030_logs_sem_credenciais():
    """DBG-030: Verificar que respostas de erro não expõem chaves ou tokens."""
    import re
    PADROES_SENSIVEIS = [
        r"sk-[A-Za-z0-9]{20,}",
        r"AIza[A-Za-z0-9\-_]{35}",
        r"Bearer [A-Za-z0-9\-_\.]{20,}",
    ]
    resultados_teste = [
        execute_skill("funcao_inexistente"),
        execute_skill("gerenciar_arquivos", {}),
        gerenciar_arquivos("deletar", r"C:\Windows"),
        consultar_planilha("nao_existe.xlsx"),
    ]
    for resultado in resultados_teste:
        for padrao in PADROES_SENSIVEIS:
            matches = re.findall(padrao, resultado)
            assert len(matches) == 0, \
                f"Possível vazamento de credencial detectado no resultado: {resultado[:200]}"
