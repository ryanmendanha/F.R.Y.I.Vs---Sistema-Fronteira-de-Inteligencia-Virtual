"""
Diagnóstico de roteamento de skills e Excel para F.R.Y.I.Vs.
Execute: python tests/test_routing_diag.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["ANONYMIZED_TELEMETRY"] = "False"

print("=== TESTE DE ROTEAMENTO ===")
from core.skill_router import SkillRouter

router = SkillRouter(collection_name="fryvis_test_diag2")
router.ensure_skills_indexed(force=True)

testes = [
    ("pesquise sobre inteligencia artificial no edge", "pesquisar_na_web"),
    ("abra o chrome e pesquise python tutorial", "pesquisar_na_web"),
    ("pesquise na web sobre machine learning", "pesquisar_na_web"),
    ("pesquise no google sobre machine learning", "pesquisar_google"),
    ("tocar musica no youtube", "pesquisar_youtube"),
    ("criar planilha de vendas", "criar_planilha"),
    ("abrir excel", "abrir_planilha"),
    ("abrir planilha de dados", "abrir_planilha"),
    ("analisar planilha relatorio.xlsx", "consultar_planilha"),
    ("abrir bloco de notas", "abrir_programa"),
]

all_ok = True
for pergunta, esperado in testes:
    skills = router.search_relevant_skills(pergunta, top_k=4)
    nomes = [s.get("function", {}).get("name") for s in skills]
    ok = esperado in nomes[:2]
    if not ok:
        all_ok = False
    print(f'  [{"OK" if ok else "FAIL"}] "{pergunta}"')
    print(f'        -> {nomes[:3]} (esperado: {esperado})')

print()
print("=== RESULTADO GERAL:", "PASSOU" if all_ok else "FALHOU", "===")

print()
print("=== TESTE EXCEL FINDER ===")
from skills.file_data_ops import _find_excel_exe
excel = _find_excel_exe()
print(f"  Excel encontrado: {excel}")
print(f"  Existe: {os.path.exists(excel) if excel else False}")

print()
print("=== TESTE WEBDRIVER-MANAGER ===")
try:
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    print("  webdriver-manager: OK (importado com sucesso)")
except Exception as e:
    print(f"  webdriver-manager: ERRO - {e}")
