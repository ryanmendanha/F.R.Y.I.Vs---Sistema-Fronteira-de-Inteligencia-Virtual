import React, { useEffect, useState, useRef, useCallback } from "react";
import ParticleDrift from "@/components/ui/particle-drift";
import AnimatedGradient from "@/registry/spell-ui/animated-gradient";
import { AIOrb } from "@/components/AIOrb";
import type { AIOrbState, AIOrbModel } from "@/components/AIOrb/types";
import { E2EELockGate } from "@/components/E2EELockGate";
import { AgentsControlPanel } from "@/components/AgentsControlPanel";
import { CommandRail, type GradientModeOption } from "@/components/CommandRail";
import { KnowledgeBaseDrawer } from "@/components/KnowledgeBaseDrawer";
import { FormattedText } from "@/components/FormattedText";
import {
  appendE2EETokenToUrl,
  buildE2EEHeaders,
  decryptChatPayload,
  encryptChatPayload,
  fetchE2EEStatus,
  getStoredE2EEToken,
  lockE2EESession,
  storeE2EEToken,
  type E2EEEnvelope,
  type E2EESession,
} from "@/lib/e2ee";
import {
  BrowserClapMonitor,
  isBrowserRecording,
  recordBrowserUtterance,
  stopActiveBrowserRecording,
} from "@/lib/webVoice";
import { Icons8Icon, type Icons8Name } from "@/components/Icons8Icon";

declare global {
  interface Window {
    __fryvisLiveScreen?: {
      open: () => void;
      close: () => void;
      toggle: () => void;
      isActive: () => boolean;
    };
  }
}

interface ChatMessageItem {
  role: "user" | "assistant";
  text: string;
  tools?: { tool: string; result: string }[];
  time: string;
}

const ENGINE_OPTIONS = [
  {
    id: "gemini",
    label: "Gemini",
    subLabel: "Cloud",
    icon: "sparkles" as Icons8Name,
    color: "text-amber-300",
    dotClass: "bg-amber-400",
    desc: "Google Gemini Cloud: raciocínio avançado e skills rápidas",
  },
  {
    id: "ollama",
    label: "Ollama",
    subLabel: "Local",
    icon: "cpu" as Icons8Name,
    color: "text-cyan-300",
    dotClass: "bg-cyan-400",
    desc: "Ollama Local: processamento privado offline",
  },
  {
    id: "hybrid",
    label: "Híbrido",
    subLabel: "Auto",
    icon: "zap" as Icons8Name,
    color: "text-emerald-300",
    dotClass: "bg-emerald-400",
    desc: "Prioriza Gemini Cloud com failover automático para Ollama",
  },
] as const;

const MODEL_PROFILES_CONFIG = [
  {
    id: "fryvis_beta",
    name: "Beta",
    fullName: "Fryvis Beta",
    tokens: "40 tok",
    description: "Ultra rápido · Respostas telegráficas",
    dotClass: "bg-cyan-400",
  },
  {
    id: "fryvis_1.0",
    name: "1.0",
    fullName: "Fryvis 1.0",
    tokens: "50 tok",
    description: "Equilibrado · Síntese clara em 1–2 frases",
    dotClass: "bg-blue-400",
  },
  {
    id: "fryvis_recursive",
    name: "Rec 1.1",
    fullName: "Recursive 1.1",
    tokens: "80+ tok",
    description: "Expandido · Raciocínio multi-etapa profundo",
    dotClass: "bg-emerald-400",
  },
] as const;

const stateTitles: Record<AIOrbState, string> = {
  idle: "SISTEMA PRONTO",
  listening: "ESCUTANDO...",
  thinking: "PROCESSANDO...",
  speaking: "FALANDO...",
};

const stateDotColors: Record<AIOrbState, string> = {
  idle: "bg-cyan-400",
  listening: "bg-emerald-400 animate-pulse",
  thinking: "bg-amber-400 animate-ping",
  speaking: "bg-blue-400 animate-bounce",
};

