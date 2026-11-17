import urllib.request
import json
import time

def call_chat(msg):
    t0 = time.time()
    url = 'http://127.0.0.1:8000/api/chat'
    payload = json.dumps({'message': msg, 'generate_speech': False}).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
        dt = time.time() - t0
        print(f"Comando: '{msg}'")
        print(f"Tempo: {dt:.2f}s | Resposta: {data.get('response')}")
        tools = data.get('tools_executed')
        if tools:
            for t in tools:
                print(f"  -> Tool executada: {t.get('tool')}")
                print(f"     Resultado: {t.get('result')}")
        print("-" * 65)

if __name__ == "__main__":
    print("=== BATERIA DE TESTES DE INTEGRAÇÃO F.R.Y.I.Vs ===")
    call_chat("Quem é você?")
    call_chat("Quem é você?")  # Teste de Cache
    call_chat("Que horas são agora?")
    call_chat("Crie uma planilha de controle chamada despesas_mensais.xlsx")
