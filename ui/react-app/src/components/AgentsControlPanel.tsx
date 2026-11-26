import { useCallback, useEffect, useRef, useState } from "react";
import type { FC, FormEvent } from "react";
import {
  Activity,
  AlertTriangle,
  BookPlus,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Code2,
  Cpu,
  FolderKanban,
  Gauge,
  Lightbulb,
  Loader2,
  OctagonX,
  RefreshCw,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import { FormattedText } from "@/components/FormattedText";

export interface AgentsControlPanelProps {
  sessionToken: string | null;
  isOpen: boolean;
  onClose: () => void;
  onKnowledgeIndexed?: (totalChunks: number) => void;
  onJobsBadgeChange?: (count: number) => void;
}

export type HermesProfileName = "pesquisador" | "organizador" | "ideias" | "engenheiro";

type AgentJobStatus =
  | "queued"
  | "running"
  | "awaiting_approval"
  | "completed"
  | "failed"
  | "cancelled"
  | "killed"
  | "offline";

type KBReviewStatus = "pending_review" | "indexed" | "discarded";

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
  kb_status?: KBReviewStatus;
  kb_file?: string;
  kb_chunks?: number;
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
    state: "online" | "native" | "offline" | "standby";
    engine_mode?: "hermes_wsl2" | "native_fryivs" | "offline";
    native_fallback_enabled?: boolean;
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
    mission: "Pesquisas aprofundadas na web, artigos, benchmarks e dossiês prontos para indexar na IA.",
    tools: ["pesquisar_informacao_web", "consultar_mapa_codigo"],
    sandbox: "Restrito (somente leitura + curadoria KB)",
    model_alias: "hermes/pesquisador",
    default_max_steps: 15,
  },
  {
    name: "organizador",
    label: "Organizador de Dados",
    mission: "Estruturação, limpeza e catalogação de planilhas Excel/CSV, documentos Word e pastas de dados.",
    tools: ["gerenciar_arquivos", "consultar_planilha", "criar_planilha", "ler_documento_word"],
    sandbox: "Workspace de dados e documentos locais",
    model_alias: "hermes/organizador",
    default_max_steps: 15,
  },
  {
    name: "ideias",
    label: "Agente de Ideias",
    mission: "Geração de novas skills, automações, fluxos cognitivos e propostas de evolução para a F.R.Y.I.Vs.",
    tools: ["resumo_arquitetura_sistema", "consultar_mapa_codigo", "pesquisar_informacao_web"],
    sandbox: "Somente leitura arquitetural + pesquisa criativa",
    model_alias: "hermes/ideias",
    default_max_steps: 12,
  },
  {
    name: "engenheiro",
    label: "Engenheiro",
    mission: "Auditoria técnica de código, grafo arquitetural (Graphify), diagnóstico de módulos e performance.",
    tools: ["consultar_mapa_codigo", "explicar_modulo_grafo", "caminho_entre_componentes"],
    sandbox: "Inspeção técnica e grafo de código",
    model_alias: "hermes/engenheiro",
    default_max_steps: 15,
  },
];

