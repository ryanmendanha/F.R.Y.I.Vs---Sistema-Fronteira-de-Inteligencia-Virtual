import uuid
import sys
from core.llm import ask_fryvis
from core.memory import salvar_memoria, buscar_contexto
from core.stt import gravar_audio, transcrever
from core.tts import falar

def loop():
    print("=" * 55)
    print("  F.R.Y.I.Vs - Terminal Mode (Ctrl+C para encerrar)")
    print("=" * 55)
    print("Para iniciar a interface web futurista, execute: python server.py\n")

    while True:
        try:
            audio, fs = gravar_audio(duracao=5)
            if len(audio) == 0:
                print("Nenhum áudio detectado no microfone.")
                continue

            texto_usuario = transcrever(audio, fs)
            if not texto_usuario.strip():
                print("Silêncio ou fala não compreendida.")
                continue

            print(f"\n[Você]: {texto_usuario}")
            contexto = buscar_contexto(texto_usuario)
            
            resposta, ferramentas = ask_fryvis(
                texto_usuario,
                context=contexto,
                enable_semantic_skill_routing=True
            )
            
            if ferramentas:
                for f in ferramentas:
                    print(f"  [⚡ Skill Executada]: {f['tool']} -> {f['result']}")

            print(f"[FRYVIS]: {resposta}\n")

            if resposta:
                salvar_memoria(f"Usuário: {texto_usuario} | FRYVIS: {resposta}", str(uuid.uuid4()))
                falar(resposta)

        except KeyboardInterrupt:
            print("\nEncerrando F.R.Y.I.Vs. Até logo!")
            sys.exit(0)
        except Exception as e:
            print(f"[Erro]: {e}")

if __name__ == "__main__":
    loop()