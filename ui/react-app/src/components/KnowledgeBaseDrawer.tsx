import React, { useCallback, useEffect, useState } from "react";
import {
  BookOpen,
  CheckCircle2,
  Database,
  FileText,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { FormattedText } from "@/components/FormattedText";

export interface KnowledgeBaseDrawerProps {
  sessionToken: string | null;
  isOpen: boolean;
  onClose: () => void;
  onStatusUpdated?: (totalChunks: number) => void;
}

interface KBStatusInfo {
  indexed: boolean;
  count: number;
  arquivos_disponiveis?: number;
  hybrid_rrf?: boolean;
}

interface KBDocumentItem {
  arquivo: string;
  nome: string;
  categoria: string;
  habilidade: string;
  tags: string;
  agente: string;
  curado_por_agente: boolean;
  trust_level: string;
  tamanho_bytes: number;
  atualizado_em: number;
}

function buildHeaders(sessionToken: string | null): Record<string, string> {
  return sessionToken ? { "X-E2EE-Session": sessionToken } : {};
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

export const KnowledgeBaseDrawer: React.FC<KnowledgeBaseDrawerProps> = ({
  sessionToken,
  isOpen,
  onClose,
  onStatusUpdated,
}) => {
  const [kbStatus, setKbStatus] = useState<KBStatusInfo>({ indexed: false, count: 0 });
  const [documents, setDocuments] = useState<KBDocumentItem[]>([]);
  const [filterMode, setFilterMode] = useState<"all" | "curated">("all");
  const [loading, setLoading] = useState(false);
  const [reindexing, setReindexing] = useState(false);

  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResult, setSearchResult] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/knowledge/documents?limit=60", {
        headers: buildHeaders(sessionToken),
        cache: "no-store",
      });
      if (!res.ok) return;
      const data = (await res.json()) as {
        status?: KBStatusInfo;
        documents?: KBDocumentItem[];
      };
      if (data.status) {
        setKbStatus(data.status);
        onStatusUpdated?.(data.status.count || 0);
      }
      setDocuments(data.documents || []);
    } catch {
      // silencioso
    } finally {
      setLoading(false);
    }
  }, [sessionToken, onStatusUpdated]);

  useEffect(() => {
    if (!isOpen) return;
    void loadDocuments();
  }, [isOpen, loadDocuments]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (!q || searching) return;
    setSearching(true);
    setSearchResult(null);
    try {
      const res = await fetch(`/api/knowledge/search?q=${encodeURIComponent(q)}&k=3`, {
        headers: buildHeaders(sessionToken),
      });
      const data = (await res.json()) as { resultado?: string; encontrou?: boolean };
      setSearchResult(
        data.encontrou && data.resultado
          ? data.resultado
          : "Nenhum trecho relevante encontrado para esta consulta.",
      );
    } catch {
      setSearchResult("Não foi possível consultar a Base de Conhecimento.");
    } finally {
      setSearching(false);
    }
  };

  const handleReindex = async () => {
    if (reindexing) return;
    setReindexing(true);
    setFeedback(null);
    try {
      const res = await fetch("/api/knowledge/reindex", {
        method: "POST",
        headers: buildHeaders(sessionToken),
      });
      const data = (await res.json()) as { total_chunks?: number; novos_chunks?: number };
      if (res.ok) {
        setFeedback(
          `Base sincronizada: ${data.total_chunks ?? 0} chunks ativos (${data.novos_chunks ?? 0} atualizados).`,
        );
        await loadDocuments();
      }
    } finally {
      setReindexing(false);
    }
  };

  if (!isOpen) return null;

  const curatedCount = documents.filter((d) => d.curado_por_agente).length;
  const visibleDocs =
    filterMode === "curated" ? documents.filter((d) => d.curado_por_agente) : documents;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-[#02060f]/78 backdrop-blur-xl"
      role="dialog"
      aria-modal="true"
      aria-labelledby="kb-drawer-title"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-xl h-full flex flex-col border-l border-emerald-400/25 bg-[#050c18]/96 text-slate-200 shadow-[0_0_80px_rgba(16,185,129,0.16)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-3 px-6 py-4 border-b border-white/10 bg-[#061120]/90">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/15 border border-emerald-400/35 flex items-center justify-center shrink-0">
              <BookOpen className="w-5 h-5 text-emerald-300" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2
                  id="kb-drawer-title"
                  className="text-sm font-bold tracking-[0.16em] uppercase text-white truncate"
                >
                  Base de Conhecimento
                </h2>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-emerald-500/15 border border-emerald-400/35 text-emerald-300">
                  RAG Híbrido RRF
                </span>
              </div>
              <p className="text-[11px] font-mono text-slate-400 truncate mt-0.5">
                ChromaDB Vetorial + BM25 Léxico · Pesquisas Curadas dos Agentes
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => void handleReindex()}
              disabled={reindexing}
              title="Sincronizar e reindexar documentos"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-white/12 bg-white/5 hover:border-emerald-400/40 hover:text-emerald-200 text-[11px] font-mono text-slate-300 transition-all cursor-pointer disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${reindexing ? "animate-spin text-emerald-300" : ""}`} />
              Sincronizar
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Fechar Base de Conhecimento"
              className="p-2 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-all cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {feedback && (
            <div className="rounded-xl bg-emerald-500/12 border border-emerald-400/35 px-3.5 py-2.5 text-xs text-emerald-200 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>{feedback}</span>
            </div>
          )}

          {/* Métricas rápidas */}
          <div className="grid grid-cols-3 gap-2.5">
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
              <p className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                Chunks Ativos
              </p>
              <p className="text-lg font-bold font-mono text-emerald-300 mt-0.5 tabular-nums">
                {kbStatus.count.toLocaleString("pt-BR")}
              </p>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
              <p className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                Documentos
              </p>
              <p className="text-lg font-bold font-mono text-white mt-0.5 tabular-nums">
                {(kbStatus.arquivos_disponiveis ?? documents.length).toLocaleString("pt-BR")}
              </p>
            </div>
            <div className="rounded-xl border border-cyan-400/20 bg-cyan-500/[0.04] p-3">
              <p className="text-[10px] font-mono uppercase tracking-wider text-cyan-300">
                Curados IA
              </p>
              <p className="text-lg font-bold font-mono text-cyan-200 mt-0.5 tabular-nums">
                {curatedCount}
              </p>
            </div>
          </div>

          {/* Consulta rápida na Base de Conhecimento */}
          <section className="space-y-2.5">
            <form onSubmit={handleSearch} className="flex gap-2">
              <div className="relative flex-1">
                <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Consultar o que a F.R.Y.I.Vs sabe na Base de Conhecimento..."
                  className="w-full rounded-xl bg-black/55 border border-white/12 focus:border-emerald-400/55 pl-9 pr-3.5 py-2.5 text-xs text-white placeholder-slate-500 outline-none transition-all"
                />
              </div>
              <button
                type="submit"
                disabled={!query.trim() || searching}
                className="px-4 py-2.5 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-400/45 text-emerald-200 font-semibold text-xs transition-all cursor-pointer disabled:opacity-40"
              >
                {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : "Buscar"}
              </button>
            </form>

            {searchResult && (
              <div className="rounded-xl border border-emerald-400/25 bg-[#071526]/90 p-3.5 text-xs text-slate-200 max-h-60 overflow-y-auto">
                <FormattedText content={searchResult} compact />
              </div>
            )}
          </section>

          {/* Lista de Documentos */}
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Database className="w-3.5 h-3.5 text-emerald-300" />
                <h3 className="text-[11px] font-mono uppercase tracking-[0.18em] text-slate-300 font-semibold">
                  Acervo Indexado ({visibleDocs.length})
                </h3>
              </div>

              <div className="flex items-center gap-1 p-0.5 rounded-lg bg-black/50 border border-white/10 text-[10px] font-mono">
                <button
                  type="button"
                  onClick={() => setFilterMode("all")}
                  className={`px-2.5 py-1 rounded-md transition-colors cursor-pointer ${
                    filterMode === "all"
                      ? "bg-white/12 text-white font-semibold"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Todos ({documents.length})
                </button>
                <button
                  type="button"
                  onClick={() => setFilterMode("curated")}
                  className={`px-2.5 py-1 rounded-md transition-colors cursor-pointer ${
                    filterMode === "curated"
                      ? "bg-cyan-500/20 text-cyan-200 font-semibold"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Agentes ({curatedCount})
                </button>
              </div>
            </div>

            {loading ? (
              <div className="py-10 flex items-center justify-center text-slate-400 text-xs gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-emerald-400" />
                Carregando acervo...
              </div>
            ) : visibleDocs.length === 0 ? (
              <div className="rounded-xl border border-white/8 bg-white/[0.02] px-4 py-8 text-center text-xs text-slate-400">
                {filterMode === "curated"
                  ? "Nenhuma pesquisa de agente indexada ainda. Delegue uma pesquisa no painel Agentes e clique em 'Indexar na Base de Conhecimento'."
                  : "Nenhum documento encontrado na pasta base_conhecimento."}
              </div>
            ) : (
              <div className="space-y-2">
                {visibleDocs.map((doc) => (
                  <div
                    key={doc.arquivo}
                    className="rounded-xl border border-white/8 bg-[#071022]/80 px-3.5 py-2.5 flex items-start justify-between gap-3 hover:border-emerald-400/25 transition-colors"
                  >
                    <div className="min-w-0 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <FileText className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span className="text-xs font-semibold text-slate-100 truncate">
                          {doc.nome}
                        </span>
                        {doc.curado_por_agente && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-mono uppercase bg-cyan-500/15 border border-cyan-400/35 text-cyan-200">
                            <Sparkles className="w-2.5 h-2.5" />
                            {doc.agente || "Agente"}
                          </span>
                        )}
                      </div>
                      <p className="text-[10px] font-mono text-slate-500 truncate">{doc.arquivo}</p>
                    </div>

                    <div className="flex flex-col items-end gap-1 shrink-0">
                      <span className="text-[10px] font-mono text-slate-400 tabular-nums">
                        {formatBytes(doc.tamanho_bytes)}
                      </span>
                      <span className="inline-flex items-center gap-1 text-[9px] font-mono text-emerald-300/80">
                        <ShieldCheck className="w-2.5 h-2.5" />
                        {doc.trust_level === "verified_internal" ? "Interno" : "Sanitizado"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
};

export default KnowledgeBaseDrawer;