const PROFILE_SUGGESTIONS: Record<HermesProfileName, string[]> = {
  pesquisador: [
    "Pesquise boas práticas de RAG híbrido em 2026",
    "Pesquise novidades do ecossistema Python 3.13",
    "Pesquise arquiteturas de agentes autônomos seguros",
  ],
  organizador: [
    "Liste e categorize os arquivos de dados do projeto",
    "Estruture um modelo de planilha financeira mensal",
    "Catalogue documentos disponíveis para organização",
  ],
  ideias: [
    "Proponha 5 novas skills de alto impacto para a F.R.Y.I.Vs",
    "Sugira automações com n8n para produtividade diária",
    "Ideias para evoluir a memória e proatividade da IA",
  ],
  engenheiro: [
    "Audite os módulos centrais e conexões da arquitetura",
    "Explique o fluxo entre servidor, pipeline e memória",
    "Identifique gargalos técnicos no mapa de código",
  ],
};

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
  selectedBorder: string;
  accentText: string;
  icon: typeof Search;
} {
  switch (profile) {
    case "pesquisador":
      return {
        badgeClass: "bg-cyan-500/15 border-cyan-400/35 text-cyan-200",
        selectedBorder: "border-cyan-400/60 bg-cyan-500/12 shadow-[0_0_20px_rgba(34,211,238,0.16)]",
        accentText: "text-cyan-300",
        icon: Search,
      };
    case "organizador":
      return {
        badgeClass: "bg-emerald-500/15 border-emerald-400/35 text-emerald-200",
        selectedBorder: "border-emerald-400/60 bg-emerald-500/12 shadow-[0_0_20px_rgba(16,185,129,0.16)]",
        accentText: "text-emerald-300",
        icon: FolderKanban,
      };
    case "ideias":
      return {
        badgeClass: "bg-amber-500/15 border-amber-400/35 text-amber-200",
        selectedBorder: "border-amber-400/60 bg-amber-500/12 shadow-[0_0_20px_rgba(245,158,11,0.16)]",
        accentText: "text-amber-300",
        icon: Lightbulb,
      };
    case "engenheiro":
      return {
        badgeClass: "bg-blue-500/15 border-blue-400/35 text-blue-200",
        selectedBorder: "border-blue-400/60 bg-blue-500/12 shadow-[0_0_20px_rgba(59,130,246,0.16)]",
        accentText: "text-blue-300",
        icon: Code2,
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
  onKnowledgeIndexed,
  onJobsBadgeChange,
}) => {
  const [statusData, setStatusData] = useState<AgentsStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bannerMsg, setBannerMsg] = useState<string | null>(null);

  const [selectedProfile, setSelectedProfile] = useState<HermesProfileName>("pesquisador");
  const [taskInput, setTaskInput] = useState("");
  const [contextTainted, setContextTainted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [killingAll, setKillingAll] = useState(false);
  const [busyJobIds, setBusyJobIds] = useState<Record<string, boolean>>({});
  const [indexingJobIds, setIndexingJobIds] = useState<Record<string, boolean>>({});
  const [discardingJobIds, setDiscardingJobIds] = useState<Record<string, boolean>>({});
  const [expandedJobIds, setExpandedJobIds] = useState<Record<string, boolean>>({});
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
            setError("Sessão E2EE bloqueada. Desbloqueie o cofre para gerenciar agentes.");
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
          const actionableCount = (data.jobs || []).filter(
            (j) =>
              j.status === "running" ||
              j.status === "queued" ||
              (j.status === "completed" && j.kb_status !== "indexed"),
          ).length;
          onJobsBadgeChange?.(actionableCount);
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
    [sessionToken, onJobsBadgeChange],
  );

  useEffect(() => {
    if (!isOpen) return;
    void fetchStatus(false);
    const interval = window.setInterval(() => {
      void fetchStatus(false);
    }, 3000);
    return () => window.clearInterval(interval);
  }, [isOpen, fetchStatus]);

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
          ? "Contexto externo detectado: aguardando sua aprovação explícita Tier 3."
          : `Missão enviada ao agente '${selectedProfile}'. Ao concluir, você poderá Indexar na Base de Conhecimento ou Descartar.`,
      );
      await fetchStatus(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao delegar missão.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleIndexJobToKB = async (job: AgentJobItem) => {
    setIndexingJobIds((prev) => ({ ...prev, [job.job_id]: true }));
    setError(null);
    setBannerMsg(null);
    try {
      const res = await fetch(`/api/agents/jobs/${encodeURIComponent(job.job_id)}/index-kb`, {
        method: "POST",
        headers: buildAuthHeaders(sessionToken, { "Content-Type": "application/json" }),
        body: JSON.stringify({ titulo: job.task.slice(0, 110) }),
      });
      const body = (await res.json().catch(() => ({}))) as {
        detail?: string;
        kb_info?: { chunks_indexados?: number; total_chunks_base?: number; arquivo?: string };
      };
      if (!res.ok) {
        throw new Error(body.detail || `Falha ao indexar na Base de Conhecimento (HTTP ${res.status}).`);
      }
      const chunks = body.kb_info?.chunks_indexados ?? 1;
      const total = body.kb_info?.total_chunks_base;
      if (typeof total === "number") {
        onKnowledgeIndexed?.(total);
      }
      setBannerMsg(
        `Conhecimento indexado com sucesso na F.R.Y.I.Vs (${chunks} chunk(s) adicionados ao ChromaDB + BM25)!`,
      );
      await fetchStatus(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao indexar na Base de Conhecimento.");
    } finally {
      setIndexingJobIds((prev) => ({ ...prev, [job.job_id]: false }));
    }
  };

  const handleDiscardJob = async (jobId: string) => {
    setDiscardingJobIds((prev) => ({ ...prev, [jobId]: true }));
    setError(null);
    setBannerMsg(null);
    try {
      const res = await fetch(`/api/agents/jobs/${encodeURIComponent(jobId)}/discard`, {
        method: "POST",
        headers: buildAuthHeaders(sessionToken),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail || `Erro ao descartar resultado (HTTP ${res.status}).`);
      }
      setStatusData((prev) =>
        prev
          ? {
              ...prev,
              jobs: prev.jobs.filter((j) => j.job_id !== jobId),
            }
          : prev,
      );
      setBannerMsg("Resultado descartado e removido da fila sem alterar a Base de Conhecimento.");
      await fetchStatus(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao descartar missão.");
    } finally {
      setDiscardingJobIds((prev) => ({ ...prev, [jobId]: false }));
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
      setBannerMsg(`Missão #${jobId.slice(0, 8)} cancelada.`);
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

  const hermesState = statusData?.hermes.state ?? "native";
  const usdPct = Math.min(100, Math.max(0, budget.usd_utilization_pct));
  const suggestions = PROFILE_SUGGESTIONS[selectedProfile] ?? [];

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-[#02060f]/80 backdrop-blur-xl"
      role="dialog"
      aria-modal="true"
      aria-labelledby="agents-control-panel-title"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-2xl h-full flex flex-col border-l border-cyan-400/25 bg-[#050b18]/96 text-slate-200 shadow-[0_0_90px_rgba(6,182,212,0.18)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Compacto */}
        <div className="flex items-center justify-between gap-3 px-6 py-4 border-b border-white/10 bg-[#060f22]/92">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/15 border border-cyan-400/35 flex items-center justify-center shrink-0">
              <Bot className="w-5 h-5 text-cyan-300" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2
                  id="agents-control-panel-title"
                  className="text-sm font-bold tracking-[0.16em] uppercase text-white truncate"
                >
                  Esquadrão de Agentes
                </h2>
                <span
                  className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider border ${
                    hermesState === "online" || hermesState === "native"
                      ? "bg-emerald-500/15 border-emerald-400/40 text-emerald-300"
                      : hermesState === "offline"
                        ? "bg-red-500/15 border-red-400/35 text-red-300"
                        : "bg-cyan-500/12 border-cyan-400/30 text-cyan-300"
                  }`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      hermesState === "online" || hermesState === "native"
                        ? "bg-emerald-400 animate-pulse"
                        : hermesState === "offline"
                          ? "bg-red-400"
                          : "bg-cyan-400"
                    }`}
                  />
                  {hermesState === "online"
                    ? "Hermes WSL2 Online"
                    : hermesState === "native"
                      ? "Motor Nativo Ativo"
                      : hermesState === "offline"
                        ? "Offline"
                        : "Standby"}
                </span>
              </div>
              <p className="text-[11px] font-mono text-slate-400 truncate mt-0.5">
                Pesquisador · Organizador de Dados · Agente de Ideias · Engenheiro
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => void fetchStatus(true)}
              disabled={loading}
              title="Atualizar status dos agentes"
              className="p-2 rounded-xl border border-white/10 bg-white/5 hover:border-cyan-400/40 hover:text-cyan-300 text-slate-400 transition-all cursor-pointer disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-cyan-300" : ""}`} />
            </button>

            <button
              type="button"
              onClick={() => void handleKillAll()}
              disabled={killingAll}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-red-500/18 hover:bg-red-500/28 border border-red-400/45 text-red-200 hover:text-white text-[11px] font-bold uppercase tracking-wider transition-all cursor-pointer disabled:opacity-50"
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
              aria-label="Fechar painel de agentes"
              className="p-2 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-all cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Barra Compacta de Governança (Budget + Segurança em 1 linha) */}
        <div className="px-6 py-2.5 border-b border-white/8 bg-[#040916] flex items-center justify-between gap-3 flex-wrap text-[10px] font-mono">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 text-slate-300">
              <Gauge className="w-3.5 h-3.5 text-cyan-400" />
              US$ {budget.daily_usd_used.toFixed(4)} / {budget.max_usd_per_day.toFixed(2)} ({usdPct.toFixed(0)}%)
            </span>
            <span className="inline-flex items-center gap-1 text-cyan-300">
              <Cpu className="w-3 h-3" />
              Ativos: {budget.active_concurrent}/{budget.max_concurrent_agents}
            </span>
          </div>
          <span className="inline-flex items-center gap-1 text-emerald-300/90">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            {pendingApprovals.length === 0
              ? "Tier 3 Limpo · Curadoria Humana Ativa"
              : `${pendingApprovals.length} Aprovação(ões) Tier 3 Pendente(s)`}
          </span>
        </div>

        {/* Corpo Rolável */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {error && (
            <div className="rounded-xl bg-red-500/12 border border-red-400/35 px-4 py-3 text-xs text-red-200 flex items-start gap-2.5">
              <ShieldAlert className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {bannerMsg && (
            <div className="rounded-xl bg-emerald-500/12 border border-emerald-400/35 px-4 py-3 text-xs text-emerald-100 flex items-start gap-2.5">
              <Sparkles className="w-4 h-4 text-emerald-300 shrink-0 mt-0.5" />
              <span>{bannerMsg}</span>
            </div>
          )}

          {/* Aprovações Tier 3 — Só expande quando realmente houver pendência! */}
          {pendingApprovals.length > 0 && (
            <section className="rounded-2xl border border-amber-400/40 bg-amber-500/[0.06] p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4 text-amber-300" />
                  <h3 className="text-[11px] font-mono uppercase tracking-[0.18em] text-amber-200 font-semibold">
                    Aprovações Tier 3 Pendentes ({pendingApprovals.length})
                  </h3>
                </div>
              </div>

              <div className="space-y-2.5">
                {pendingApprovals.map((item) => {
                  const busy = Boolean(busyApprovalIds[item.approval_id]);
                  return (
                    <div
                      key={item.approval_id}
                      className="rounded-xl border border-amber-400/35 bg-[#071022]/95 p-3.5 space-y-2.5"
                    >
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-bold font-mono text-white">{item.tool}</span>
                        <span className="px-2 py-0.5 rounded-full text-[9px] font-mono uppercase bg-red-500/20 border border-red-400/40 text-red-200">
                          Tier {item.tier}
                        </span>
                        {item.context_tainted && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-mono uppercase bg-amber-500/25 border border-amber-400/50 text-amber-200">
                            <AlertTriangle className="w-2.5 h-2.5" />
                            Contexto Externo
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-300 leading-relaxed">{item.reason}</p>
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
            </section>
          )}

          {/* 1. Seleção dos 4 Agentes + Delegação Imediata */}
          <section className="rounded-2xl border border-white/10 bg-white/[0.025] p-4 space-y-3.5">
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
                        ? meta.selectedBorder
                        : "border-white/10 bg-black/35 hover:border-white/25 hover:bg-white/[0.04]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="inline-flex items-center gap-1.5 text-xs font-bold text-white">
                        <Icon className={`w-3.5 h-3.5 ${meta.accentText}`} />
                        {prof.label}
                      </span>
                      <span className="text-[9px] font-mono text-slate-400">
                        ≤ {prof.default_max_steps} passos
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-300/90 leading-snug line-clamp-2">
                      {prof.mission}
                    </p>
                  </button>
                );
              })}
            </div>

            {/* Sugestões rápidas contextualizadas por agente */}
            <div className="flex flex-wrap gap-1.5 pt-0.5">
              {suggestions.map((sug, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => setTaskInput(sug)}
                  className="px-2.5 py-1 rounded-lg bg-white/[0.04] hover:bg-cyan-500/12 border border-white/8 hover:border-cyan-400/35 text-[10.5px] text-slate-300 hover:text-cyan-200 transition-colors cursor-pointer"
                >
                  {sug}
                </button>
              ))}
            </div>

            <form onSubmit={handleDelegate} className="space-y-2.5 pt-1">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={taskInput}
                  onChange={(e) => setTaskInput(e.target.value)}
                  placeholder={`Descreva a missão para '${
                    profiles.find((p) => p.name === selectedProfile)?.label ?? selectedProfile
                  }'...`}
                  disabled={submitting}
                  className="flex-1 rounded-xl bg-black/65 border border-white/12 focus:border-cyan-400/60 px-3.5 py-2.5 text-xs text-white placeholder-slate-500 outline-none transition-all"
                />
                <button
                  type="submit"
                  disabled={!taskInput.trim() || submitting}
                  className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold text-[11px] uppercase tracking-wider transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
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
                  Contexto externo não confiável (exige confirmação humana Tier 3 antes de executar)
                </span>
              </label>
            </form>
          </section>

          {/* 2. Resultados & Curadoria para a Base de Conhecimento */}
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-cyan-300" />
                <h3 className="text-[11px] font-mono uppercase tracking-[0.18em] text-cyan-200 font-semibold">
                  Missões & Curadoria ({jobs.length})
                </h3>
              </div>
              <span className="text-[10px] font-mono text-slate-500">Tempo real · 3s</span>
            </div>

            {jobs.length === 0 ? (
              <div className="rounded-2xl border border-white/8 bg-white/[0.02] px-4 py-7 text-center text-xs text-slate-400">
                Nenhuma missão na fila. Escolha um dos 4 agentes acima para pesquisar, organizar
                dados, gerar ideias para a F.R.Y.I.Vs ou auditar a engenharia.
              </div>
            ) : (
              <div className="space-y-3">
                {jobs.map((job) => {
                  const profileMeta = getProfileMeta(job.profile);
                  const ProfileIcon = profileMeta.icon;
                  const statusBadge = getStatusBadge(job.status);
                  const isActive =
                    job.status === "queued" ||
                    job.status === "running" ||
                    job.status === "awaiting_approval";
                  const cancelling = Boolean(busyJobIds[job.job_id]);
                  const indexing = Boolean(indexingJobIds[job.job_id]);
                  const discarding = Boolean(discardingJobIds[job.job_id]);
                  const isExpanded = Boolean(expandedJobIds[job.job_id]);
                  const isIndexed = job.kb_status === "indexed";

                  return (
                    <div
                      key={job.job_id}
                      className={`rounded-2xl border p-4 space-y-3 transition-colors ${
                        isIndexed
                          ? "border-emerald-400/35 bg-[#061522]/90"
                          : "border-white/10 bg-[#071022]/88 hover:border-cyan-400/25"
                      }`}
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
                          {job.transport === "native_fryivs" && (
                            <span className="px-2 py-0.5 rounded-full text-[9px] font-mono uppercase bg-cyan-500/12 border border-cyan-400/30 text-cyan-300">
                              Motor Nativo
                            </span>
                          )}
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

                      <p className="text-xs font-medium text-white leading-relaxed">{job.task}</p>

                      {/* Barra de progresso */}
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
                                  : "bg-cyan-400"
                            }`}
                            style={{ width: `${Math.min(100, Math.max(0, job.progress_pct))}%` }}
                          />
                        </div>
                      </div>

                      {/* Relatório formatado + Ações de Curadoria (Indexar ou Descartar) */}
                      {job.result && (
                        <div className="space-y-2.5">
                          <div
                            className={`rounded-xl bg-[#040a16] border border-white/10 px-3.5 py-3 text-xs text-slate-200 overflow-y-auto transition-all ${
                              isExpanded ? "max-h-[420px]" : "max-h-52"
                            }`}
                          >
                            <FormattedText content={job.result} compact />
                          </div>

                          <div className="flex items-center justify-between gap-2 flex-wrap pt-0.5">
                            {job.result.length > 360 ? (
                              <button
                                type="button"
                                onClick={() =>
                                  setExpandedJobIds((prev) => ({
                                    ...prev,
                                    [job.job_id]: !isExpanded,
                                  }))
                                }
                                className="inline-flex items-center gap-1 text-[11px] font-mono text-cyan-300 hover:text-cyan-200 cursor-pointer"
                              >
                                {isExpanded ? (
                                  <>
                                    <ChevronUp className="w-3.5 h-3.5" /> Recolher leitura
                                  </>
                                ) : (
                                  <>
                                    <ChevronDown className="w-3.5 h-3.5" /> Expandir relatório completo
                                  </>
                                )}
                              </button>
                            ) : (
                              <span />
                            )}

                            {job.status === "completed" && (
                              <div className="flex items-center gap-2 ml-auto">
                                {isIndexed ? (
                                  <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-500/18 border border-emerald-400/45 text-emerald-200 text-[11px] font-semibold">
                                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                                    Indexado na Base ({job.kb_chunks || 1} chunks)
                                  </span>
                                ) : (
                                  <button
                                    type="button"
                                    disabled={indexing || discarding}
                                    onClick={() => void handleIndexJobToKB(job)}
                                    className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-emerald-500/22 hover:bg-emerald-500/32 border border-emerald-400/50 text-emerald-100 text-[11px] font-semibold transition-all cursor-pointer disabled:opacity-50"
                                  >
                                    {indexing ? (
                                      <Loader2 className="w-3.5 h-3.5 animate-spin text-emerald-300" />
                                    ) : (
                                      <BookPlus className="w-3.5 h-3.5 text-emerald-300" />
                                    )}
                                    Indexar na Base de Conhecimento
                                  </button>
                                )}

                                <button
                                  type="button"
                                  disabled={indexing || discarding}
                                  onClick={() => void handleDiscardJob(job.job_id)}
                                  title={
                                    isIndexed
                                      ? "Limpar este card da visualização (mantém o documento já indexado)"
                                      : "Descartar resultado sem salvar na Base de Conhecimento"
                                  }
                                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-red-500/18 border border-white/12 hover:border-red-400/40 text-slate-300 hover:text-red-200 text-[11px] font-medium transition-all cursor-pointer disabled:opacity-50"
                                >
                                  {discarding ? (
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                  ) : (
                                    <Trash2 className="w-3.5 h-3.5" />
                                  )}
                                  Descartar
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {job.error && (
                        <div className="flex items-center justify-between gap-2 rounded-xl bg-red-500/10 border border-red-400/25 px-3 py-2 text-[11px] text-red-200/95">
                          <span>{job.error}</span>
                          {!isActive && (
                            <button
                              type="button"
                              disabled={discarding}
                              onClick={() => void handleDiscardJob(job.job_id)}
                              className="shrink-0 inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white/5 hover:bg-red-500/20 border border-white/10 text-[10px] text-slate-200 cursor-pointer"
                            >
                              <Trash2 className="w-3 h-3" />
                              Descartar
                            </button>
                          )}
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
