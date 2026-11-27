"""
Módulo de Text-to-Speech Neural 2.0 para F.R.Y.I.Vs.
- Voz principal: Microsoft Edge Neural TTS (fr-FR-VivienneMultilingualNeural) com prosódia ajustada.
- Humanizador prosódico e fonético PT-BR (pausas naturais, siglas, moedas, código/links).
- Streaming por sentenças de baixa latência para reprodução local quase instantânea.
- Fallback offline nativo do Windows (OneCore / SAPI5) quando sem internet.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import os
import re
import shutil
import sys
import threading
import time
import uuid
from typing import Callable, Optional

import requests
from dotenv import load_dotenv

try:
    from core.tts_voicestudio import falar_voicestudio, voicestudio_disponivel
except ImportError:
    try:
        from tts_voicestudio import falar_voicestudio, voicestudio_disponivel
    except ImportError:
        falar_voicestudio = None
        voicestudio_disponivel = None

DEFAULT_VOICE = "nova"
TTS_MODEL = "tts-1"
OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"

EDGE_TTS_VOICE = "fr-FR-VivienneMultilingualNeural"
EDGE_TTS_VOICE_EN = "fr-FR-VivienneMultilingualNeural"
EDGE_TTS_RATE = "+4%"
EDGE_TTS_PITCH = "+0Hz"
EDGE_TTS_VOLUME = "+0%"

_ENGLISH_PHRASE_REGEX = re.compile(
    r"(Recursive\s+Yield\s+Female\s+Virtual(?:\s+Intelligence)?\s+system)",
    re.IGNORECASE,
)

from core.runtime_mode import get_audio_cache_dir

_TTS_LOCK = threading.Lock()
AUDIO_CACHE_DIR = str(get_audio_cache_dir())


def _em_teste() -> bool:
    return "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))


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
_openai_quota_exhausted_at: float = 0.0
_OPENAI_CB_TTL: float = 60.0


def _falar_openai(texto: str, output_path: str) -> str:
    """Tenta gerar áudio via OpenAI TTS de forma atômica. Retorna caminho ou '' se falhar."""
    global _openai_quota_exhausted, _openai_quota_exhausted_at
    if _openai_quota_exhausted:
        if time.time() - _openai_quota_exhausted_at < _OPENAI_CB_TTL:
            return ""
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
                print(
                    f"[TTS] OpenAI quota/credencial inválida ({response.status_code}). "
                    f"Alternando para Edge TTS por {_OPENAI_CB_TTL:.0f}s."
                )
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


def _obter_parametros_edge() -> tuple[str, str, str, str, str]:
    voice = os.getenv("EDGE_TTS_VOICE", EDGE_TTS_VOICE).strip() or EDGE_TTS_VOICE
    voice_en = os.getenv("EDGE_TTS_VOICE_EN", EDGE_TTS_VOICE_EN).strip() or EDGE_TTS_VOICE_EN
    rate = os.getenv("EDGE_TTS_RATE", EDGE_TTS_RATE).strip() or EDGE_TTS_RATE
    pitch = os.getenv("EDGE_TTS_PITCH", EDGE_TTS_PITCH).strip() or EDGE_TTS_PITCH
    volume = os.getenv("EDGE_TTS_VOLUME", EDGE_TTS_VOLUME).strip() or EDGE_TTS_VOLUME
    return voice, voice_en, rate, pitch, volume


def _falar_windows_offline(texto: str, output_path: str) -> str:
    """Fallback offline nativo usando vozes Windows OneCore / SAPI5 (ex: Microsoft Maria)."""
    if sys.platform != "win32" or not texto.strip():
        return ""
    try:
        import win32com.client

        os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
        base_root, _ = os.path.splitext(output_path)
        wav_target = f"{base_root}.wav" if output_path.lower().endswith(".wav") else os.path.join(
            AUDIO_CACHE_DIR, f"offline_{uuid.uuid4().hex[:10]}.wav"
        )

        sp_voice = win32com.client.Dispatch("SAPI.SpVoice")
        chosen_tok = None
        for cat_path in (
            r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices",
            r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices",
        ):
            try:
                cat = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
                cat.SetId(cat_path, False)
                tokens = cat.EnumerateTokens()
                for i in range(tokens.Count):
                    tok = tokens.Item(i)
                    desc = (tok.GetDescription() or "").lower()
                    if "maria" in desc or "portuguese" in desc or "brasil" in desc or "brazil" in desc:
                        chosen_tok = tok
                        break
                if chosen_tok is not None:
                    break
            except Exception:
                continue

        if chosen_tok is not None:
            sp_voice.Voice = chosen_tok
        sp_voice.Rate = 1
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(wav_target, 3, False)
        try:
            sp_voice.AudioOutputStream = stream
            sp_voice.Speak(texto.strip())
        finally:
            stream.Close()

        if os.path.exists(wav_target) and os.path.getsize(wav_target) > 200:
            print(f"[TTS-Offline] Áudio sintetizado localmente via Windows OneCore -> {wav_target}")
            return wav_target
    except Exception as exc:
        print(f"[TTS-Offline] Falha no fallback offline Windows: {exc}")
    return ""


def _falar_edge_tts(texto: str, output_path: str, use_cache: bool = True) -> str:
    """Gera áudio via Microsoft Edge Neural TTS com prosódia ajustada, cache SHA-1 e gravação atômica."""
    voice, voice_en, rate, pitch, volume = _obter_parametros_edge()
    cache_key = hashlib.sha1(
        f"{voice}|{voice_en}|{rate}|{pitch}|{volume}|{texto.strip()}".encode("utf-8")
    ).hexdigest()[:16]
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
            c = edge_tts.Communicate(
                chunk_text.strip(), chunk_voice, rate=rate, pitch=pitch, volume=volume
            )
            data = b""
            async for chunk in c.stream():
                if chunk["type"] == "audio":
                    data += chunk["data"]
            return data

        async def _generate() -> None:
            match = None if voice == voice_en else _ENGLISH_PHRASE_REGEX.search(texto)
            if not match:
                communicate = edge_tts.Communicate(
                    texto.strip(), voice, rate=rate, pitch=pitch, volume=volume
                )
                await communicate.save(temp_path)
                return

            prefix = texto[: match.start()].strip()
            english_text = match.group(1).strip()
            suffix = texto[match.end() :].strip()

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
                    f"[TTS] Audio gerado via Edge TTS ({voice}, rate={rate}, pitch={pitch}) "
                    f"-> {output_path} ({file_size} bytes)"
                )
                return output_path
        return ""

    except Exception as e:
        print(f"[TTS] Erro Edge TTS: {e}")
        offline_enabled = os.getenv("TTS_OFFLINE_FALLBACK", "true").strip().lower() not in (
            "false",
            "0",
            "no",
        )
        if offline_enabled and not _em_teste():
            return _falar_windows_offline(texto, output_path)
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
        _PERMANENTES = {"senhor_ack.mp3"}
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
    Mantido 100% compatível com o contrato unitário de limpeza básica.
    """
    if not texto:
        return ""
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texto)
    t = re.sub(r"\*+", "", t)
    t = re.sub(r"`+", "", t)
    t = re.sub(r"#+\s*", "", t)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"[_~>|]", " ", t)
    t = re.sub(r"\(?\s*l[eê]-se\s+fra?y[i]?vis\s*\)?", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\(?\s*pronuncia-se\s+fra?y[i]?vis\s*\)?", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\bF\.?R\.?Y\.?I\.?V\.?s\b", "Frayvis", t, flags=re.IGNORECASE)
    t = re.sub(r"F\.R\.Y\.I\.Vs", "Frayvis", t, flags=re.IGNORECASE)
    t = re.sub(r"FRYIVs", "Frayvis", t, flags=re.IGNORECASE)
    t = re.sub(r"\bFryvis\b", "Frayvis", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def humanizar_texto_para_fala(texto: str) -> str:
    """
    Camada avançada de naturalização prosódica e fonética em Português:
    - Substitui blocos de código extensos e URLs cruas por resumos naturais.
    - Insere pausas respiratórias em listas e quebras de seção para evitar atropelo.
    - Converte moedas, graus e siglas técnicas para pronúncia natural.
    """
    if not texto:
        return ""

    t = texto
    # 1. Blocos de código cercados por ```...``` viram aviso falado conciso
    t = re.sub(
        r"```[\s\S]*?```",
        " Deixei o código detalhado no terminal. ",
        t,
    )

    # 2. Preserva rótulo de links markdown [rótulo](url) antes de remover URLs soltas
    t = re.sub(r"\[([^\]]+)\]\(https?://[^)\s]+\)", r"\1", t)
    t = re.sub(r"https?://\S+", " link disponível no chat ", t)

    # 3. Adiciona pontuação prosódica ao fim de linhas de lista/título sem pontuação final
    linhas_ajustadas: list[str] = []
    for linha in t.splitlines():
        s = linha.strip()
        if not s:
            continue
        eh_item_ou_titulo = bool(re.match(r"^(?:[-*+•]|\d+[.)]|#+)\s+", s))
        s = re.sub(r"^(?:[-*+•]|\d+[.)])\s+", "", s)
        s = re.sub(r"^#+\s*", "", s)
        if eh_item_ou_titulo and s and s[-1] not in ".!?:;,":
            s = f"{s}."
        linhas_ajustadas.append(s)
    t = " ".join(linhas_ajustadas)

    # 4. Expansões fonéticas naturais para PT-BR
    t = re.sub(r"R\$\s*(\d+(?:[.,]\d+)?)", r"\1 reais", t)
    t = re.sub(r"US\$\s*(\d+(?:[.,]\d+)?)", r"\1 dólares", t)
    t = re.sub(r"(\d+)\s*°C\b", r"\1 graus Celsius", t)
    t = re.sub(r"\bE2EE\b", "criptografia ponta a ponta", t)
    t = re.sub(r"\bchunks\s+KB\b", "blocos na base de conhecimento", t, flags=re.IGNORECASE)

    return limpar_texto_para_fala(t)


def dividir_em_sentencas_fala(
    texto_humanizado: str, min_chars: int = 38, max_chars: int = 230
) -> list[str]:
    """
    Divide um texto já humanizado em sentenças equilibradas para síntese streaming,
    unindo fragmentos muito curtos ("Sim, senhor.") à sentença seguinte para manter fluidez.
    """
    limpo = (texto_humanizado or "").strip()
    if not limpo:
        return []
    if len(limpo) <= min_chars * 2:
        return [limpo]

    partes_brutas = [p.strip() for p in re.split(r"(?<=[.!?;])\s+", limpo) if p.strip()]
    sentencas: list[str] = []
    buffer = ""

    for parte in partes_brutas:
        if not buffer:
            buffer = parte
        elif len(buffer) < min_chars or (len(buffer) + 1 + len(parte) <= 95):
            buffer = f"{buffer} {parte}"
        else:
            sentencas.append(buffer)
            buffer = parte

        while len(buffer) > max_chars:
            corte = buffer.rfind(", ", min_chars, max_chars)
            if corte == -1:
                corte = buffer.rfind(" ", min_chars, max_chars)
            if corte == -1:
                break
            sentencas.append(buffer[:corte].strip())
            buffer = buffer[corte:].strip(", ").strip()

    if buffer:
        if sentencas and len(buffer) < 22:
            sentencas[-1] = f"{sentencas[-1]} {buffer}"
        else:
            sentencas.append(buffer)

    return sentencas


def falar(
    texto: str,
    output_path: Optional[str] = "resposta.mp3",
    unique_file: bool = False,
) -> str:
    """
    Gera áudio da fala com thread-safety completo e humanização prosódica.
    """
    from core.e2ee_auth import is_session_unlocked

    if not is_session_unlocked():
        print("[TTS] Saída de voz bloqueada (F.R.Y.I.Vs travada via E2EE).")
        return ""

    try:
        from core.mute_state import is_muted

        if is_muted():
            print("[TTS] Saída de voz bloqueada (sistema mutado).")
            return ""
    except Exception:
        pass

    if not texto or not texto.strip():
        return ""

    texto_para_voz = humanizar_texto_para_fala(texto)
    if not texto_para_voz:
        return ""

    if unique_file or output_path is None:
        os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
        target_path = os.path.join(AUDIO_CACHE_DIR, f"audio_{uuid.uuid4().hex}.mp3")
    else:
        target_path = output_path

    load_dotenv()
    provider = os.getenv("TTS_PROVIDER", "auto").strip().lower()

    if provider == "offline":
        return _falar_windows_offline(texto_para_voz, target_path)

    if provider == "voicestudio":
        if falar_voicestudio is not None:
            result = falar_voicestudio(texto_para_voz, target_path)
            if result:
                return result
            print("[TTS] VoiceStudio indisponivel. Verifique se o app esta rodando.")
        else:
            print("[TTS] Modulo tts_voicestudio nao encontrado.")
        result = _falar_openai(texto_para_voz, target_path)
        if result:
            return result
        result = _falar_edge_tts(texto_para_voz, target_path)
        if result:
            return result

    elif provider == "edge":
        result = _falar_edge_tts(texto_para_voz, target_path)
        if result:
            return result

    else:
        if falar_voicestudio is not None and voicestudio_disponivel is not None:
            if voicestudio_disponivel():
                result = falar_voicestudio(texto_para_voz, target_path)
                if result:
                    return result
                print("[TTS] VoiceStudio falhou. Tentando OpenAI TTS...")

        result = _falar_openai(texto_para_voz, target_path)
        if result:
            return result

        print("[TTS] Usando fallback Edge TTS (gratuito)...")
        result = _falar_edge_tts(texto_para_voz, target_path)
        if result:
            return result

    print("[TTS] Nenhum provedor TTS disponivel.")
    return ""


def falar_streaming_local(
    texto: str,
    output_path: str = "resposta.mp3",
    tocar_fn: Optional[Callable[[str, bool], bool]] = None,
) -> tuple[str, bool]:
    """
    Síntese e reprodução local por sentenças com baixa latência de 1ª palavra:
    1. Divide respostas longas em sentenças naturais.
    2. Sintetiza a 1ª sentença e já dispara `tocar(bloquear=False)` imediatamente.
    3. Sintetiza as demais em sequência, enfileirando no `audio_player` e aguardando a última.
    4. Salva o áudio completo consolidado em `output_path` para consumo web (`/api/audio/last`).
    """
    from core.e2ee_auth import is_session_unlocked

    if not is_session_unlocked() or not texto or not texto.strip():
        return "", False

    if tocar_fn is None:
        from core.audio_player import tocar as _default_tocar

        tocar_fn = lambda p, b: _default_tocar(p, bloquear=b)

    humanizado = humanizar_texto_para_fala(texto)
    sentencas = dividir_em_sentencas_fala(humanizado)
    if len(sentencas) <= 1:
        caminho = falar(texto, output_path=output_path)
        if caminho and os.path.exists(caminho) and os.path.getsize(caminho) > 0:
            tocou = bool(tocar_fn(caminho, True))
            return caminho, tocou
        return "", False

    arquivos_gerados: list[str] = []
    tocou_algum = False
    try:
        from core.command_control import check_cancelled

        for idx, sentenca in enumerate(sentencas):
            check_cancelled()
            eh_ultima = idx == len(sentencas) - 1
            chunk_path = falar(sentenca, unique_file=True)
            if not chunk_path or not os.path.exists(chunk_path):
                continue
            arquivos_gerados.append(chunk_path)
            ok = bool(tocar_fn(chunk_path, eh_ultima))
            tocou_algum = tocou_algum or ok

        if not arquivos_gerados:
            return "", False

        # Consolida MP3 completo em output_path para /api/audio/last
        todos_mp3 = all(p.lower().endswith(".mp3") for p in arquivos_gerados)
        if todos_mp3 and output_path:
            temp_merged = f"{output_path}.tmp_merge_{os.getpid()}_{uuid.uuid4().hex[:8]}"
            try:
                with open(temp_merged, "wb") as out_f:
                    for part in arquivos_gerados:
                        with open(part, "rb") as in_f:
                            shutil.copyfileobj(in_f, out_f)
                if _safe_atomic_save(temp_merged, output_path):
                    return output_path, tocou_algum
            finally:
                if os.path.exists(temp_merged):
                    try:
                        os.remove(temp_merged)
                    except Exception:
                        pass

        return arquivos_gerados[-1], tocou_algum
    finally:
        for p in arquivos_gerados:
            if p != output_path and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
