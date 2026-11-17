"""
Módulo de Operações de Arquivos, Planilhas Excel e Documentos Word para F.R.Y.I.Vs.
Utiliza pathlib e shutil para manipulação segura do sistema de arquivos,
pandas + openpyxl para análise e filtragem veloz de dados em Excel (.xlsx) e CSV,
e python-docx para criação, edição e leitura de documentos Word (.docx).
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any, Final, Literal
from pydantic import BaseModel, Field

try:
    import pandas as pd
    import openpyxl
except ImportError:
    pd = None
    openpyxl = None

try:
    import docx as _docx
    from docx import Document as _Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    _DOCX_AVAILABLE = True
except ImportError:
    _docx = None
    _Document = None
    _DOCX_AVAILABLE = False

# Diretórios protegidos contra exclusão acidental
_PROTECTED_PATHS: Final[set[str]] = {
    "c:\\", "c:\\windows", "c:\\windows\\system32", "c:\\program files",
    "c:\\program files (x86)", os.environ.get("SYSTEMROOT", "c:\\windows").lower()
}

# Pasta padrão onde TODAS as planilhas criadas pela FRYIVS são salvas
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
PLANILHAS_DIR: Final[Path] = PROJECT_ROOT / "planilhas-fryivs"


def _normalizar_nome_xlsx(nome: str) -> str:
    nome = (nome or "").strip().strip('"').strip("'")
    if not nome:
        nome = "planilha_fryivs"
    if not nome.lower().endswith((".xlsx", ".xlsm", ".csv")):
        nome = f"{nome}.xlsx"
    return nome


def _caminho_nova_planilha(nome: str) -> Path:
    """
    Destino de uma planilha NOVA:
    - Se o caminho informado contém diretório explícito, respeita o diretório.
    - Caso seja apenas um nome de arquivo, salva dentro de planilhas-fryivs.
    """
    bruto = str(nome or "").strip().strip('"').strip("'")
    norm = _normalizar_nome_xlsx(bruto)
    p_cand = Path(norm)
    if p_cand.parent != Path("."):
        p_cand.parent.mkdir(parents=True, exist_ok=True)
        return p_cand.resolve()
    PLANILHAS_DIR.mkdir(parents=True, exist_ok=True)
    return PLANILHAS_DIR / p_cand.name


def _localizar_planilha(nome: str) -> Path | None:
    """Localiza uma planilha existente: caminho informado, artefato ativo, planilhas-fryivs ou raiz do projeto."""
    bruto = str(nome or "").strip().strip('"').strip("'")
    if bruto.lower() in ("", "atual", "ativa", "planilha_atual", "planilha_ativa", "planilha", "este", "esta"):
        try:
            from core.session_state import obter_artefato
            ativo = obter_artefato("excel")
            if ativo and ativo.get("caminho"):
                p_at = Path(str(ativo["caminho"]))
                if p_at.exists() and p_at.is_file():
                    return p_at.resolve()
        except Exception:
            pass
        if not bruto:
            return None
    candidatos = [Path(bruto)]
    if not Path(bruto).suffix:
        candidatos.append(Path(_normalizar_nome_xlsx(bruto)))
    for c in list(candidatos):
        candidatos.append(PLANILHAS_DIR / c.name)
        candidatos.append(PROJECT_ROOT / c.name)
    for c in candidatos:
        try:
            if c.exists() and c.is_file():
                return c.resolve()
        except OSError:
            continue
    return None


def _parse_estrutura(valor: Any) -> Any:
    """Converte listas/dicts enviados como string pela LLM (JSON ou literal Python)."""
    if not isinstance(valor, str):
        return valor
    s = valor.strip()
    if s.lower() in ("null", "none", "", "[]", "{}"):
        return None
    import json
    import ast
    try:
        return json.loads(s)
    except Exception:
        pass
    try:
        return ast.literal_eval(s)
    except Exception:
        return valor


def _coagir_valor(v: Any) -> Any:
    """Converte '150' / '150,50' em número; mantém texto caso contrário."""
    if not isinstance(v, str):
        return v
    s = v.strip()
    if s == "":
        return s
    try:
        if s.lstrip("-").isdigit():
            return int(s)
        return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)
    except ValueError:
        return v


def _achar_coluna(colunas: list[Any], nome: str | None) -> Any:
    if not nome:
        return None
    alvo = str(nome).strip().lower()
    return next((c for c in colunas if str(c).strip().lower() == alvo), None)


def _fechar_no_excel_se_aberto(caminho: Path) -> bool:
    """Fecha o workbook no Excel (sem salvar) caso ele esteja travando o arquivo."""
    try:
        from skills.office_live import fechar_planilha_live
        if fechar_planilha_live(caminho):
            time.sleep(0.15)
            return True
    except Exception:
        pass
    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        try:
            excel = win32com.client.GetActiveObject("Excel.Application")
            alvo = str(caminho.resolve()).lower()
            nome_alvo = caminho.name.lower()
            for wb in list(excel.Workbooks):
                if str(wb.FullName).lower() == alvo or str(wb.Name).lower() == nome_alvo:
                    wb.Close(SaveChanges=False)
                    time.sleep(0.15)
                    return True
        finally:
            pythoncom.CoUninitialize()
    except Exception:
        pass
    return False


def _aplicar_estilo_executivo(p: Path) -> None:
    """Aplica o layout executivo (cabeçalho navy, zebra, bordas, moeda, auto-filtro)."""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.load_workbook(p)
    ws = wb.active

    fill_header = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    font_header = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    font_corpo = Font(name="Segoe UI", size=10)
    fill_zebra = PatternFill(start_color="F2F5F9", end_color="F2F5F9", fill_type="solid")
    fill_vazio = PatternFill(fill_type=None)
    thin_side = Side(border_style="thin", color="D9D9D9")
    borda_padrao = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    ws.row_dimensions[1].height = 28
    for cell in ws[1]:
        cell.fill = fill_header
        cell.font = font_header
        cell.alignment = align_center
        cell.border = borda_padrao

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, max_row=ws.max_row), start=2):
        ws.row_dimensions[row_idx].height = 20
        for cell in row:
            cell.font = font_corpo
            cell.border = borda_padrao
            cell.fill = fill_zebra if row_idx % 2 == 0 else fill_vazio
            val = cell.value
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                cell.alignment = align_right
                col_header = str(ws.cell(row=1, column=cell.column).value or "").lower()
                if any(t in col_header for t in ["r$", "valor", "preco", "preço", "total", "custo", "receita", "entrada", "saida", "saída", "saldo"]):
                    cell.number_format = 'R$ #,##0.00'
                elif "%" in col_header or "taxa" in col_header:
                    cell.number_format = '0.00%'
            elif str(val).strip().lower() in ["concluído", "concluido", "pago", "aprovado", "ativo"]:
                cell.alignment = align_center
            else:
                cell.alignment = align_left

    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = max((len(str(c.value or "")) for c in col), default=0)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    ws.auto_filter.ref = ws.dimensions
    wb.save(p)


# ── Schemas Pydantic ────────────────────────────────────────────────────────

class GerenciarArquivosParams(BaseModel):
    acao: Literal["copiar", "mover", "deletar", "criar_pasta", "listar"] = Field(
        ...,
        description="Ação a executar: 'copiar', 'mover', 'deletar', 'criar_pasta' ou 'listar'"
    )
    origem: str = Field(..., description="Caminho do arquivo ou pasta de origem")
    destino: str | None = Field(
        default=None,
        description="Caminho de destino (obrigatório para ações 'copiar' e 'mover')"
    )


class ConsultarPlanilhaParams(BaseModel):
    caminho_arquivo: str = Field(..., description="Caminho do arquivo Excel (.xlsx, .xls) ou CSV")
    acao: Literal["resumo", "primeiras_linhas", "filtrar"] = Field(
        default="resumo",
        description="Tipo de análise: 'resumo' (linhas/colunas), 'primeiras_linhas' ou 'filtrar'"
    )
    filtro_coluna: str | None = Field(
        default=None,
        description="Nome da coluna para aplicar filtro (usado com acao='filtrar')"
    )
    filtro_valor: str | None = Field(
        default=None,
        description="Valor a procurar na coluna filtrada"
    )


# ── Funções Executáveis ─────────────────────────────────────────────────────

def gerenciar_arquivos(acao: str, origem: str, destino: str | None = None) -> str:
    """
    Executa ações seguras no sistema de arquivos usando pathlib e shutil.
    """
    try:
        p_origem = Path(origem).resolve()
        acao_limpa = acao.lower().strip()

        # Proteção contra deleção de diretórios vitais do Windows
        if acao_limpa == "deletar":
            caminho_str = str(p_origem).lower()
            if caminho_str in _PROTECTED_PATHS or len(p_origem.parts) <= 2:
                return f"Operação bloqueada por segurança: o caminho '{p_origem}' é protegido pelo sistema."

            if not p_origem.exists():
                return f"O item especificado para deletar não existe: '{p_origem}'"

            if p_origem.is_dir():
                shutil.rmtree(p_origem)
                return f"Pasta e seus conteúdos removidos com sucesso: '{p_origem}'"
            else:
                p_origem.unlink()
                return f"Arquivo removido com sucesso: '{p_origem}'"

        if acao_limpa == "criar_pasta":
            p_origem.mkdir(parents=True, exist_ok=True)
            return f"Diretório criado com sucesso: '{p_origem}'"

        if acao_limpa == "listar":
            if not p_origem.exists() or not p_origem.is_dir():
                return f"Diretório não encontrado: '{p_origem}'"
            itens = [f"[{'PASTA' if item.is_dir() else 'ARQ'}] {item.name}" for item in p_origem.iterdir()]
            itens_limitados = itens[:25]
            resto = len(itens) - len(itens_limitados)
            txt = ", ".join(itens_limitados)
            if resto > 0:
                txt += f" e mais {resto} itens."
            return f"Conteúdo do diretório ({p_origem.name}): {txt}"

        # Operações que requerem destino
        if not destino:
            return f"A ação '{acao}' requer o parâmetro 'destino'."

        p_destino = Path(destino).resolve()
        p_destino.parent.mkdir(parents=True, exist_ok=True)

        if not p_origem.exists():
            return f"Origem não encontrada: '{p_origem}'"

        if acao_limpa == "copiar":
            if p_origem.is_dir():
                shutil.copytree(p_origem, p_destino, dirs_exist_ok=True)
                return f"Pasta copiada com sucesso de '{p_origem.name}' para '{p_destino}'"
            else:
                shutil.copy2(p_origem, p_destino)
                return f"Arquivo copiado com sucesso para: '{p_destino}'"

        if acao_limpa == "mover":
            shutil.move(str(p_origem), str(p_destino))
            return f"Item movido com sucesso para: '{p_destino}'"

        return f"Ação desconhecida: '{acao}'. Use copiar, mover, deletar, criar_pasta ou listar."
    except Exception as e:
        return f"Falha na operação de arquivos: {e}"


def consultar_planilha(
    caminho_arquivo: str,
    acao: str = "resumo",
    filtro_coluna: str | None = None,
    filtro_valor: str | None = None
) -> str:
    """
    Lê e processa planilhas Excel (.xlsx) e CSVs com Pandas e OpenPyXL.
    """
    if pd is None:
        return "Erro: A biblioteca Pandas é necessária para processar planilhas."

    try:
        caminho = _localizar_planilha(caminho_arquivo)
        if caminho is None:
            return f"Arquivo de planilha não encontrado: '{caminho_arquivo}' (procurado também em '{PLANILHAS_DIR.name}')."

        # Carregar arquivo com base na extensão
        ext = caminho.suffix.lower()
        if ext in (".xlsx", ".xlsm", ".xltx", ".xltm"):
            df = pd.read_excel(caminho, engine="openpyxl")
        elif ext == ".csv":
            df = pd.read_csv(caminho)
        else:
            return f"Formato de arquivo não suportado: '{ext}'. Use .xlsx ou .csv."

        linhas, colunas = df.shape
        col_nomes = list(df.columns)

        if acao == "resumo":
            return (
                f"Planilha '{caminho.name}' carregada com sucesso. "
                f"Total de {linhas} linhas e {colunas} colunas. "
                f"Colunas presentes: {', '.join(map(str, col_nomes[:10]))}."
            )

        if acao == "primeiras_linhas":
            preview = df.head(3).to_dict(orient="records")
            return f"Amostra dos primeiros dados da planilha '{caminho.name}':\n{preview}"

        if acao == "filtrar":
            if not filtro_coluna or filtro_valor is None:
                return "Para filtrar a planilha, informe 'filtro_coluna' e 'filtro_valor'."

            # Busca case-insensitive no nome da coluna
            col_match = next((c for c in col_nomes if str(c).lower() == filtro_coluna.lower()), None)
            if not col_match:
                return f"Coluna '{filtro_coluna}' não encontrada. Colunas disponíveis: {col_nomes}"

            # Filtrar
            filtrado = df[df[col_match].astype(str).str.contains(str(filtro_valor), case=False, na=False)]
            total_matches = len(filtrado)
            amostra = filtrado.head(3).to_dict(orient="records")

            return (
                f"Filtro aplicado na coluna '{col_match}' por '{filtro_valor}': "
                f"Foram encontradas {total_matches} linhas correspondentes. Amostra: {amostra}"
            )

        return f"Ação de planilha desconhecida: '{acao}'."
    except Exception as e:
        return f"Erro ao processar planilha com Pandas/OpenPyXL: {e}"


def _find_excel_exe() -> str | None:
    """
    Localiza o executável do Microsoft Excel procurando no Registro do Windows
    e em caminhos conhecidos das versões Office 2016, 2019, 2021 e 365.
    """
    import subprocess
    # 1. Busca pelo Registro do Windows (método mais confiável)
    try:
        import winreg
        key_paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\EXCEL.EXE",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\EXCEL.EXE",
        ]
        for key_path in key_paths:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        val, _ = winreg.QueryValueEx(key, "")
                        if val and os.path.exists(str(val)):
                            return str(val)
                except (FileNotFoundError, OSError):
                    continue
    except Exception:
        pass

    # 2. Caminhos absolutos para todas as versões do Office
    excel_candidates = [
        r"C:\Program Files\Microsoft Office\Office16\EXCEL.EXE",
        r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
        r"C:\Program Files\Microsoft Office\Office15\EXCEL.EXE",
        r"C:\Program Files\Microsoft Office\root\Office15\EXCEL.EXE",
        r"C:\Program Files (x86)\Microsoft Office\Office16\EXCEL.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\EXCEL.EXE",
        r"C:\Program Files (x86)\Microsoft Office\Office15\EXCEL.EXE",
        # Office 365 / 2021 Click-to-Run
        os.path.expandvars(r"%ProgramFiles%\Microsoft Office\root\Office16\EXCEL.EXE"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft Office\root\Office16\EXCEL.EXE"),
    ]
    for c in excel_candidates:
        if c and os.path.exists(c):
            return c

    # 3. Fallback via shutil.which
    import shutil
    return shutil.which("EXCEL.EXE") or shutil.which("excel")


def abrir_planilha(caminho_arquivo: str | None = None) -> str:
    """
    Abre o Microsoft Excel em segundo plano (visível na tela sem roubar o foco)
    e ativa o indicador flutuante FRY.png.
    Usa automação Windows COM (office_live) como método primário e os.startfile como fallback.
    """
    caminho_abs = None
    if caminho_arquivo and str(caminho_arquivo).strip():
        encontrado = _localizar_planilha(str(caminho_arquivo))
        if encontrado is None:
            return f"Planilha '{caminho_arquivo}' não encontrada (procurada também em '{PLANILHAS_DIR.name}')."
        caminho_abs = str(encontrado)
        try:
            from core.session_state import registrar_artefato
            registrar_artefato("excel", caminho=caminho_abs)
        except Exception:
            pass

    # 1. Método Primário: Office Live STA COM (sem roubar foco + barra FRY.png)
    try:
        from skills.office_live import abrir_planilha_live
        ok, msg_live = abrir_planilha_live(Path(caminho_abs) if caminho_abs else None, sem_foco=True)
        if ok:
            return msg_live
    except Exception as e_com:
        print(f"[abrir_planilha] Aviso no OfficeLive COM: {e_com}. Tentando método nativo...")

    # 2. Método Secundário: os.startfile nativo do Windows
    if caminho_abs and os.path.exists(caminho_abs):
        try:
            os.startfile(caminho_abs)
            nome = Path(caminho_abs).name
            return f"Planilha '{nome}' aberta no Microsoft Excel com sucesso."
        except Exception:
            pass

    # 3. Método Terciário: subprocess com SW_SHOWNOACTIVATE (4)
    import subprocess
    excel_exe = _find_excel_exe()
    if excel_exe and os.path.exists(excel_exe):
        try:
            cmd = [excel_exe]
            if caminho_abs:
                cmd.append(caminho_abs)

            SW_SHOWNOACTIVATE = 4
            STARTF_USESHOWWINDOW = 0x00000001
            si = subprocess.STARTUPINFO()
            si.dwFlags |= STARTF_USESHOWWINDOW
            si.wShowWindow = SW_SHOWNOACTIVATE

            subprocess.Popen(cmd, startupinfo=si)
            return "Microsoft Excel aberto em segundo plano na tela com sucesso."
        except Exception as e_sub:
            return f"Falha ao abrir Microsoft Excel: {e_sub}"

    return "Não foi possível abrir o Microsoft Excel no sistema."


def criar_planilha(
    caminho_arquivo: str,
    colunas: list[str] | None = None,
    dados: list[dict[str, Any]] | list[list[Any]] | None = None,
    titulo_tabela: str | None = None,
    abrir_no_excel: bool = True,
    aba: str | None = None,
    **_extra: Any,
) -> str:
    """
    Cria uma nova planilha Excel (.xlsx) de padrão profissional:
    - Tipografia executiva (Segoe UI / Calibri)
    - Cabeçalho estilizado com preenchimento escuro elegante e texto contrastante
    - Alinhamentos numéricos e textuais adequados
    - Ajuste automático da largura das colunas
    - Abertura imediata em segundo plano no Microsoft Excel (sem roubar foco).
    """
    if pd is None or openpyxl is None:
        return "Erro: Pandas e OpenPyXL são necessários para criar planilhas."

    try:
        p = _caminho_nova_planilha(str(caminho_arquivo))

        # Normaliza booleanos e argumentos passados como string pela LLM
        if isinstance(abrir_no_excel, str):
            abrir_no_excel = abrir_no_excel.strip().lower() in ("true", "1", "yes", "sim")

        colunas = _parse_estrutura(colunas)
        if isinstance(colunas, str):
            colunas = [c.strip() for c in colunas.split(",") if c.strip()]
        if not isinstance(colunas, list):
            colunas = None

        # Listas enviadas como texto (JSON ou literal Python) são convertidas
        dados_raw = _parse_estrutura(dados)
        dados_norm: list[dict[str, Any]] | None = None
        if isinstance(dados_raw, list) and dados_raw:
            dicts = [d for d in dados_raw if isinstance(d, dict) and any(str(v).strip() for v in d.values())]
            if dicts:
                dados_norm = dicts
            elif colunas and all(isinstance(r, (list, tuple)) for r in dados_raw):
                dados_norm = [
                    {str(colunas[i]): r[i] for i in range(min(len(colunas), len(r)))}
                    for r in dados_raw
                    if any(str(v).strip() for v in r)
                ] or None
        dados = dados_norm

        if dados and isinstance(dados, list) and len(dados) > 0:
            df = pd.DataFrame(dados)
        elif colunas and isinstance(colunas, list) and len(colunas) > 0:
            df = pd.DataFrame(columns=colunas)
        else:
            df = pd.DataFrame({
                "Item": ["Produto A", "Serviço B", "Consultoria C"],
                "Categoria": ["Vendas", "Operacional", "Estratégico"],
                "Quantidade": [10, 5, 2],
                "Valor Unitário (R$)": [150.00, 320.50, 1200.00],
                "Total (R$)": [1500.00, 1602.50, 2400.00],
                "Status": ["Concluído", "Pendente", "Em Andamento"]
            })

        # Salva base com Pandas (só fecha no Excel via COM se o arquivo estiver travado)
        try:
            df.to_excel(p, index=False, engine="openpyxl")
        except PermissionError:
            _fechar_no_excel_se_aberto(p)
            df.to_excel(p, index=False, engine="openpyxl")
        _aplicar_estilo_executivo(p)

        try:
            from core.session_state import registrar_artefato
            registrar_artefato("excel", caminho=str(p), colunas=[str(c) for c in df.columns])
        except Exception:
            pass

        msg = (
            f"Planilha profissional '{p.name}' criada em '{p.parent.name}' "
            f"({len(df.columns)} colunas x {len(df)} linhas) com design executivo e auto-filtro."
        )

        from skills.office_live import _em_teste
        if abrir_no_excel and not _em_teste():
            abrir_planilha(str(p))
            msg += " Aberta em segundo plano no Microsoft Excel."

        return msg
    except Exception as e:
        return f"Falha ao criar planilha: {e}"


def editar_planilha(
    caminho_arquivo: str,
    acao: str,
    dados: Any = None,
    filtro_coluna: str | None = None,
    filtro_valor: Any = None,
    coluna: str | None = None,
    novo_valor: Any = None,
    abrir_no_excel: Any = True,
) -> str:
    """
    Manipula uma planilha existente (padrão: pasta planilhas-fryivs).
    Ações: adicionar_linha, remover_linha, editar_celula, adicionar_coluna, remover_coluna.
    Mantém o layout executivo após cada alteração.
    """
    if pd is None or openpyxl is None:
        return "Erro: Pandas e OpenPyXL são necessários para editar planilhas."

    p = _localizar_planilha(caminho_arquivo)
    if p is None:
        return f"Planilha '{caminho_arquivo}' não encontrada (procurada também em '{PLANILHAS_DIR.name}')."
    if p.suffix.lower() == ".csv":
        return "Edição suportada apenas para arquivos .xlsx."

    if isinstance(abrir_no_excel, str):
        abrir_no_excel = abrir_no_excel.strip().lower() in ("true", "1", "yes", "sim")

    acao = (acao or "").strip().lower()
    try:
        df = pd.read_excel(p, engine="openpyxl")
        cols = list(df.columns)

        def _mascara() -> Any:
            col_f = _achar_coluna(cols, filtro_coluna)
            if col_f is None:
                return None, f"Coluna de filtro '{filtro_coluna}' não encontrada. Colunas: {cols}"
            alvo = str(filtro_valor).strip().lower()
            serie = df[col_f].astype(str).str.strip().str.lower()
            # Normaliza números lidos como float (ex.: '10.0' vs '10')
            serie = serie.str.replace(r"\.0$", "", regex=True)
            alvo = alvo[:-2] if alvo.endswith(".0") else alvo
            return serie == alvo, None

        if acao == "adicionar_linha":
            registros = _parse_estrutura(dados)
            if isinstance(registros, dict):
                registros = [registros]
            if not isinstance(registros, list) or not registros:
                return "Informe 'dados' com a(s) linha(s) a adicionar (ex.: [{'Produto': 'Mouse', 'Quantidade': 3}])."
            novas = []
            for r in registros:
                if not isinstance(r, dict):
                    continue
                linha = {}
                for k, v in r.items():
                    c = _achar_coluna(cols, k) or k
                    linha[c] = _coagir_valor(v)
                novas.append(linha)
            df = pd.concat([df, pd.DataFrame(novas)], ignore_index=True)
            resumo = f"{len(novas)} linha(s) adicionada(s)"

        elif acao == "remover_linha":
            mask, erro = _mascara()
            if erro:
                return erro
            qtd = int(mask.sum())
            if qtd == 0:
                return f"Nenhuma linha com '{filtro_coluna}' = '{filtro_valor}' encontrada. Nada foi removido."
            df = df[~mask].reset_index(drop=True)
            resumo = f"{qtd} linha(s) removida(s) onde '{filtro_coluna}' = '{filtro_valor}'"

        elif acao == "editar_celula":
            col_alvo = _achar_coluna(cols, coluna)
            if col_alvo is None:
                return f"Coluna a editar '{coluna}' não encontrada. Colunas: {cols}"
            mask, erro = _mascara()
            if erro:
                return erro
            qtd = int(mask.sum())
            if qtd == 0:
                return f"Nenhuma linha com '{filtro_coluna}' = '{filtro_valor}' encontrada. Nada foi editado."
            df[col_alvo] = df[col_alvo].astype(object)
            df.loc[mask, col_alvo] = _coagir_valor(novo_valor)
            resumo = f"'{col_alvo}' atualizado para '{novo_valor}' em {qtd} linha(s)"

        elif acao == "adicionar_coluna":
            if not coluna or not str(coluna).strip():
                return "Informe o nome da nova 'coluna'."
            if _achar_coluna(cols, coluna) is not None:
                return f"A coluna '{coluna}' já existe."
            df[str(coluna).strip()] = _coagir_valor(novo_valor) if novo_valor is not None else ""
            resumo = f"coluna '{coluna}' adicionada"

        elif acao == "remover_coluna":
            col_alvo = _achar_coluna(cols, coluna)
            if col_alvo is None:
                return f"Coluna '{coluna}' não encontrada. Colunas: {cols}"
            df = df.drop(columns=[col_alvo])
            resumo = f"coluna '{col_alvo}' removida"

        else:
            return (
                f"Ação '{acao}' desconhecida. Use: adicionar_linha, remover_linha, "
                "editar_celula, adicionar_coluna ou remover_coluna."
            )

        from skills.office_live import (
            _em_teste,
            editar_planilha_live,
            esta_aberta_no_excel,
            garantizar_backup_sessao,
        )
        garantizar_backup_sessao(p)

        # Se já estiver aberta no Excel (ou em execução interativa com abrir_no_excel), edita AO VIVO via COM sem fechar
        aberta_agora = False if _em_teste() else esta_aberta_no_excel(p)
        if aberta_agora or (abrir_no_excel and not _em_teste()):
            ok_live, msg_live = editar_planilha_live(p, df, resumo, sem_foco=True)
            if ok_live:
                try:
                    from core.session_state import registrar_artefato
                    registrar_artefato("excel", caminho=str(p), colunas=[str(c) for c in df.columns])
                except Exception:
                    pass
                return msg_live

        # Fallback: grava com openpyxl (fecha se necessário e reabre em 2º plano)
        fechado = _fechar_no_excel_se_aberto(p)
        try:
            df.to_excel(p, index=False, engine="openpyxl")
        except PermissionError:
            return (
                f"A planilha '{p.name}' está aberta e bloqueada em outro programa. "
                "Feche-a e peça novamente."
            )
        _aplicar_estilo_executivo(p)

        try:
            from core.session_state import registrar_artefato
            registrar_artefato("excel", caminho=str(p), colunas=[str(c) for c in df.columns])
        except Exception:
            pass

        msg = f"Planilha '{p.name}' atualizada: {resumo}. Agora com {len(df)} linhas e {len(df.columns)} colunas."
        if (abrir_no_excel or fechado) and not _em_teste():
            abrir_planilha(str(p))
            msg += " Atualizada em segundo plano no Excel."
        return msg
    except Exception as e:
        return f"Falha ao editar planilha: {e}"


# ── Schemas OpenAPI ─────────────────────────────────────────────────────────

FILE_DATA_SCHEMAS: Final[list[dict[str, Any]]] = [
    {
        "type": "function",
        "function": {
            "name": "gerenciar_arquivos",
            "description": "Gerencia arquivos e pastas no computador (copiar, mover, deletar, criar pasta ou listar) de forma segura.",
            "parameters": {
                "type": "object",
                "properties": {
                    "acao": {
                        "type": "string",
                        "enum": ["copiar", "mover", "deletar", "criar_pasta", "listar"],
                        "description": "Ação a ser realizada no sistema de arquivos"
                    },
                    "origem": {
                        "type": "string",
                        "description": "Caminho do arquivo ou pasta de origem"
                    },
                    "destino": {
                        "type": "string",
                        "description": "Caminho de destino (para copiar ou mover)"
                    }
                },
                "required": ["acao", "origem"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_planilha",
            "description": "Abre, analisa e filtra tabelas e planilhas Excel (.xlsx) ou CSV de forma extremamente rápida.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho_arquivo": {
                        "type": "string",
                        "description": "Caminho do arquivo .xlsx ou .csv"
                    },
                    "acao": {
                        "type": "string",
                        "enum": ["resumo", "primeiras_linhas", "filtrar"],
                        "description": "Tipo de consulta ('resumo', 'primeiras_linhas' ou 'filtrar')"
                    },
                    "filtro_coluna": {
                        "type": "string",
                        "description": "Nome da coluna para filtrar (opcional)"
                    },
                    "filtro_valor": {
                        "type": "string",
                        "description": "Valor procurado na coluna (opcional)"
                    }
                },
                "required": ["caminho_arquivo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "criar_planilha",
            "description": "Cria uma nova planilha Excel (.xlsx) personalizada e a abre no Microsoft Excel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho_arquivo": {
                        "type": "string",
                        "description": "Nome ou caminho da planilha (ex: 'vendas_2026.xlsx' ou 'relatorio.xlsx')"
                    },
                    "colunas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista opcional de nomes de colunas (ex: ['Produto', 'Quantidade', 'Preco'])"
                    },
                    "dados": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Lista de registros/linhas a preencher (ex: [{'Produto': 'Teclado', 'Quantidade': 5, 'Preco': 150}])"
                    },
                    "abrir_no_excel": {
                        "type": "boolean",
                        "description": "Se deve abrir a planilha no programa Excel imediatamente (padrão: true)"
                    }
                },
                "required": ["caminho_arquivo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_planilha",
            "description": "Abre o aplicativo Microsoft Excel ou abre um arquivo de planilha existente no Excel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho_arquivo": {
                        "type": "string",
                        "description": "Caminho opcional do arquivo de planilha (.xlsx, .csv). Se omitido, abre o Excel vazio."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "editar_planilha",
            "description": (
                "Edita uma planilha Excel (.xlsx) já existente na pasta planilhas-fryivs: "
                "adiciona linhas, remove linhas, altera valores de células, adiciona ou remove colunas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho_arquivo": {
                        "type": "string",
                        "description": "Nome da planilha existente (ex: 'gestao_financeira.xlsx')"
                    },
                    "acao": {
                        "type": "string",
                        "enum": ["adicionar_linha", "remover_linha", "editar_celula", "adicionar_coluna", "remover_coluna"],
                        "description": "Operação a executar na planilha"
                    },
                    "dados": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Para 'adicionar_linha': lista de linhas (ex: [{'Produto': 'Mouse', 'Quantidade': 3}])"
                    },
                    "filtro_coluna": {
                        "type": "string",
                        "description": "Para 'remover_linha'/'editar_celula': coluna usada para localizar a linha (ex: 'Produto')"
                    },
                    "filtro_valor": {
                        "type": "string",
                        "description": "Para 'remover_linha'/'editar_celula': valor exato procurado na coluna de filtro (ex: 'Mouse')"
                    },
                    "coluna": {
                        "type": "string",
                        "description": "Para 'editar_celula'/'adicionar_coluna'/'remover_coluna': nome da coluna alvo"
                    },
                    "novo_valor": {
                        "type": "string",
                        "description": "Para 'editar_celula': novo valor. Para 'adicionar_coluna': valor padrão (opcional)"
                    }
                },
                "required": ["caminho_arquivo", "acao"]
            }
        }
    }
]


# ── Funções de Manipulação de Documentos Word (.docx) ──────────────────────

def _find_word_exe() -> str | None:
    """
    Localiza o executável do Microsoft Word procurando no Registro do Windows
    e em caminhos conhecidos das versões Office 2016, 2019, 2021 e 365.
    """
    try:
        import winreg
        key_paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE",
        ]
        for key_path in key_paths:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        val, _ = winreg.QueryValueEx(key, "")
                        if val and os.path.exists(str(val)):
                            return str(val)
                except (FileNotFoundError, OSError):
                    continue
    except Exception:
        pass

    word_candidates = [
        r"C:\Program Files\Microsoft Office\Office16\WINWORD.EXE",
        r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
        r"C:\Program Files\Microsoft Office\Office15\WINWORD.EXE",
        r"C:\Program Files (x86)\Microsoft Office\Office16\WINWORD.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE",
        os.path.expandvars(r"%ProgramFiles%\Microsoft Office\root\Office16\WINWORD.EXE"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft Office\root\Office16\WINWORD.EXE"),
    ]
    for c in word_candidates:
        if c and os.path.exists(c):
            return c
    return shutil.which("WINWORD.EXE") or shutil.which("winword")


def criar_documento_word(
    caminho_arquivo: str,
    titulo: str | None = None,
    subtitulo: str | None = None,
    paragrafos: list[str] | None = None,
    lista_itens: list[str] | None = None,
    lista_numerada: list[str] | None = None,
    tabela_dados: list[list[str]] | None = None,
    abrir_no_word: bool = True,
) -> str:
    """
    Cria um novo documento Word (.docx) com título, subtítulos, parágrafos,
    listas com marcadores, listas numeradas e tabelas estruturadas.
    """
    if not _DOCX_AVAILABLE:
        return (
            "Erro: O módulo 'python-docx' não está instalado. "
            "Execute: pip install python-docx"
        )
    try:
        caminho_str = caminho_arquivo.strip()
        if not caminho_str.lower().endswith(".docx"):
            caminho_str = f"{caminho_str}.docx"

        p = Path(caminho_str).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)

        doc = _Document()

        # Título principal (Heading 1)
        if titulo:
            doc.add_heading(titulo, level=1)

        # Subtítulo (Heading 2)
        if subtitulo:
            doc.add_heading(subtitulo, level=2)

        # Parágrafos de texto
        if paragrafos:
            for paragrafo in paragrafos:
                doc.add_paragraph(str(paragrafo))

        # Lista com marcadores (bullet points)
        if lista_itens:
            for item in lista_itens:
                doc.add_paragraph(str(item), style="List Bullet")

        # Lista numerada
        if lista_numerada:
            for item in lista_numerada:
                doc.add_paragraph(str(item), style="List Number")

        # Tabela estruturada
        if tabela_dados and len(tabela_dados) > 0:
            num_colunas = len(tabela_dados[0])
            tabela = doc.add_table(rows=len(tabela_dados), cols=num_colunas)
            tabela.style = "Table Grid"
            for i, linha in enumerate(tabela_dados):
                for j, celula in enumerate(linha):
                    cell = tabela.cell(i, j)
                    cell.text = str(celula)
                    # Formatar cabeçalho (primeira linha) com negrito
                    if i == 0:
                        for run in cell.paragraphs[0].runs:
                            run.bold = True

        doc.save(str(p))

        try:
            from core.session_state import registrar_artefato
            registrar_artefato("word", caminho=str(p))
        except Exception:
            pass

        num_paragrafos = len(doc.paragraphs)
        msg = (
            f"Documento Word '{p.name}' criado com sucesso em '{p.parent}'. "
            f"Total de {num_paragrafos} parágrafos no documento."
        )

        from skills.office_live import _em_teste
        if abrir_no_word and not _em_teste():
            abrir_documento_word(str(p))
            msg += " Aberto em segundo plano no Microsoft Word para visualização."

        return msg
    except Exception as e:
        return f"Falha ao criar documento Word: {e}"


def _localizar_documento_word(caminho_arquivo: str) -> Path:
    """Resolve o caminho de um documento Word, usando o artefato ativo se o caller pediu 'atual'."""
    bruto = str(caminho_arquivo or "").strip().strip('"').strip("'")
    if bruto.lower() in ("", "atual", "ativo", "documento_atual", "documento_ativo", "documento", "word", "este", "esta"):
        try:
            from core.session_state import obter_artefato
            ativo = obter_artefato("word")
            if ativo and ativo.get("caminho"):
                return Path(str(ativo["caminho"])).resolve()
        except Exception:
            pass
    caminho = Path(bruto).resolve() if bruto else Path("")
    if not caminho.exists() and bruto:
        caminho = Path(os.path.abspath(bruto))
    return caminho


def editar_documento_word(
    caminho_arquivo: str,
    substituir_de: str | None = None,
    substituir_para: str | None = None,
    adicionar_paragrafos: list[str] | None = None,
    adicionar_titulo: str | None = None,
) -> str:
    """
    Edita um documento Word (.docx) existente: substitui texto e/ou adiciona
    novos parágrafos e títulos ao final do documento (em tempo real se aberto no Word).
    """
    if not _DOCX_AVAILABLE:
        return "Erro: O módulo 'python-docx' não está instalado. Execute: pip install python-docx"
    try:
        caminho = _localizar_documento_word(caminho_arquivo)
        if not caminho.exists() or not caminho.is_file():
            return f"Documento Word não encontrado: '{caminho_arquivo}'."
        if caminho.suffix.lower() != ".docx":
            return f"Formato inválido: '{caminho.suffix}'. Apenas arquivos .docx são suportados."

        from skills.office_live import (
            _em_teste,
            abrir_documento_word_live,
            editar_documento_word_live,
            esta_aberto_no_word,
            garantizar_backup_sessao,
        )
        garantizar_backup_sessao(caminho)

        # Se já estiver aberto no Microsoft Word, edita AO VIVO via COM sem conflito de lock
        if not _em_teste() and esta_aberto_no_word(caminho):
            ok_live, msg_live = editar_documento_word_live(
                caminho,
                substituir_de=substituir_de,
                substituir_para=substituir_para,
                adicionar_paragrafos=adicionar_paragrafos,
                adicionar_titulo=adicionar_titulo,
                sem_foco=True,
            )
            if ok_live:
                try:
                    from core.session_state import registrar_artefato
                    registrar_artefato("word", caminho=str(caminho))
                except Exception:
                    pass
                return msg_live

        import io

        # Lê o documento em memória com retries para evitar falhas por lock de leitura
        doc_stream = None
        for tentativa in range(15):
            try:
                with open(caminho, "rb") as f_in:
                    doc_stream = io.BytesIO(f_in.read())
                break
            except (PermissionError, OSError) as e_read:
                if tentativa == 14:
                    raise e_read
                time.sleep(0.08 * (tentativa + 1))

        doc = _Document(doc_stream)
        substituicoes = 0

        # Substituição de texto nos parágrafos
        if substituir_de and substituir_para is not None:
            for paragrafo in doc.paragraphs:
                if substituir_de in paragrafo.text:
                    for run in paragrafo.runs:
                        if substituir_de in run.text:
                            run.text = run.text.replace(substituir_de, substituir_para)
                            substituicoes += 1
            # Substituição em células de tabelas
            for tabela in doc.tables:
                for linha in tabela.rows:
                    for celula in linha.cells:
                        if substituir_de in celula.text:
                            for paragrafo in celula.paragraphs:
                                for run in paragrafo.runs:
                                    if substituir_de in run.text:
                                        run.text = run.text.replace(substituir_de, substituir_para)
                                        substituicoes += 1

        # Adicionar título ao final
        if adicionar_titulo:
            doc.add_heading(adicionar_titulo, level=2)

        # Adicionar parágrafos ao final
        if adicionar_paragrafos:
            for p in adicionar_paragrafos:
                doc.add_paragraph(str(p))

        # Serializa para buffer e grava de forma atômica via os.replace para evitar locks transitórios
        out_stream = io.BytesIO()
        doc.save(out_stream)
        data_bytes = out_stream.getvalue()

        tmp_path = caminho.with_name(f"{caminho.stem}_{time.time_ns()}.tmp")
        with open(tmp_path, "wb") as f_tmp:
            f_tmp.write(data_bytes)

        for tentativa in range(20):
            try:
                os.replace(tmp_path, caminho)
                break
            except (PermissionError, OSError) as e_lock:
                if tentativa == 19:
                    if tmp_path.exists():
                        try:
                            tmp_path.unlink()
                        except Exception:
                            pass
                    raise e_lock
                time.sleep(0.12)

        partes = []
        if substituicoes > 0:
            partes.append(f"{substituicoes} substituição(ões) de texto realizadas")
        if adicionar_titulo:
            partes.append("título adicionado")
        if adicionar_paragrafos:
            partes.append(f"{len(adicionar_paragrafos)} parágrafo(s) adicionado(s)")

        resumo = "; ".join(partes) if partes else "nenhuma alteração realizada"
        try:
            from core.session_state import registrar_artefato
            registrar_artefato("word", caminho=str(caminho))
        except Exception:
            pass
        if not _em_teste():
            abrir_documento_word_live(caminho, sem_foco=True)
        return f"Documento '{caminho.name}' editado com sucesso: {resumo}."
    except Exception as e:
        return f"Erro ao editar documento Word: {e}"


def ler_documento_word(caminho_arquivo: str) -> str:
    """
    Lê e extrai o texto completo de um documento Word (.docx).
    Retorna o conteúdo em texto simples formatado com estrutura de cabeçalhos.
    """
    if not _DOCX_AVAILABLE:
        return "Erro: O módulo 'python-docx' não está instalado. Execute: pip install python-docx"
    try:
        caminho = _localizar_documento_word(caminho_arquivo)
        if not caminho.exists() or not caminho.is_file():
            return f"Documento Word não encontrado: '{caminho_arquivo}'."
        if caminho.suffix.lower() != ".docx":
            return f"Formato inválido: '{caminho.suffix}'. Apenas arquivos .docx são suportados."

        try:
            from core.session_state import registrar_artefato
            registrar_artefato("word", caminho=str(caminho))
        except Exception:
            pass

        doc = _Document(str(caminho))
        linhas: list[str] = []

        for paragrafo in doc.paragraphs:
            texto = paragrafo.text.strip()
            if not texto:
                continue
            estilo = paragrafo.style.name if paragrafo.style else ""
            if "Heading 1" in estilo:
                linhas.append(f"# {texto}")
            elif "Heading 2" in estilo:
                linhas.append(f"## {texto}")
            elif "Heading 3" in estilo:
                linhas.append(f"### {texto}")
            elif "List Bullet" in estilo:
                linhas.append(f"• {texto}")
            elif "List Number" in estilo:
                linhas.append(f"1. {texto}")
            else:
                linhas.append(texto)

        # Extrair texto de tabelas
        for idx_tab, tabela in enumerate(doc.tables):
            linhas.append(f"\n[Tabela {idx_tab + 1}]")
            for linha in tabela.rows:
                celulas = [celula.text.strip() for celula in linha.cells]
                linhas.append(" | ".join(celulas))

        if not linhas:
            return f"O documento '{caminho.name}' existe, mas está vazio."

        conteudo = "\n".join(linhas)
        num_palavras = len(conteudo.split())
        return (
            f"Conteúdo do documento '{caminho.name}' ({num_palavras} palavras):\n\n"
            + conteudo
        )
    except Exception as e:
        return f"Erro ao ler documento Word: {e}"


def abrir_documento_word(caminho_arquivo: str | None = None) -> str:
    """
    Abre o Microsoft Word em segundo plano (visível na tela sem roubar o foco),
    reaproveitando a janela aberta se o documento já estiver carregado.
    """
    import subprocess
    from skills.office_live import abrir_documento_word_live

    if not caminho_arquivo or not str(caminho_arquivo).strip():
        ok, msg = abrir_documento_word_live(None, sem_foco=True)
        if ok:
            return msg
        word_exe = _find_word_exe()
        if word_exe and os.path.exists(word_exe):
            try:
                subprocess.Popen([word_exe])
                return "O aplicativo Microsoft Word foi aberto com sucesso."
            except Exception as e:
                return f"Falha ao abrir Microsoft Word: {e}"
        return "Microsoft Word não encontrado no sistema. Instale o Microsoft Office."

    caminho = _localizar_documento_word(caminho_arquivo)
    if not caminho.exists() or not caminho.is_file():
        return f"Arquivo não encontrado: '{caminho_arquivo}'. Verifique o caminho."

    try:
        from core.session_state import registrar_artefato
        registrar_artefato("word", caminho=str(caminho))
    except Exception:
        pass

    ok, msg = abrir_documento_word_live(caminho, sem_foco=True)
    if ok:
        return msg

    try:
        word_exe = _find_word_exe()
        if word_exe and os.path.exists(word_exe):
            SW_SHOWNOACTIVATE = 4
            STARTF_USESHOWWINDOW = 0x00000001
            si = subprocess.STARTUPINFO()
            si.dwFlags |= STARTF_USESHOWWINDOW
            si.wShowWindow = SW_SHOWNOACTIVATE
            subprocess.Popen([word_exe, str(caminho)], startupinfo=si)
        else:
            os.startfile(str(caminho))
        return f"Documento '{caminho.name}' aberto com sucesso."
    except Exception as e:
        try:
            os.startfile(str(caminho))
            return f"Documento '{caminho.name}' aberto no programa padrão do sistema."
        except Exception as e2:
            return f"Erro ao abrir documento Word: {e} / {e2}"


# ── Schemas OpenAPI para as funções Word ─────────────────────────────────────

WORD_DOC_SCHEMAS: Final[list[dict[str, Any]]] = [
    {
        "type": "function",
        "function": {
            "name": "criar_documento_word",
            "description": (
                "Cria um novo documento Word (.docx) com título, subtítulo, parágrafos, "
                "listas com marcadores, listas numeradas e tabelas estruturadas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho_arquivo": {
                        "type": "string",
                        "description": "Nome ou caminho do documento Word (ex: 'relatorio.docx' ou 'pasta/ata_reuniao.docx')"
                    },
                    "titulo": {
                        "type": "string",
                        "description": "Título principal do documento (Heading 1)"
                    },
                    "subtitulo": {
                        "type": "string",
                        "description": "Subtítulo do documento (Heading 2)"
                    },
                    "paragrafos": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de parágrafos de texto para adicionar ao documento"
                    },
                    "lista_itens": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista com marcadores (bullet points)"
                    },
                    "lista_numerada": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista numerada de itens"
                    },
                    "tabela_dados": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "description": "Tabela de dados: primeira linha é o cabeçalho, demais são as linhas de dados. Ex: [['Nome','Valor'],['Produto A','100']]"
                    },
                    "abrir_no_word": {
                        "type": "boolean",
                        "description": "Abre o documento no Microsoft Word na tela após a criação para o usuário ver (padrão: true). Use false somente se o usuário pedir explicitamente para não abrir."
                    }
                },
                "required": ["caminho_arquivo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "editar_documento_word",
            "description": (
                "Edita um documento Word (.docx) existente: substitui texto, "
                "adiciona novos parágrafos e títulos ao final."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho_arquivo": {
                        "type": "string",
                        "description": "Caminho do documento Word a ser editado"
                    },
                    "substituir_de": {
                        "type": "string",
                        "description": "Texto a ser encontrado e substituído"
                    },
                    "substituir_para": {
                        "type": "string",
                        "description": "Texto de substituição"
                    },
                    "adicionar_paragrafos": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Parágrafos a adicionar ao final do documento"
                    },
                    "adicionar_titulo": {
                        "type": "string",
                        "description": "Título (Heading 2) a adicionar ao final do documento"
                    }
                },
                "required": ["caminho_arquivo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ler_documento_word",
            "description": "Lê e extrai o texto completo de um documento Word (.docx), incluindo parágrafos e tabelas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho_arquivo": {
                        "type": "string",
                        "description": "Caminho do arquivo .docx a ser lido"
                    }
                },
                "required": ["caminho_arquivo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_documento_word",
            "description": "Abre o Microsoft Word ou um documento .docx específico na tela.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho_arquivo": {
                        "type": "string",
                        "description": "Caminho do documento .docx a abrir. Se omitido, abre o Word vazio."
                    }
                }
            }
        }
    },
]
