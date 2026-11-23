import React, { useEffect, useState, useRef, useCallback } from "react";
import ParticleDrift from "@/components/ui/particle-drift";
import { AIOrb } from "@/components/AIOrb";
import type { AIOrbState, AIOrbModel } from "@/components/AIOrb/types";
import { E2EELockGate } from "@/components/E2EELockGate";
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
  Mic,
  MicOff,
  SendHorizontal,
  Brain,
  Cpu,
  Maximize2,
  Minimize2,
  TerminalSquare,
  Monitor,
  Camera,
  VolumeX,
  Volume2,
  MonitorUp,
  Activity,
  Sliders,
  Lock,
  Unlock,
  ShieldCheck,
  X,
  ChevronDown,
  Check,
  Sparkles,
  ChevronRight,
  MessageSquare,
  Zap,
  Bot,
  User,
  Radio,
} from "lucide-react";

export default function App() {
  const [aiState, setAiState] = useState<AIOrbState>("idle");
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState("");
  const chatTextareaRef = useRef<HTMLTextAreaElement>(null);
  const [status, setStatus] = useState<any>({});
  const [wsConnected, setWsConnected] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [isFullScreenOrb, setIsFullScreenOrb] = useState(false);
  const [showDemoToolbar, setShowDemoToolbar] = useState(true);
  const [chatOpen, setChatOpen] = useState(true);

  const [wakeWordActive, setWakeWordActive] = useState(true);

  const [micMuted, setMicMuted] = useState<boolean>(false);

  const [orbModel, setOrbModel] = useState<AIOrbModel>(() => {
    try {
      return (localStorage.getItem("fryvis_orb_model") as AIOrbModel) || "orbital-hud";
    } catch {
      return "orbital-hud";
    }
  });

  const handleOrbModelChange = (m: AIOrbModel) => {
    setOrbModel(m);
    try { localStorage.setItem("fryvis_orb_model", m); } catch {}
  };

  const [isAdmin, setIsAdmin] = useState<boolean>(false);

  // Estado E2EE (End-to-End Encryption Gate)
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
    try { return localStorage.getItem("fryvis_engine_provider") || "gemini"; } catch { return "gemini"; }
  });

  const handleEngineChange = (provider: string) => {
    setEngineProvider(provider);
    try { localStorage.setItem("fryvis_engine_provider", provider); } catch {}
  };

  const ENGINE_OPTIONS = [
    {
      id: "gemini",
      label: "Gemini",
      subLabel: "Principal",
      fullName: "Google Gemini Cloud",
      badge: "Nuvem · Motor Principal",
      icon: Sparkles,
      color: "text-amber-400",
      activeClass: "bg-amber-500/20 border-amber-500/50 text-amber-200 shadow-[0_0_15px_rgba(245,158,11,0.3)]",
      badgeClass: "bg-amber-500/25 text-amber-300 border-amber-500/40",
      desc: "Google AI Studio: Motor principal em nuvem para raciocínio avançado e skills."
    },
    {
      id: "ollama",
      label: "Ollama",
      subLabel: "Secundário",
      fullName: "Ollama Local",
      badge: "Local · Motor Secundário",
      icon: Cpu,
      color: "text-cyan-400",
      activeClass: "bg-cyan-500/20 border-cyan-500/50 text-cyan-200 shadow-[0_0_15px_rgba(6,182,212,0.3)]",
      badgeClass: "bg-cyan-500/25 text-cyan-300 border-cyan-500/40",
      desc: "Ollama Local: Motor secundário de processamento offline rápido e privado."
    },
    {
      id: "hybrid",
      label: "Híbrido",
      subLabel: "Auto",
      fullName: "Modo Híbrido",
      badge: "Failover Inteligente",
      icon: Zap,
      color: "text-purple-400",
      activeClass: "bg-purple-500/20 border-purple-500/50 text-purple-200 shadow-[0_0_15px_rgba(168,85,247,0.3)]",
      badgeClass: "bg-purple-500/25 text-purple-300 border-purple-500/40",
      desc: "Modo Híbrido: Prioriza Gemini Cloud e faz failover automático para Ollama."
    }
  ];

  const [modelProfile, setModelProfile] = useState<string>(() => {
    try { return localStorage.getItem("fryvis_model_profile") || "fryvis_1.0"; } catch { return "fryvis_1.0"; }
  });

  const handleProfileChange = (p: string) => {
    setModelProfile(p);
    try { localStorage.setItem("fryvis_model_profile", p); } catch {}
  };

  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const modelDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (modelDropdownRef.current && !modelDropdownRef.current.contains(event.target as Node)) {
        setModelDropdownOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setModelDropdownOpen(false);
    }
    if (modelDropdownOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [modelDropdownOpen]);

  const MODEL_PROFILES_CONFIG = [
    {
      id: "fryvis_beta",
      name: "Beta",
      fullName: "Fryvis Beta",
      tokens: "40 tok",
      tokenLimit: 40,
      description: "Ultra rápido · Respostas concisas e telegráficas",
      badgeClass: "bg-cyan-500/15 border-cyan-500/40 text-cyan-300",
      activeBg: "bg-cyan-500/10 border-cyan-500/50 text-cyan-200",
      dotClass: "bg-cyan-400",
      hoverClass: "hover:bg-cyan-500/10 hover:border-cyan-500/30",
    },
    {
      id: "fryvis_1.0",
      name: "1.0",
      fullName: "Fryvis 1.0",
      tokens: "50 tok",
      tokenLimit: 50,
      description: "Equilibrado · Síntese objetiva em 1 a 2 frases",
      badgeClass: "bg-blue-500/15 border-blue-500/40 text-blue-300",
      activeBg: "bg-blue-500/10 border-blue-500/50 text-blue-200",
      dotClass: "bg-blue-400",
      hoverClass: "hover:bg-blue-500/10 hover:border-blue-500/30",
    },
    {
      id: "fryvis_recursive",
      name: "Rec 1.1",
      fullName: "Recursive 1.1",
      tokens: "80 tok",
      tokenLimit: 80,
      description: "Refinado · Raciocínio recursivo expandido",
      badgeClass: "bg-purple-500/15 border-purple-500/40 text-purple-300",
      activeBg: "bg-purple-500/10 border-purple-500/50 text-purple-200",
      dotClass: "bg-purple-400",
      hoverClass: "hover:bg-purple-500/10 hover:border-purple-500/30",
    },
  ];

  const currentProfile =
    MODEL_PROFILES_CONFIG.find((p) => p.id === modelProfile) || MODEL_PROFILES_CONFIG[1];

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const dataArrayRef = useRef<Uint8Array<ArrayBuffer> | null>(null);
  const sourceNodeRef = useRef<MediaElementAudioSourceNode | null>(null);

  const forceLocalLock = useCallback(() => {
    e2eeSessionKeyRef.current = null;
    storeE2EEToken(null);
    setE2eeSessionToken(null);
    setE2eeUnlocked(false);
    setIsAdmin(false);
    setAiState("idle");
    setAudioLevel(0);
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
        // Fail-closed: mantém bloqueado se não confirmar estado
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
      .catch((err) => console.error(err));

    return () => {
      active = false;
    };
  }, []);

  const wsRef = useRef<WebSocket | null>(null);
  const wsReconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wsReconnectDelay = useRef<number>(1000);

  useEffect(() => {
    // Não abre WebSocket enquanto o núcleo E2EE estiver bloqueado
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

    function connectWs() {
      if (disposed) return;
      if (wsReconnectTimerRef.current) {
        clearTimeout(wsReconnectTimerRef.current);
        wsReconnectTimerRef.current = null;
      }
      const protocol = location.protocol === "https:" ? "wss:" : "ws:";
      const baseWsUrl = `${protocol}//${location.host || "127.0.0.1:8000"}/ws`;
      const wsUrl = appendE2EETokenToUrl(baseWsUrl, e2eeSessionToken);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
        wsReconnectDelay.current = 1000;
      };

      ws.onclose = (ev) => {
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
              { role: "assistant", text: data.response || "Senhor?", time: new Date().toLocaleTimeString() },
            ]);
          } else if (data.type === "transcription" && data.transcription) {
            setMessages((prev) => [
              ...prev,
              { role: "user", text: data.transcription, time: new Date().toLocaleTimeString() },
            ]);
          } else if (data.type === "chat_response") {
            setMessages((prev) => [
              ...prev,
              { role: "assistant", text: data.response, tools: data.tools_executed, time: new Date().toLocaleTimeString() },
            ]);
          } else if (data.type === "voice_daemon_status") {
            if (typeof data.active === "boolean") setWakeWordActive(data.active);
          } else if (data.type === "mic_muted") {
            if (typeof data.muted === "boolean") setMicMuted(data.muted);
          }
        } catch {}
      };
    }

    connectWs();

    return () => {
      disposed = true;
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
    } catch (e) {
      console.warn("Web Audio Analyser not initialized:", e);
    }
  };

  useEffect(() => {
    let animId: number;
    const updateAudioLevel = () => {
      if (analyserRef.current && dataArrayRef.current) {
        analyserRef.current.getByteFrequencyData(dataArrayRef.current);
        let sum = 0;
        for (let i = 0; i < dataArrayRef.current.length; i++) sum += dataArrayRef.current[i];
        const avg = sum / (dataArrayRef.current.length * 255);
        if (avg > 0.01) setAudioLevel(avg);
      }
      animId = requestAnimationFrame(updateAudioLevel);
    };
    animId = requestAnimationFrame(updateAudioLevel);
    return () => cancelAnimationFrame(animId);
  }, []);

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
    try { window.speechSynthesis.cancel(); } catch {}

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

    const englishPattern = /(Recursive\s+Yield\s+Female\s+Virtual(?:\s+Intelligence)?\s+system)/i;
    const match = englishPattern.exec(cleaned);
    const speakUtterance = (chunk: string, lang: string, isLast: boolean) => {
      const u = new SpeechSynthesisUtterance(chunk);
      (window as any).__fryvisActiveUtterance = u;
      u.lang = lang;
      u.rate = 1.05;
      u.pitch = 1.0;
      if (isLast) {
        u.onend = finishSpeech;
        u.onerror = finishSpeech;
      }
      try {
        window.speechSynthesis.speak(u);
      } catch {
        finishSpeech();
      }
    };

    setAiState("speaking");
    if (match) {
      const prefix = cleaned.substring(0, match.index).trim();
      const english = match[1].trim();
      const suffix = cleaned.substring(match.index + match[0].length).trim();
      const items: { text: string; lang: string }[] = [];
      if (prefix) items.push({ text: prefix, lang: "pt-BR" });
      items.push({ text: english, lang: "en-US" });
      if (suffix) items.push({ text: suffix, lang: "pt-BR" });
      items.forEach((item, idx) => speakUtterance(item.text, item.lang, idx === items.length - 1));
    } else {
      speakUtterance(cleaned, "pt-BR", true);
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

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (e2eeRequired && !e2eeUnlocked) return;
    if (!input.trim()) return;
    const userMsg = input;
    const recentHistory = messages.slice(-8).map((m) => ({
      role: m.role === "assistant" ? "assistant" : "user",
      content: m.text,
    }));
    setInput("");
    if (chatTextareaRef.current) {
      chatTextareaRef.current.style.height = "auto";
    }
    setMessages((prev) => [...prev, { role: "user", text: userMsg, time: new Date().toLocaleTimeString() }]);
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
        setMessages((prev) => [...prev, { role: "assistant", text: data.response, tools: data.tools_executed, time: new Date().toLocaleTimeString() }]);
      }

      if (data && data.played_locally) {
        setAiState("idle");
        setAudioLevel(0);
      } else if (data && data.has_audio && audioRef.current) {
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
        }, 25000);

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
      } else if (data && data.response) {
        speakWithBrowser(data.response);
      } else {
        setAiState("idle");
      }
    } catch (err: any) {
      console.error("[F.R.Y.I.Vs] Erro na requisição do chat:", err);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Não foi possível obter resposta no momento, senhor. O núcleo está restabelecendo conexões.", time: new Date().toLocaleTimeString() }
      ]);
      setAiState("idle");
    }
  };

  const voiceAbortControllerRef = useRef<AbortController | null>(null);

  const pararEscutaComando = () => {
    if (voiceAbortControllerRef.current) {
      voiceAbortControllerRef.current.abort();
      voiceAbortControllerRef.current = null;
    }
    setAiState("idle");
    setAudioLevel(0);
  };

  const pararComandoAtivo = async () => {
    pararEscutaComando();
    try {
      await fetch("/api/commands/cancel", {
        method: "POST",
        headers: buildE2EEHeaders(e2eeSessionToken),
      });
    } catch {
    }
  };

  const handleVoice = async () => {
    if (e2eeRequired && !e2eeUnlocked) return;
    if (aiState === "thinking" || aiState === "speaking") {
      return;
    }
    if (aiState === "listening") {
      pararEscutaComando();
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
      if (res.status === 423) {
        forceLocalLock();
      }
    } catch {}
  };

  const executeSkill = async (skill: string, args: any = {}) => {
    if (e2eeRequired && !e2eeUnlocked) return;
    try {
      const res = await fetch("/api/skills/execute", {
        method: "POST",
        headers: buildE2EEHeaders(e2eeSessionToken, { "Content-Type": "application/json" }),
        body: JSON.stringify({ skill, arguments: args }),
      });
      if (res.status === 423) {
        forceLocalLock();
      }
    } catch {}
  };

  const stateTitles: Record<AIOrbState, string> = {
    idle:      "SISTEMA PRONTO",
    listening: "ESCUTANDO...",
    thinking:  "PROCESSANDO...",
    speaking:  "FALANDO...",
  };

  const stateDotColors: Record<AIOrbState, string> = {
    idle:      "bg-blue-400",
    listening: "bg-emerald-400 animate-pulse",
    thinking:  "bg-purple-400 animate-ping",
    speaking:  "bg-pink-400 animate-bounce",
  };

  const ORB_MODEL_OPTIONS: { id: AIOrbModel; label: string; desc: string }[] = [
    { id: "orbital-hud",      label: "Orbital HUD",       desc: "Novo · Anéis orbitais + Núcleo neon" },
    { id: "neural-fibonacci",  label: "Neural Fibonacci",   desc: "Clássico · Anel Fibonacci em partículas" },
  ];

  const chatSidebarWidth = chatOpen && !isFullScreenOrb ? 420 : 0;

  return (
    <div className="w-screen h-dvh flex overflow-hidden bg-black text-slate-200 font-sans selection:bg-blue-500/30">
      <audio ref={audioRef} className="hidden" preload="auto" />

      <div className="fixed inset-0 z-0 pointer-events-none opacity-20 mix-blend-screen">
        <ParticleDrift
          mode="dark"
          speed={aiState === "thinking" ? 1.2 : 0.4}
          density={0.5}
          hue={aiState === "thinking" ? 280 : aiState === "listening" ? 140 : 220}
        />
      </div>

      <div className="flex-1 min-w-0 relative flex flex-col items-center justify-center z-10 bg-black overflow-hidden">
        <header
          className="absolute top-0 left-0 z-30 flex items-center gap-2.5 px-4 py-2 pointer-events-none min-w-0"
          style={{ right: chatSidebarWidth }}
        >
          <div className="flex items-center gap-2.5 pointer-events-auto shrink-0 min-w-fit">
            <img
              src="/static/fryivs-icon-removebg-preview.png"
              alt="F.R.Y.I.Vs"
              className="w-9 h-9 object-contain shrink-0 drop-shadow-[0_0_10px_rgba(34,211,238,0.75)] hover:drop-shadow-[0_0_16px_rgba(34,211,238,0.9)] transition-all duration-300"
            />
            <div className="flex flex-col justify-center gap-[2px]">
              <h1 className="text-[14px] font-bold tracking-[0.3em] text-white leading-none drop-shadow-[0_0_8px_rgba(34,211,238,0.4)] tabular-nums whitespace-nowrap">
                F.R.Y.I.Vs
              </h1>
              <p className="text-[8px] uppercase tracking-[0.28em] text-slate-400 font-mono leading-none whitespace-nowrap">
                NEURAL INTELLIGENCE <span className="text-cyan-400 font-bold">OS</span>
              </p>
            </div>
          </div>

          <div className="hidden sm:flex items-center gap-1 p-1 rounded-full bg-black/55 border border-white/10 backdrop-blur-2xl shadow-[0_4px_20px_rgba(0,0,0,0.7)] pointer-events-auto shrink-0">
            {ENGINE_OPTIONS.map((eng) => {
              const isSelected = engineProvider === eng.id;
              const Icon = eng.icon;
              return (
                <button
                  key={eng.id}
                  type="button"
                  onClick={() => handleEngineChange(eng.id)}
                  title={eng.desc}
                  aria-label={`Motor: ${eng.label} — ${eng.subLabel}`}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-mono transition-all duration-200 border cursor-pointer ${
                    isSelected
                      ? `${eng.activeClass} font-semibold`
                      : "bg-transparent border-transparent text-slate-400 hover:text-slate-200 hover:bg-white/5"
                  }`}
                >
                  <Icon size={11} className={isSelected ? eng.color : "text-slate-500"} />
                  <span className={isSelected ? "text-slate-100 font-bold" : "text-slate-400"}>{eng.label}</span>
                  <span className={`text-[7px] px-1 py-0.5 rounded font-sans uppercase tracking-wider font-bold border ${
                    isSelected ? eng.badgeClass : "bg-white/5 text-slate-600 border-white/5"
                  }`}>{eng.subLabel}</span>
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-1.5 pointer-events-auto shrink-0 ml-auto">
            <div ref={modelDropdownRef} className="relative z-30">
              <button
                type="button"
                onClick={() => setModelDropdownOpen((prev) => !prev)}
                aria-expanded={modelDropdownOpen}
                aria-label="Seletor de perfil de modelo"
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full bg-black/55 border border-white/10 backdrop-blur-xl hover:border-white/22 transition-all text-[10px] font-mono text-slate-300 hover:text-white"
              >
                <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? "bg-emerald-400" : "bg-red-400"} shrink-0`} />
                <Cpu size={10} className="text-cyan-400 shrink-0" />
                <span className={`w-1.5 h-1.5 rounded-full ${currentProfile.dotClass}`} />
                <span className="hidden sm:inline">{currentProfile.name}</span>
                <ChevronDown size={10} className={`text-slate-500 transition-transform duration-200 ${modelDropdownOpen ? "rotate-180" : ""}`} />
              </button>

              {modelDropdownOpen && (
                <div
                  role="listbox"
                  className="absolute right-0 top-full mt-2 w-64 p-1.5 bg-[#060a10]/97 backdrop-blur-2xl border border-white/12 rounded-2xl shadow-2xl shadow-black/90 ring-1 ring-white/8 space-y-0.5 z-50"
                >
                  <div className="px-2.5 py-1.5 flex items-center justify-between border-b border-white/5 mb-1">
                    <span className="text-[9px] font-mono uppercase tracking-widest text-slate-400 flex items-center gap-1 font-semibold">
                      <Sparkles size={10} className="text-cyan-400" /> Seletor de Modelo
                    </span>
                    <span className="text-[9px] font-mono text-slate-500">Tokens</span>
                  </div>
                  {MODEL_PROFILES_CONFIG.map((profile) => {
                    const isSelected = modelProfile === profile.id;
                    return (
                      <button
                        key={profile.id}
                        type="button"
                        role="option"
                        aria-selected={isSelected}
                        onClick={() => { handleProfileChange(profile.id); setModelDropdownOpen(false); }}
                        className={`w-full text-left p-2 rounded-xl transition-all flex items-center justify-between border ${
                          isSelected
                            ? `${profile.activeBg} font-semibold shadow-sm`
                            : `bg-white/[0.02] border-transparent text-slate-400 ${profile.hoverClass} hover:text-slate-200`
                        }`}
                      >
                        <div className="flex items-center gap-2.5 min-w-0 pr-2">
                          <div className={`size-2 rounded-full shrink-0 ${isSelected ? profile.dotClass : "bg-slate-600"}`} />
                          <div className="min-w-0">
                            <span className="text-xs font-mono font-medium text-slate-100 block truncate">{profile.fullName}</span>
                            <p className="text-[10px] text-slate-400 truncate mt-0.5">{profile.description}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border tabular-nums ${profile.badgeClass}`}>{profile.tokens}</span>
                          {isSelected && <Check size={13} className="text-emerald-400" />}
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="flex items-center gap-0.5 p-0.5 rounded-full bg-black/55 border border-white/10 backdrop-blur-xl">
              {ORB_MODEL_OPTIONS.map((opt) => (
                <button
                  key={opt.id}
                  onClick={() => handleOrbModelChange(opt.id)}
                  title={`${opt.label}: ${opt.desc}`}
                  aria-label={`Modo de orbe: ${opt.label}`}
                  className={`px-2.5 py-1 rounded-full text-[10px] font-mono transition-all ${
                    orbModel === opt.id
                      ? "bg-white/15 text-white border border-white/20 shadow-sm"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {opt.id === "orbital-hud" ? "HUD" : "FIB"}
                </button>
              ))}
            </div>

            <div className="w-px h-5 bg-white/10 mx-0.5" />

            {e2eeUnlocked && (
              <div
                title="Sessão protegida com E2EE (ECDH P-256 + HKDF-SHA256 + AES-256-GCM)"
                className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/12 border border-emerald-400/30 text-emerald-300 text-[9px] font-mono tracking-wider shrink-0"
              >
                <ShieldCheck size={11} className="text-emerald-400 shrink-0" />
                <span>E2EE</span>
              </div>
            )}

            {e2eeRequired && e2eeUnlocked && (
              <button
                onClick={handleLockAI}
                aria-label="Bloquear IA"
                title="Bloquear IA imediatamente (corta voz, escuta e acesso E2EE)"
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full bg-red-500/15 hover:bg-red-500/25 border border-red-400/35 text-red-300 text-[10px] font-mono font-semibold transition-all cursor-pointer"
              >
                <Lock size={11} className="text-red-400 shrink-0" />
                <span className="hidden sm:inline">Bloquear IA</span>
              </button>
            )}

            <button
              onClick={() => setIsAdmin((v) => !v)}
              aria-label={isAdmin ? "Ocultar Controles Avançados" : "Mostrar Controles Avançados"}
              className={`p-2 rounded-full transition-all cursor-pointer ${
                isAdmin
                  ? "bg-amber-500/15 text-amber-300 border border-amber-500/30 shadow-[0_0_14px_rgba(245,158,11,0.2)] hover:bg-amber-500/25"
                  : "bg-black/55 border border-white/10 text-slate-500 hover:text-white hover:border-white/22 backdrop-blur-xl"
              }`}
              title={isAdmin ? "Controles Avançados Ativos (Sessão E2EE Verificada)" : "Ativar Controles Avançados (Sessão E2EE Verificada)"}
            >
              {isAdmin ? <Unlock size={13} className="text-amber-400" /> : <Sliders size={13} />}
            </button>

            <button
              onClick={() => setChatOpen((v) => !v)}
              aria-label={chatOpen ? "Ocultar Terminal de Diálogo" : "Mostrar Terminal de Diálogo"}
              className={`p-2 rounded-full backdrop-blur-xl transition-all ${
                chatOpen
                  ? "bg-cyan-500/15 border border-cyan-400/40 text-cyan-300 hover:bg-cyan-500/25"
                  : "bg-black/55 border border-white/10 text-slate-500 hover:text-white hover:border-white/22"
              }`}
              title={chatOpen ? "Ocultar Chat" : "Mostrar Chat"}
            >
              <MessageSquare size={13} />
            </button>

            <button
              onClick={() => setIsFullScreenOrb((v) => !v)}
              aria-label="Alternar tela cheia"
              className="p-2 rounded-full bg-black/55 border border-white/10 text-slate-500 hover:text-white hover:border-white/22 backdrop-blur-xl transition-all"
              title="Alternar Tela Cheia"
            >
              {isFullScreenOrb ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
            </button>
          </div>
        </header>

        <div className="absolute top-[72px] z-20 flex flex-col items-center pointer-events-none">
          <div className="px-5 py-1.5 rounded-full border border-white/8 bg-black/40 backdrop-blur-xl flex items-center gap-2.5 shadow-xl shadow-purple-500/5">
            <div className={`w-2 h-2 rounded-full ${stateDotColors[aiState]}`} />
            <span className="text-[10px] uppercase tracking-[0.25em] font-mono font-bold text-slate-300">
              {stateTitles[aiState]}
            </span>
          </div>
        </div>

        <div className="w-full h-full flex items-center justify-center relative">
          <AIOrb
            model={orbModel}
            state={aiState}
            audioLevel={audioLevel}
            className="w-full h-full"
          />
        </div>

        <div className="absolute bottom-8 z-20 flex flex-col items-center gap-4">
          <div className="flex items-center gap-4">
            <button
              onClick={toggleMicMute}
              title={micMuted ? "Microfone mudo — clique para reativar (desbloqueia entrada e saída de voz)" : "Mutar microfone e saída de voz"}
              aria-label={micMuted ? "Reativar microfone" : "Mutar microfone"}
              className={`group relative w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300 ${
                micMuted
                  ? "bg-red-700/90 border border-red-400/60 shadow-[0_0_22px_rgba(239,68,68,0.6)] scale-105"
                  : "bg-black/60 border border-white/12 hover:bg-red-900/30 hover:border-red-500/40 backdrop-blur-xl"
              }`}
            >
              {micMuted
                ? <MicOff className="w-5 h-5 text-white" />
                : <MicOff className="w-5 h-5 text-slate-500 group-hover:text-red-400 transition-colors" />
              }
              {micMuted && (
                <div className="absolute inset-0 rounded-full border-2 border-red-500 animate-ping opacity-40" />
              )}
            </button>

            {(aiState === "thinking" || aiState === "speaking") && (
              <button
                onClick={pararComandoAtivo}
                title="Parar comando atual"
                className="group relative w-10 h-10 rounded-full flex items-center justify-center bg-red-600/80 hover:bg-red-500 border border-red-400/40 shadow-[0_0_20px_rgba(239,68,68,0.5)] transition-all duration-200"
              >
                <X className="w-4 h-4 text-white" />
              </button>
            )}
            <button
              onClick={handleVoice}
              disabled={aiState === "thinking" || aiState === "speaking"}
              title={
                aiState === "thinking"
                  ? "Processando comando... escuta desabilitada"
                  : aiState === "speaking"
                  ? "Falando... escuta desabilitada"
                  : aiState === "listening"
                  ? "Ouvindo... clique para cancelar"
                  : "Ativar escuta por voz"
              }
              className={`group relative w-14 h-14 rounded-full flex items-center justify-center transition-all duration-300 ${
                aiState === "thinking" || aiState === "speaking"
                  ? "bg-black/30 border border-white/5 opacity-40 cursor-not-allowed"
                  : aiState === "listening"
                  ? "bg-emerald-500 scale-110 shadow-[0_0_35px_rgba(16,185,129,0.7)] cursor-pointer"
                  : "bg-black/60 border border-white/12 hover:bg-white/8 hover:border-purple-500/40 backdrop-blur-xl cursor-pointer"
              }`}
            >
              <Mic className={`w-6 h-6 ${aiState === "listening" ? "text-white" : "text-slate-300 group-hover:text-blue-400"}`} />
              {aiState === "listening" && (
                <div className="absolute inset-0 rounded-full border-2 border-emerald-400 animate-ping" />
              )}
            </button>
          </div>

          {isAdmin && (
            <div className="flex gap-1.5 px-3 py-2 bg-black/60 backdrop-blur-2xl border border-white/8 rounded-2xl shadow-xl">
              {[
                { onClick: () => executeSkill("listar_janelas"), icon: <Monitor size={16} />, title: "Listar Janelas" },
                { onClick: () => executeSkill("tirar_screenshot"), icon: <Camera size={16} />, title: "Capturar Tela" },
                { onClick: () => executeSkill("controlar_volume", { acao: "mutar" }), icon: <VolumeX size={16} />, title: "Mutar" },
                { onClick: () => executeSkill("controlar_volume", { acao: "aumentar" }), icon: <Volume2 size={16} />, title: "Volume +" },
                { onClick: () => executeSkill("pressionar_atalho", { teclas: ["win", "d"] }), icon: <MonitorUp size={16} />, title: "Desktop" },
              ].map((btn, i) => (
                <button
                  key={i}
                  onClick={btn.onClick}
                  title={btn.title}
                  className="p-2 hover:bg-white/10 rounded-xl text-slate-500 hover:text-white transition-colors"
                >
                  {btn.icon}
                </button>
              ))}
            </div>
          )}
        </div>

        {isAdmin && (
          <div className="absolute top-[72px] right-6 z-30 flex flex-col items-end gap-2">
            <button
              onClick={() => setShowDemoToolbar((prev) => !prev)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-black/60 border border-white/8 hover:bg-white/8 text-[10px] font-mono text-slate-400 hover:text-white backdrop-blur-xl transition-colors"
            >
              <Sliders size={12} />
              {showDemoToolbar ? "Ocultar Demo" : "Testar Estados"}
            </button>
            {showDemoToolbar && (
              <div className="flex flex-col gap-2 p-3 rounded-2xl bg-black/80 border border-white/8 backdrop-blur-2xl shadow-2xl font-mono text-xs w-56">
                <span className="text-[9px] uppercase tracking-wider text-slate-400 font-bold px-1">
                  Estados do Orbe
                </span>
                <div className="grid grid-cols-2 gap-1.5">
                  {(["idle", "listening", "thinking", "speaking"] as AIOrbState[]).map((st) => (
                    <button
                      key={st}
                      onClick={() => {
                        setAiState(st);
                        setAudioLevel(st === "listening" || st === "speaking" ? 0.4 : 0);
                      }}
                      className={`px-2 py-1.5 rounded-lg border transition-all text-center capitalize ${
                        aiState === st
                          ? "bg-gradient-to-r from-blue-600 to-purple-600 border-white/20 text-white font-bold shadow-md"
                          : "bg-white/4 border-white/8 text-slate-400 hover:bg-white/8 hover:text-white"
                      }`}
                    >
                      {st}
                    </button>
                  ))}
                </div>
                <div className="mt-1 pt-2 border-t border-white/8">
                  <div className="flex justify-between items-center text-[10px] text-slate-400 mb-1 px-1">
                    <span className="flex items-center gap-1"><Activity size={10} /> Áudio:</span>
                    <span className="text-white">{Math.round(audioLevel * 100)}%</span>
                  </div>
                  <input
                    type="range" min="0" max="1" step="0.05" value={audioLevel}
                    onChange={(e) => setAudioLevel(parseFloat(e.target.value))}
                    className="w-full accent-purple-500 cursor-pointer h-1.5 bg-white/8 rounded-lg"
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div
        className={`h-full z-20 flex flex-col border-l border-white/10 bg-[#040812]/85 backdrop-blur-3xl transition-all duration-500 ease-in-out overflow-hidden ${
          chatOpen && !isFullScreenOrb ? "w-[420px] opacity-100" : "w-0 opacity-0"
        }`}
      >
        {chatOpen && !isFullScreenOrb && (
          <div className="flex flex-col h-full p-5 min-w-[420px]">
            <div className="flex items-center justify-between mb-4 pb-2 border-b border-white/5">
              <div className="flex items-center gap-2">
                <MessageSquare size={15} className="text-cyan-400" />
                <span className="text-[11px] font-mono uppercase tracking-widest text-slate-300 font-bold">
                  Terminal de Diálogo
                </span>
              </div>
              <button
                onClick={() => setChatOpen(false)}
                className="p-1.5 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-white/5 transition-colors"
                title="Fechar painel"
              >
                <ChevronRight size={14} />
              </button>
            </div>

            {(() => {
              const activeEngine = ENGINE_OPTIONS.find(e => e.id === engineProvider) || ENGINE_OPTIONS[0];
              const EngIcon = activeEngine.icon;
              return (
                <div className="mb-3 flex items-center gap-2 px-3 py-2 rounded-xl bg-black/35 border border-white/6 backdrop-blur-md">
                  <Radio size={10} className={`${wakeWordActive ? "text-emerald-400 animate-pulse" : "text-slate-500"} shrink-0`} />
                  <span className="text-[9px] font-mono uppercase tracking-wider text-slate-500 font-semibold">Motor</span>
                  <div className="flex items-center gap-1.5 ml-1">
                    <EngIcon size={10} className={activeEngine.color} />
                    <span className={`text-[10px] font-mono font-semibold ${activeEngine.color}`}>{activeEngine.label}</span>
                    <span className={`text-[7px] px-1.5 py-0.5 rounded font-mono uppercase tracking-wider border ${activeEngine.badgeClass}`}>{activeEngine.subLabel}</span>
                  </div>
                </div>
              );
            })()}

            <div className="flex gap-1.5 mb-3 text-[10px] font-mono flex-wrap">
              {micMuted && (
                <div className="flex items-center gap-1.5 bg-red-500/15 rounded-lg px-2.5 py-1.5 border border-red-400/35 shrink-0">
                  <MicOff size={10} className="text-red-400" />
                  <span className="text-red-300 font-mono font-bold tracking-wider text-[9px]">MIC MUDO</span>
                </div>
              )}
              <div className="flex items-center gap-1.5 bg-white/5 rounded-lg px-2.5 py-1.5 border border-white/10 flex-1 truncate">
                <div className={`w-1.5 h-1.5 rounded-full ${status.ollama_online ? "bg-emerald-400" : "bg-red-400"} animate-pulse shrink-0`} />
                <span className="text-slate-400 truncate">
                  Ollama: <span className="text-slate-200 font-semibold">{status.model || "Local"}</span>
                </span>
              </div>
              {status.gemini_configured && (
                <div className="flex items-center gap-1.5 bg-white/5 rounded-lg px-2.5 py-1.5 border border-white/10 shrink-0">
                  <div className={`w-1.5 h-1.5 rounded-full ${status.gemini_online ? "bg-cyan-400" : "bg-amber-400"} animate-pulse`} />
                  <span className="text-slate-400">Gemini: <span className="text-cyan-300 font-semibold">Cloud</span></span>
                </div>
              )}
            </div>

            <div className="flex-1 overflow-y-auto pr-1 space-y-4 font-sans scrollbar-thin scrollbar-thumb-white/8 scrollbar-track-transparent">
              {messages.length === 0 && (
                <div className="h-full flex flex-col items-center justify-center gap-3 text-slate-500 text-center px-6 py-8">
                  <div className="size-12 rounded-2xl flex items-center justify-center bg-cyan-950/30 border border-cyan-400/20">
                    <Brain className="w-6 h-6 text-cyan-400/60" />
                  </div>
                  <div>
                    <p className="text-[11px] font-mono uppercase tracking-widest text-slate-500">Aguardando comando</p>
                    <p className="text-[10px] font-mono text-slate-600 mt-0.5">por texto ou voz...</p>
                  </div>
                </div>
              )}
              {messages.map((msg, i) => {
                const isUser = msg.role === "user";
                return (
                  <div key={i} className={`flex gap-2.5 ${isUser ? "flex-row-reverse" : "flex-row"} w-full`}>
                    <div className={`shrink-0 size-7 rounded-full flex items-center justify-center mt-0.5 ${
                      isUser
                        ? "bg-gradient-to-br from-blue-600/40 to-cyan-600/30 border border-cyan-400/30"
                        : "bg-gradient-to-br from-slate-800 to-slate-900 border border-cyan-400/25 shadow-[0_0_10px_rgba(34,211,238,0.18)]"
                    }`}>
                      {isUser
                        ? <User size={13} className="text-cyan-300" />
                        : <Bot size={13} className="text-cyan-400" />
                      }
                    </div>
                    <div className={`flex flex-col gap-1 max-w-[85%] ${isUser ? "items-end" : "items-start"}`}>
                      <div className={`flex items-center gap-1.5 text-[9px] font-mono ${isUser ? "flex-row-reverse" : "flex-row"}`}>
                        <span className={`font-bold tracking-wider ${isUser ? "text-cyan-400" : "text-blue-300"}`}>
                          {isUser ? "VOCÊ" : "F.R.Y.I.Vs"}
                        </span>
                        <span className="text-slate-600">·</span>
                        <span className="text-slate-500 tabular-nums">{msg.time}</span>
                      </div>
                      <div
                        className={`px-3.5 py-2.5 text-[12.5px] leading-relaxed select-text ${
                          isUser
                            ? "rounded-2xl rounded-tr-sm bg-gradient-to-br from-blue-600/30 to-cyan-700/20 border border-cyan-400/25 text-slate-100"
                            : "rounded-2xl rounded-tl-sm bg-[#091120]/85 border border-white/10 text-slate-200 shadow-[0_2px_16px_rgba(0,0,0,0.5)]"
                        }`}
                        style={{ wordBreak: "break-word", overflowWrap: "anywhere" }}
                      >
                        <p className="text-pretty whitespace-pre-wrap">{msg.text}</p>
                      </div>
                      {isAdmin && msg.tools && msg.tools.map((t: any, j: number) => (
                        <div key={j} className="mt-1 text-[10px] font-mono bg-indigo-950/60 border border-indigo-400/30 text-indigo-200 px-3 py-2 rounded-xl max-w-full break-words">
                          <span className="text-cyan-300 font-bold">⚡ Executado:</span> <span className="text-white font-semibold">{t.tool}</span>
                          <span className="text-indigo-200/70 text-[9px] block mt-0.5">{t.result}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
              <div ref={messagesEndRef} />
            </div>

            <form
              onSubmit={handleSend}
              className="mt-3 flex items-end gap-2 p-1.5 pl-3 bg-[#060d1a]/90 border border-white/12 rounded-2xl focus-within:border-cyan-400/60 focus-within:shadow-[0_0_20px_rgba(34,211,238,0.25)] transition-all"
            >
              <div className="pb-2 text-cyan-400/60 shrink-0 pointer-events-none">
                <TerminalSquare size={16} />
              </div>
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
                placeholder="Digite uma mensagem para a F.R.Y.I.Vs..."
                aria-label="Campo de mensagem"
                rows={1}
                autoComplete="off"
                autoCorrect="off"
                spellCheck={false}
                className="flex-1 bg-transparent border-0 outline-none resize-none py-1.5 text-[13px] leading-relaxed text-white placeholder-slate-500 font-sans max-h-32 min-h-[36px] overflow-y-auto"
                style={{ height: "auto" }}
              />
              <button
                type="submit"
                disabled={!input.trim()}
                aria-label="Enviar mensagem"
                title="Enviar mensagem (Enter)"
                className="size-9 shrink-0 flex items-center justify-center rounded-xl bg-gradient-to-r from-cyan-400 to-blue-500 hover:from-cyan-300 hover:to-blue-400 text-slate-950 font-bold transition-all shadow-[0_0_15px_rgba(34,211,238,0.35)] disabled:opacity-25 disabled:pointer-events-none disabled:shadow-none active:scale-95 mb-0.5"
              >
                <SendHorizontal size={17} className="text-slate-950" />
              </button>
            </form>
          </div>
        )}
      </div>

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
