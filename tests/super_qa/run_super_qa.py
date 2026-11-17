#!/usr/bin/env python
"""
run_super_qa.py — Runner Unificado dos 250 Testes da FRYIVS Super QA
Executa toda a bateria, coleta métricas, detecta falhas e gera o relatório final.
"""
import subprocess
import sys
import json
import time
import re
from pathlib import Path
from datetime import datetime

# Garante saída UTF-8 no Windows sem erros de charmap
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent.parent
SANDBOX = PROJECT_ROOT / "FRYIVS_TESTES"
RELATORIO_DIR = SANDBOX / "relatorios"
RELATORIO_DIR.mkdir(parents=True, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RELATORIO_JSON = RELATORIO_DIR / f"resultado_super_qa_{TIMESTAMP}.json"
RELATORIO_MD = RELATORIO_DIR / f"relatorio_final_{TIMESTAMP}.md"
RELATORIO_TXT = RELATORIO_DIR / f"relatorio_final_{TIMESTAMP}.txt"

CATEGORIAS = {
    "ARQ": {"arquivo": "test_01_arq.py", "total": 15, "nome": "Arquivos no PC"},
    "XLS": {"arquivo": "test_02_xls.py", "total": 15, "nome": "Planilhas Excel/CSV"},
    "DOC": {"arquivo": "test_03_doc.py", "total": 15, "nome": "Documentos Word (.docx)"},
    "DSK": {"arquivo": "test_04_dsk.py", "total": 25, "nome": "Navegação Desktop"},
    "WEB": {"arquivo": "test_05_web.py", "total": 25, "nome": "Navegação Web"},
    "MEM": {"arquivo": "test_06_mem.py", "total": 30, "nome": "Memória Semântica"},
    "RES": {"arquivo": "test_07_res.py", "total": 40, "nome": "Respostas da IA"},
    "AUT": {"arquivo": "test_08_aut.py", "total": 30, "nome": "Automação Multi-etapas"},
    "DBG": {"arquivo": "test_09_dbg.py", "total": 30, "nome": "Debug e Resiliência"},
    "RSP": {"arquivo": "test_10_rsp.py", "total": 25, "nome": "Responsividade e Carga"},
}

def executar_categoria(codigo: str, info: dict, python_exe: str) -> dict:
    """Executa os testes de uma categoria e retorna os resultados."""
    print(f"\n{'='*60}", flush=True)
    print(f"  Executando: [{codigo}] {info['nome']} ({info['total']} testes)...", flush=True)
    print(f"{'='*60}", flush=True)

    suite_dir = Path(__file__).parent
    arquivo = suite_dir / info["arquivo"]

    t0 = time.perf_counter()
    resultado = subprocess.run(
        [
            python_exe, "-m", "pytest",
            str(arquivo),
            "-v",
            "--tb=short",
            "--no-header",
            f"--rootdir={PROJECT_ROOT}",
            "-p", "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=300  # 5 minutos por categoria
    )
    elapsed = (time.perf_counter() - t0)

    stdout = resultado.stdout
    stderr = resultado.stderr

    # Parsear resultados do pytest
    passou = len(re.findall(r' PASSED', stdout))
    falhou = len(re.findall(r' FAILED', stdout))
    erro = len(re.findall(r' ERROR', stdout))
    skipped = len(re.findall(r' SKIPPED', stdout))

    # Extrair resumo final do pytest
    resumo_match = re.search(r'(\d+) passed(?:.*?(\d+) failed)?(?:.*?(\d+) error)?(?:.*?(\d+) warning)?', stdout)

    print(stdout[-3000:] if len(stdout) > 3000 else stdout)
    if stderr and "error" in stderr.lower():
        print(f"STDERR: {stderr[-500:]}")

    total_executado = passou + falhou + erro + skipped
    nota = round((passou / info["total"]) * 10, 1) if info["total"] > 0 else 0

    return {
        "codigo": codigo,
        "nome": info["nome"],
        "total_esperado": info["total"],
        "total_executado": total_executado,
        "passou": passou,
        "falhou": falhou,
        "erro": erro,
        "skipped": skipped,
        "nota": nota,
        "tempo_s": round(elapsed, 2),
        "returncode": resultado.returncode,
        "saida": stdout[-2000:],
    }


def calcular_severidade(resultados_categoria: list) -> dict:
    """Classifica bugs por severidade baseado nos padrões de falha."""
    bugs = {"S1": [], "S2": [], "S3": [], "S4": []}

    for cat in resultados_categoria:
        codigo = cat["codigo"]
        if cat["erro"] > 0:
            bugs["S1"].append(f"[{codigo}] {cat['erro']} teste(s) com ERROR crítico")
        if cat["falhou"] > 0:
            if codigo in ["ARQ", "MEM", "AUT"]:
                bugs["S2"].append(f"[{codigo}] {cat['falhou']} teste(s) FALHOU em categoria crítica")
            elif codigo in ["XLS", "DOC", "DSK"]:
                bugs["S3"].append(f"[{codigo}] {cat['falhou']} teste(s) FALHOU")
            else:
                bugs["S4"].append(f"[{codigo}] {cat['falhou']} teste(s) FALHOU")

    return bugs


def gerar_relatorio_md(resultados: list, bugs: dict, total_passou: int, total_falhou: int,
                        total_erro: int, total_skipped: int, tempo_total: float) -> str:
    """Gera o relatório final em Markdown."""
    total = sum(r["total_esperado"] for r in resultados)
    total_exec = total_passou + total_falhou + total_erro + total_skipped
    pct_passou = round((total_passou / total) * 100, 1) if total > 0 else 0
    pct_falhou = round((total_falhou / total) * 100, 1) if total > 0 else 0

    # Determinar veredito
    bugs_s1_abertos = len(bugs["S1"])
    bugs_s2_criticos = len([b for b in bugs["S2"] if any(c in b for c in ["ARQ", "MEM", "AUT"])])

    if bugs_s1_abertos > 0:
        veredito = "🔴 REPROVADA"
        veredito_detalhe = f"{bugs_s1_abertos} bug(s) S1 crítico(s) em aberto."
    elif bugs_s2_criticos > 0 or pct_passou < 90:
        veredito = "🟡 APROVADA COM RESSALVAS"
        veredito_detalhe = f"{pct_passou}% de aprovação ({100 - pct_passou:.1f}% abaixo da meta de 90%)."
    else:
        veredito = "🟢 APROVADA"
        veredito_detalhe = f"{pct_passou}% de aprovação — acima da meta de 90%."

    linhas = [
        "# Relatório Final de Homologação — F.R.Y.I.Vs Super QA",
        f"**Data:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        f"**Bateria:** 250 Testes de Ponta a Ponta",
        f"**Ambiente:** Windows / Python 3.12+ / FastAPI / Ollama & Gemini",
        "",
        "---",
        "",
        "## 1. Resumo Executivo",
        "",
        f"| Métrica | Valor |",
        f"|---|---|",
        f"| **Total de Testes** | {total} |",
        f"| **Executados** | {total_exec} |",
        f"| **✅ PASSOU** | {total_passou} ({pct_passou}%) |",
        f"| **❌ FALHOU** | {total_falhou} ({pct_falhou}%) |",
        f"| **⚠️ ERRO** | {total_erro} |",
        f"| **⏭️ SKIPPED** | {total_skipped} |",
        f"| **Tempo Total** | {tempo_total:.1f}s |",
        "",
        f"## 2. Veredito Final",
        "",
        f"### {veredito}",
        f"> {veredito_detalhe}",
        "",
        "---",
        "",
        "## 3. Resultados por Categoria",
        "",
        "| Categoria | Nome | Esperado | Passou | Falhou | Erro | Skip | Nota | Tempo(s) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for r in resultados:
        emoji = "✅" if r["falhou"] == 0 and r["erro"] == 0 else ("❌" if r["erro"] > 0 else "⚠️")
        linhas.append(
            f"| {emoji} **{r['codigo']}** | {r['nome']} | {r['total_esperado']} | "
            f"{r['passou']} | {r['falhou']} | {r['erro']} | {r['skipped']} | "
            f"**{r['nota']}/10** | {r['tempo_s']}s |"
        )

    linhas += [
        "",
        "---",
        "",
        "## 4. Bugs Detectados por Severidade",
        "",
    ]

    for sev, lista in bugs.items():
        if lista:
            linhas.append(f"### {sev}")
            for bug in lista:
                linhas.append(f"- {bug}")
            linhas.append("")

    if not any(bugs.values()):
        linhas.append("✅ **Nenhum bug detectado!**")

    linhas += [
        "",
        "---",
        "",
        "## 5. Top 5 Riscos para Uso Real da FRYIVS",
        "",
        "1. **Dependências de ambiente**: Selenium, Tesseract e ChromaDB exigem instalação correta para automação web e OCR.",
        "2. **Latência de LLM**: Modelos Ollama locais podem ter latência alta em hardware limitado.",
        "3. **Permissões do Windows**: Operações de arquivo podem falhar em diretórios protegidos.",
        "4. **Concorrência no ChromaDB**: Operações simultâneas de leitura/escrita podem gerar inconsistências.",
        "5. **python-docx vs Word Online**: Documentos criados podem ter pequenas diferenças de formatação.",
        "",
        "---",
        "",
        "## 6. Critérios de Aprovação",
        "",
        f"| Critério | Meta | Obtido | Status |",
        f"|---|---|---|---|",
        f"| Bugs S1 abertos | 0 | {len(bugs['S1'])} | {'✅' if len(bugs['S1']) == 0 else '❌'} |",
        f"| Bugs S2 em ARQ/MEM/AUT | 0 | {bugs_s2_criticos} | {'✅' if bugs_s2_criticos == 0 else '❌'} |",
        f"| % Passou | ≥ 90% | {pct_passou}% | {'✅' if pct_passou >= 90 else '❌'} |",
        "",
        "---",
        "",
        "*Relatório gerado automaticamente pelo runner Super QA da F.R.Y.I.Vs.*",
    ]

    return "\n".join(linhas)


def main():
    print("\n" + "=" * 70)
    print("   🤖 F.R.Y.I.Vs — SUPER QA: BATERIA COMPLETA DE 250 TESTES")
    print("=" * 70)
    print(f"   Início: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"   Sandbox: {SANDBOX}")
    print("=" * 70)

    # Detectar o Python correto (venv ou sistema)
    python_exe = sys.executable
    venv_python = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        python_exe = str(venv_python)

    print(f"   Python: {python_exe}")
    print()

    resultados = []
    t_inicio = time.perf_counter()

    for codigo, info in CATEGORIAS.items():
        try:
            resultado = executar_categoria(codigo, info, python_exe)
            resultados.append(resultado)
            status = "✅ OK" if resultado["falhou"] == 0 and resultado["erro"] == 0 and resultado["skipped"] == 0 else f"❌ {resultado['falhou']}F/{resultado['erro']}E/{resultado['skipped']}S"
            print(f"\n  [{codigo}] {info['nome']}: {resultado['passou']}/{info['total']} PASSOU — Nota: {resultado['nota']}/10 — {status}", flush=True)
        except subprocess.TimeoutExpired:
            print(f"\n  [{codigo}] TIMEOUT após 5 minutos!", flush=True)
            resultados.append({
                "codigo": codigo, "nome": info["nome"],
                "total_esperado": info["total"], "total_executado": 0,
                "passou": 0, "falhou": 0, "erro": info["total"], "skipped": 0,
                "nota": 0, "tempo_s": 300, "returncode": -1, "saida": "TIMEOUT"
            })
        except Exception as e:
            print(f"\n  [{codigo}] ERRO ao executar: {e}", flush=True)
            resultados.append({
                "codigo": codigo, "nome": info["nome"],
                "total_esperado": info["total"], "total_executado": 0,
                "passou": 0, "falhou": 0, "erro": info["total"], "skipped": 0,
                "nota": 0, "tempo_s": 0, "returncode": -1, "saida": str(e)
            })

    tempo_total = time.perf_counter() - t_inicio

    # Totais consolidados
    total_passou = sum(r["passou"] for r in resultados)
    total_falhou = sum(r["falhou"] for r in resultados)
    total_erro = sum(r["erro"] for r in resultados)
    total_skipped = sum(r["skipped"] for r in resultados)
    total_esperado = sum(r["total_esperado"] for r in resultados)

    # Análise de bugs
    bugs = calcular_severidade(resultados)

    # Salvar JSON
    dados_json = {
        "timestamp": TIMESTAMP,
        "total_esperado": total_esperado,
        "total_passou": total_passou,
        "total_falhou": total_falhou,
        "total_erro": total_erro,
        "total_skipped": total_skipped,
        "tempo_total_s": round(tempo_total, 2),
        "resultados": resultados,
        "bugs": bugs,
    }
    RELATORIO_JSON.write_text(json.dumps(dados_json, indent=2, ensure_ascii=False), encoding="utf-8")

    # Gerar e salvar relatório Markdown
    relatorio_md = gerar_relatorio_md(
        resultados, bugs, total_passou, total_falhou, total_erro, total_skipped, tempo_total
    )
    RELATORIO_MD.write_text(relatorio_md, encoding="utf-8")

    # Imprimir resumo final
    print("\n\n" + "=" * 70)
    print("   📊 RESULTADO FINAL DA BATERIA SUPER QA")
    print("=" * 70)
    print(f"\n   Total de Testes: {total_esperado}")
    print(f"   ✅ PASSOU:  {total_passou} ({round(total_passou/total_esperado*100,1)}%)")
    print(f"   ❌ FALHOU:  {total_falhou} ({round(total_falhou/total_esperado*100,1)}%)")
    print(f"   ⚠️  ERRO:    {total_erro}")
    print(f"   ⏭️  SKIPPED: {total_skipped}")
    print(f"   ⏱️  Tempo:   {tempo_total:.1f}s")
    print()
    print("   Resultados por Categoria:")
    print(f"   {'Código':<6} {'Nome':<28} {'Passou':<8} {'Nota':<8}")
    print(f"   {'-'*52}")
    for r in resultados:
        emoji = "✅" if r["falhou"] == 0 and r["erro"] == 0 else "❌"
        print(f"   {r['codigo']:<6} {r['nome']:<28} {r['passou']}/{r['total_esperado']:<5}  {r['nota']}/10 {emoji}")

    pct = round(total_passou / total_esperado * 100, 1) if total_esperado > 0 else 0
    s1 = len(bugs["S1"])
    s2_criticos = len([b for b in bugs["S2"] if any(c in b for c in ["ARQ", "MEM", "AUT"])])

    print()
    if s1 > 0:
        veredito = "🔴 REPROVADA"
    elif s2_criticos > 0 or pct < 90:
        veredito = "🟡 APROVADA COM RESSALVAS"
    else:
        veredito = "🟢 APROVADA"

    print(f"   VEREDITO FINAL: {veredito}")
    print(f"   ({pct}% de aprovação)")
    print()
    print(f"   Relatório salvo em:")
    print(f"   📄 {RELATORIO_MD}")
    print(f"   📊 {RELATORIO_JSON}")
    print("=" * 70)

    return 0 if (s1 == 0 and pct >= 90) else 1


if __name__ == "__main__":
    sys.exit(main())
