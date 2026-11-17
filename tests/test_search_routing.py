import sys, os
sys.path.insert(0, os.path.abspath("."))
from core.skill_router import get_skill_router

router = get_skill_router()

test_queries = [
    # Caso B: Usuário NÃO pede para abrir navegador -> APENAS pesquisar e retornar no chat
    ("Pesquise sobre a teoria da relatividade", "pesquisar_informacao_web"),
    ("O que é inteligência artificial", "pesquisar_informacao_web"),
    ("Quem foi Alan Turing", "pesquisar_informacao_web"),
    ("Qual a cotação do dólar hoje", "pesquisar_informacao_web"),
    ("Procure sobre o telescópio James Webb", "pesquisar_informacao_web"),
    ("Busque informações sobre buracos negros", "pesquisar_informacao_web"),

    # Caso A: Usuário PEDE para abrir Chrome/Edge -> Abre diretamente no navegador em segundo plano
    ("Abra o Chrome e pesquise sobre carros elétricos", "pesquisar_google"),
    ("Pesquise no Chrome sobre Python", "pesquisar_google"),
    ("Abra no Edge e pesquise notícias de tecnologia", "pesquisar_google"),
    ("Pesquise no Edge sobre cotação do euro", "pesquisar_google"),
    ("Abra o navegador e pesquise sobre IA", "pesquisar_google"),

    # Casos de Abertura Simples (sem pesquisa)
    ("Abra o Chrome", "abrir_programa"),
    ("Abra o bloco de notas", "abrir_programa"),
]

print("=" * 60)
print("TESTE DE ROTEAMENTO DE PESQUISA (CHAT VS NAVEGADOR SEGUNDO PLANO)")
print("=" * 60)

passed = 0
total = len(test_queries)

for q, expected in test_queries:
    skills = router.search_relevant_skills(q, top_k=2)
    names = [s.get('function', {}).get('name') for s in skills]
    primary_skill = names[0] if names else None
    ok = (primary_skill == expected)
    if ok:
        passed += 1
        status = "[PASS]"
    else:
        status = "[FAIL]"
    print(f"{status} '{q}' -> Esperado: {expected} | Obtido: {primary_skill} (todas: {names})")

print("=" * 60)
print(f"Resultado final: {passed}/{total} testes passaram ({passed/total*100:.1f}%)")
print("=" * 60)
assert passed == total, f"Falha: {total - passed} testes não passaram!"
