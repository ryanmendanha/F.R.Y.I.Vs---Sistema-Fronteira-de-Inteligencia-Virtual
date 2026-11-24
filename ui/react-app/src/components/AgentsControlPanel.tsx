import { useCallback, useEffect, useRef, useState } from "react";
import type { FC, FormEvent } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  Check,
  CheckCircle2,
  Clock,
  Code2,
  Cpu,
  Eye,
  Gauge,
  Loader2,
  OctagonX,
  RefreshCw,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  X,
  XCircle,
  Zap,
} from "lucide-react";

export interface AgentsControlPanelProps {
  sessionToken: string | null;
  isOpen: boolean;
  onClose: () => void;
}

type HermesProfileName = "pesquisador" | "engenheiro" | "analista" | "sentinela";

type AgentJobStatus =
  | "queued"
  | "running"
  | "awaiting_approval"
  | "completed"
  | "failed"
  | "cancelled"
  | "killed"
  | "offline";

interface HermesProfileInfo {
  name: HermesProfileName;
  label: string;
  mission: string;
  tools: string[];
  sandbox: string;
  model_alias: string;
  default_max_steps: number;
}

interface AgentJobItem {
  job_id: string;
  profile: HermesProfileName;
  task: string;
  status: AgentJobStatus;
  correlation_id: string;
  hop_count: number;
  context_tainted: boolean;
  approval_id: string | null;
  elapsed_seconds: number;
  steps_completed: number;
  max_steps: number;
  progress_pct: number;
  tokens_used: number;
  estimated_usd: number;
  result: string;
  error: string;
  transport: string;
}

interface PendingApprovalItem {
  approval_id: string;
  tool: string;
  tier: number;
  args_summary: string;
  created_at: number;
  created_at_iso: string;
  expires_at: number;
  status: "pending" | "approved" | "denied" | "expired";
  actor: string;
  agent: string;
  correlation_id: string;
  reason: string;
  context_tainted: boolean;
}

interface BudgetSnapshot {
  date: string;
  daily_tokens_used: number;
  daily_usd_used: number;
  max_usd_per_day: number;
  usd_utilization_pct: number;
  active_concurrent: number;
  max_concurrent_agents: number;
  max_hop_count: number;
  max_steps_hermes: number;
  max_wall_time_s: number;
  max_tokens_per_job: number;
}

interface AgentsStatusResponse {
  hermes: {
    api_url: string;
    online: boolean;
    state: "online" | "offline" | "standby";
    detail: string;
    redis_configured: boolean;
    profiles: HermesProfileInfo[];
  };
  budget: BudgetSnapshot;
  active_jobs: AgentJobItem[];
  jobs: AgentJobItem[];
  pending_approvals: PendingApprovalItem[];
}

const DEFAULT_PROFILES: HermesProfileInfo[] = [
  {
    name: "pesquisador",
    label: "Pesquisador",
    mission: "Pesquisas longitudinais, benchmarks, papers e monitoramento de mercado.",
    tools: ["web_search", "browser", "mcp_rag_read"],
    sandbox: "Restrito (somente leitura)",
    model_alias: "hermes/pesquisador",
    default_max_steps: 15,
  },
  {
    name: "engenheiro",
    label: "Engenheiro",
    mission: "Desenvolvimento, refatoração, testes e auditoria de repositórios.",
    tools: ["terminal_sandbox", "git", "mcp_graphify"],
    sandbox: "Workspace isolado / Docker",
    model_alias: "hermes/engenheiro",
    default_max_steps: 15,
  },
  {
    name: "analista",
    label: "Analista",
    mission: "ETL, análise Pandas/SQL, relatórios executivos e planilhas.",
    tools: ["python_sandbox", "mcp_filesystem_restricted", "n8n_read"],
    sandbox: "Pasta dedicada de dados",
    model_alias: "hermes/analista",
    default_max_steps: 15,
  },
  {
    name: "sentinela",
    label: "Sentinela 24/7",
    mission: "Monitoramento contínuo via Hermes Cron, triagem e alertas HMAC.",
    tools: ["hermes_cron", "webhooks_hmac", "mcp_n8n_notify"],
    sandbox: "Somente leitura + alertas",
    model_alias: "hermes/sentinela",
    default_max_steps: 10,
  },
];

