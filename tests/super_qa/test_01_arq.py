"""
ARQ-001 a ARQ-015 — Arquivos no PC
Testa criação, leitura, cópia, movimentação, renomeação, listagem, exclusão
e bloqueios de segurança, exclusivamente dentro da sandbox FRYIVS_TESTES/.
"""
import os
import shutil
import time
from pathlib import Path
import pytest

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from skills.file_data_ops import gerenciar_arquivos

SANDBOX = PROJECT_ROOT / "FRYIVS_TESTES" / "arq"
SANDBOX.mkdir(parents=True, exist_ok=True)

def sb(name: str) -> str:
    """Retorna caminho absoluto dentro da sandbox ARQ."""
    return str(SANDBOX / name)


# ── ARQ-001 ──────────────────────────────────────────────────────────────────
def test_ARQ_001_criar_pasta():
    """ARQ-001: Criar pasta simples na sandbox."""
    resultado = gerenciar_arquivos("criar_pasta", sb("lote1"))
    assert "criado" in resultado.lower() or Path(sb("lote1")).exists(), resultado


# ── ARQ-002 ──────────────────────────────────────────────────────────────────
def test_ARQ_002_criar_arquivo_texto():
    """ARQ-002: Criar arquivo de texto UTF-8 simples."""
    caminho = sb("lote1/teste_utf8.txt")
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    Path(caminho).write_text("Conteúdo de teste com acentuação: áéíóú ção 🚀", encoding="utf-8")
    assert Path(caminho).exists(), "Arquivo não foi criado"
    conteudo = Path(caminho).read_text(encoding="utf-8")
    assert "áéíóú" in conteudo


# ── ARQ-003 ──────────────────────────────────────────────────────────────────
def test_ARQ_003_ler_arquivo_existente():
    """ARQ-003: Ler conteúdo de arquivo existente com integridade."""
    caminho = sb("lote1/teste_utf8.txt")
    assert Path(caminho).exists(), "Pré-condição: arquivo deve existir (rode ARQ-002 primeiro)"
    conteudo = Path(caminho).read_text(encoding="utf-8")
    assert len(conteudo) > 10, "Arquivo parece vazio"
    assert "teste" in conteudo.lower() or "conteúdo" in conteudo.lower()


# ── ARQ-004 ──────────────────────────────────────────────────────────────────
def test_ARQ_004_copiar_arquivo():
    """ARQ-004: Copiar arquivo para subpasta de destino."""
    origem = sb("lote1/teste_utf8.txt")
    destino = sb("lote1/copia/teste_copia.txt")
    if not Path(origem).exists():
        Path(origem).parent.mkdir(parents=True, exist_ok=True)
        Path(origem).write_text("arquivo origem para cópia", encoding="utf-8")
    resultado = gerenciar_arquivos("copiar", origem, destino)
    assert Path(destino).exists(), f"Cópia falhou: {resultado}"


# ── ARQ-005 ──────────────────────────────────────────────────────────────────
def test_ARQ_005_mover_arquivo():
    """ARQ-005: Mover arquivo entre diretórios."""
    origem = sb("lote1/para_mover.txt")
    destino = sb("lote1/movido/arquivo_movido.txt")
    Path(origem).parent.mkdir(parents=True, exist_ok=True)
    Path(origem).write_text("arquivo a ser movido", encoding="utf-8")
    resultado = gerenciar_arquivos("mover", origem, destino)
    assert Path(destino).exists(), f"Mover falhou: {resultado}"
    assert not Path(origem).exists(), "Arquivo original ainda existe após mover"


# ── ARQ-006 ──────────────────────────────────────────────────────────────────
def test_ARQ_006_renomear_com_acento_e_espaco():
    """ARQ-006: Renomear arquivo com acento e espaço no nome."""
    original = sb("lote1/relatorio final.txt")
    renomeado = sb("lote1/relatorio_v2.txt")
    Path(original).parent.mkdir(parents=True, exist_ok=True)
    Path(original).write_text("conteúdo do relatório", encoding="utf-8")
    resultado = gerenciar_arquivos("mover", original, renomeado)
    assert Path(renomeado).exists(), f"Renomeação falhou: {resultado}"
    conteudo = Path(renomeado).read_text(encoding="utf-8")
    assert "conteúdo" in conteudo, "Conteúdo corrompido após renomeação"


# ── ARQ-007 ──────────────────────────────────────────────────────────────────
def test_ARQ_007_listar_diretorio():
    """ARQ-007: Listar diretório contendo arquivos e pastas."""
    resultado = gerenciar_arquivos("listar", sb("lote1"))
    assert "arq" in resultado.lower() or "." in resultado or len(resultado) > 5, resultado