export default function App() {
  const [aiState, setAiState] = useState<AIOrbState>("idle");
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [input, setInput] = useState("");
  const chatTextareaRef = useRef<HTMLTextAreaElement>(null);
  const [status, setStatus] = useState<Record<string, any>>({});
  const [wsConnected, setWsConnected] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [isFullScreenOrb, setIsFullScreenOrb] = useState(false);
  const [chatOpen, setChatOpen] = useState(true);
  const [wakeWordActive, setWakeWordActive] = useState(true);
  const [micMuted, setMicMuted] = useState<boolean>(false);
  const [clapEnabled, setClapEnabled] = useState<boolean>(true);
  const [clapFlash, setClapFlash] = useState<boolean>(false);
  const clapTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clapMonitorRef = useRef<BrowserClapMonitor | null>(null);
  const fileUploadInputRef = useRef<HTMLInputElement>(null);
  const [uploadingFile, setUploadingFile] = useState<boolean>(false);
  const isWebMode = status.runtime_mode === "web";

  const [gradientMode, setGradientMode] = useState<GradientModeOption>(() => {
    try {
      return (localStorage.getItem("fryvis_gradient_mode") as GradientModeOption) || "auto";
    } catch {
      return "auto";
    }
  });

  const handleGradientModeChange = (mode: GradientModeOption) => {
    setGradientMode(mode);
    try {
      localStorage.setItem("fryvis_gradient_mode", mode);
    } catch {}
  };

  const [orbModel, setOrbModel] = useState<AIOrbModel>(() => {
    try {
      return (localStorage.getItem("fryvis_orb_model") as AIOrbModel) || "orbital-hud";
    } catch {
      return "orbital-hud";
    }
  });

  const handleOrbModelChange = (m: AIOrbModel) => {
    setOrbModel(m);
    try {
      localStorage.setItem("fryvis_orb_model", m);
    } catch {}
  };

  const [agentsPanelOpen, setAgentsPanelOpen] = useState(false);
  const [agentsBadgeCount, setAgentsBadgeCount] = useState(0);
  const [officeCommand, setOfficeCommand] = useState<{
    seq: number;
    action: string;
    profile?: any;
    activity?: string | null;
    view_mode?: "office3d" | "list" | null;
  } | null>(null);
  const [agentEventSeq, setAgentEventSeq] = useState(0);
  const [kbDrawerOpen, setKbDrawerOpen] = useState(false);
  const [kbChunksCount, setKbChunksCount] = useState(0);
  const [liveScreenActive, setLiveScreenActive] = useState(false);
  const [expandedToolsMsgIdx, setExpandedToolsMsgIdx] = useState<Record<number, boolean>>({});
  const [copiedMsgIdx, setCopiedMsgIdx] = useState<number | null>(null);

  // Estado E2EE
  const [e2eeChecking, setE2eeChecking] = useState<boolean>(true);
  const [e2eeRequired, setE2eeRequired] = useState<boolean>(true);
  const [e2eeUnlocked, setE2eeUnlocked] = useState<boolean>(false);
  const [e2eeHasPassword, setE2eeHasPassword] = useState<boolean>(true);
  const [e2eeLockoutSecs, setE2eeLockoutSecs] = useState<number>(0);
  const [e2eeSessionToken, setE2eeSessionToken] = useState<string | null>(() =>
    getStoredE2EEToken(),
  );
  const e2eeSessionKeyRef = useRef<CryptoKey | null>(null);

  const [engineProvider, setEngineProvider] = useState<string>(() => {
    try {
      return localStorage.getItem("fryvis_engine_provider") || "gemini";
    } catch {
      return "gemini";
    }
  });

  const handleEngineChange = (provider: string) => {
    setEngineProvider(provider);
    try {
      localStorage.setItem("fryvis_engine_provider", provider);
    } catch {}
  };

  const [modelProfile, setModelProfile] = useState<string>(() => {
    try {
      return localStorage.getItem("fryvis_model_profile") || "fryvis_1.0";
    } catch {
      return "fryvis_1.0";
    }
  });

  const handleProfileChange = (p: string) => {
    setModelProfile(p);
    try {
      localStorage.setItem("fryvis_model_profile", p);
    } catch {}
  };

  // Menu unificado Motor + Perfil no Top HUD
  const [enginePopoverOpen, setEnginePopoverOpen] = useState(false);
  const enginePopoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!enginePopoverOpen) return;
    const onOutside = (e: MouseEvent) => {
      if (enginePopoverRef.current && !enginePopoverRef.current.contains(e.target as Node)) {
        setEnginePopoverOpen(false);
      }
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setEnginePopoverOpen(false);
    };
    document.addEventListener("mousedown", onOutside);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onOutside);
      document.removeEventListener("keydown", onEsc);
    };
  }, [enginePopoverOpen]);

  useEffect(() => {
    const onLiveScreenChange = (e: Event) => {
      const detail = (e as CustomEvent<{ active?: boolean }>).detail;
      setLiveScreenActive(Boolean(detail?.active));
    };
    window.addEventListener("fryvis-live-screen-change", onLiveScreenChange);
    return () => window.removeEventListener("fryvis-live-screen-change", onLiveScreenChange);
  }, []);

  const currentEngine =
    ENGINE_OPTIONS.find((e) => e.id === engineProvider) || ENGINE_OPTIONS[0];
  const currentProfile =
    MODEL_PROFILES_CONFIG.find((p) => p.id === modelProfile) || MODEL_PROFILES_CONFIG[1];

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const dataArrayRef = useRef<Uint8Array<ArrayBuffer> | null>(null);
  const sourceNodeRef = useRef<MediaElementAudioSourceNode | null>(null);

  const forceLocalLock = useCallback(() => {
    stopActiveBrowserRecording();
    clapMonitorRef.current?.stop();
    clapMonitorRef.current = null;
    e2eeSessionKeyRef.current = null;
    storeE2EEToken(null);
    setE2eeSessionToken(null);
    setE2eeUnlocked(false);
    setAgentsPanelOpen(false);
    setKbDrawerOpen(false);
    setAiState("idle");
    setAudioLevel(0);
    window.__fryvisLiveScreen?.close();
    try {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.removeAttribute("src");
      }
    } catch {}
    try {
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    } catch {}
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    let active = true;
    const storedToken = getStoredE2EEToken();
    fetchE2EEStatus(storedToken)
      .then((e2eeSt) => {
        if (!active) return;
        setE2eeRequired(e2eeSt.required);
        setE2eeHasPassword(e2eeSt.has_password_configured);
        setE2eeLockoutSecs(e2eeSt.lockout_remaining_seconds || 0);
        if (!e2eeSt.required) {
          setE2eeUnlocked(true);
        } else if (e2eeSt.unlocked && e2eeSt.session_valid && storedToken) {
          setE2eeSessionToken(storedToken);
          setE2eeUnlocked(true);
        } else {
          storeE2EEToken(null);
          setE2eeSessionToken(null);
          setE2eeUnlocked(false);
        }
      })
      .catch(() => {
        if (!active) return;
        setE2eeRequired(true);
        setE2eeUnlocked(false);
      })
      .finally(() => {
        if (active) setE2eeChecking(false);
      });

    fetch("/api/status")
      .then((res) => res.json())
      .then((data) => {
        if (!active) return;
        setStatus(data);
        if (typeof data.voice_daemon_active === "boolean") {
          setWakeWordActive(data.voice_daemon_active);
        }
        if (typeof data.mic_muted === "boolean") {
          setMicMuted(data.mic_muted);
        }
      })
      .catch(() => {});

    fetch("/api/knowledge/status")
      .then((res) => res.json())
      .then((kb) => {
        if (active && typeof kb.count === "number") {
          setKbChunksCount(kb.count);
        }
      })
      .catch(() => {});

    fetch("/api/voice/clap")
      .then((res) => res.json())
      .then((cl) => {
        if (active && typeof cl.enabled === "boolean") {
          setClapEnabled(cl.enabled);
        }
      })
      .catch(() => {});

    return () => {
      active = false;
      if (clapTimerRef.current) clearTimeout(clapTimerRef.current);
    };
  }, []);

  const wsRef = useRef<WebSocket | null>(null);
  const wsReconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wsReconnectDelay = useRef<number>(1000);

  useEffect(() => {
    if (e2eeChecking || (e2eeRequired && (!e2eeUnlocked || !e2eeSessionToken))) {
      if (wsReconnectTimerRef.current) {
        clearTimeout(wsReconnectTimerRef.current);
        wsReconnectTimerRef.current = null;
      }
      wsRef.current?.close();
      wsRef.current = null;
      setWsConnected(false);
      return;
    }

    let disposed = false;
    let wsPingTimer: ReturnType<typeof setInterval> | null = null;

    function connectWs() {
      if (disposed) return;
      if (wsReconnectTimerRef.current) {
        clearTimeout(wsReconnectTimerRef.current);
        wsReconnectTimerRef.current = null;
      }
      if (wsPingTimer) {
        clearInterval(wsPingTimer);
        wsPingTimer = null;
      }
      const protocol = location.protocol === "https:" ? "wss:" : "ws:";
      const baseWsUrl = `${protocol}//${location.host || "127.0.0.1:8000"}/ws`;
      const wsUrl = appendE2EETokenToUrl(baseWsUrl, e2eeSessionToken);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
        wsReconnectDelay.current = 1000;
        if (wsPingTimer) clearInterval(wsPingTimer);
        wsPingTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, 25000);
      };

      ws.onclose = (ev) => {
        if (wsPingTimer) {
          clearInterval(wsPingTimer);
          wsPingTimer = null;
        }
        setWsConnected(false);
        wsRef.current = null;
        if (disposed) return;
        if (ev.code === 4423) {
          forceLocalLock();
          return;
        }
        const delay = wsReconnectDelay.current;
        wsReconnectDelay.current = Math.min(delay * 2, 30000);
        wsReconnectTimerRef.current = setTimeout(connectWs, delay);
      };

      ws.onerror = () => {
        ws.close();
      };

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.type === "e2ee_locked") {
            forceLocalLock();
            return;
          }
          if (data.type === "state_change") {
            setAiState(data.state);
            if (data.state === "idle") setAudioLevel(0);
          } else if (data.type === "wake_detected") {
            setAiState("speaking");
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant",
                text: data.response || "Senhor?",
                time: new Date().toLocaleTimeString(),
              },
            ]);
          } else if (data.type === "transcription" && data.transcription) {
            setMessages((prev) => [
              ...prev,
              { role: "user", text: data.transcription, time: new Date().toLocaleTimeString() },
            ]);
          } else if (data.type === "chat_response") {
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant",
                text: data.response,
                tools: data.tools_executed,
                time: new Date().toLocaleTimeString(),
              },
            ]);
          } else if (data.type === "voice_daemon_status") {
            if (typeof data.active === "boolean") setWakeWordActive(data.active);
          } else if (data.type === "mic_muted") {
            if (typeof data.muted === "boolean") setMicMuted(data.muted);
          } else if (data.type === "clap_config") {
            if (typeof data.enabled === "boolean") setClapEnabled(data.enabled);
          } else if (data.type === "clap_detected") {
            setClapFlash(true);
            if (clapTimerRef.current) clearTimeout(clapTimerRef.current);
            clapTimerRef.current = setTimeout(() => setClapFlash(false), 2400);
          } else if (data.type === "agent_office_command") {
            if (data.action === "close") {
              setAgentsPanelOpen(false);
            } else {
              setAgentsPanelOpen(true);
              setOfficeCommand({
                seq: Date.now() + Math.random(),
                action: data.action,
                profile: data.profile,
                activity: data.activity,
                view_mode: data.view_mode,
              });
            }
          } else if (typeof data.type === "string" && data.type.startsWith("agent_job_")) {
            setAgentEventSeq((s) => s + 1);
            if (
              data.type === "agent_job_indexed" &&
              typeof data.kb_info?.total_chunks_base === "number"
            ) {
              setKbChunksCount(data.kb_info.total_chunks_base);
            }
          }
        } catch {}
      };
    }

    connectWs();

    return () => {
      disposed = true;
      if (wsPingTimer) clearInterval(wsPingTimer);
      if (wsReconnectTimerRef.current) clearTimeout(wsReconnectTimerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [e2eeChecking, e2eeRequired, e2eeUnlocked, e2eeSessionToken, forceLocalLock]);

  const initAudioAnalyser = () => {
    if (!audioRef.current || audioContextRef.current) return;
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      const ctx = new AudioCtx();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 64;
      analyser.smoothingTimeConstant = 0.8;
      const source = ctx.createMediaElementSource(audioRef.current);
      source.connect(analyser);
      analyser.connect(ctx.destination);
      audioContextRef.current = ctx;
      analyserRef.current = analyser;
      sourceNodeRef.current = source;
      dataArrayRef.current = new Uint8Array(analyser.frequencyBinCount);
    } catch {}
  };

  useEffect(() => {
    if (aiState !== "speaking" && aiState !== "listening") {
      setAudioLevel(0);
      return;
    }
    let animId: number;
    const updateAudioLevel = (t: number) => {
      let measured = 0;
      const browserPlaying = Boolean(audioRef.current && !audioRef.current.paused);
      if (browserPlaying && analyserRef.current && dataArrayRef.current) {
        analyserRef.current.getByteFrequencyData(dataArrayRef.current);
        let sum = 0;
        for (let i = 0; i < dataArrayRef.current.length; i++) sum += dataArrayRef.current[i];
        measured = sum / (dataArrayRef.current.length * 255);
      }
      if (measured > 0.015) {
        setAudioLevel(Math.min(1, measured * 1.45));
      } else if (aiState === "speaking") {
        const s = t * 0.001;
        const synthetic =
          0.26 +
          0.16 * Math.abs(Math.sin(s * 6.4)) +
          0.11 * Math.abs(Math.sin(s * 11.3 + 0.8));
        setAudioLevel(synthetic);
      } else if (aiState === "listening") {
        const s = t * 0.001;
        setAudioLevel(0.14 + 0.08 * Math.abs(Math.sin(s * 3.8)));
      }
      animId = requestAnimationFrame(updateAudioLevel);
    };
    animId = requestAnimationFrame(updateAudioLevel);
    return () => cancelAnimationFrame(animId);
  }, [aiState]);

  const cleanTextForSpeech = (text: string) => {
    if (!text) return "";
    return text
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/\*+/g, "")
      .replace(/`+/g, "")
      .replace(/#+\s*/g, "")
      .replace(/^\s*[-*+]\s+/gm, "")
      .replace(/\(?\s*l[eê]-se\s+fra?y[i]?vis\s*\)?/gi, "")
      .replace(/\(?\s*pronuncia-se\s+fra?y[i]?vis\s*\)?/gi, "")
      .replace(/\bF\.?R\.?Y\.?I\.?V\.?s\b/gi, "Frayvis")
      .replace(/F\.R\.Y\.I\.Vs/gi, "Frayvis")
      .replace(/FRYIVs/gi, "Frayvis")
      .replace(/\bFryvis\b/gi, "Frayvis")
      .replace(/[_~>|]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  };

  const speakWithBrowser = (text: string) => {
    if (!text || !("speechSynthesis" in window)) {
      setAiState("idle");
      return;
    }
    const cleaned = cleanTextForSpeech(text);
    if (!cleaned) {
      setAiState("idle");
      return;
    }
    try {
      window.speechSynthesis.cancel();
    } catch {}

    const estimatedMs = Math.min(25000, Math.max(2500, cleaned.length * 85));
    const safetyTimer = setTimeout(() => {
      setAiState("idle");
      setAudioLevel(0);
    }, estimatedMs);

    const finishSpeech = () => {
      clearTimeout(safetyTimer);
      setAiState("idle");
      setAudioLevel(0);
    };

    const u = new SpeechSynthesisUtterance(cleaned);
    (window as any).__fryvisActiveUtterance = u;
    u.lang = "pt-BR";
    u.rate = 1.05;
    u.pitch = 1.0;
    u.onend = finishSpeech;
    u.onerror = finishSpeech;

    setAiState("speaking");
    try {
      window.speechSynthesis.speak(u);
    } catch {
      finishSpeech();
    }
  };

  const handleE2EEUnlocked = (session: E2EESession) => {
    e2eeSessionKeyRef.current = session.sessionKey;
    setE2eeSessionToken(session.token);
    setE2eeUnlocked(true);
    setE2eeLockoutSecs(0);
  };

  const handleLockAI = async () => {
    const tokenToRevoke = e2eeSessionToken;
    wsRef.current?.close();
    wsRef.current = null;
    forceLocalLock();
    await lockE2EESession(tokenToRevoke);
  };

  const toggleMicMute = async () => {
    if (e2eeRequired && !e2eeUnlocked) return;
    const novoMute = !micMuted;
    setMicMuted(novoMute);
    try {
      const res = await fetch("/api/voice/mute", {
        method: "POST",
        headers: buildE2EEHeaders(e2eeSessionToken, { "Content-Type": "application/json" }),
        body: JSON.stringify({ muted: novoMute }),
      });
      if (res.status === 423) {
        forceLocalLock();
        setMicMuted(!novoMute);
      }
    } catch {
      setMicMuted(!novoMute);
    }
  };

  const sendMessageText = async (rawText: string) => {
    if (e2eeRequired && !e2eeUnlocked) return;
    const userMsg = rawText.trim();
    if (!userMsg) return;

    const recentHistory = messages.slice(-8).map((m) => ({
      role: m.role === "assistant" ? "assistant" : "user",
      content: m.text,
    }));
    setInput("");
    if (chatTextareaRef.current) {
      chatTextareaRef.current.style.height = "auto";
    }
    setMessages((prev) => [
      ...prev,
      { role: "user", text: userMsg, time: new Date().toLocaleTimeString() },
    ]);
    setAiState("thinking");
    try {
      const rawChatPayload = {
        message: userMsg,
        model_profile: modelProfile,
        provider: engineProvider,
        use_memory: true,
        generate_speech: true,
        history: recentHistory,
      };

      const sessionKey = e2eeSessionKeyRef.current;
      const bodyObj =
        sessionKey && e2eeSessionToken
          ? { e2ee: await encryptChatPayload(sessionKey, rawChatPayload) }
          : rawChatPayload;

      const res = await fetch("/api/chat", {
        method: "POST",
        headers: buildE2EEHeaders(e2eeSessionToken, { "Content-Type": "application/json" }),
        body: JSON.stringify(bodyObj),
      });

      if (res.status === 423) {
        forceLocalLock();
        return;
      }

      const rawData = await res.json();
      const data =
        rawData && rawData.encrypted && rawData.e2ee && sessionKey
          ? await decryptChatPayload<any>(sessionKey, rawData.e2ee as E2EEEnvelope)
          : rawData;

      if (data && data.response) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            text: data.response,
            tools: data.tools_executed,
            time: new Date().toLocaleTimeString(),
          },
        ]);
      }

      if (data && data.played_locally) {
        setAiState("idle");
        setAudioLevel(0);
      } else if (data && data.has_audio && audioRef.current && !micMuted) {
        initAudioAnalyser();
        if (audioContextRef.current?.state === "suspended") {
          audioContextRef.current.resume().catch(() => {});
        }
        setAiState("speaking");
        const baseAudioSrc = data.audio_url || `/api/audio/last?v=${Date.now()}`;
        audioRef.current.src = appendE2EETokenToUrl(baseAudioSrc, e2eeSessionToken);

        const audioTimer = setTimeout(() => {
          setAiState("idle");
          setAudioLevel(0);
        }, 30000);

        audioRef.current.onended = () => {
          clearTimeout(audioTimer);
          setAiState("idle");
          setAudioLevel(0);
        };
        audioRef.current.onerror = () => {
          clearTimeout(audioTimer);
          speakWithBrowser(data.response);
        };
        audioRef.current.play().catch(() => {
          clearTimeout(audioTimer);
          speakWithBrowser(data.response);
        });
      } else if (data && data.response && !micMuted) {
        speakWithBrowser(data.response);
      } else {
        setAiState("idle");
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: "Não foi possível obter resposta no momento, senhor. O núcleo está restabelecendo conexões.",
          time: new Date().toLocaleTimeString(),
        },
      ]);
      setAiState("idle");
    }
  };

  const handleSend = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    void sendMessageText(input);
  };

  const pararComandoAtivo = async () => {
    stopActiveBrowserRecording();
    try {
      if (audioRef.current) {
        audioRef.current.pause();
      }
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    } catch {}
    setAiState("idle");
    setAudioLevel(0);
    try {
      await fetch("/api/commands/cancel", {
        method: "POST",
        headers: buildE2EEHeaders(e2eeSessionToken),
      });
    } catch {}
  };

  const handleVoice = async () => {
    if (e2eeRequired && !e2eeUnlocked) return;
    if (aiState === "thinking" || aiState === "speaking") return;

    if (isWebMode) {
      if (isBrowserRecording() || aiState === "listening") {
        stopActiveBrowserRecording();
        return;
      }
      if (micMuted) {
        await toggleMicMute();
        return;
      }
      setAiState("listening");
      clapMonitorRef.current?.setSuppressed(true);
      try {
        const blob = await recordBrowserUtterance({
          maxDurationMs: 10000,
          silenceHoldMs: 1200,
          onLevel: setAudioLevel,
        });
        if (!blob || blob.size < 128) {
          setAiState("idle");
          setAudioLevel(0);
          clapMonitorRef.current?.setSuppressed(false);
          return;
        }
        setAiState("thinking");
        setAudioLevel(0);
        const qs = new URLSearchParams({
          profile: modelProfile,
          provider: engineProvider,
        });
        const res = await fetch(`/api/voice/transcribe?${qs.toString()}`, {
          method: "POST",
          headers: buildE2EEHeaders(e2eeSessionToken, {
            "Content-Type": blob.type || "audio/webm",
          }),
          body: blob,
        });
        if (res.status === 423) {
          forceLocalLock();
          return;
        }
        if (!res.ok) {
          setAiState("idle");
          return;
        }
        const data = await res.json();
        if (data.transcription) {
          setMessages((prev) => [
            ...prev,
            {
              role: "user",
              text: data.transcription,
              time: new Date().toLocaleTimeString(),
            },
          ]);
        }
        if (data.response) {
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              text: data.response,
              tools: data.tools_executed,
              time: new Date().toLocaleTimeString(),
            },
          ]);
        }
        if (data.has_audio && audioRef.current && !micMuted) {
          initAudioAnalyser();
          if (audioContextRef.current?.state === "suspended") {
            audioContextRef.current.resume().catch(() => {});
          }
          setAiState("speaking");
          const baseAudioSrc = data.audio_url || `/api/audio/last?v=${Date.now()}`;
          audioRef.current.src = appendE2EETokenToUrl(baseAudioSrc, e2eeSessionToken);
          const audioTimer = setTimeout(() => {
            setAiState("idle");
            setAudioLevel(0);
          }, 30000);
          audioRef.current.onended = () => {
            clearTimeout(audioTimer);
            setAiState("idle");
            setAudioLevel(0);
          };
          audioRef.current.onerror = () => {
            clearTimeout(audioTimer);
            speakWithBrowser(data.response);
          };
          audioRef.current.play().catch(() => {
            clearTimeout(audioTimer);
            speakWithBrowser(data.response);
          });
        } else if (data.response && !micMuted) {
          speakWithBrowser(data.response);
        } else {
          setAiState("idle");
        }
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            text: "Permita o acesso ao microfone no navegador para comandos por voz, senhor.",
            time: new Date().toLocaleTimeString(),
          },
        ]);
        setAiState("idle");
        setAudioLevel(0);
      }
      return;
    }

    if (aiState === "listening") {
      setAiState("idle");
      setAudioLevel(0);
      return;
    }
    if (micMuted) {
      await toggleMicMute();
      return;
    }
    try {
      const res = await fetch("/api/voice/trigger", {
        method: "POST",
        headers: buildE2EEHeaders(e2eeSessionToken),
      });
      if (res.status === 423) forceLocalLock();
    } catch {}
  };

  const handleVoiceRef = useRef(handleVoice);
  handleVoiceRef.current = handleVoice;

  useEffect(() => {
    clapMonitorRef.current?.setSuppressed(aiState !== "idle");
  }, [aiState]);

  useEffect(() => {
    const canListenClaps =
      isWebMode &&
      !e2eeChecking &&
      (!e2eeRequired || e2eeUnlocked) &&
      clapEnabled &&
      !micMuted;
    if (!canListenClaps) {
      clapMonitorRef.current?.stop();
      clapMonitorRef.current = null;
      return;
    }
    const monitor = new BrowserClapMonitor();
    clapMonitorRef.current = monitor;
    void monitor.start(() => {
      setClapFlash(true);
      if (clapTimerRef.current) clearTimeout(clapTimerRef.current);
      clapTimerRef.current = setTimeout(() => setClapFlash(false), 2400);
      void handleVoiceRef.current();
    });
    return () => {
      monitor.stop();
      if (clapMonitorRef.current === monitor) {
        clapMonitorRef.current = null;
      }
    };
  }, [isWebMode, e2eeChecking, e2eeRequired, e2eeUnlocked, clapEnabled, micMuted]);

  const handleUploadWorkspaceFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || (e2eeRequired && !e2eeUnlocked)) return;
    setUploadingFile(true);
    try {
      const res = await fetch(`/api/files/upload?filename=${encodeURIComponent(file.name)}`, {
        method: "POST",
        headers: buildE2EEHeaders(e2eeSessionToken, {
          "Content-Type": file.type || "application/octet-stream",
        }),
        body: file,
      });
      if (res.status === 423) {
        forceLocalLock();
        return;
      }
      const data = await res.json();
      if (!res.ok) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            text: data?.detail || "Não foi possível enviar o arquivo, senhor.",
            time: new Date().toLocaleTimeString(),
          },
        ]);
        return;
      }
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: `Arquivo **${data.name}** carregado no workspace, senhor. Pode pedir para analisar, resumir ou editar os dados.`,
          time: new Date().toLocaleTimeString(),
        },
      ]);
      chatTextareaRef.current?.focus();
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: "Falha de conexão ao enviar o arquivo, senhor.",
          time: new Date().toLocaleTimeString(),
        },
      ]);
    } finally {
      setUploadingFile(false);
    }
  };

  const executeSkill = async (skill: string, args: Record<string, unknown> = {}) => {
    if (e2eeRequired && !e2eeUnlocked) return;
    try {
      const res = await fetch("/api/skills/execute", {
        method: "POST",
        headers: buildE2EEHeaders(e2eeSessionToken, { "Content-Type": "application/json" }),
        body: JSON.stringify({ skill, arguments: args }),
      });
      if (res.status === 423) forceLocalLock();
    } catch {}
  };

  const handleCopyMsg = (idx: number, text: string) => {
    navigator.clipboard?.writeText(text).then(() => {
      setCopiedMsgIdx(idx);
      setTimeout(() => setCopiedMsgIdx(null), 1600);
    });
  };

  const toggleClapWake = async () => {
    if (e2eeRequired && !e2eeUnlocked) return;
    const nextVal = !clapEnabled;
    setClapEnabled(nextVal);
    try {
      const res = await fetch("/api/voice/clap", {
        method: "POST",
        headers: buildE2EEHeaders(e2eeSessionToken, { "Content-Type": "application/json" }),
        body: JSON.stringify({ enabled: nextVal }),
      });
      if (res.status === 423) {
        forceLocalLock();
        setClapEnabled(!nextVal);
      }
    } catch {
      setClapEnabled(!nextVal);
    }
  };

  const activeGradientPreset =
    gradientMode === "auto"
      ? clapFlash || aiState === "listening"
        ? "Pulse"
        : aiState === "thinking"
          ? "Plasma"
          : "Prism"
      : gradientMode === "off"
        ? "Prism"
        : gradientMode;

  const activeGradientSpeed =
    aiState === "speaking" ? Math.round(30 + audioLevel * 36) : clapFlash ? 42 : 28;

  return (
    <div className="w-screen h-dvh flex overflow-hidden bg-[#02050b] text-slate-200 font-sans selection:bg-cyan-500/30">
      <audio ref={audioRef} className="hidden" preload="auto" />

      {/* Camada Spell UI AnimatedGradient (Prism / Reativo) + Partículas Sutis */}
      {gradientMode !== "off" && (
        <div className="fixed inset-0 z-0 pointer-events-none opacity-45 transition-opacity duration-700">
          <AnimatedGradient
            paused={agentsPanelOpen}
            style={{ zIndex: 0 }}
            config={{ preset: activeGradientPreset, speed: activeGradientSpeed }}
            noise={{ opacity: 0.07 }}
          />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_44%_50%,transparent_14%,#02050b_85%)]" />
        </div>
      )}

      {/* Partículas ambientais sutis */}
      <div className="fixed inset-0 z-0 pointer-events-none opacity-15 mix-blend-screen">
        {!agentsPanelOpen && (
          <ParticleDrift
            mode="dark"
            speed={aiState === "thinking" ? 1.1 : 0.35}
            density={0.45}
            hue={aiState === "thinking" ? 195 : aiState === "listening" ? 150 : 210}
          />
        )}
      </div>

      {/* 1. Command Rail Lateral Esquerdo */}
      {!isFullScreenOrb && (
        <CommandRail
          orbModel={orbModel}
          onOrbModelChange={handleOrbModelChange}
          gradientMode={gradientMode}
          onGradientModeChange={handleGradientModeChange}
          isFullScreenOrb={isFullScreenOrb}
          onToggleFullScreen={() => setIsFullScreenOrb((v) => !v)}
          agentsOpen={agentsPanelOpen}
          onOpenAgents={() => setAgentsPanelOpen(true)}
          agentsBadgeCount={agentsBadgeCount}
          kbOpen={kbDrawerOpen}
          onOpenKB={() => setKbDrawerOpen(true)}
          kbChunksCount={kbChunksCount}
          chatOpen={chatOpen}
          onToggleChat={() => setChatOpen((v) => !v)}
          onToggleLiveScreen={() => window.__fryvisLiveScreen?.toggle()}
          liveScreenActive={liveScreenActive}
          onExecuteSkill={executeSkill}
          aiState={aiState}
          onSetDemoState={(st, lvl) => {
            setAiState(st);
            setAudioLevel(lvl);
          }}
          audioLevel={audioLevel}
          onAudioLevelChange={setAudioLevel}
          e2eeRequired={e2eeRequired}
          e2eeUnlocked={e2eeUnlocked}
          onLockAI={handleLockAI}
          isWebMode={isWebMode}
        />
      )}

      {/* 2. Palco Central 3D + Top HUD Minimalista */}
      <main className="flex-1 min-w-0 relative flex flex-col items-center justify-center z-10 overflow-hidden">
        {/* Top HUD enxuto e respirável */}
        <header className="absolute top-0 inset-x-0 z-30 flex items-center justify-between gap-3 px-5 py-3.5 pointer-events-none">
          {/* Esquerda: Wordmark + Conexão */}
          <div className="flex items-center gap-3 pointer-events-auto">
            <div className="flex flex-col">
              <div className="flex items-center gap-2">
                <h1 className="text-[13px] font-bold tracking-[0.28em] text-white leading-none">
                  F.R.Y.I.Vs
                </h1>
                <span
                  title={wsConnected ? "Conectado em tempo real (WebSocket)" : "Reconectando..."}
                  className={`w-1.5 h-1.5 rounded-full ${
                    wsConnected ? "bg-emerald-400" : "bg-red-400"
                  }`}
                />
              </div>
              <p className="text-[8.5px] uppercase tracking-[0.24em] text-slate-400 font-mono mt-1">
                SISTEMA FRONTEIRA DE INTELIGÊNCIA <span className="text-cyan-400 font-semibold">VIRTUAL</span>
              </p>
            </div>
          </div>

          {/* Centro: Pílula de Estado Cognitivo */}
          <div className="hidden md:flex items-center gap-2 px-4 py-1.5 rounded-full border border-white/10 bg-[#050b16]/80 backdrop-blur-xl">
            <span className={`w-2 h-2 rounded-full ${stateDotColors[aiState]}`} />
            <span className="text-[10px] uppercase tracking-[0.22em] font-mono font-semibold text-slate-200">
              {stateTitles[aiState]}
            </span>
          </div>

          {/* Direita: Seletor Unificado (Motor + Perfil) + Agentes + E2EE */}
          <div className="flex items-center gap-2 pointer-events-auto">
            <div ref={enginePopoverRef} className="relative">
              <button
                type="button"
                onClick={() => setEnginePopoverOpen((v) => !v)}
                aria-expanded={enginePopoverOpen}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[#060d1c]/85 border border-white/12 hover:border-cyan-400/40 text-[11px] font-mono text-slate-200 transition-all cursor-pointer backdrop-blur-xl"
              >
                <Icons8Icon name={currentEngine.icon} size={13} className={currentEngine.color} />
                <span className="font-semibold">{currentEngine.label}</span>
                <span className="text-slate-600">·</span>
                <span className="text-slate-300">{currentProfile.name}</span>
                <Icons8Icon
                  name="chevron-down"
                  size={12}
                  className={`text-slate-400 transition-transform ${
                    enginePopoverOpen ? "rotate-180" : ""
                  }`}
                />
              </button>

              {enginePopoverOpen && (
                <div className="absolute right-0 top-full mt-2 w-72 rounded-2xl bg-[#050b18]/98 border border-white/12 shadow-2xl backdrop-blur-3xl p-3 space-y-3 z-50">
                  <div>
                    <p className="text-[9.5px] font-mono uppercase tracking-widest text-slate-400 font-semibold px-1 mb-1.5">
                      Motor de Inteligência
                    </p>
                    <div className="grid grid-cols-3 gap-1.5">
                      {ENGINE_OPTIONS.map((eng) => {
                        const active = engineProvider === eng.id;
                        return (
                          <button
                            key={eng.id}
                            type="button"
                            onClick={() => handleEngineChange(eng.id)}
                            title={eng.desc}
                            className={`flex flex-col items-center gap-1 py-2 px-2 rounded-xl border text-[10.5px] font-mono transition-all cursor-pointer ${
                              active
                                ? "bg-cyan-500/16 border-cyan-400/50 text-white font-semibold"
                                : "bg-white/[0.03] border-white/8 text-slate-400 hover:text-slate-200"
                            }`}
                          >
                            <Icons8Icon
                              name={eng.icon}
                              size={14}
                              className={active ? eng.color : "text-slate-500"}
                            />
                            <span>{eng.label}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="pt-2.5 border-t border-white/10">
                    <p className="text-[9.5px] font-mono uppercase tracking-widest text-slate-400 font-semibold px-1 mb-1.5">
                      Perfil de Raciocínio
                    </p>
                    <div className="space-y-1">
                      {MODEL_PROFILES_CONFIG.map((prof) => {
                        const active = modelProfile === prof.id;
                        return (
                          <button
                            key={prof.id}
                            type="button"
                            onClick={() => {
                              handleProfileChange(prof.id);
                              setEnginePopoverOpen(false);
                            }}
                            className={`w-full text-left px-2.5 py-2 rounded-xl border flex items-center justify-between transition-all cursor-pointer ${
                              active
                                ? "bg-cyan-500/12 border-cyan-400/45 text-white"
                                : "bg-transparent border-transparent hover:bg-white/[0.04] text-slate-300"
                            }`}
                          >
                            <div className="min-w-0 pr-2">
                              <div className="flex items-center gap-2">
                                <span className={`w-1.5 h-1.5 rounded-full ${prof.dotClass}`} />
                                <span className="text-xs font-mono font-semibold">{prof.fullName}</span>
                              </div>
                              <p className="text-[10px] text-slate-400 truncate mt-0.5">
                                {prof.description}
                              </p>
                            </div>
                            <div className="flex items-center gap-1.5 shrink-0">
                              <span className="text-[9.5px] font-mono px-1.5 py-0.5 rounded bg-white/6 text-cyan-200">
                                {prof.tokens}
                              </span>
                              {active && <Icons8Icon name="check" size={12} className="text-emerald-400" />}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={() => setAgentsPanelOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-cyan-500/14 hover:bg-cyan-500/24 border border-cyan-400/35 text-cyan-200 text-[11px] font-mono font-semibold transition-all cursor-pointer backdrop-blur-xl"
            >
              <Icons8Icon name="bot" size={14} className="text-cyan-300" />
              <span className="hidden sm:inline">Agentes</span>
              {agentsBadgeCount > 0 && (
                <span className="px-1.5 py-0.2 rounded-full bg-cyan-400 text-slate-950 text-[9px] font-bold">
                  {agentsBadgeCount}
                </span>
              )}
            </button>

            {e2eeUnlocked && (
              <div
                title="Sessão Criptografada Ponta a Ponta (ECDH P-256 + AES-256-GCM)"
                className="hidden lg:inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-emerald-500/12 border border-emerald-400/30 text-emerald-300 text-[10px] font-mono"
              >
                <Icons8Icon name="shield-check" size={13} className="text-emerald-400" />
                <span>E2EE</span>
              </div>
            )}

            {isFullScreenOrb && (
              <button
                type="button"
                onClick={() => setIsFullScreenOrb(false)}
                className="px-3 py-1.5 rounded-xl bg-white/8 hover:bg-white/15 border border-white/15 text-[11px] font-mono text-slate-200 cursor-pointer"
              >
                Sair Tela Cheia
              </button>
            )}
          </div>
        </header>

        {/* Orbe 3D Central (pausado quando Escritório 3D está em tela cheia p/ poupar GPU) */}
        <div className="w-full h-full flex items-center justify-center relative">
          {!agentsPanelOpen && (
            <AIOrb
              model={orbModel}
              state={aiState}
              audioLevel={audioLevel}
              className="w-full h-full"
            />
          )}
        </div>

        {/* Dock Flutuante de Voz */}
        <div className="absolute bottom-7 z-20 flex flex-col items-center gap-2.5">
          <div className="flex items-center gap-3 px-4 py-2 rounded-full bg-[#050b16]/80 border border-white/10 backdrop-blur-2xl shadow-[0_12px_40px_rgba(0,0,0,0.65)]">
            <button
              type="button"
              onClick={toggleMicMute}
              title={micMuted ? "Reativar microfone e voz" : "Mutar microfone e saída de voz"}
              aria-label={micMuted ? "Reativar microfone" : "Mutar microfone"}
              className={`w-10 h-10 rounded-full flex items-center justify-center transition-all cursor-pointer border ${
                micMuted
                  ? "bg-red-600/85 border-red-400/60 text-white shadow-[0_0_18px_rgba(239,68,68,0.45)]"
                  : "bg-white/[0.04] border-white/10 text-slate-400 hover:text-red-300 hover:border-red-400/35"
              }`}
            >
              <Icons8Icon name="mic-off" className="w-[18px] h-[18px]" />
            </button>

            <button
              type="button"
              onClick={handleVoice}
              disabled={aiState === "thinking" || aiState === "speaking"}
              aria-label="Ativar comando por voz"
              title={
                aiState === "listening"
                  ? "Ouvindo... clique para encerrar"
                  : "Falar com a F.R.Y.I.Vs"
              }
              className={`relative w-13 h-13 rounded-full flex items-center justify-center transition-all cursor-pointer border ${
                aiState === "thinking" || aiState === "speaking"
                  ? "bg-white/5 border-white/8 opacity-45 cursor-not-allowed"
                  : aiState === "listening"
                    ? "bg-emerald-500 border-emerald-300 text-slate-950 scale-105 shadow-[0_0_28px_rgba(16,185,129,0.65)]"
                    : "bg-cyan-500/18 hover:bg-cyan-500/28 border-cyan-400/45 text-cyan-200 shadow-[0_0_20px_rgba(34,211,238,0.2)]"
              }`}
            >
              <Icons8Icon name="mic" className="w-5 h-5" />
              {aiState === "listening" && (
                <span className="absolute inset-0 rounded-full border-2 border-emerald-300 animate-ping" />
              )}
            </button>

            <button
              type="button"
              onClick={toggleClapWake}
              title={
                clapEnabled
                  ? "Ativação por 2 palmas ativa (clique para desativar)"
                  : "Ativar despertar por 2 palmas (Clap on Jarvis)"
              }
              aria-label="Alternar ativação por duas palmas"
              className={`w-10 h-10 rounded-full flex items-center justify-center transition-all cursor-pointer border ${
                clapFlash
                  ? "bg-emerald-400 border-emerald-200 text-slate-950 scale-110 shadow-[0_0_22px_rgba(52,211,153,0.75)]"
                  : clapEnabled
                    ? "bg-emerald-500/16 border-emerald-400/40 text-emerald-300 hover:bg-emerald-500/26"
                    : "bg-white/[0.04] border-white/10 text-slate-500 hover:text-slate-300"
              }`}
            >
              <Icons8Icon name="applause" className="w-[18px] h-[18px]" />
            </button>

            {(aiState === "thinking" || aiState === "speaking") && (
              <button
                type="button"
                onClick={pararComandoAtivo}
                title="Interromper resposta/execução atual"
                aria-label="Parar comando atual"
                className="w-10 h-10 rounded-full flex items-center justify-center bg-red-500/25 hover:bg-red-500/40 border border-red-400/45 text-red-200 transition-all cursor-pointer"
              >
                <Icons8Icon name="close" className="w-4 h-4" />
              </button>
            )}
          </div>

          <div className="inline-flex items-center gap-1.5 text-[10px] font-mono text-slate-400">
            <Icons8Icon
              name={clapFlash ? "applause" : "radio"}
              size={12}
              className={
                clapFlash
                  ? "text-emerald-300 animate-bounce"
                  : micMuted
                    ? "text-red-400"
                    : wakeWordActive
                      ? "text-emerald-400 animate-pulse"
                      : "text-slate-500"
              }
            />
            <span>
              {clapFlash
                ? "2 palmas detectadas · ouvindo senhor!"
                : micMuted
                  ? "Voz silenciada"
                  : isWebMode
                    ? clapEnabled
                      ? "Modo Web · clique no mic ou bata 2 palmas"
                      : "Modo Web · clique no microfone para falar"
                    : wakeWordActive
                      ? clapEnabled
                        ? 'Escuta ativa · diga "FRYIVS" ou bata 2 palmas'
                        : 'Escuta ativa · diga "FRYIVS"'
                      : "Escuta em espera"}
            </span>
          </div>
        </div>
      </main>

      {/* 3. Terminal de Diálogo Rico (Direita) */}
      <section
        aria-label="Terminal de Diálogo"
        className={`h-full z-20 flex flex-col border-l border-white/10 bg-[#040914]/92 backdrop-blur-3xl transition-all duration-300 ease-out overflow-hidden ${
          chatOpen && !isFullScreenOrb ? "w-[440px] opacity-100" : "w-0 opacity-0"
        }`}
      >
        {chatOpen && !isFullScreenOrb && (
          <div className="flex flex-col h-full min-w-[440px]">
            {/* Header enxuto do Chat */}
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/8 bg-[#050c1a]/80">
              <div className="flex items-center gap-2.5">
                <Icons8Icon name="message" size={16} className="text-cyan-400" />
                <div>
                  <h2 className="text-xs font-mono uppercase tracking-[0.18em] text-white font-bold">
                    Terminal Neural
                  </h2>
                  <p className="text-[10px] font-mono text-slate-400 flex items-center gap-2 mt-0.5">
                    <span>
                      {status.gemini_configured ? "Gemini Cloud" : status.model || "Ollama"}
                    </span>
                    <span>·</span>
                    <button
                      type="button"
                      onClick={() => setKbDrawerOpen(true)}
                      className="inline-flex items-center gap-1 text-emerald-300 hover:underline cursor-pointer"
                    >
                      <Icons8Icon name="book-open" size={11} />
                      {kbChunksCount} chunks KB
                    </button>
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1">
                {messages.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setMessages([])}
                    title="Limpar conversa atual"
                    aria-label="Limpar conversa"
                    className="p-1.5 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-white/6 transition-colors cursor-pointer"
                  >
                    <Icons8Icon name="trash" size={15} />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setChatOpen(false)}
                  title="Recolher painel de diálogo"
                  aria-label="Recolher painel de diálogo"
                  className="p-1.5 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-white/6 transition-colors cursor-pointer"
                >
                  <Icons8Icon name="chevron-right" size={15} />
                </button>
              </div>
            </div>

            {/* Área de Mensagens */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
              {messages.length === 0 ? (
                <div className="h-full flex flex-col justify-center gap-5 py-4">
                  <div className="relative overflow-hidden rounded-2xl border border-cyan-400/20 p-5 flex flex-col items-center text-center gap-2.5">
                    {gradientMode !== "off" && (
                      <AnimatedGradient
                        paused={agentsPanelOpen}
                        style={{ zIndex: 0, opacity: 0.42 }}
                        radius="16px"
                        config={{ preset: "Prism", speed: 24 }}
                      />
                    )}
                    <div className="relative z-10 w-12 h-12 rounded-2xl flex items-center justify-center bg-cyan-500/15 border border-cyan-400/35 backdrop-blur-md">
                      <Icons8Icon name="brain" className="w-6 h-6 text-cyan-200" />
                    </div>
                    <div className="relative z-10">
                      <p className="text-xs font-mono uppercase tracking-[0.2em] text-white font-semibold">
                        Núcleo F.R.Y.I.Vs Operacional
                      </p>
                      <p className="text-xs text-slate-300 mt-1 leading-relaxed">
                        Comande por voz, bata duas palmas ou acione o esquadrão abaixo.
                      </p>
                    </div>
                  </div>

                  {/* Quick Starters alinhados aos 4 novos Agentes & Capacidades */}
                  <div className="grid grid-cols-1 gap-2">
                    {[
                      {
                        icon: "search" as Icons8Name,
                        accent: "text-cyan-300",
                        title: "Pesquisar & Indexar Conhecimento",
                        desc: "Acionar Agente Pesquisador e salvar na Base da IA",
                        onClick: () => setAgentsPanelOpen(true),
                      },
                      {
                        icon: "folder-kanban" as Icons8Name,
                        accent: "text-emerald-300",
                        title: "Organizar Planilhas e Arquivos",
                        desc: "Estruturar dados, documentos Word e tabelas Excel",
                        onClick: () =>
                          void sendMessageText(
                            "Delegue ao agente organizador listar e organizar os arquivos de dados do projeto.",
                          ),
                      },
                      {
                        icon: "lightbulb" as Icons8Name,
                        accent: "text-amber-300",
                        title: "Gerar Ideias para Evoluir a IA",
                        desc: "Pedir propostas criativas ao Agente de Ideias",
                        onClick: () =>
                          void sendMessageText(
                            "Delegue ao agente ideias propor 3 melhorias inovadoras para a F.R.Y.I.Vs.",
                          ),
                      },
                      {
                        icon: "code" as Icons8Name,
                        accent: "text-blue-300",
                        title: "Diagnóstico de Engenharia",
                        desc: "Consultar arquitetura e saúde do sistema",
                        onClick: () =>
                          void sendMessageText("Mostre o status atual de CPU, RAM e resumo da arquitetura."),
                      },
                    ].map((card, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={card.onClick}
                        className="text-left rounded-xl border border-white/8 bg-white/[0.025] hover:bg-cyan-500/[0.07] hover:border-cyan-400/30 p-3 flex items-start gap-3 transition-all cursor-pointer group"
                      >
                        <div className="w-8 h-8 rounded-lg bg-black/45 border border-white/10 flex items-center justify-center shrink-0 mt-0.5">
                          <Icons8Icon name={card.icon} className={`w-4 h-4 ${card.accent}`} />
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs font-semibold text-slate-100 group-hover:text-white">
                            {card.title}
                          </p>
                          <p className="text-[11px] text-slate-400 truncate mt-0.5">{card.desc}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((msg, i) => {
                  const isUser = msg.role === "user";
                  const hasTools = Boolean(msg.tools && msg.tools.length > 0);
                  const toolsExpanded = Boolean(expandedToolsMsgIdx[i]);
                  return (
                    <div
                      key={i}
                      className={`flex gap-2.5 ${isUser ? "flex-row-reverse" : "flex-row"} w-full`}
                    >
                      <div
                        className={`shrink-0 w-7 h-7 rounded-lg flex items-center justify-center mt-0.5 border ${
                          isUser
                            ? "bg-cyan-500/18 border-cyan-400/35"
                            : "bg-[#0a1428] border-white/12"
                        }`}
                      >
                        {isUser ? (
                          <Icons8Icon name="user" size={14} className="text-cyan-300" />
                        ) : (
                          <Icons8Icon name="bot" size={14} className="text-cyan-400" />
                        )}
                      </div>

                      <div
                        className={`flex flex-col gap-1 max-w-[86%] min-w-0 ${
                          isUser ? "items-end" : "items-start"
                        }`}
                      >
                        <div
                          className={`flex items-center gap-1.5 text-[9.5px] font-mono ${
                            isUser ? "flex-row-reverse" : "flex-row"
                          }`}
                        >
                          <span
                            className={`font-semibold tracking-wider ${
                              isUser ? "text-cyan-300" : "text-slate-300"
                            }`}
                          >
                            {isUser ? "VOCÊ" : "F.R.Y.I.Vs"}
                          </span>
                          <span className="text-slate-600">·</span>
                          <span className="text-slate-500 tabular-nums">{msg.time}</span>
                          {!isUser && (
                            <button
                              type="button"
                              onClick={() => handleCopyMsg(i, msg.text)}
                              title="Copiar resposta"
                              className="text-slate-500 hover:text-cyan-300 transition-colors ml-1 cursor-pointer"
                            >
                              {copiedMsgIdx === i ? (
                                <Icons8Icon name="check" size={12} className="text-emerald-400" />
                              ) : (
                                <Icons8Icon name="copy" size={12} />
                              )}
                            </button>
                          )}
                        </div>

                        <div
                          className={`px-3.5 py-2.5 text-[12.5px] select-text max-w-full ${
                            isUser
                              ? "rounded-2xl rounded-tr-sm bg-cyan-500/18 border border-cyan-400/30 text-white"
                              : "rounded-2xl rounded-tl-sm bg-[#081121] border border-white/10 text-slate-200"
                          }`}
                          style={{ wordBreak: "break-word", overflowWrap: "anywhere" }}
                        >
                          {isUser ? (
                            <p className="whitespace-pre-wrap leading-relaxed">{msg.text}</p>
                          ) : (
                            <FormattedText content={msg.text} />
                          )}
                        </div>

                        {hasTools && (
                          <div className="w-full">
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedToolsMsgIdx((prev) => ({
                                  ...prev,
                                  [i]: !toolsExpanded,
                                }))
                              }
                              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-[10px] font-mono text-cyan-300 cursor-pointer"
                            >
                              <Icons8Icon name="wrench" size={11} />
                              <span>{msg.tools!.length} skill(s) executada(s)</span>
                              <Icons8Icon
                                name="chevron-down"
                                size={10}
                                className={`transition-transform ${toolsExpanded ? "rotate-180" : ""}`}
                              />
                            </button>

                            {toolsExpanded && (
                              <div className="mt-1.5 space-y-1.5">
                                {msg.tools!.map((t, j) => (
                                  <div
                                    key={j}
                                    className="text-[10px] font-mono bg-[#050b16] border border-cyan-400/20 text-slate-300 px-3 py-2 rounded-xl break-words"
                                  >
                                    <span className="text-cyan-300 font-semibold">{t.tool}</span>
                                    <p className="text-slate-400 text-[9.5px] mt-0.5 line-clamp-4">
                                      {t.result}
                                    </p>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Composer */}
            <div className="p-4 pt-2 border-t border-white/8 bg-[#050c1a]/70">
              <input
                ref={fileUploadInputRef}
                type="file"
                accept=".xlsx,.xlsm,.csv,.docx,.txt,.md,.json,.pdf"
                className="hidden"
                onChange={handleUploadWorkspaceFile}
              />
              <form
                onSubmit={handleSend}
                className="flex items-end gap-2 p-1.5 pl-2.5 bg-[#070f20] border border-white/12 rounded-2xl focus-within:border-cyan-400/55 transition-all"
              >
                <button
                  type="button"
                  onClick={() => fileUploadInputRef.current?.click()}
                  disabled={uploadingFile}
                  title="Enviar planilha (.xlsx/.csv) ou documento (.docx) para o workspace"
                  aria-label="Enviar arquivo para análise"
                  className="w-8 h-8 mb-0.5 shrink-0 flex items-center justify-center rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-cyan-500/12 transition-colors cursor-pointer disabled:opacity-40"
                >
                  <Icons8Icon
                    name={uploadingFile ? "loader" : "book-add"}
                    size={16}
                    className={uploadingFile ? "animate-spin text-cyan-300" : ""}
                  />
                </button>
                <textarea
                  ref={chatTextareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSend(e);
                    }
                  }}
                  onInput={(e: any) => {
                    e.target.style.height = "auto";
                    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
                  }}
                  placeholder="Comande a F.R.Y.I.Vs..."
                  aria-label="Campo de mensagem"
                  rows={1}
                  autoComplete="off"
                  spellCheck={false}
                  className="flex-1 bg-transparent border-0 outline-none resize-none py-1.5 text-[13px] leading-relaxed text-white placeholder-slate-500 font-sans max-h-32 min-h-[36px] overflow-y-auto"
                />
                <button
                  type="submit"
                  disabled={!input.trim()}
                  aria-label="Enviar mensagem"
                  title="Enviar mensagem (Enter)"
                  className="w-9 h-9 shrink-0 flex items-center justify-center rounded-xl bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold transition-all disabled:opacity-25 disabled:pointer-events-none cursor-pointer mb-0.5"
                >
                  <Icons8Icon name="send" size={16} />
                </button>
              </form>
            </div>
          </div>
        )}
      </section>

      {/* Drawers Modulares: Esquadrão de 4 Agentes & Base de Conhecimento */}
      <AgentsControlPanel
        sessionToken={e2eeSessionToken}
        isOpen={agentsPanelOpen}
        onClose={() => setAgentsPanelOpen(false)}
        onKnowledgeIndexed={(total) => setKbChunksCount(total)}
        onJobsBadgeChange={setAgentsBadgeCount}
        officeCommand={officeCommand}
        agentEventSeq={agentEventSeq}
      />

      <KnowledgeBaseDrawer
        sessionToken={e2eeSessionToken}
        isOpen={kbDrawerOpen}
        onClose={() => setKbDrawerOpen(false)}
        onStatusUpdated={(total) => setKbChunksCount(total)}
      />

      {!e2eeChecking && e2eeRequired && !e2eeUnlocked && (
        <E2EELockGate
          hasPasswordConfigured={e2eeHasPassword}
          initialLockoutSeconds={e2eeLockoutSecs}
          onUnlocked={handleE2EEUnlocked}
        />
      )}
    </div>
  );
}