function buildAuthHeaders(
  sessionToken: string | null,
  extra: Record<string, string> = {},
): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  if (sessionToken) {
    headers["X-E2EE-Session"] = sessionToken;
  }
  return headers;
}

function formatElapsed(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  if (safe < 60) return `${safe}s`;
  const mins = Math.floor(safe / 60);
  const rem = safe % 60;
  return `${mins}m ${rem.toString().padStart(2, "0")}s`;
}

function getProfileMeta(profile: HermesProfileName): {
  badgeClass: string;
  accentText: string;
  icon: typeof Search;
} {
  switch (profile) {
    case "pesquisador":
      return {
        badgeClass: "bg-cyan-500/15 border-cyan-400/35 text-cyan-200",
        accentText: "text-cyan-300",
        icon: Search,
      };
    case "engenheiro":
      return {
        badgeClass: "bg-blue-500/15 border-blue-400/35 text-blue-200",
        accentText: "text-blue-300",
        icon: Code2,
      };
    case "analista":
      return {
        badgeClass: "bg-emerald-500/15 border-emerald-400/35 text-emerald-200",
        accentText: "text-emerald-300",
        icon: BarChart3,
      };
    case "sentinela":
      return {
        badgeClass: "bg-amber-500/15 border-amber-400/35 text-amber-200",
        accentText: "text-amber-300",
        icon: Eye,
      };
  }
}

function getStatusBadge(status: AgentJobStatus): { label: string; className: string } {
  switch (status) {
    case "running":
      return {
        label: "Em execução",
        className: "bg-cyan-500/20 border-cyan-400/45 text-cyan-200",
      };
    case "queued":
      return {
        label: "Na fila",
        className: "bg-blue-500/20 border-blue-400/40 text-blue-200",
      };
    case "awaiting_approval":
      return {
        label: "Aguardando Tier 3",
        className: "bg-amber-500/20 border-amber-400/50 text-amber-200",
      };
    case "completed":
      return {
        label: "Concluído",
        className: "bg-emerald-500/20 border-emerald-400/40 text-emerald-200",
      };
    case "offline":
      return {
        label: "Hermes Offline",
        className: "bg-slate-500/20 border-slate-400/40 text-slate-300",
      };
    case "cancelled":
      return {
        label: "Cancelado",
        className: "bg-slate-600/25 border-slate-500/40 text-slate-300",
      };
    case "killed":
      return {
        label: "Kill-Switch",
        className: "bg-red-500/25 border-red-400/50 text-red-200",
      };
    case "failed":
      return {
        label: "Falhou",
        className: "bg-red-500/20 border-red-400/45 text-red-200",
      };
  }
}

