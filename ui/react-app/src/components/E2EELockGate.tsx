import React, { useEffect, useState } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  Lock,
  KeyRound,
  Eye,
  EyeOff,
  Loader2,
  Cpu,
  VolumeX,
} from "lucide-react";
import {
  E2EEAuthError,
  performE2EEUnlock,
  type E2EESession,
} from "@/lib/e2ee";

interface E2EELockGateProps {
  hasPasswordConfigured: boolean;
  initialLockoutSeconds?: number;
  onUnlocked: (session: E2EESession) => void;
}

export const E2EELockGate: React.FC<E2EELockGateProps> = ({
  hasPasswordConfigured,
  initialLockoutSeconds = 0,
  onUnlocked,
}) => {
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [lockoutSeconds, setLockoutSeconds] = useState(initialLockoutSeconds);

  useEffect(() => {
    setLockoutSeconds(initialLockoutSeconds);
  }, [initialLockoutSeconds]);

  useEffect(() => {
    if (lockoutSeconds <= 0) return;
    const timer = setInterval(() => {
      setLockoutSeconds((prev) => (prev <= 1 ? 0 : prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [lockoutSeconds]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim() || loading || lockoutSeconds > 0) return;

    setLoading(true);
    setError("");
    try {
      const session = await performE2EEUnlock(password);
      setPassword("");
      onUnlocked(session);
    } catch (err) {
      if (err instanceof E2EEAuthError) {
        setError(err.message);
        if (err.status === 429 && err.retryAfterSeconds > 0) {
          setLockoutSeconds(err.retryAfterSeconds);
        }
      } else {
        setError("Erro inesperado durante o handshake criptografado E2EE.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#02060f]/95 backdrop-blur-2xl p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="e2ee-gate-title"
    >
      {/* Brilhos ambientais futuristas */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-32 left-1/2 -translate-x-1/2 w-[540px] h-[540px] rounded-full bg-cyan-500/10 blur-[140px]" />
        <div className="absolute -bottom-40 right-1/4 w-[420px] h-[420px] rounded-full bg-blue-600/12 blur-[130px]" />
      </div>

      <div className="relative w-full max-w-md rounded-3xl border border-cyan-400/25 bg-[#050b18]/90 shadow-[0_0_80px_rgba(6,182,212,0.18)] backdrop-blur-3xl p-7 text-slate-200">
        {/* Cabeçalho */}
        <div className="flex flex-col items-center text-center mb-6">
          <div className="relative mb-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-cyan-500/20 to-blue-600/20 border border-cyan-400/40 flex items-center justify-center shadow-[0_0_30px_rgba(34,211,238,0.28)]">
              <Lock className="w-7 h-7 text-cyan-300" />
            </div>
            <span className="absolute -bottom-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-[#050b18] border border-cyan-400/50">
              <ShieldCheck className="w-3 h-3 text-emerald-400" />
            </span>
          </div>

          <div className="flex items-center gap-2 mb-1">
            <img
              src="/static/fryivs-icon-removebg-preview.png"
              alt="F.R.Y.I.Vs"
              className="w-6 h-6 object-contain drop-shadow-[0_0_8px_rgba(34,211,238,0.75)]"
            />
            <h2
              id="e2ee-gate-title"
              className="text-lg font-bold tracking-[0.28em] text-white"
            >
              F.R.Y.I.Vs
            </h2>
          </div>

          <p className="text-[11px] font-mono uppercase tracking-[0.22em] text-cyan-300/90">
            Cofre Criptografado Ponta a Ponta
          </p>
        </div>

        {/* Aviso de bloqueio rígido */}
        <div className="mb-5 rounded-2xl bg-red-500/8 border border-red-400/25 px-3.5 py-2.5 flex items-start gap-2.5 text-[11px] leading-relaxed text-red-200/90">
          <VolumeX className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <span>
            <strong className="text-red-300">Fala, escuta e comandos bloqueados.</strong>{" "}
            A F.R.Y.I.Vs permanece em silêncio absoluto (TTS, Wake Word, Chat e WebSocket) até o desbloqueio E2EE.
          </span>
        </div>

        {/* Badges criptográficas */}
        <div className="flex flex-wrap items-center justify-center gap-1.5 mb-5">
          {["ECDH P-256", "HKDF-SHA256", "AES-256-GCM", "Anti-Replay"].map((pill) => (
            <span
              key={pill}
              className="px-2 py-0.5 rounded-full text-[9px] font-mono uppercase tracking-wider bg-cyan-500/10 border border-cyan-400/25 text-cyan-300"
            >
              {pill}
            </span>
          ))}
        </div>

        {/* Formulário de senha */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="e2ee-password-input"
              className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest text-slate-400 font-semibold mb-2"
            >
              <KeyRound className="w-3.5 h-3.5 text-cyan-400" />
              Senha de Acesso Neural
            </label>

            <div className="relative">
              <input
                id="e2ee-password-input"
                type={showPassword ? "text" : "password"}
                autoFocus
                autoComplete="current-password"
                disabled={loading || lockoutSeconds > 0}
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (error) setError("");
                }}
                placeholder="Digite a senha para desbloquear..."
                className="w-full rounded-xl bg-black/70 border border-white/12 focus:border-cyan-400/60 focus:shadow-[0_0_20px_rgba(34,211,238,0.22)] pl-4 pr-11 py-3 text-sm text-white placeholder-slate-600 outline-none transition-all disabled:opacity-50"
              />
              <button
                type="button"
                onClick={() => setShowPassword((prev) => !prev)}
                aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-slate-500 hover:text-cyan-300 transition-colors"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {error && (
            <div className="rounded-xl bg-red-500/10 border border-red-500/30 px-3.5 py-2.5 text-xs text-red-300 flex items-start gap-2">
              <ShieldAlert className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {lockoutSeconds > 0 && (
            <div className="rounded-xl bg-amber-500/10 border border-amber-400/30 px-3.5 py-2 text-[11px] font-mono text-amber-300 text-center">
              Bloqueio temporário anti-força-bruta ativo: aguarde {lockoutSeconds}s
            </div>
          )}

          <button
            type="submit"
            disabled={!password.trim() || loading || lockoutSeconds > 0}
            className="w-full py-3 rounded-xl bg-gradient-to-r from-cyan-400 to-blue-500 hover:from-cyan-300 hover:to-blue-400 text-slate-950 font-bold text-xs uppercase tracking-[0.2em] shadow-[0_0_25px_rgba(34,211,238,0.35)] transition-all disabled:opacity-35 disabled:cursor-not-allowed flex items-center justify-center gap-2 cursor-pointer"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Negociando Chaves E2EE...
              </>
            ) : (
              <>
                <ShieldCheck className="w-4 h-4" />
                Desbloquear F.R.Y.I.Vs
              </>
            )}
          </button>
        </form>

        {/* Nota técnica */}
        <div className="mt-5 pt-4 border-t border-white/8 text-[10px] font-mono text-slate-500 space-y-1.5">
          <div className="flex items-center gap-1.5 text-slate-400">
            <Cpu className="w-3 h-3 text-cyan-400 shrink-0" />
            <span>A senha é cifrada localmente via WebCrypto antes de sair do navegador.</span>
          </div>
          {!hasPasswordConfigured && (
            <p className="text-amber-300/80">
              Dica: defina <code>FRYIVS_VOICE_PASSWORD</code> no arquivo <code>.env</code> (ou use a senha efêmera exibida no terminal do servidor).
            </p>
          )}
        </div>
      </div>
    </div>
  );
};
