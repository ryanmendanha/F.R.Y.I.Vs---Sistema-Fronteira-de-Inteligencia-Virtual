import React, { useState, useRef, useEffect } from "react";
import { Icons8Icon, type Icons8Name } from "@/components/Icons8Icon";
import type { AIOrbModel, AIOrbState } from "@/components/AIOrb/types";
import type { PresetName } from "@/registry/spell-ui/animated-gradient";

export type GradientModeOption = "auto" | PresetName | "off";

export interface CommandRailProps {
  orbModel: AIOrbModel;
  onOrbModelChange: (model: AIOrbModel) => void;
  gradientMode?: GradientModeOption;
  onGradientModeChange?: (mode: GradientModeOption) => void;
  isFullScreenOrb: boolean;
  onToggleFullScreen: () => void;
  agentsOpen: boolean;
  onOpenAgents: () => void;
  agentsBadgeCount: number;
  kbOpen: boolean;
  onOpenKB: () => void;
  kbChunksCount: number;
  chatOpen: boolean;
  onToggleChat: () => void;
  onToggleLiveScreen: () => void;
  liveScreenActive: boolean;
  onExecuteSkill: (skill: string, args?: Record<string, unknown>) => void;
  aiState: AIOrbState;
  onSetDemoState: (state: AIOrbState, level: number) => void;
  audioLevel: number;
  onAudioLevelChange: (level: number) => void;
  e2eeRequired: boolean;
  e2eeUnlocked: boolean;
  onLockAI: () => void;
  isWebMode?: boolean;
}

