"""
Módulo de Text-to-Speech para F.R.Y.I.Vs.
Provider primário: OpenAI TTS (modelo tts-1) com voz configurável via .env.
Fallback gratuito: Edge TTS (Microsoft) com voz natural em PT-BR.
Garante que a IA SEMPRE fale, mesmo sem créditos na OpenAI.
"""

import asyncio
import os
import shutil
import threading
import time
import uuid
from typing import Optional
import re
import requests
from dotenv import load_dotenv

# Integrador VoiceStudio TTS (OmniVoice - clonagem de voz, 646+ idiomas)
try:
    from core.tts_voicestudio import falar_voicestudio, voicestudio_disponivel
except ImportError:
    try:
        from tts_voicestudio import falar_voicestudio, voicestudio_disponivel
    except ImportError:
        falar_voicestudio = None
        voicestudio_disponivel = None

# ── Configuração OpenAI TTS ──────────────────────────────────────────────────
DEFAULT_VOICE = "nova"          # alloy | echo | fable | onyx | nova | shimmer
TTS_MODEL = "tts-1"            # tts-1 (rápido) ou tts-1-hd (máxima qualidade)
OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"

# ── Configuração Edge TTS (fallback gratuito) ────────────────────────────────
EDGE_TTS_VOICE = "pt-BR-FranciscaNeural"     # Voz feminina natural PT-BR
EDGE_TTS_VOICE_EN = "en-US-JennyNeural"      # Voz feminina nativa americana para termos em inglês

# Padrão para segmentação bilíngue automática na pronúncia da sigla
_ENGLISH_PHRASE_REGEX = re.compile(
    r'(Recursive\s+Yield\s+Female\s+Virtual(?:\s+Intelligence)?\s+system)',
    re.IGNORECASE
)

# ── Thread-safety e Gerenciamento Multi-Usuário ──────────────────────────────
_TTS_LOCK = threading.Lock()
AUDIO_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "audio_cache"
)


def _safe_atomic_save(temp_path: str, target_path: str) -> bool:
    """
    Substitui target_path pelo arquivo temp_path de forma atômica e thread-safe.
    Lida com locks transitórios de arquivo do Windows com retentativas.
    """
    dir_name = os.path.dirname(os.path.abspath(target_path))
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    with _TTS_LOCK:
        for attempt in range(5):
            try:
                if os.path.exists(target_path):
                    try:
                        os.replace(temp_path, target_path)
                    except PermissionError:
                        time.sleep(0.05 * (attempt + 1))
                        shutil.copy2(temp_path, target_path)
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass
                else:
                    os.replace(temp_path, target_path)
                return True
            except Exception as e:
                if attempt == 4:
                    print(f"[TTS] Falha ao mover arquivo atômico {temp_path} -> {target_path}: {e}")
                    return False
                time.sleep(0.05 * (attempt + 1))
        return False


_openai_quota_exhausted = False
_openai_quota_exhausted_at: float = 0.0   # timestamp de quando o circuit breaker fechou
_OPENAI_CB_TTL: float = 60.0              # segundos antes de tentar novamente (half-open)


