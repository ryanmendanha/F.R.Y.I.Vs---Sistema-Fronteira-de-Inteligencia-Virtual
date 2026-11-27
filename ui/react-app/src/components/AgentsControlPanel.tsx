import { useCallback, useEffect, useRef, useState } from "react";
import type { FC, FormEvent } from "react";
import { Icons8Icon, type Icons8Name } from "@/components/Icons8Icon";
import { FormattedText } from "@/components/FormattedText";
import { AgentsOffice3D, type OfficeExternalCommand } from "@/components/AgentsOffice3D";

export interface AgentsControlPanelProps {
  sessionToken: string | null;
  isOpen: boolean;
  onClose: () => void;
  onKnowledgeIndexed?: (totalChunks: number) => void;
  onJobsBadgeChange?: (count: number) => void;
  officeCommand?: (OfficeExternalCommand & { view_mode?: "office3d" | "list" | null }) | null;
  agentEventSeq?: number;
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
  reason: string;
  context_tainted: boolean;
}

interface BudgetSnapshot {
  daily_tokens_used: number;
  daily_usd_used: number;
  max_usd_per_day: number;
  usd_utilization_pct: number;
  active_concurrent: number;
  max_concurrent_agents: number;
}

interface AgentsStatusResponse {
  hermes: {
    state: "online" | "native" | "offline" | "standby";
    profiles: HermesProfileInfo[];
  };
  budget: BudgetSnapshot;
  jobs: AgentJobItem[];
  pending_approvals: PendingApprovalItem[];
}

const DEFAULT_PROFILES: HermesProfileInfo[] = [
  {
    name: "pesquisador",
    label: "Pesquisador",
    mission: "",
    tools: [],
    sandbox: "",
    model_alias: "hermes/pesquisador",
    default_max_steps: 15,
  },
  {
    name: "organizador",
    label: "Organizador",
    mission: "",
    tools: [],
    sandbox: "",
    model_alias: "hermes/organizador",
    default_max_steps: 15,
  },
  {
    name: "ideias",
    label: "Ideias",
    mission: "",
    tools: [],
    sandbox: "",
    model_alias: "hermes/ideias",
    default_max_steps: 12,
  },
  {
    name: "engenheiro",
    label: "Engenheiro",
    mission: "",
    tools: [],
    sandbox: "",
    model_alias: "hermes/engenheiro",
    default_max_steps: 15,
  },
];