export const AgentsControlPanel: FC<AgentsControlPanelProps> = ({
  sessionToken,
  isOpen,
  onClose,
}) => {
  const [statusData, setStatusData] = useState<AgentsStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bannerMsg, setBannerMsg] = useState<string | null>(null);

  // Estado do formulário rápido de delegação
  const [selectedProfile, setSelectedProfile] = useState<HermesProfileName>("pesquisador");
  const [taskInput, setTaskInput] = useState("");
  const [contextTainted, setContextTainted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Estados de ações em andamento
  const [killingAll, setKillingAll] = useState(false);
  const [busyJobIds, setBusyJobIds] = useState<Record<string, boolean>>({});
  const [busyApprovalIds, setBusyApprovalIds] = useState<Record<string, boolean>>({});

  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const fetchStatus = useCallback(
    async (probe = false) => {
      try {
        setLoading(true);
        const query = probe ? "?probe=true" : "";
        const res = await fetch(`/api/agents/status${query}`, {
          method: "GET",
          headers: buildAuthHeaders(sessionToken),
          cache: "no-store",
        });

        if (res.status === 423) {
          if (mountedRef.current) {
            setError("Sessão E2EE bloqueada. Desbloqueie o cofre para gerenciar subagentes.");
          }
          return;
        }

        if (!res.ok) {
          throw new Error(`Falha ao consultar agentes (HTTP ${res.status}).`);
        }

        const data = (await res.json()) as AgentsStatusResponse;
        if (mountedRef.current) {
          setStatusData(data);
          setError(null);
        }
      } catch (err) {
        if (mountedRef.current) {
          setError(
            err instanceof Error
              ? err.message
              : "Não foi possível conectar ao orquestrador de agentes.",
          );
        }
      } finally {
        if (mountedRef.current) {
          setLoading(false);
        }
      }
    },
    [sessionToken],
  );

  // Polling periódico enquanto o painel estiver aberto
  useEffect(() => {
    if (!isOpen) return;
    void fetchStatus(false);
    const interval = window.setInterval(() => {
      void fetchStatus(false);
    }, 3000);
    return () => window.clearInterval(interval);
  }, [isOpen, fetchStatus]);

  // Fechar com Escape
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  const handleDelegate = async (e: FormEvent) => {
    e.preventDefault();
    const cleanTask = taskInput.trim();
    if (!cleanTask || submitting) return;

    setSubmitting(true);
    setError(null);
    setBannerMsg(null);
    try {
      const res = await fetch("/api/agents/delegate", {
        method: "POST",
        headers: buildAuthHeaders(sessionToken, { "Content-Type": "application/json" }),
        body: JSON.stringify({
          profile: selectedProfile,
          task: cleanTask,
          context_tainted: contextTainted,
          hop_count: 0,
        }),
      });
      const body = (await res.json().catch(() => ({}))) as {
        detail?: string;
        requires_approval?: boolean;
        job?: AgentJobItem;
      };
      if (!res.ok) {
        throw new Error(body.detail || `Erro ao delegar missão (HTTP ${res.status}).`);
      }

      setTaskInput("");
      setContextTainted(false);
      setBannerMsg(
        body.requires_approval
          ? "Missão marcada como contexto externo: aguardando aprovação explícita Tier 3."
          : `Missão delegada ao perfil '${selectedProfile}' em segundo plano.`,
      );
      await fetchStatus(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao delegar missão.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancelJob = async (jobId: string) => {
    setBusyJobIds((prev) => ({ ...prev, [jobId]: true }));
    setError(null);
    try {
      const res = await fetch(`/api/agents/jobs/${encodeURIComponent(jobId)}/cancel`, {
        method: "POST",
        headers: buildAuthHeaders(sessionToken),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail || `Erro ao cancelar missão (HTTP ${res.status}).`);
      }
      setBannerMsg(`Missão ${jobId.slice(0, 8)} cancelada.`);
      await fetchStatus(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao cancelar missão.");
    } finally {
      setBusyJobIds((prev) => ({ ...prev, [jobId]: false }));
    }
  };

  const handleKillAll = async () => {
    if (killingAll) return;
    setKillingAll(true);
    setError(null);
    setBannerMsg(null);
    try {
      const res = await fetch("/api/agents/kill-all", {
        method: "POST",
        headers: buildAuthHeaders(sessionToken),
      });
      const body = (await res.json().catch(() => ({}))) as {
        killed_count?: number;
        detail?: string;
      };
      if (!res.ok) {
        throw new Error(body.detail || `Falha no Kill-Switch (HTTP ${res.status}).`);
      }
      setBannerMsg(
        `Kill-Switch acionado: ${body.killed_count ?? 0} missão(ões) interrompida(s) imediatamente.`,
      );
      await fetchStatus(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao executar Kill-Switch.");
    } finally {
      setKillingAll(false);
    }
  };

  const handleApprovalDecision = async (approvalId: string, approved: boolean) => {
    setBusyApprovalIds((prev) => ({ ...prev, [approvalId]: true }));
    setError(null);
    setBannerMsg(null);
    try {
      const res = await fetch(`/api/agents/approvals/${encodeURIComponent(approvalId)}`, {
        method: "POST",
        headers: buildAuthHeaders(sessionToken, { "Content-Type": "application/json" }),
        body: JSON.stringify({
          approved,
          decision: approved ? "approve" : "deny",
        }),
      });
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      if (!res.ok) {
        throw new Error(body.detail || `Falha ao registrar decisão (HTTP ${res.status}).`);
      }
      setBannerMsg(
        approved
          ? `Aprovação Tier 3 (${approvalId.slice(0, 8)}) autorizada.`
          : `Aprovação Tier 3 (${approvalId.slice(0, 8)}) negada.`,
      );
      await fetchStatus(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao decidir aprovação Tier 3.");
    } finally {
      setBusyApprovalIds((prev) => ({ ...prev, [approvalId]: false }));
    }
  };

  if (!isOpen) return null;

  const profiles = statusData?.hermes.profiles ?? DEFAULT_PROFILES;
  const jobs = statusData?.jobs ?? [];
  const pendingApprovals = statusData?.pending_approvals ?? [];
  const budget: BudgetSnapshot = statusData?.budget ?? {
    date: "",
    daily_tokens_used: 0,
    daily_usd_used: 0,
    max_usd_per_day: 5,
    usd_utilization_pct: 0,
    active_concurrent: 0,
    max_concurrent_agents: 2,
    max_hop_count: 2,
    max_steps_hermes: 15,
    max_wall_time_s: 180,
    max_tokens_per_job: 32000,
  };

  const hermesState = statusData?.hermes.state ?? "standby";
  const usdPct = Math.min(100, Math.max(0, budget.usd_utilization_pct));
  const budgetBarColor =
    usdPct >= 90
      ? "from-red-500 to-rose-400"
      : usdPct >= 70
        ? "from-amber-400 to-orange-500"
        : "from-cyan-400 to-blue-500";

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-[#02060f]/80 backdrop-blur-xl"
      role="dialog"
      aria-modal="true"
      aria-labelledby="agents-control-panel-title"
      onClick={onClose}
    >
      {/* Brilhos ambientais cyan/blue */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-24 right-24 w-[420px] h-[420px] rounded-full bg-cyan-500/10 blur-[130px]" />
        <div className="absolute bottom-0 right-1/3 w-[360px] h-[360px] rounded-full bg-blue-600/12 blur-[120px]" />
      </div>

      {/* Drawer principal */}
      <div
        className="relative w-full max-w-2xl h-full flex flex-col border-l border-cyan-400/25 bg-[#050b18]/95 text-slate-200 shadow-[0_0_90px_rgba(6,182,212,0.2)] backdrop-blur-3xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-3 px-6 py-4 border-b border-white/10 bg-[#060f22]/90">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-600/25 border border-cyan-400/40 flex items-center justify-center shadow-[0_0_20px_rgba(34,211,238,0.22)] shrink-0">
              <Bot className="w-5 h-5 text-cyan-300" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2
                  id="agents-control-panel-title"
                  className="text-sm font-bold tracking-[0.18em] uppercase text-white truncate"
                >
                  Central Multi-Agente
                </h2>
                <span
                  className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider border ${
                    hermesState === "online"
                      ? "bg-emerald-500/15 border-emerald-400/40 text-emerald-300"
                      : hermesState === "offline"
                        ? "bg-red-500/15 border-red-400/35 text-red-300"
                        : "bg-cyan-500/12 border-cyan-400/30 text-cyan-300"
                  }`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      hermesState === "online"
                        ? "bg-emerald-400 animate-pulse"
                        : hermesState === "offline"
                          ? "bg-red-400"
                          : "bg-cyan-400"
                    }`}
                  />
                  Hermes {hermesState === "online" ? "Online" : hermesState === "offline" ? "Offline" : "Standby"}
                </span>
              </div>
              <p className="text-[11px] font-mono text-slate-400 truncate mt-0.5">
                Hermes WSL2 (127.0.0.1:8642) · Policy Engine · Budget Guard
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => void fetchStatus(true)}
              disabled={loading}
              title="Atualizar e sondar Hermes WSL2"
              className="p-2 rounded-xl border border-white/10 bg-white/5 hover:border-cyan-400/40 hover:text-cyan-300 text-slate-400 transition-all cursor-pointer disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-cyan-300" : ""}`} />
            </button>

            <button
              type="button"
              onClick={() => void handleKillAll()}
              disabled={killingAll}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-red-500/20 hover:bg-red-500/30 border border-red-400/50 text-red-200 hover:text-white text-[11px] font-bold uppercase tracking-wider shadow-[0_0_20px_rgba(239,68,68,0.25)] transition-all cursor-pointer disabled:opacity-50"
            >
              {killingAll ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <OctagonX className="w-3.5 h-3.5 text-red-300" />
              )}
              Kill All
            </button>

            <button
              type="button"
              onClick={onClose}
              aria-label="Fechar painel multi-agente"
              className="p-2 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-all cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Conteúdo rolável */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {/* Alertas / Feedback */}
          {error && (
            <div className="rounded-2xl bg-red-500/10 border border-red-400/35 px-4 py-3 text-xs text-red-200 flex items-start gap-2.5">
              <ShieldAlert className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {bannerMsg && (
            <div className="rounded-2xl bg-cyan-500/10 border border-cyan-400/35 px-4 py-3 text-xs text-cyan-100 flex items-start gap-2.5">
              <Sparkles className="w-4 h-4 text-cyan-300 shrink-0 mt-0.5" />
              <span>{bannerMsg}</span>
            </div>
          )}

          {/* 1. Daily Budget Guard */}
          <section className="rounded-2xl border border-cyan-400/20 bg-white/[0.03] p-4 space-y-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-2">
                <Gauge className="w-4 h-4 text-cyan-300" />
                <h3 className="text-[11px] font-mono uppercase tracking-[0.2em] text-cyan-200 font-semibold">
                  Budget Guard Diário
                </h3>
              </div>

              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono bg-cyan-500/15 border border-cyan-400/30 text-cyan-200">
                  <Cpu className="w-3 h-3 text-cyan-300" />
                  Concorrência: {budget.active_concurrent}/{budget.max_concurrent_agents}
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-white/5 border border-white/10 text-slate-300">
                  Hop ≤ {budget.max_hop_count}
                </span>
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-baseline justify-between text-xs font-mono">
                <span className="text-slate-300">
                  US$ {budget.daily_usd_used.toFixed(4)}{" "}
                  <span className="text-slate-500">/ US$ {budget.max_usd_per_day.toFixed(2)}</span>
                </span>
                <span className="text-cyan-300">
                  {budget.daily_tokens_used.toLocaleString("pt-BR")} tokens ({usdPct.toFixed(1)}%)
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-black/60 border border-white/10 overflow-hidden">
                <div
                  className={`h-full rounded-full bg-gradient-to-r ${budgetBarColor} transition-all duration-500`}
                  style={{ width: `${usdPct}%` }}
                />
              </div>
            </div>
          </section>

          {/* 2. Fila de Aprovações Tier 3 (Human-in-the-Loop) */}
          <section className="rounded-2xl border border-amber-400/25 bg-amber-500/[0.04] p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-amber-300" />
                <h3 className="text-[11px] font-mono uppercase tracking-[0.2em] text-amber-200 font-semibold">
                  Aprovações Tier 3 Pendentes
                </h3>
              </div>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-amber-500/20 border border-amber-400/40 text-amber-200">
                {pendingApprovals.length} pendente(s)
              </span>
            </div>

            {pendingApprovals.length === 0 ? (
              <div className="rounded-xl border border-white/8 bg-black/30 px-3.5 py-3 text-xs text-slate-400 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>Nenhuma ação crítica Tier 3 aguardando confirmação humana no momento.</span>
              </div>
            ) : (
              <div className="space-y-2.5">
                {pendingApprovals.map((item) => {
                  const busy = Boolean(busyApprovalIds[item.approval_id]);
                  return (
                    <div
                      key={item.approval_id}
                      className="rounded-xl border border-amber-400/35 bg-[#071022]/90 p-3.5 space-y-2.5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="space-y-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-xs font-bold font-mono text-white">
                              {item.tool}
                            </span>
                            <span className="px-2 py-0.5 rounded-full text-[9px] font-mono uppercase bg-red-500/20 border border-red-400/40 text-red-200">
                              Tier {item.tier}
                            </span>
                            {item.context_tainted && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-mono uppercase bg-amber-500/25 border border-amber-400/50 text-amber-200">
                                <AlertTriangle className="w-2.5 h-2.5" />
                                Tainted Context
                              </span>
                            )}
                          </div>
                          <p className="text-[11px] text-slate-300 leading-relaxed">
                            {item.reason}
                          </p>
                          <p className="text-[10px] font-mono text-slate-500 break-all">
                            Agente: {item.agent} · Args: {item.args_summary}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center justify-end gap-2 pt-1">
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void handleApprovalDecision(item.approval_id, false)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/15 hover:bg-red-500/25 border border-red-400/40 text-red-200 text-[11px] font-semibold transition-all cursor-pointer disabled:opacity-50"
                        >
                          <XCircle className="w-3.5 h-3.5" />
                          Negar
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void handleApprovalDecision(item.approval_id, true)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-400/45 text-emerald-200 text-[11px] font-semibold transition-all cursor-pointer disabled:opacity-50"
                        >
                          {busy ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Check className="w-3.5 h-3.5" />
                          )}
                          Aprovar
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* 3. Perfis Especialistas Hermes & Delegação Rápida */}
          <section className="rounded-2xl border border-white/10 bg-white/[0.025] p-4 space-y-3.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap className="w-4 h-4 text-cyan-300" />
                <h3 className="text-[11px] font-mono uppercase tracking-[0.2em] text-cyan-200 font-semibold">
                  Perfis Especialistas Hermes
                </h3>
              </div>
              <span className="text-[10px] font-mono text-slate-400">
                {profiles.length} perfis isolados (~/.hermes)
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {profiles.map((prof) => {
                const meta = getProfileMeta(prof.name);
                const Icon = meta.icon;
                const isSelected = selectedProfile === prof.name;
                return (
                  <button
                    key={prof.name}
                    type="button"
                    onClick={() => setSelectedProfile(prof.name)}
                    className={`text-left rounded-xl p-3 border transition-all cursor-pointer ${
                      isSelected
                        ? "border-cyan-400/60 bg-cyan-500/12 shadow-[0_0_20px_rgba(34,211,238,0.16)]"
                        : "border-white/10 bg-black/35 hover:border-cyan-400/30 hover:bg-white/[0.04]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="inline-flex items-center gap-1.5 text-xs font-bold text-white">
                        <Icon className={`w-3.5 h-3.5 ${meta.accentText}`} />
                        {prof.label}
                      </span>
                      <span className="text-[9px] font-mono text-slate-400">
                        ≤ {prof.default_max_steps} steps
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-snug line-clamp-2">
                      {prof.mission}
                    </p>
                    <p className="text-[9px] font-mono text-slate-500 mt-1.5 truncate">
                      Sandbox: {prof.sandbox}
                    </p>
                  </button>
                );
              })}
            </div>

            {/* Formulário de delegação assíncrona */}
            <form onSubmit={handleDelegate} className="space-y-2.5 pt-1">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={taskInput}
                  onChange={(e) => setTaskInput(e.target.value)}
                  placeholder={`Delegar missão assíncrona para '${selectedProfile}'...`}
                  disabled={submitting}
                  className="flex-1 rounded-xl bg-black/65 border border-white/12 focus:border-cyan-400/60 px-3.5 py-2.5 text-xs text-white placeholder-slate-500 outline-none transition-all"
                />
                <button
                  type="submit"
                  disabled={!taskInput.trim() || submitting}
                  className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-400 to-blue-500 hover:from-cyan-300 hover:to-blue-400 text-slate-950 font-bold text-[11px] uppercase tracking-wider shadow-[0_0_20px_rgba(34,211,238,0.28)] transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {submitting ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Send className="w-3.5 h-3.5" />
                  )}
                  Delegar
                </button>
              </div>

              <label className="inline-flex items-center gap-2 text-[11px] text-slate-400 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={contextTainted}
                  onChange={(e) => setContextTainted(e.target.checked)}
                  className="rounded border-white/20 bg-black/60 accent-amber-400"
                />
                <span>
                  Marcar como contexto externo não confiável (ativa Taint-Tracking → aprovação Tier 3)
                </span>
              </label>
            </form>
          </section>

          {/* 4. Cards de Missões Assíncronas */}
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-cyan-300" />
                <h3 className="text-[11px] font-mono uppercase tracking-[0.2em] text-cyan-200 font-semibold">
                  Missões Assíncronas ({jobs.length})
                </h3>
              </div>
              <span className="text-[10px] font-mono text-slate-500">
                Atualização automática · 3s
              </span>
            </div>

            {jobs.length === 0 ? (
              <div className="rounded-2xl border border-white/8 bg-white/[0.02] px-4 py-6 text-center text-xs text-slate-500">
                Nenhuma missão delegada ainda. Selecione um perfil Hermes acima para iniciar uma
                tarefa em segundo plano.
              </div>
            ) : (
              <div className="space-y-2.5">
                {jobs.map((job) => {
                  const profileMeta = getProfileMeta(job.profile);
                  const ProfileIcon = profileMeta.icon;
                  const statusBadge = getStatusBadge(job.status);
                  const isActive =
                    job.status === "queued" ||
                    job.status === "running" ||
                    job.status === "awaiting_approval";
                  const cancelling = Boolean(busyJobIds[job.job_id]);

                  return (
                    <div
                      key={job.job_id}
                      className="rounded-2xl border border-white/10 bg-[#071022]/85 p-4 space-y-2.5 hover:border-cyan-400/25 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono uppercase border ${profileMeta.badgeClass}`}
                          >
                            <ProfileIcon className="w-3 h-3" />
                            {job.profile}
                          </span>
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono border ${statusBadge.className}`}
                          >
                            {job.status === "running" && (
                              <Loader2 className="w-2.5 h-2.5 animate-spin" />
                            )}
                            {job.status === "completed" && <CheckCircle2 className="w-2.5 h-2.5" />}
                            {statusBadge.label}
                          </span>
                          <span className="text-[10px] font-mono text-slate-500">
                            #{job.job_id.slice(0, 8)}
                          </span>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          <span className="inline-flex items-center gap-1 text-[10px] font-mono text-slate-400">
                            <Clock className="w-3 h-3 text-slate-500" />
                            {formatElapsed(job.elapsed_seconds)}
                          </span>
                          {isActive && (
                            <button
                              type="button"
                              disabled={cancelling}
                              onClick={() => void handleCancelJob(job.job_id)}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-red-500/15 hover:bg-red-500/25 border border-red-400/35 text-red-200 text-[10px] font-semibold transition-all cursor-pointer disabled:opacity-50"
                            >
                              {cancelling ? (
                                <Loader2 className="w-3 h-3 animate-spin" />
                              ) : (
                                <XCircle className="w-3 h-3" />
                              )}
                              Cancelar
                            </button>
                          )}
                        </div>
                      </div>

                      <p className="text-xs text-slate-200 leading-relaxed">{job.task}</p>

                      {/* Barra de progresso + métricas */}
                      <div className="space-y-1">
                        <div className="flex items-center justify-between text-[10px] font-mono text-slate-400">
                          <span>
                            Passos: {job.steps_completed}/{job.max_steps} · Hop {job.hop_count}
                          </span>
                          <span>
                            {job.tokens_used.toLocaleString("pt-BR")} tok · US${" "}
                            {job.estimated_usd.toFixed(4)} · {job.progress_pct}%
                          </span>
                        </div>
                        <div className="h-1.5 w-full rounded-full bg-black/60 overflow-hidden border border-white/8">
                          <div
                            className={`h-full rounded-full transition-all duration-500 ${
                              job.status === "failed" || job.status === "killed"
                                ? "bg-red-500"
                                : job.status === "completed"
                                  ? "bg-emerald-400"
                                  : "bg-gradient-to-r from-cyan-400 to-blue-500"
                            }`}
                            style={{ width: `${Math.min(100, Math.max(0, job.progress_pct))}%` }}
                          />
                        </div>
                      </div>

                      {job.result && (
                        <div className="rounded-xl bg-emerald-500/8 border border-emerald-400/20 px-3 py-2 text-[11px] text-emerald-100/90 whitespace-pre-wrap line-clamp-4">
                          {job.result}
                        </div>
                      )}

                      {job.error && (
                        <div className="rounded-xl bg-red-500/8 border border-red-400/25 px-3 py-2 text-[11px] text-red-200/90">
                          {job.error}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
};

export default AgentsControlPanel;