def _falar_openai(texto: str, output_path: str) -> str:
    """Tenta gerar áudio via OpenAI TTS de forma atômica. Retorna caminho ou '' se falhar."""
    global _openai_quota_exhausted, _openai_quota_exhausted_at
    if _openai_quota_exhausted:
        if time.time() - _openai_quota_exhausted_at < _OPENAI_CB_TTL:
            return ""
        # TTL expirado: tenta novamente (circuit breaker half-open)
        _openai_quota_exhausted = False
        print(f"[TTS] Circuit breaker OpenAI: tentando novamente após {_OPENAI_CB_TTL:.0f}s.")

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not api_key or api_key in ("", "sua_openai_api_key_aqui"):
        return ""

    voice = os.getenv("OPENAI_TTS_VOICE", DEFAULT_VOICE).strip() or DEFAULT_VOICE
    model = os.getenv("OPENAI_TTS_MODEL", TTS_MODEL).strip() or TTS_MODEL

    temp_path = f"{output_path}.tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}"

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "input": texto.strip(),
            "voice": voice,
            "response_format": "mp3",
        }
        response = requests.post(
            OPENAI_TTS_URL,
            headers=headers,
            json=payload,
            timeout=8,
            stream=True,
        )

        if response.status_code == 200:
            with open(temp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                if _safe_atomic_save(temp_path, output_path):
                    file_size = os.path.getsize(output_path)
                    print(
                        f"[TTS] Audio gerado via OpenAI TTS ({model}, voz: {voice}) "
                        f"-> {output_path} ({file_size} bytes)"
                    )
                    return output_path
            return ""
        else:
            if response.status_code in (401, 429):
                _openai_quota_exhausted = True
                _openai_quota_exhausted_at = time.time()
                print(f"[TTS] OpenAI quota/credencial inválida ({response.status_code}). Alternando para Edge TTS por {_OPENAI_CB_TTL:.0f}s.")
            err = ""
            try:
                err = response.json().get("error", {}).get("message", "")
            except Exception:
                err = response.text[:200]
            print(f"[TTS] OpenAI TTS falhou (status {response.status_code}): {err}")
            return ""

    except requests.exceptions.Timeout:
        print("[TTS] Timeout na OpenAI TTS.")
        return ""
    except Exception as e:
        print(f"[TTS] Erro OpenAI TTS: {e}")
        return ""
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def _falar_edge_tts(texto: str, output_path: str, use_cache: bool = True) -> str:
    """Fallback gratuito: gera áudio via Edge TTS com gravação atômica, cache por hash e suporte bilíngue."""
    import hashlib
    voice = os.getenv("EDGE_TTS_VOICE", EDGE_TTS_VOICE).strip() or EDGE_TTS_VOICE
    voice_en = os.getenv("EDGE_TTS_VOICE_EN", EDGE_TTS_VOICE_EN).strip() or EDGE_TTS_VOICE_EN
    cache_key = hashlib.sha1(f"{voice}|{voice_en}|{texto.strip()}".encode("utf-8")).hexdigest()[:16]
    os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
    cached_mp3 = os.path.join(AUDIO_CACHE_DIR, f"tts_{cache_key}.mp3")

    if use_cache and os.path.exists(cached_mp3) and os.path.getsize(cached_mp3) > 0:
        if os.path.abspath(cached_mp3) == os.path.abspath(output_path):
            return output_path
        temp_copy = f"{output_path}.tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}"
        try:
            shutil.copy2(cached_mp3, temp_copy)
            if _safe_atomic_save(temp_copy, output_path):
                return output_path
        except Exception:
            if os.path.exists(temp_copy):
                try:
                    os.remove(temp_copy)
                except Exception:
                    pass

    try:
        import edge_tts
    except ImportError:
        print("[TTS] edge-tts nao instalado. Execute: pip install edge-tts")
        return ""

    temp_path = f"{output_path}.tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    try:

        async def _fetch(chunk_text: str, chunk_voice: str) -> bytes:
            if not chunk_text or not chunk_text.strip():
                return b""
            c = edge_tts.Communicate(chunk_text.strip(), chunk_voice)
            data = b""
            async for chunk in c.stream():
                if chunk["type"] == "audio":
                    data += chunk["data"]
            return data

        async def _generate():
            match = _ENGLISH_PHRASE_REGEX.search(texto)
            if not match:
                communicate = edge_tts.Communicate(texto.strip(), voice)
                await communicate.save(temp_path)
                return

            # Síntese Bilíngue Nativa: divide em prefixo (PT), frase em inglês (EN nativo) e sufixo (PT)
            prefix = texto[:match.start()].strip()
            english_text = match.group(1).strip()
            suffix = texto[match.end():].strip()

            tasks = []
            if prefix:
                tasks.append(_fetch(prefix, voice))
            tasks.append(_fetch(english_text, voice_en))
            if suffix:
                tasks.append(_fetch(suffix, voice))

            parts = await asyncio.gather(*tasks)
            combined_audio = b"".join(parts)
            with open(temp_path, "wb") as f:
                f.write(combined_audio)

        # Sempre executa em thread dedicada para evitar conflito com o event loop do FastAPI
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _generate())
            future.result(timeout=30)

        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            try:
                shutil.copy2(temp_path, cached_mp3)
            except Exception:
                pass
            if _safe_atomic_save(temp_path, output_path):
                file_size = os.path.getsize(output_path)
                print(
                    f"[TTS] Audio gerado via Edge TTS (voz PT: {voice}, voz EN: {voice_en}) "
                    f"-> {output_path} ({file_size} bytes)"
                )
                return output_path
        return ""

    except Exception as e:
        print(f"[TTS] Erro Edge TTS: {e}")
        return ""
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def limpar_cache_audio(max_idade_segundos: int = 3600) -> int:
    """Remove arquivos de áudio temporários do cache mais antigos que max_idade_segundos."""
    if not os.path.exists(AUDIO_CACHE_DIR):
        return 0
    removidos = 0
    agora = time.time()
    try:
        _PERMANENTES = {"senhor_ack.mp3"}  # áudios permanentes — nunca remover
        for f in os.listdir(AUDIO_CACHE_DIR):
            if f in _PERMANENTES or f.startswith("tts_"):
                continue
            caminho = os.path.join(AUDIO_CACHE_DIR, f)
            if os.path.isfile(caminho) and (agora - os.path.getmtime(caminho) > max_idade_segundos):
                try:
                    os.remove(caminho)
                    removidos += 1
                except Exception:
                    pass
    except Exception:
        pass
    return removidos