export const CommandRail: React.FC<CommandRailProps> = ({
  orbModel,
  onOrbModelChange,
  gradientMode = "auto",
  onGradientModeChange,
  isFullScreenOrb,
  onToggleFullScreen,
  agentsOpen,
  onOpenAgents,
  agentsBadgeCount,
  kbOpen,
  onOpenKB,
  kbChunksCount,
  chatOpen,
  onToggleChat,
  onToggleLiveScreen,
  liveScreenActive,
  onExecuteSkill,
  aiState,
  onSetDemoState,
  audioLevel,
  onAudioLevelChange,
  e2eeRequired,
  e2eeUnlocked,
  onLockAI,
  isWebMode = false,
}) => {
  const [toolsMenuOpen, setToolsMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!toolsMenuOpen) return;
    const onOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setToolsMenuOpen(false);
      }
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setToolsMenuOpen(false);
    };
    document.addEventListener("mousedown", onOutside);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onOutside);
      document.removeEventListener("keydown", onEsc);
    };
  }, [toolsMenuOpen]);

  const railBtnBase =
    "relative group w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-200 cursor-pointer border";

  const quickShortcuts: { onClick: () => void; icon: Icons8Name; title: string }[] = [
    {
      onClick: () => onExecuteSkill("listar_janelas"),
      icon: "monitor",
      title: "Listar Janelas",
    },
    {
      onClick: () => onExecuteSkill("tirar_screenshot"),
      icon: "camera",
      title: "Capturar Tela",
    },
    {
      onClick: () => onExecuteSkill("controlar_volume", { acao: "mutar" }),
      icon: "volume-mute",
      title: "Mutar Áudio",
    },
    {
      onClick: () => onExecuteSkill("controlar_volume", { acao: "aumentar" }),
      icon: "volume-up",
      title: "Volume +",
    },
    {
      onClick: () => onExecuteSkill("pressionar_atalho", { teclas: ["win", "d"] }),
      icon: "desktop",
      title: "Mostrar Desktop",
    },
  ];

  return (
    <aside
      aria-label="Barra de comando principal"
      className="h-full w-[62px] shrink-0 z-30 flex flex-col items-center justify-between py-3.5 bg-[#040914]/92 border-r border-white/10 backdrop-blur-2xl select-none"
    >
      {/* Topo: Identidade F.R.Y.I.Vs */}
      <div className="flex flex-col items-center gap-3">
        <button
          type="button"
          onClick={() =>
            onOrbModelChange(orbModel === "orbital-hud" ? "neural-fibonacci" : "orbital-hud")
          }
          title={`Alternar estilo do Orbe (${orbModel === "orbital-hud" ? "Orbital HUD" : "Neural Fibonacci"})`}
          aria-label="Alternar visualização do Orbe 3D"
          className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-400/30 flex items-center justify-center hover:border-cyan-400/60 hover:bg-cyan-500/18 transition-all cursor-pointer shadow-[0_0_16px_rgba(34,211,238,0.18)]"
        >
          <img
            src="/static/fryivs-icon-removebg-preview.png"
            alt="F.R.Y.I.Vs"
            className="w-6 h-6 object-contain drop-shadow-[0_0_8px_rgba(34,211,238,0.75)]"
          />
        </button>

        <div className="w-6 h-px bg-white/10" />

        {/* Navegação de Módulos */}
        <nav className="flex flex-col items-center gap-2" aria-label="Módulos da IA">
          {/* 1. Esquadrão de 4 Agentes */}
          <button
            type="button"
            onClick={onOpenAgents}
            aria-label="Abrir Esquadrão de Agentes"
            title="Esquadrão de Agentes (Pesquisador · Organizador · Ideias · Engenheiro)"
            className={`${railBtnBase} ${
              agentsOpen
                ? "bg-cyan-500/20 border-cyan-400/55 text-cyan-200 shadow-[0_0_16px_rgba(34,211,238,0.24)]"
                : "bg-white/[0.03] border-white/8 text-slate-400 hover:text-cyan-200 hover:border-cyan-400/35 hover:bg-cyan-500/10"
            }`}
          >
            <Icons8Icon name="bot" className="w-[19px] h-[19px]" />
            {agentsBadgeCount > 0 && (
              <span className="absolute -top-1 -right-1 min-w-[16px] h-4 px-1 rounded-full bg-cyan-400 text-slate-950 font-mono font-bold text-[9px] flex items-center justify-center shadow">
                {agentsBadgeCount > 9 ? "9+" : agentsBadgeCount}
              </span>
            )}
          </button>

          {/* 2. Base de Conhecimento */}
          <button
            type="button"
            onClick={onOpenKB}
            aria-label="Abrir Base de Conhecimento da IA"
            title={`Base de Conhecimento Híbrida (${kbChunksCount} chunks indexados)`}
            className={`${railBtnBase} ${
              kbOpen
                ? "bg-emerald-500/20 border-emerald-400/55 text-emerald-200 shadow-[0_0_16px_rgba(16,185,129,0.22)]"
                : "bg-white/[0.03] border-white/8 text-slate-400 hover:text-emerald-200 hover:border-emerald-400/35 hover:bg-emerald-500/10"
            }`}
          >
            <Icons8Icon name="book-open" className="w-[19px] h-[19px]" />
            {kbChunksCount > 0 && (
              <span className="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-400 ring-2 ring-[#040914]" />
            )}
          </button>

          {/* 3. Tela ao Vivo (apenas no modo Desktop Windows) */}
          {!isWebMode && (
            <button
              type="button"
              onClick={onToggleLiveScreen}
              aria-label="Alternar Tela ao Vivo"
              title="Tela ao Vivo (espelhamento em tempo real da área de trabalho)"
              className={`${railBtnBase} ${
                liveScreenActive
                  ? "bg-blue-500/20 border-blue-400/55 text-blue-200 shadow-[0_0_14px_rgba(59,130,246,0.22)]"
                  : "bg-white/[0.03] border-white/8 text-slate-400 hover:text-blue-200 hover:border-blue-400/35 hover:bg-blue-500/10"
              }`}
            >
              <Icons8Icon name="live-tv" className="w-[19px] h-[19px]" />
            </button>
          )}

          {/* 4. Alternar Modo Visual do Orbe */}
          <button
            type="button"
            onClick={() =>
              onOrbModelChange(orbModel === "orbital-hud" ? "neural-fibonacci" : "orbital-hud")
            }
            aria-label="Alternar Geometria do Orbe"
            title={`Geometria do Orbe: ${orbModel === "orbital-hud" ? "Orbital HUD" : "Neural Fibonacci"}`}
            className={`${railBtnBase} bg-white/[0.03] border-white/8 text-slate-400 hover:text-white hover:border-white/25 hover:bg-white/8`}
          >
            <Icons8Icon name="orbit" className="w-[19px] h-[19px]" />
            <span className="absolute -bottom-1 px-1 rounded bg-[#091224] border border-white/15 text-[7px] font-mono text-cyan-300 uppercase">
              {orbModel === "orbital-hud" ? "HUD" : "FIB"}
            </span>
          </button>

          {/* 5. Controles de Sistema & Diagnóstico */}
          <div ref={menuRef} className="relative">
            <button
              type="button"
              onClick={() => setToolsMenuOpen((v) => !v)}
              aria-expanded={toolsMenuOpen}
              aria-label="Atalhos de Sistema e Diagnóstico"
              title="Atalhos Rápidos do Sistema & Simulador do Orbe"
              className={`${railBtnBase} ${
                toolsMenuOpen
                  ? "bg-amber-500/20 border-amber-400/50 text-amber-200"
                  : "bg-white/[0.03] border-white/8 text-slate-400 hover:text-amber-200 hover:border-amber-400/35 hover:bg-amber-500/10"
              }`}
            >
              <Icons8Icon name="sliders" className="w-[19px] h-[19px]" />
            </button>

            {toolsMenuOpen && (
              <div className="absolute left-14 top-0 w-64 rounded-2xl bg-[#060d1d]/97 border border-white/12 shadow-2xl backdrop-blur-3xl p-3.5 space-y-3 z-50">
                {!isWebMode && (
                  <div>
                    <p className="text-[10px] font-mono uppercase tracking-widest text-cyan-300 font-semibold mb-2">
                      Atalhos Rápidos Windows
                    </p>
                    <div className="grid grid-cols-5 gap-1.5">
                      {quickShortcuts.map((btn, idx) => (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => {
                            btn.onClick();
                            setToolsMenuOpen(false);
                          }}
                          title={btn.title}
                          className="h-9 rounded-lg bg-white/[0.04] hover:bg-cyan-500/15 border border-white/8 hover:border-cyan-400/35 flex items-center justify-center text-slate-300 hover:text-cyan-200 transition-colors cursor-pointer"
                        >
                          <Icons8Icon name={btn.icon} size={16} />
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div className={`${!isWebMode ? "pt-2.5 border-t border-white/10 " : ""}space-y-2`}>
                  <p className="text-[10px] font-mono uppercase tracking-widest text-slate-400 font-semibold">
                    Calibração do Orbe
                  </p>
                  <div className="grid grid-cols-2 gap-1.5 font-mono text-[10px]">
                    {(["idle", "listening", "thinking", "speaking"] as AIOrbState[]).map((st) => (
                      <button
                        key={st}
                        type="button"
                        onClick={() =>
                          onSetDemoState(st, st === "listening" || st === "speaking" ? 0.45 : 0)
                        }
                        className={`px-2 py-1.5 rounded-lg border capitalize transition-all cursor-pointer ${
                          aiState === st
                            ? "bg-cyan-500/20 border-cyan-400/50 text-cyan-100 font-semibold"
                            : "bg-white/[0.03] border-white/8 text-slate-400 hover:text-white"
                        }`}
                      >
                        {st}
                      </button>
                    ))}
                  </div>
                  <div className="pt-1">
                    <div className="flex justify-between text-[10px] font-mono text-slate-400 mb-1">
                      <span className="inline-flex items-center gap-1">
                        <Icons8Icon name="activity" size={12} /> Reatividade Áudio
                      </span>
                      <span className="text-slate-200">{Math.round(audioLevel * 100)}%</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={audioLevel}
                      onChange={(e) => onAudioLevelChange(parseFloat(e.target.value))}
                      className="w-full accent-cyan-400 cursor-pointer h-1.5 bg-white/10 rounded-lg"
                    />
                  </div>
                </div>

                {onGradientModeChange && (
                  <div className="pt-2.5 border-t border-white/10 space-y-1.5">
                    <p className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest text-cyan-300 font-semibold">
                      <Icons8Icon name="palette" size={12} />
                      Spell UI Gradient
                    </p>
                    <div className="grid grid-cols-3 gap-1 font-mono text-[10px]">
                      {(["auto", "Prism", "Pulse", "Plasma", "Vortex", "off"] as GradientModeOption[]).map(
                        (gm) => (
                          <button
                            key={gm}
                            type="button"
                            onClick={() => onGradientModeChange(gm)}
                            className={`px-2 py-1 rounded-lg border transition-all cursor-pointer ${
                              gradientMode === gm
                                ? "bg-cyan-500/20 border-cyan-400/50 text-cyan-100 font-semibold"
                                : "bg-white/[0.03] border-white/8 text-slate-400 hover:text-white"
                            }`}
                          >
                            {gm === "auto" ? "Auto" : gm === "off" ? "Off" : gm}
                          </button>
                        ),
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </nav>
      </div>

      {/* Rodapé do Rail: Chat, Tela Cheia e Bloqueio E2EE */}
      <div className="flex flex-col items-center gap-2">
        <button
          type="button"
          onClick={onToggleChat}
          aria-label={chatOpen ? "Ocultar Terminal de Diálogo" : "Mostrar Terminal de Diálogo"}
          title={chatOpen ? "Ocultar Terminal de Diálogo" : "Abrir Terminal de Diálogo"}
          className={`${railBtnBase} ${
            chatOpen && !isFullScreenOrb
              ? "bg-cyan-500/18 border-cyan-400/45 text-cyan-200"
              : "bg-white/[0.03] border-white/8 text-slate-400 hover:text-white hover:border-white/20"
          }`}
        >
          <Icons8Icon name="message" className="w-[18px] h-[18px]" />
        </button>

        <button
          type="button"
          onClick={onToggleFullScreen}
          aria-label="Modo Imersivo do Orbe"
          title={isFullScreenOrb ? "Sair do Modo Imersivo" : "Modo Imersivo Tela Cheia"}
          className={`${railBtnBase} bg-white/[0.03] border-white/8 text-slate-400 hover:text-white hover:border-white/20`}
        >
          {isFullScreenOrb ? (
            <Icons8Icon name="minimize" className="w-[18px] h-[18px]" />
          ) : (
            <Icons8Icon name="maximize" className="w-[18px] h-[18px]" />
          )}
        </button>

        {e2eeRequired && e2eeUnlocked && (
          <button
            type="button"
            onClick={onLockAI}
            aria-label="Bloquear IA (Cofre E2EE)"
            title="Bloquear IA imediatamente (encerra sessão E2EE e áudio)"
            className={`${railBtnBase} bg-red-500/14 border-red-400/35 text-red-300 hover:bg-red-500/25 hover:text-red-100`}
          >
            <Icons8Icon name="lock" className="w-[18px] h-[18px]" />
          </button>
        )}
      </div>
    </aside>
  );
};

export default CommandRail;
