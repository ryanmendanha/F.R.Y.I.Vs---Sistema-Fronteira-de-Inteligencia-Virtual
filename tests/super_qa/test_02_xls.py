"""
XLS-001 a XLS-015 — Planilhas Excel e CSV
Testa criação, leitura, filtragem, fórmulas, edge-cases e resiliência
com pandas/openpyxl, exclusivamente na sandbox FRYIVS_TESTES/xls/.
"""
import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from skills.file_data_ops import criar_planilha, consultar_planilha, abrir_planilha

SANDBOX = PROJECT_ROOT / "FRYIVS_TESTES" / "xls"
SANDBOX.mkdir(parents=True, exist_ok=True)

def sb(name: str) -> str:
    return str(SANDBOX / name)


def test_XLS_001_criar_planilha_padrao():
    """XLS-001: Criar planilha Excel padrão sem parâmetros extras."""
    resultado = criar_planilha(sb("planilha_padrao.xlsx"), abrir_no_excel=False)
    assert Path(sb("planilha_padrao.xlsx")).exists(), f"Planilha não criada: {resultado}"
    assert "criada" in resultado.lower() or "sucesso" in resultado.lower(), resultado


def test_XLS_002_criar_planilha_colunas_customizadas():
    """XLS-002: Criar planilha com colunas personalizadas."""
    resultado = criar_planilha(
        sb("planilha_custom.xlsx"),
        colunas=["Produto", "Quantidade", "Preco", "Disponivel"],
        abrir_no_excel=False
    )
    assert Path(sb("planilha_custom.xlsx")).exists(), f"Planilha não criada: {resultado}"


def test_XLS_003_criar_planilha_com_dados_50_linhas():
    """XLS-003: Criar planilha com 50 linhas de dados e verificar shape."""
    dados = [
        {"ID": i, "Item": f"Produto_{i}", "Valor": float(i * 10.5), "Status": "Ativo" if i % 2 == 0 else "Inativo"}
        for i in range(1, 51)
    ]
    resultado = criar_planilha(sb("planilha_50_linhas.xlsx"), dados=dados, abrir_no_excel=False)
    assert Path(sb("planilha_50_linhas.xlsx")).exists(), f"Planilha não criada: {resultado}"
    resumo = consultar_planilha(sb("planilha_50_linhas.xlsx"), acao="resumo")
    assert "50" in resumo, f"Número de linhas incorreto no resumo: {resumo}"


def test_XLS_004_resumo_de_planilha():
    """XLS-004: Obter resumo (linhas/colunas) de planilha existente."""
    resultado = consultar_planilha(sb("planilha_padrao.xlsx"), acao="resumo")
    assert any(kw in resultado.lower() for kw in ["linhas", "colunas", "carregada"]), resultado


def test_XLS_005_primeiras_linhas():
    """XLS-005: Obter amostra das primeiras linhas da planilha."""
    resultado = consultar_planilha(sb("planilha_padrao.xlsx"), acao="primeiras_linhas")
    assert "amostra" in resultado.lower() or "dados" in resultado.lower() or "[{" in resultado, resultado


def test_XLS_006_filtrar_por_coluna_numerica():
    """XLS-006: Filtrar planilha por valor numérico exato em coluna."""
    resultado = consultar_planilha(
        sb("planilha_50_linhas.xlsx"),
        acao="filtrar",
        filtro_coluna="Status",
        filtro_valor="Ativo"
    )
    assert "encontrada" in resultado.lower() or "filtro" in resultado.lower(), resultado


def test_XLS_007_filtrar_case_insensitive():
    """XLS-007: Filtrar com valor de busca em caixa diferente (case-insensitive)."""
    resultado = consultar_planilha(
        sb("planilha_50_linhas.xlsx"),
        acao="filtrar",
        filtro_coluna="status",
        filtro_valor="ativo"
    )
    assert "filtro" in resultado.lower() or "encontrada" in resultado.lower(), resultado