def limpar_texto_para_fala(texto: str) -> str:
    """
    Higieniza o texto removendo caracteres markdown para síntese vocal suave.
    Elimina asteriscos (*, **), cabeçalhos (#), crases, links markdown e marcadores,
    evitando que os motores TTS pronunciem 'asterisco' ou pontuações estranhas.
    """
    if not texto:
        return ""
    # Converte links [texto](url) -> texto
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', texto)
    # Remove asteriscos de negrito e itálico (**palavra**, *palavra*, etc)
    t = re.sub(r'\*+', '', t)
    # Remove crases de código (`codigo` ou ```bloco```)
    t = re.sub(r'`+', '', t)
    # Remove cabeçalhos markdown (# Titulo)
    t = re.sub(r'#+\s*', '', t)
    # Remove marcadores de lista no início de linhas (* item, - item, + item)
    t = re.sub(r'^\s*[-*+]\s+', '', t, flags=re.MULTILINE)
    # Remove outros caracteres estranhos para voz
    t = re.sub(r'[_~>|]', ' ', t)
    # Remove anotações como (lê-se...) ou (pronuncia-se...) para não duplicar fala
    t = re.sub(r'\(?\s*l[eê]-se\s+fra?y[i]?vis\s*\)?', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\(?\s*pronuncia-se\s+fra?y[i]?vis\s*\)?', '', t, flags=re.IGNORECASE)
    # Substitui qualquer menção ao nome da assistente por Frayvis (som fonético exato "Frái-vis")
    t = re.sub(r'\bF\.?R\.?Y\.?I\.?V\.?s\b', 'Frayvis', t, flags=re.IGNORECASE)
    t = re.sub(r'F\.R\.Y\.I\.Vs', 'Frayvis', t, flags=re.IGNORECASE)
    t = re.sub(r'FRYIVs', 'Frayvis', t, flags=re.IGNORECASE)
    t = re.sub(r'\bFryvis\b', 'Frayvis', t, flags=re.IGNORECASE)
    # Normaliza múltiplos espaços e quebras
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def falar(
    texto: str,
    output_path: Optional[str] = "resposta.mp3",
    unique_file: bool = False
) -> str:
    """
    Gera áudio da fala com thread-safety completo para múltiplos usuários/threads.
    Higieniza previamente o texto para remover asteriscos e marcas markdown.
    
    Args:
        texto: Conteúdo a ser sintetizado
        output_path: Caminho de saída desejado. Se None ou se unique_file=True,
                     um arquivo exclusivo e isolado é gerado em audio_cache/.
        unique_file: Se True, garante geração em arquivo individual com UUID.
    
    Retorna o caminho do arquivo gerado ou string vazia se indisponível.
    """
    # Bloqueia geração de voz quando o sistema está mutado
    try:
        from core.mute_state import is_muted
        if is_muted():
            print("[TTS] Saída de voz bloqueada (sistema mutado).")
            return ""
    except Exception:
        pass

    if not texto or not texto.strip():
        return ""

    texto_para_voz = limpar_texto_para_fala(texto)
    if not texto_para_voz:
        return ""

    # Em cenários multi-usuário simultâneo, gera arquivo individual para isolar sessões
    if unique_file or output_path is None:
        os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
        target_path = os.path.join(AUDIO_CACHE_DIR, f"audio_{uuid.uuid4().hex}.mp3")
    else:
        target_path = output_path

    # Determina o provedor TTS configurado (.env)
    load_dotenv()
    provider = os.getenv("TTS_PROVIDER", "auto").strip().lower()

    # 0. VoiceStudio (OmniVoice) — provedor premium local com clonagem de voz
    if provider == "voicestudio":
        if falar_voicestudio is not None:
            result = falar_voicestudio(texto_para_voz, target_path)
            if result:
                return result
            print("[TTS] VoiceStudio indisponivel. Verifique se o app esta rodando.")
        else:
            print("[TTS] Modulo tts_voicestudio nao encontrado.")
        # Fallback em cascata se VoiceStudio falhar
        result = _falar_openai(texto_para_voz, target_path)
        if result:
            return result
        result = _falar_edge_tts(texto_para_voz, target_path)
        if result:
            return result

    # 1. Se provedor for estritamente edge, vai direto sem perda de tempo
    elif provider == "edge":
        result = _falar_edge_tts(texto_para_voz, target_path)
        if result:
            return result

    # 2. Tenta OpenAI TTS (se provider não for edge nem voicestudio)
    else:
        # Modo auto: tenta VoiceStudio primeiro se disponível e rodando
        if falar_voicestudio is not None and voicestudio_disponivel is not None:
            if voicestudio_disponivel():
                result = falar_voicestudio(texto_para_voz, target_path)
                if result:
                    return result
                print("[TTS] VoiceStudio falhou. Tentando OpenAI TTS...")

        result = _falar_openai(texto_para_voz, target_path)
        if result:
            return result

        # Fallback para Edge TTS se OpenAI falhar/esgotar quota
        print("[TTS] Usando fallback Edge TTS (gratuito)...")
        result = _falar_edge_tts(texto_para_voz, target_path)
        if result:
            return result

    print("[TTS] Nenhum provedor TTS disponivel.")
    return ""