# ── ARQ-008 ──────────────────────────────────────────────────────────────────
def test_ARQ_008_arvore_pastas_aninhadas():
    """ARQ-008: Criar árvore com 4 níveis de profundidade."""
    caminho_profundo = sb("nivel1/nivel2/nivel3/nivel4")
    resultado = gerenciar_arquivos("criar_pasta", caminho_profundo)
    assert Path(caminho_profundo).exists(), f"Árvore de pastas falhou: {resultado}"


# ── ARQ-009 ──────────────────────────────────────────────────────────────────
def test_ARQ_009_copiar_diretorio_recursivo():
    """ARQ-009: Copiar diretório completo com múltiplos arquivos."""
    origem_dir = sb("origem_recursiva")
    destino_dir = sb("destino_recursiva")
    Path(origem_dir).mkdir(parents=True, exist_ok=True)
    for i in range(5):
        (Path(origem_dir) / f"arq_{i}.txt").write_text(f"conteudo {i}", encoding="utf-8")
    resultado = gerenciar_arquivos("copiar", origem_dir, destino_dir)
    arquivos_destino = list(Path(destino_dir).glob("*.txt"))
    assert len(arquivos_destino) == 5, f"Esperado 5 arquivos, obtido {len(arquivos_destino)}: {resultado}"


# ── ARQ-010 ──────────────────────────────────────────────────────────────────
def test_ARQ_010_deletar_arquivo_sandbox():
    """ARQ-010: Deletar arquivo dentro da sandbox de forma segura."""
    alvo = sb("para_deletar.txt")
    Path(alvo).parent.mkdir(parents=True, exist_ok=True)
    Path(alvo).write_text("arquivo descartável", encoding="utf-8")
    resultado = gerenciar_arquivos("deletar", alvo)
    assert not Path(alvo).exists(), f"Arquivo não foi deletado: {resultado}"


# ── ARQ-011 ──────────────────────────────────────────────────────────────────
def test_ARQ_011_deletar_diretorio_sandbox():
    """ARQ-011: Deletar diretório completo dentro da sandbox."""
    alvo = sb("pasta_descartavel")
    Path(alvo).mkdir(parents=True, exist_ok=True)
    (Path(alvo) / "arq.txt").write_text("temp", encoding="utf-8")
    resultado = gerenciar_arquivos("deletar", alvo)
    assert not Path(alvo).exists(), f"Pasta não foi deletada: {resultado}"


# ── ARQ-012 ──────────────────────────────────────────────────────────────────
def test_ARQ_012_ler_arquivo_inexistente():
    """ARQ-012: Tentativa de operação em arquivo inexistente — espera erro amigável."""
    caminho_fantasma = sb("nao_existe_de_jeito_nenhum.txt")
    resultado = gerenciar_arquivos("mover", caminho_fantasma, sb("destino_fantasma.txt"))
    assert any(kw in resultado.lower() for kw in ["não encontrad", "nao encontrad", "inexistente", "origem"]), \
        f"Erro não foi amigável: {resultado}"


# ── ARQ-013 ──────────────────────────────────────────────────────────────────
def test_ARQ_013_deletar_caminho_inexistente():
    """ARQ-013: Deletar caminho inexistente — deve retornar mensagem controlada."""
    resultado = gerenciar_arquivos("deletar", sb("fantasma_delete.txt"))
    assert any(kw in resultado.lower() for kw in ["não exist", "nao exist", "não encontrad"]), \
        f"Resposta inesperada: {resultado}"


# ── ARQ-014 ──────────────────────────────────────────────────────────────────
def test_ARQ_014_bloqueio_caminho_protegido():
    """ARQ-014: Bloqueio de segurança para caminho protegido do Windows."""
    resultado = gerenciar_arquivos("deletar", r"C:\Windows")
    assert any(kw in resultado.lower() for kw in ["bloqueado", "protegido", "segurança"]), \
        f"Proteção de segurança não ativou: {resultado}"


# ── ARQ-015 ──────────────────────────────────────────────────────────────────
def test_ARQ_015_caracteres_especiais_no_nome():
    """ARQ-015: Criar e renomear arquivo com caracteres especiais no nome."""
    original = sb("arquivo_especial_#@!$.txt")
    destino = sb("arquivo_especial_renomeado.txt")
    Path(original).parent.mkdir(parents=True, exist_ok=True)
    Path(original).write_text("dados especiais", encoding="utf-8")
    resultado = gerenciar_arquivos("mover", original, destino)
    assert Path(destino).exists(), f"Renomeação com char especial falhou: {resultado}"
    conteudo = Path(destino).read_text(encoding="utf-8")
    assert "dados" in conteudo
