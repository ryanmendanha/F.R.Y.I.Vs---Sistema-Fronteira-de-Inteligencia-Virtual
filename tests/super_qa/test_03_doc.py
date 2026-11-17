"""
DOC-001 a DOC-015 — Documentos Word (.docx)
Testa criação, edição, leitura e abertura de documentos Word via python-docx,
exclusivamente na sandbox FRYIVS_TESTES/doc/.
"""
import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from skills.file_data_ops import (
    criar_documento_word,
    editar_documento_word,
    ler_documento_word,
    abrir_documento_word,
    _DOCX_AVAILABLE,
)

SANDBOX = PROJECT_ROOT / "FRYIVS_TESTES" / "doc"
SANDBOX.mkdir(parents=True, exist_ok=True)

def sb(name: str) -> str:
    return str(SANDBOX / name)

pytestmark = pytest.mark.skipif(
    not _DOCX_AVAILABLE,
    reason="python-docx não está instalado"
)


def test_DOC_001_modulo_disponivel():
    """DOC-001: python-docx está instalado e disponível."""
    assert _DOCX_AVAILABLE, "python-docx não está instalado — instale com: pip install python-docx"


def test_DOC_002_criar_com_titulo():
    """DOC-002: Criar documento Word com título principal (Heading 1)."""
    resultado = criar_documento_word(
        sb("doc_titulo.docx"),
        titulo="Relatório FRYIVS 2026"
    )
    assert Path(sb("doc_titulo.docx")).exists(), f"Documento não criado: {resultado}"
    assert "criado" in resultado.lower() or "sucesso" in resultado.lower(), resultado


def test_DOC_003_criar_com_subtitulo():
    """DOC-003: Criar documento com subtítulo (Heading 2)."""
    resultado = criar_documento_word(
        sb("doc_subtitulo.docx"),
        titulo="Relatório Principal",
        subtitulo="Seção de Análise de Dados"
    )
    assert Path(sb("doc_subtitulo.docx")).exists(), f"Documento não criado: {resultado}"
    leitura = ler_documento_word(sb("doc_subtitulo.docx"))
    assert "Análise" in leitura or "Relatório" in leitura, leitura


def test_DOC_004_criar_com_paragrafos():
    """DOC-004: Criar documento com parágrafos de texto."""
    paragrafos = [
        "Este é o primeiro parágrafo com texto normal.",
        "Este é o segundo parágrafo com informações adicionais e acentuação: ção, ã, é, ü.",
        "Terceiro parágrafo — resumo final do documento."
    ]
    resultado = criar_documento_word(sb("doc_paragrafos.docx"), paragrafos=paragrafos)
    assert Path(sb("doc_paragrafos.docx")).exists(), f"Falhou: {resultado}"
    leitura = ler_documento_word(sb("doc_paragrafos.docx"))
    assert "primeiro parágrafo" in leitura, leitura


def test_DOC_005_criar_lista_bullets():
    """DOC-005: Criar documento com lista de marcadores (bullet points)."""
    itens = ["Item Alpha", "Item Beta", "Item Gamma", "Item Delta"]
    resultado = criar_documento_word(sb("doc_bullets.docx"), lista_itens=itens)
    assert Path(sb("doc_bullets.docx")).exists(), f"Falhou: {resultado}"
    leitura = ler_documento_word(sb("doc_bullets.docx"))
    assert "Alpha" in leitura, leitura


def test_DOC_006_criar_lista_numerada():
    """DOC-006: Criar documento com lista numerada."""
    itens = ["Primeiro passo", "Segundo passo", "Terceiro passo", "Quarto passo"]
    resultado = criar_documento_word(sb("doc_numerado.docx"), lista_numerada=itens)
    assert Path(sb("doc_numerado.docx")).exists(), f"Falhou: {resultado}"
    leitura = ler_documento_word(sb("doc_numerado.docx"))
    assert "passo" in leitura.lower(), leitura


def test_DOC_007_criar_tabela_4x3():
    """DOC-007: Criar documento com tabela estruturada 4x3."""
    tabela = [
        ["Produto", "Quantidade", "Preço"],
        ["Notebook", "10", "R$ 2.500,00"],
        ["Mouse", "50", "R$ 45,00"],
        ["Teclado", "30", "R$ 120,00"],
    ]
    resultado = criar_documento_word(sb("doc_tabela.docx"), tabela_dados=tabela)
    assert Path(sb("doc_tabela.docx")).exists(), f"Falhou: {resultado}"
    leitura = ler_documento_word(sb("doc_tabela.docx"))
    assert "Notebook" in leitura or "Tabela" in leitura, leitura