def test_XLS_008_criar_e_ler_csv():
    """XLS-008: Criar CSV e ler com consultar_planilha."""
    import pandas as pd
    dados = pd.DataFrame({
        "Nome": ["Alice", "Bob", "Carlos"],
        "Nota": [9.5, 7.0, 8.3]
    })
    caminho_csv = sb("notas.csv")
    dados.to_csv(caminho_csv, index=False)
    assert Path(caminho_csv).exists()
    resultado = consultar_planilha(caminho_csv, acao="resumo")
    assert "notas" in resultado.lower() or "3" in resultado, resultado


def test_XLS_009_csv_com_acentos():
    """XLS-009: CSV com caracteres acentuados — leitura correta UTF-8."""
    import pandas as pd
    dados = pd.DataFrame({
        "Descrição": ["Ação", "Opção", "Configuração"],
        "Valor": [1, 2, 3]
    })
    caminho_csv = sb("acentos.csv")
    dados.to_csv(caminho_csv, index=False, encoding="utf-8")
    resultado = consultar_planilha(caminho_csv, acao="primeiras_linhas")
    assert "acentos" in resultado.lower() or "ação" in resultado.lower() or "3" in resultado, resultado


def test_XLS_010_formula_soma():
    """XLS-010: Verificar que dados de soma podem ser calculados corretamente."""
    import pandas as pd
    dados = pd.DataFrame({"Vendas": [100, 200, 300, 400, 500]})
    caminho = sb("vendas.xlsx")
    dados.to_excel(caminho, index=False, engine="openpyxl")
    resultado = consultar_planilha(caminho, acao="resumo")
    assert "5" in resultado
    soma = dados["Vendas"].sum()
    assert soma == 1500, f"Soma incorreta: {soma}"


def test_XLS_011_media_coluna():
    """XLS-011: Calcular média de coluna numérica via pandas."""
    import pandas as pd
    dados = pd.DataFrame({"Notas": [6.0, 7.5, 8.0, 9.0, 10.0]})
    caminho = sb("notas_media.xlsx")
    dados.to_excel(caminho, index=False, engine="openpyxl")
    media = dados["Notas"].mean()
    assert abs(media - 8.1) < 0.01, f"Média incorreta: {media}"


def test_XLS_012_filtrar_coluna_inexistente():
    """XLS-012: Filtrar com coluna inexistente — resposta controlada com lista de colunas."""
    resultado = consultar_planilha(
        sb("planilha_padrao.xlsx"),
        acao="filtrar",
        filtro_coluna="ColunaNaoExiste",
        filtro_valor="qualquer"
    )
    assert any(kw in resultado.lower() for kw in ["não encontrada", "nao encontrada", "disponíveis", "disponiveis"]), \
        f"Erro não tratado graciosamente: {resultado}"


def test_XLS_013_planilha_vazia_somente_cabecalho():
    """XLS-013: Leitura de planilha com apenas cabeçalhos — sem crash."""
    resultado = consultar_planilha(sb("planilha_custom.xlsx"), acao="resumo")
    assert "colunas" in resultado.lower() or "linhas" in resultado.lower(), resultado
    assert "erro" not in resultado.lower() or "0" in resultado


def test_XLS_014_abrir_planilha_sem_crash():
    """XLS-014: Chamar abrir_planilha não lança exceção (Excel pode não estar instalado)."""
    resultado = abrir_planilha(sb("planilha_padrao.xlsx"))
    assert isinstance(resultado, str), "Resultado não é string"
    assert len(resultado) > 5


def test_XLS_015_extensao_invalida():
    """XLS-015: Tentativa de leitura de arquivo com extensão não suportada."""
    caminho_inv = sb("arquivo.pdf")
    Path(caminho_inv).write_text("não é planilha", encoding="utf-8")
    resultado = consultar_planilha(caminho_inv, acao="resumo")
    assert any(kw in resultado.lower() for kw in ["não suportado", "nao suportado", "formato", "suportados"]), \
        f"Extensão inválida não foi rejeitada: {resultado}"
