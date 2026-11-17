import sys, os
sys.path.insert(0, os.path.abspath("."))
from core.llm import ask_fryvis

print("=== TESTE 1: Pesquisa direta no chat (SEM abrir navegador) ===")
prompt_chat = "Pesquise sobre a teoria da relatividade"
resp_chat, tools_chat = ask_fryvis(prompt_chat)
print(f"Prompt: {prompt_chat}")
print(f"Tools executadas: {[t.get('tool') for t in tools_chat]}")
print(f"Resposta gerada:\n{resp_chat}\n")

assert any(t.get('tool') == 'pesquisar_informacao_web' for t in tools_chat), "Deveria ter executado pesquisar_informacao_web!"
assert "senhor" in resp_chat.lower(), "Deveria conter 'senhor' na resposta!"
print("[OK] Teste 1 passou com sucesso!")

print("\n=== TESTE 2: Pesquisa solicitada no Chrome (SEGUNDO PLANO) ===")
prompt_chrome = "Abra o Chrome e pesquise sobre carros elétricos"
resp_chrome, tools_chrome = ask_fryvis(prompt_chrome)
print(f"Prompt: {prompt_chrome}")
print(f"Tools executadas: {[t.get('tool') for t in tools_chrome]}")
print(f"Resposta gerada:\n{resp_chrome}\n")

assert any(t.get('tool') == 'pesquisar_google' for t in tools_chrome), "Deveria ter executado pesquisar_google!"
assert "senhor" in resp_chrome.lower(), "Deveria conter 'senhor' na resposta!"
print("[OK] Teste 2 passou com sucesso!")

print("\nTODOS OS TESTES END-TO-END DE PESQUISA PASSARAM COM SUCESSO!")