def test_DOC_008_tabela_com_dados_inventario():
    """DOC-008: Criar tabela de inventário com dados reais."""
    inventario = [
        ["ID", "Produto", "Estoque", "Valor Unitário"],
        ["001", "Cadeira Ergonômica", "25", "R$ 890,00"],
        ["002", "Mesa de Escritório", "15", "R$ 1.200,00"],
        ["003", "Monitor 24\"", "40", "R$ 1.450,00"],
        ["004", "Headset USB", "60", "R$ 180,00"],
    ]
    resultado = criar_documento_word(
        sb("doc_inventario.docx"),
        titulo="Inventário de Equipamentos 2026",
        tabela_dados=inventario
    )
    assert Path(sb("doc_inventario.docx")).exists(), f"Falhou: {resultado}"
    leitura = ler_documento_word(sb("doc_inventario.docx"))
    assert "Inventário" in leitura or "Estoque" in leitura, leitura


def test_DOC_009_ler_documento_existente():
    """DOC-009: Extrair texto completo de documento existente."""
    criar_documento_word(
        sb("doc_leitura.docx"),
        titulo="Documento de Leitura",
        paragrafos=["Parágrafo único de conteúdo para verificação de leitura completa."]
    )
    resultado = ler_documento_word(sb("doc_leitura.docx"))
    assert "Documento de Leitura" in resultado, resultado
    assert "verificação" in resultado, resultado
    assert "palavras" in resultado.lower(), resultado


def test_DOC_010_substituir_texto():
    """DOC-010: Localizar e substituir palavra-chave no documento."""
    criar_documento_word(
        sb("doc_substituicao.docx"),
        titulo="Contrato de Serviço",
        paragrafos=["O cliente PLACEHOLDER concorda com os termos estabelecidos neste documento."]
    )
    resultado = editar_documento_word(
        sb("doc_substituicao.docx"),
        substituir_de="PLACEHOLDER",
        substituir_para="João Silva"
    )
    assert "substituição" in resultado.lower() or "editado" in resultado.lower(), resultado
    leitura = ler_documento_word(sb("doc_substituicao.docx"))
    assert "João Silva" in leitura, f"Substituição não aplicada: {leitura}"
    assert "PLACEHOLDER" not in leitura, "PLACEHOLDER ainda presente"


def test_DOC_011_adicionar_paragrafos_ao_existente():
    """DOC-011: Adicionar parágrafos ao final de documento existente."""
    criar_documento_word(
        sb("doc_adicao.docx"),
        titulo="Documento Base",
        paragrafos=["Conteúdo original do documento."]
    )
    resultado = editar_documento_word(
        sb("doc_adicao.docx"),
        adicionar_titulo="Nova Seção",
        adicionar_paragrafos=["Primeiro parágrafo adicionado.", "Segundo parágrafo adicionado."]
    )
    assert "adicionado" in resultado.lower() or "editado" in resultado.lower(), resultado
    leitura = ler_documento_word(sb("doc_adicao.docx"))
    assert "Nova Seção" in leitura, leitura
    assert "Primeiro parágrafo adicionado" in leitura, leitura


def test_DOC_012_salvar_com_acento_no_caminho():
    """DOC-012: Salvar documento em subpasta com caracteres acentuados."""
    caminho_acento = str(SANDBOX / "relatórios" / "ata_reunião_2026.docx")
    resultado = criar_documento_word(
        caminho_acento,
        titulo="Ata de Reunião",
        paragrafos=["Reunião realizada em outubro de 2026."]
    )
    assert Path(caminho_acento).exists(), f"Falhou com caminho acentuado: {resultado}"


def test_DOC_013_ler_documento_inexistente():
    """DOC-013: Ler documento inexistente — mensagem de erro amigável."""
    resultado = ler_documento_word(sb("nao_existe.docx"))
    assert any(kw in resultado.lower() for kw in ["não encontrado", "nao encontrado", "inexistente"]), \
        f"Erro não amigável: {resultado}"


def test_DOC_014_editar_preserva_conteudo_anterior():
    """DOC-014: Edição incremental preserva o conteúdo original."""
    criar_documento_word(
        sb("doc_incremental.docx"),
        titulo="Documento Incremental",
        paragrafos=["Conteúdo original que NÃO deve ser apagado."]
    )
    editar_documento_word(
        sb("doc_incremental.docx"),
        adicionar_paragrafos=["Conteúdo novo adicionado posteriormente."]
    )
    leitura = ler_documento_word(sb("doc_incremental.docx"))
    assert "NÃO deve ser apagado" in leitura, f"Conteúdo original perdido: {leitura}"
    assert "Conteúdo novo" in leitura, f"Conteúdo novo ausente: {leitura}"


def test_DOC_015_abrir_documento_sem_crash():
    """DOC-015: Chamar abrir_documento_word não lança exceção (Word pode não estar instalado)."""
    criar_documento_word(
        sb("doc_abertura.docx"),
        titulo="Documento para Abertura",
        paragrafos=["Teste de abertura do documento no aplicativo padrão."]
    )
    resultado = abrir_documento_word(sb("doc_abertura.docx"))
    assert isinstance(resultado, str), "Resultado não é string"
    assert len(resultado) > 5
