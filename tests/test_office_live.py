"""
Testes de edição em tempo real de planilhas Excel, documentos Word e backup de sessão
(`skills/office_live.py` e `skills/file_data_ops.py`).
"""

import json
import os
from pathlib import Path

import openpyxl
from docx import Document

from core import session_state
from skills.file_data_ops import (
    criar_documento_word,
    criar_planilha,
    editar_documento_word,
    editar_planilha,
    ler_documento_word,
)
from skills.office_live import garantir_backup_sessao


class TestOfficeLiveAndCoPilot:
    def setup_method(self):
        session_state.limpar()

    def test_garantir_backup_sessao_cria_bak_uma_vez(self, tmp_path: Path):
        arq = tmp_path / "dados.xlsx"
        arq.write_bytes(b"conteudo-original-v1")

        bak1 = garantir_backup_sessao(str(arq))
        assert bak1 is not None
        assert os.path.exists(bak1)
        assert Path(bak1).read_bytes() == b"conteudo-original-v1"

        arq.write_bytes(b"conteudo-modificado-v2")
        bak2 = garantir_backup_sessao(str(arq))
        assert bak2 == bak1
        assert Path(bak2).read_bytes() == b"conteudo-original-v1"

    def test_fluxo_incremental_excel_com_artefato_ativo(self, tmp_path: Path):
        caminho = str(tmp_path / "estoque_live.xlsx")
        res_criacao = criar_planilha(
            caminho_arquivo=caminho,
            colunas=json.dumps(["Produto", "Qtd", "Preco"]),
            dados=json.dumps([{"Produto": "Mouse", "Qtd": 10, "Preco": 99.90}]),
            abrir_no_excel=False,
        )
        assert "sucesso" in res_criacao.lower() or "criada" in res_criacao.lower()
        assert os.path.exists(caminho)

        art = session_state.obter_artefato("excel")
        assert art is not None
        assert os.path.abspath(art["caminho"]) == os.path.abspath(caminho)

        res_edicao = editar_planilha(
            caminho_arquivo="atual",
            acao="adicionar_linha",
            dados=json.dumps([{"Produto": "Teclado Mecânico", "Qtd": 5, "Preco": 299.00}]),
            abrir_no_excel=False,
        )
        assert "adicionada" in res_edicao.lower() or "atualizada" in res_edicao.lower()
        assert os.path.exists(caminho + ".bak")

        wb = openpyxl.load_workbook(caminho)
        ws = wb.active
        valores = list(ws.iter_rows(values_only=True))
        wb.close()

        assert len(valores) == 3
        assert valores[0] == ("Produto", "Qtd", "Preco")
        assert valores[1][0] == "Mouse"
        assert valores[2][0] == "Teclado Mecânico"

    def test_fluxo_incremental_word_com_artefato_ativo(self, tmp_path: Path):
        caminho = str(tmp_path / "ata_reuniao.docx")
        res_criacao = criar_documento_word(
            caminho_arquivo=caminho,
            titulo="Ata de Reunião",
            paragrafos=["Pauta 1: Arquitetura da FRYIVS.", "Pauta 2: Modo Supercomputador."],
            abrir_no_word=False,
        )
        assert "sucesso" in res_criacao.lower()
        assert os.path.exists(caminho)

        res_edicao = editar_documento_word(
            caminho_arquivo="atual",
            adicionar_titulo="Conclusão",
            adicionar_paragrafos=["Decisão final: Aprovado para produção."],
        )
        assert "adicionado" in res_edicao.lower() or "sucesso" in res_edicao.lower()
        assert os.path.exists(caminho + ".bak")

        leitura = ler_documento_word(caminho_arquivo="atual")
        assert "Ata de Reunião" in leitura
        assert "Conclusão" in leitura
        assert "Decisão final: Aprovado para produção." in leitura