const SHORT_LABELS: Record<HermesProfileName, string> = {
  pesquisador: "Pesquisador",
  organizador: "Organizador",
  ideias: "Ideias",
  engenheiro: "Engenheiro",
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

function getProfileMeta(profile: HermesProfileName): {
  badgeClass: string;
  selectedBorder: string;
  accentText: string;
  icon: Icons8Name;
} {
  switch (profile) {
    case "pesquisador":
      return {
        badgeClass: "bg-blue-500/18 border-blue-400/40 text-blue-200",
        selectedBorder: "border-blue-400/65 bg-blue-500/16",
        accentText: "text-blue-300",
        icon: "search",
      };
    case "organizador":
      return {
        badgeClass: "bg-emerald-500/18 border-emerald-400/40 text-emerald-200",
        selectedBorder: "border-emerald-400/65 bg-emerald-500/16",
        accentText: "text-emerald-300",
        icon: "folder-kanban",
      };
    case "ideias":
      return {
        badgeClass: "bg-purple-500/18 border-purple-400/40 text-purple-200",
        selectedBorder: "border-purple-400/65 bg-purple-500/16",
        accentText: "text-purple-300",
        icon: "lightbulb",
      };
    case "engenheiro":
      return {
        badgeClass: "bg-cyan-500/18 border-cyan-400/40 text-cyan-200",
        selectedBorder: "border-cyan-400/65 bg-cyan-500/16",
        accentText: "text-cyan-300",
        icon: "code",
      };
  }
}

function getStatusBadge(status: AgentJobStatus): { label: string; className: string } {
  switch (status) {
    case "running":
      return { label: "Executando", className: "bg-cyan-500/20 border-cyan-400/45 text-cyan-200" };
    case "queued":
      return { label: "Fila", className: "bg-blue-500/20 border-blue-400/40 text-blue-200" };
    case "awaiting_approval":
      return { label: "Tier 3", className: "bg-amber-500/20 border-amber-400/50 text-amber-200" };
    case "completed":
      return { label: "Pronto", className: "bg-emerald-500/20 border-emerald-400/40 text-emerald-200" };
    case "offline":
      return { label: "Offline", className: "bg-slate-500/20 border-slate-400/40 text-slate-300" };
    case "cancelled":
      return { label: "Cancelado", className: "bg-slate-600/25 border-slate-500/40 text-slate-300" };
    case "killed":
      return { label: "Parado", className: "bg-red-500/25 border-red-400/50 text-red-200" };
    case "failed":
      return { label: "Erro", className: "bg-red-500/20 border-red-400/45 text-red-200" };
  }
}

export const AgentsControlPanel: FC<AgentsControlPanelProps> = ({
  sessionToken,
  isOpen,
  onClose,
  onKnowledgeIndexed,
  onJobsBadgeChange,
  officeCommand,
  agentEventSeq,
}) => {
  const [viewMode, setViewMode] = useState<"office3d" | "list">("office3d");
  const [officeSidebarOpen, setOfficeSidebarOpen] = useState(true);
  const [celebrationSignal, setCelebrationSignal] = useState(0);

  const [statusData, setStatusData] = useState<AgentsStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
          if (mountedRef.current) setError("Sessão E2EE bloqueada.");
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

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
          setError(err instanceof Error ? err.message : "Erro de conexão.");
        }
      } finally {
        if (mountedRef.current) setLoading(false);
      }
    },
    [sessionToken, onJobsBadgeChange],
  );

  useEffect(() => {
    if (!isOpen) return;
    void fetchStatus(false);
    const interval = window.setInterval(() => {
      void fetchStatus(false);
    }, 2800);
    return () => window.clearInterval(interval);
  }, [isOpen, fetchStatus]);

  useEffect(() => {
    if (isOpen && agentEventSeq) {
      void fetchStatus(false);
    }
  }, [isOpen, agentEventSeq, fetchStatus]);

  useEffect(() => {
    if (!officeCommand) return;
    if (officeCommand.view_mode === "list" || officeCommand.view_mode === "office3d") {
      setViewMode(officeCommand.view_mode);
    }
    if (officeCommand.profile) {
      setSelectedProfile(officeCommand.profile);
    }
  }, [officeCommand]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  const handleSelectAgent = (prof: HermesProfileName) => {
    setSelectedProfile(prof);
    if (!officeSidebarOpen) setOfficeSidebarOpen(true);
  };

  const handleDelegate = async (e: FormEvent) => {
    e.preventDefault();
    const cleanTask = taskInput.trim();
    if (!cleanTask || submitting) return;

    setSubmitting(true);
    setError(null);
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
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);

      setTaskInput("");
      setContextTainted(false);
      await fetchStatus(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao enviar.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleIndexJobToKB = async (job: AgentJobItem) => {
    setIndexingJobIds((prev) => ({ ...prev, [job.job_id]: true }));
    setError(null);
    try {
      const res = await fetch(`/api/agents/jobs/${encodeURIComponent(job.job_id)}/index-kb`, {
        method: "POST",
        headers: buildAuthHeaders(sessionToken, { "Content-Type": "application/json" }),
        body: JSON.stringify({ titulo: job.task.slice(0, 110) }),
      });
      const body = (await res.json().catch(() => ({}))) as {
        detail?: string;
        kb_info?: { total_chunks_base?: number };
      };
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      if (typeof body.kb_info?.total_chunks_base === "number") {
        onKnowledgeIndexed?.(body.kb_info.total_chunks_base);
      }
      setCelebrationSignal((s) => s + 1);
      await fetchStatus(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao indexar.");
    } finally {
      setIndexingJobIds((prev) => ({ ...prev, [job.job_id]: false }));
    }
  };

  const handleDiscardJob = async (jobId: string) => {
    setDiscardingJobIds((prev) => ({ ...prev, [jobId]: true }));
    setError(null);
    try {
      const res = await fetch(`/api/agents/jobs/${encodeURIComponent(jobId)}/discard`, {
        method: "POST",
        headers: buildAuthHeaders(sessionToken),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setStatusData((prev) =>
        prev ? { ...prev, jobs: prev.jobs.filter((j) => j.job_id !== jobId) } : prev,
      );
      await fetchStatus(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao descartar.");
    } finally {
      setDiscardingJobIds((prev) => ({ ...prev, [jobId]: false }));
    }
  };

  const handleCancelJob = async (jobId: string) => {
    setBusyJobIds((prev) => ({ ...prev, [jobId]: true }));
    try {
      await fetch(`/api/agents/jobs/${encodeURIComponent(jobId)}/cancel`, {
        method: "POST",
        headers: buildAuthHeaders(sessionToken),
      });
      await fetchStatus(false);
    } finally {
      setBusyJobIds((prev) => ({ ...prev, [jobId]: false }));
    }
  };

  const handleKillAll = async () => {
    if (killingAll) return;
    setKillingAll(true);
    try {
      await fetch("/api/agents/kill-all", {
        method: "POST",
        headers: buildAuthHeaders(sessionToken),
      });
      await fetchStatus(false);
    } finally {
      setKillingAll(false);
    }
  };

  const handleApprovalDecision = async (approvalId: string, approved: boolean) => {
    setBusyApprovalIds((prev) => ({ ...prev, [approvalId]: true }));
    try {
      await fetch(`/api/agents/approvals/${encodeURIComponent(approvalId)}`, {
        method: "POST",
        headers: buildAuthHeaders(sessionToken, { "Content-Type": "application/json" }),
        body: JSON.stringify({ approved, decision: approved ? "approve" : "deny" }),
      });
      await fetchStatus(false);
    } finally {
      setBusyApprovalIds((prev) => ({ ...prev, [approvalId]: false }));
    }
  };

  if (!isOpen) return null;

  const profiles = statusData?.hermes.profiles ?? DEFAULT_PROFILES;
  const jobs = statusData?.jobs ?? [];
  const pendingApprovals = statusData?.pending_approvals ?? [];
  const budget = statusData?.budget ?? {
    daily_tokens_used: 0,
    daily_usd_used: 0,
    max_usd_per_day: 5,
    usd_utilization_pct: 0,
    active_concurrent: 0,
    max_concurrent_agents: 2,
  };

  const selectedIconName = getProfileMeta(selectedProfile).icon;

  const renderJobCard = (job: AgentJobItem) => {
    const profileMeta = getProfileMeta(job.profile);
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
        className={`rounded-xl border p-3 space-y-2 transition-colors ${
          isIndexed
            ? "border-emerald-400/35 bg-[#061522]/90"
            : "border-white/10 bg-[#071022]/92 hover:border-cyan-400/25"
        }`}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5">
            <span
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono uppercase border ${profileMeta.badgeClass}`}
            >
              <Icons8Icon name={profileMeta.icon} className="w-3 h-3" />
              {SHORT_LABELS[job.profile]}
            </span>
            <span
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono border ${statusBadge.className}`}
            >
              {job.status === "running" && <Icons8Icon name="loader" className="w-2.5 h-2.5 animate-spin" />}
              {job.status === "completed" && <Icons8Icon name="check-circle" className="w-2.5 h-2.5" />}
              {statusBadge.label}
            </span>
          </div>

          {isActive && (
            <button
              type="button"
              disabled={cancelling}
              onClick={() => void handleCancelJob(job.job_id)}
              title="Cancelar"
              className="p-1 rounded-lg bg-red-500/15 hover:bg-red-500/25 border border-red-400/35 text-red-200 cursor-pointer disabled:opacity-50"
            >
              {cancelling ? (
                <Icons8Icon name="loader" className="w-3 h-3 animate-spin" />
              ) : (
                <Icons8Icon name="cancel-circle" className="w-3 h-3" />
              )}
            </button>
          )}
        </div>

        <p className="text-xs font-medium text-white leading-snug">{job.task}</p>

        {isActive && (
          <div className="h-1 w-full rounded-full bg-black/60 overflow-hidden">
            <div
              className="h-full rounded-full bg-cyan-400 transition-all duration-500"
              style={{ width: `${Math.min(100, Math.max(12, job.progress_pct))}%` }}
            />
          </div>
        )}

        {job.result && (
          <div className="space-y-2">
            <div
              className={`rounded-lg bg-[#040a16] border border-white/8 px-3 py-2 text-xs text-slate-200 overflow-y-auto ${
                isExpanded ? "max-h-[380px]" : "max-h-44"
              }`}
            >
              <FormattedText content={job.result} compact />
            </div>

            <div className="flex items-center justify-between gap-1.5">
              {job.result.length > 280 ? (
                <button
                  type="button"
                  onClick={() =>
                    setExpandedJobIds((prev) => ({
                      ...prev,
                      [job.job_id]: !isExpanded,
                    }))
                  }
                  className="inline-flex items-center gap-1 text-[10.5px] font-mono text-cyan-300 hover:text-cyan-200 cursor-pointer"
                >
                  {isExpanded ? (
                    <>
                      <Icons8Icon name="chevron-up" className="w-3 h-3" /> Menos
                    </>
                  ) : (
                    <>
                      <Icons8Icon name="chevron-down" className="w-3 h-3" /> Expandir
                    </>
                  )}
                </button>
              ) : (
                <span />
              )}

              {job.status === "completed" && (
                <div className="flex items-center gap-1.5 ml-auto">
                  {isIndexed ? (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-500/18 border border-emerald-400/45 text-emerald-200 text-[10.5px] font-semibold">
                      <Icons8Icon name="check-circle" className="w-3 h-3 text-emerald-400" />
                      Indexado
                    </span>
                  ) : (
                    <button
                      type="button"
                      disabled={indexing || discarding}
                      onClick={() => void handleIndexJobToKB(job)}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-500/22 hover:bg-emerald-500/34 border border-emerald-400/50 text-emerald-100 text-[10.5px] font-semibold transition-all cursor-pointer disabled:opacity-50"
                    >
                      {indexing ? (
                        <Icons8Icon name="loader" className="w-3 h-3 animate-spin text-emerald-300" />
                      ) : (
                        <Icons8Icon name="book-add" className="w-3 h-3 text-emerald-300" />
                      )}
                      Indexar
                    </button>
                  )}

                  <button
                    type="button"
                    disabled={indexing || discarding}
                    onClick={() => void handleDiscardJob(job.job_id)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white/[0.04] hover:bg-red-500/18 border border-white/12 hover:border-red-400/40 text-slate-300 hover:text-red-200 text-[10.5px] transition-all cursor-pointer disabled:opacity-50"
                  >
                    {discarding ? (
                      <Icons8Icon name="loader" className="w-3 h-3 animate-spin" />
                    ) : (
                      <Icons8Icon name="trash" className="w-3 h-3" />
                    )}
                    Descartar
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {job.error && (
          <div className="flex items-center justify-between gap-2 rounded-lg bg-red-500/10 border border-red-400/25 px-2.5 py-1.5 text-[11px] text-red-200">
            <span className="truncate">{job.error}</span>
            {!isActive && (
              <button
                type="button"
                disabled={discarding}
                onClick={() => void handleDiscardJob(job.job_id)}
                className="p-1 rounded hover:bg-red-500/20 text-slate-200 cursor-pointer"
              >
                <Icons8Icon name="trash" className="w-3 h-3" />
              </button>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-[#030711]/96 text-slate-200 backdrop-blur-2xl"
      role="dialog"
      aria-modal="true"
      aria-labelledby="agents-control-panel-title"
    >
      {/* Top Bar Minimalista */}
      <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-white/10 bg-[#050c1d]/95 shrink-0">
        <div className="flex items-center gap-2.5">
          <Icons8Icon name="bot" className="w-4 h-4 text-cyan-300" />
          <h2
            id="agents-control-panel-title"
            className="text-xs font-bold tracking-[0.18em] uppercase text-white"
          >
            Agentes
          </h2>
          <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-white/5 border border-white/10 text-slate-300">
            {budget.active_concurrent}/{budget.max_concurrent_agents}
          </span>
        </div>

        {/* Abas curtas: 3D vs Fila */}
        <div className="flex items-center gap-1 p-0.5 rounded-xl bg-black/55 border border-white/10">
          <button
            type="button"
            onClick={() => setViewMode("office3d")}
            className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              viewMode === "office3d"
                ? "bg-cyan-400 text-slate-950"
                : "text-slate-300 hover:text-white"
            }`}
          >
            <Icons8Icon name="building" className="w-3.5 h-3.5" />
            3D
          </button>
          <button
            type="button"
            onClick={() => setViewMode("list")}
            className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              viewMode === "list"
                ? "bg-cyan-400 text-slate-950"
                : "text-slate-300 hover:text-white"
            }`}
          >
            <Icons8Icon name="layout-list" className="w-3.5 h-3.5" />
            Fila ({jobs.length})
          </button>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => void fetchStatus(true)}
            disabled={loading}
            title="Atualizar"
            className="p-2 rounded-xl border border-white/10 bg-white/5 hover:text-cyan-300 text-slate-400 cursor-pointer disabled:opacity-50"
          >
            <Icons8Icon name="refresh" className={`w-3.5 h-3.5 ${loading ? "animate-spin text-cyan-300" : ""}`} />
          </button>

          <button
            type="button"
            onClick={() => void handleKillAll()}
            disabled={killingAll}
            title="Parar todos os agentes"
            className="p-2 rounded-xl bg-red-500/18 hover:bg-red-500/28 border border-red-400/45 text-red-200 cursor-pointer disabled:opacity-50"
          >
            {killingAll ? (
              <Icons8Icon name="loader" className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Icons8Icon name="stop-all" className="w-3.5 h-3.5" />
            )}
          </button>

          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar"
            title="Fechar"
            className="p-2 rounded-xl border border-white/12 bg-white/6 hover:bg-white/12 text-slate-200 cursor-pointer"
          >
            <Icons8Icon name="close" className="w-4 h-4" />
          </button>
        </div>
      </div>

      {viewMode === "office3d" ? (
        <div className="flex-1 min-h-0 flex relative overflow-hidden">
          <div className="flex-1 min-w-0 relative flex flex-col">
            <AgentsOffice3D
              jobs={jobs}
              selectedProfile={selectedProfile}
              onSelectProfile={handleSelectAgent}
              celebrationSignal={celebrationSignal}
              externalCommand={officeCommand}
            />

            {!officeSidebarOpen && (
              <button
                type="button"
                onClick={() => setOfficeSidebarOpen(true)}
                className="absolute top-3 right-3 z-20 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#060d1d]/90 hover:bg-[#09152e] border border-cyan-400/40 text-cyan-200 text-xs font-semibold backdrop-blur-xl cursor-pointer"
              >
                <Icons8Icon name="panel-right" className="w-3.5 h-3.5" />
                {jobs.length > 0 ? `${jobs.length}` : ""}
              </button>
            )}

            {/* Dock Inferior de 1 Linha (Sem descrições longas) */}
            <div className="absolute bottom-3.5 inset-x-4 z-20 flex justify-center pointer-events-none">
              <div className="inline-flex items-center gap-1.5 p-1.5 rounded-2xl bg-[#050b18]/88 border border-white/12 backdrop-blur-2xl pointer-events-auto flex-wrap justify-center">
                {profiles.map((prof) => {
                  const meta = getProfileMeta(prof.name);
                  const isSelected = selectedProfile === prof.name;
                  const activeJob = jobs.some(
                    (j) =>
                      j.profile === prof.name &&
                      (j.status === "running" || j.status === "queued"),
                  );
                  const readyCount = jobs.filter(
                    (j) =>
                      j.profile === prof.name &&
                      j.status === "completed" &&
                      j.kb_status !== "indexed",
                  ).length;

                  return (
                    <button
                      key={prof.name}
                      type="button"
                      onClick={() => handleSelectAgent(prof.name)}
                      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all cursor-pointer ${
                        isSelected
                          ? `${meta.selectedBorder} text-white`
                          : "border-transparent text-slate-300 hover:bg-white/6 hover:text-white"
                      }`}
                    >
                      <Icons8Icon name={meta.icon} className={`w-3.5 h-3.5 ${meta.accentText}`} />
                      <span>{SHORT_LABELS[prof.name]}</span>
                      {activeJob ? (
                        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                      ) : readyCount > 0 ? (
                        <span className="min-w-[16px] h-4 px-1 rounded-full bg-emerald-400 text-slate-950 text-[9px] font-mono font-bold flex items-center justify-center">
                          {readyCount}
                        </span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Painel Lateral Enxuto */}
          {officeSidebarOpen && (
            <aside className="w-full sm:w-[360px] shrink-0 h-full border-l border-white/10 bg-[#050b18]/96 backdrop-blur-3xl flex flex-col z-20">
              <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/8 bg-[#061022]">
                <div className="flex items-center gap-2">
                  <Icons8Icon
                    name={selectedIconName}
                    className={`w-4 h-4 ${getProfileMeta(selectedProfile).accentText}`}
                  />
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                    {SHORT_LABELS[selectedProfile]}
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setOfficeSidebarOpen(false)}
                  title="Ocultar painel"
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/8 cursor-pointer"
                >
                  <Icons8Icon name="chevron-right" className="w-4 h-4" />
                </button>
              </div>

              <div className="p-3 border-b border-white/8">
                <form onSubmit={handleDelegate} className="flex items-center gap-1.5">
                  <input
                    type="text"
                    value={taskInput}
                    onChange={(e) => setTaskInput(e.target.value)}
                    placeholder={`Missão para ${SHORT_LABELS[selectedProfile]}...`}
                    disabled={submitting}
                    className="flex-1 rounded-xl bg-black/65 border border-white/12 focus:border-cyan-400/60 px-3 py-2 text-xs text-white placeholder-slate-500 outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setContextTainted((v) => !v)}
                    title={
                      contextTainted
                        ? "Contexto externo ativo (exigirá aprovação Tier 3)"
                        : "Marcar contexto externo"
                    }
                    className={`p-2 rounded-xl border transition-colors cursor-pointer ${
                      contextTainted
                        ? "bg-amber-500/22 border-amber-400/50 text-amber-200"
                        : "bg-white/[0.03] border-white/10 text-slate-500 hover:text-slate-300"
                    }`}
                  >
                    <Icons8Icon name="alert-triangle" className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="submit"
                    disabled={!taskInput.trim() || submitting}
                    className="p-2 rounded-xl bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold transition-all cursor-pointer disabled:opacity-40"
                    title="Enviar missão"
                  >
                    {submitting ? (
                      <Icons8Icon name="loader" className="w-4 h-4 animate-spin" />
                    ) : (
                      <Icons8Icon name="send" className="w-4 h-4" />
                    )}
                  </button>
                </form>
              </div>

              <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
                {error && (
                  <div className="rounded-lg bg-red-500/12 border border-red-400/35 px-3 py-2 text-xs text-red-200 flex items-center gap-2">
                    <Icons8Icon name="shield-alert" className="w-3.5 h-3.5 text-red-400 shrink-0" />
                    <span>{error}</span>
                  </div>
                )}

                {pendingApprovals.map((item) => {
                  const busy = Boolean(busyApprovalIds[item.approval_id]);
                  return (
                    <div
                      key={item.approval_id}
                      className="rounded-xl border border-amber-400/40 bg-amber-500/10 p-3 space-y-2"
                    >
                      <p className="text-xs font-semibold text-amber-100">Tier 3 · {item.tool}</p>
                      <div className="flex justify-end gap-1.5">
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void handleApprovalDecision(item.approval_id, false)}
                          className="px-2.5 py-1 rounded-lg bg-red-500/20 border border-red-400/40 text-red-200 text-[11px] cursor-pointer"
                        >
                          Negar
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void handleApprovalDecision(item.approval_id, true)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-500/25 border border-emerald-400/45 text-emerald-100 text-[11px] font-semibold cursor-pointer"
                        >
                          {busy ? (
                            <Icons8Icon name="loader" className="w-3 h-3 animate-spin" />
                          ) : (
                            <Icons8Icon name="check" className="w-3 h-3" />
                          )}
                          Aprovar
                        </button>
                      </div>
                    </div>
                  );
                })}

                {jobs.length === 0 ? (
                  <p className="py-10 text-center text-xs text-slate-500 font-mono">Sem missões.</p>
                ) : (
                  jobs.map(renderJobCard)
                )}
              </div>
            </aside>
          )}
        </div>
      ) : (
        /* MODO LISTA MINIMALISTA */
        <div className="flex-1 overflow-y-auto px-5 py-5">
          <div className="max-w-3xl mx-auto space-y-3">
            <div className="flex items-center justify-between text-xs font-mono text-slate-400 px-1">
              <span>Missões ({jobs.length})</span>
              <span>
                US$ {budget.daily_usd_used.toFixed(4)} / {budget.max_usd_per_day.toFixed(2)}
              </span>
            </div>
            {jobs.length === 0 ? (
              <p className="py-12 text-center text-xs text-slate-500 font-mono">Sem missões.</p>
            ) : (
              jobs.map(renderJobCard)
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default AgentsControlPanel;
