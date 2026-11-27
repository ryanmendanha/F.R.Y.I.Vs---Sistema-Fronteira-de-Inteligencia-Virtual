import React, { useState } from "react";
import { Icons8Icon } from "@/components/Icons8Icon";

interface FormattedTextProps {
  content: string;
  className?: string;
  compact?: boolean;
}

function renderInline(text: string): React.ReactNode[] {
  const tokens = text.split(
    /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\((?:https?:\/\/|\/api\/files\/download\/)[^)\s]+\)|https?:\/\/[^\s<)]+)/g,
  );
  return tokens.map((tok, idx) => {
    if (!tok) return null;
    if (tok.startsWith("`") && tok.endsWith("`") && tok.length >= 2) {
      return (
        <code
          key={idx}
          className="px-1.5 py-0.5 rounded bg-cyan-950/70 border border-cyan-400/20 text-cyan-200 font-mono text-[0.92em]"
        >
          {tok.slice(1, -1)}
        </code>
      );
    }
    if (tok.startsWith("**") && tok.endsWith("**") && tok.length >= 4) {
      return (
        <strong key={idx} className="font-semibold text-white">
          {tok.slice(2, -2)}
        </strong>
      );
    }
    const mdDownload = /^\[([^\]]+)\]\((\/api\/files\/download\/[^)\s]+)\)$/.exec(tok);
    if (mdDownload) {
      let href = mdDownload[2];
      try {
        const e2eeTok = sessionStorage.getItem("fryivs_e2ee_session_token");
        if (e2eeTok) {
          href += `${href.includes("?") ? "&" : "?"}e2ee_token=${encodeURIComponent(e2eeTok)}`;
        }
      } catch {}
      return (
        <a
          key={idx}
          href={href}
          download
          className="inline-flex items-center gap-1.5 px-2.5 py-1 my-0.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-400/45 text-emerald-200 font-semibold text-[11.5px] no-underline transition-all"
        >
          <Icons8Icon name="file-text" className="w-3.5 h-3.5 text-emerald-300" />
          {mdDownload[1]}
        </a>
      );
    }
    const mdLink = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/.exec(tok);
    if (mdLink) {
      return (
        <a
          key={idx}
          href={mdLink[2]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-cyan-300 underline decoration-cyan-400/40 underline-offset-2 hover:text-cyan-200"
        >
          {mdLink[1]}
        </a>
      );
    }
    if (/^https?:\/\/[^\s<)]+$/.test(tok)) {
      return (
        <a
          key={idx}
          href={tok}
          target="_blank"
          rel="noopener noreferrer"
          className="text-cyan-300 underline decoration-cyan-400/40 underline-offset-2 hover:text-cyan-200 break-all"
        >
          {tok}
        </a>
      );
    }
    return <React.Fragment key={idx}>{tok}</React.Fragment>;
  });
}

function CodeFenceBlock({ lang, code }: { lang: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard?.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  };

  return (
    <div className="my-2 rounded-xl border border-white/10 bg-[#030711] overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 bg-white/[0.04] border-b border-white/8 text-[10px] font-mono text-slate-400">
        <span className="uppercase tracking-wider">{lang || "code"}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex items-center gap-1 text-slate-400 hover:text-cyan-300 transition-colors cursor-pointer"
        >
          {copied ? (
            <Icons8Icon name="check" className="w-3 h-3 text-emerald-400" />
          ) : (
            <Icons8Icon name="copy" className="w-3 h-3" />
          )}
          {copied ? "Copiado" : "Copiar"}
        </button>
      </div>
      <pre className="p-3 text-[11.5px] font-mono text-slate-200 overflow-x-auto leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  );
}

export const FormattedText: React.FC<FormattedTextProps> = ({
  content,
  className = "",
  compact = false,
}) => {
  if (!content) return null;

  const segments = content.split(/(```[\s\S]*?```)/g);

  return (
    <div className={`space-y-2 ${className}`}>
      {segments.map((seg, sIdx) => {
        if (seg.startsWith("```") && seg.endsWith("```")) {
          const inner = seg.slice(3, -3);
          const newlinePos = inner.indexOf("\n");
          const lang = newlinePos >= 0 ? inner.slice(0, newlinePos).trim() : "";
          const code = newlinePos >= 0 ? inner.slice(newlinePos + 1).replace(/\n$/, "") : inner;
          return <CodeFenceBlock key={sIdx} lang={lang} code={code} />;
        }

        const lines = seg.split(/\r?\n/);
        const nodes: React.ReactNode[] = [];
        let listItems: { ordered: boolean; text: string }[] = [];

        const flushList = (keySuffix: string) => {
          if (listItems.length === 0) return;
          const isOrdered = listItems[0].ordered;
          const Tag = isOrdered ? "ol" : "ul";
          nodes.push(
            <Tag
              key={`list-${sIdx}-${keySuffix}`}
              className={`space-y-1 pl-4 ${isOrdered ? "list-decimal" : "list-disc"} marker:text-cyan-400/80`}
            >
              {listItems.map((li, liIdx) => (
                <li key={liIdx} className="leading-relaxed">
                  {renderInline(li.text)}
                </li>
              ))}
            </Tag>,
          );
          listItems = [];
        };

        lines.forEach((rawLine, lIdx) => {
          const line = rawLine.trimEnd();
          const trimmed = line.trim();

          if (!trimmed) {
            flushList(String(lIdx));
            return;
          }

          if (/^---+$/.test(trimmed)) {
            flushList(String(lIdx));
            nodes.push(<hr key={`hr-${sIdx}-${lIdx}`} className="border-white/10 my-2" />);
            return;
          }

          const headingMatch = /^(#{1,4})\s+(.+)$/.exec(trimmed);
          if (headingMatch) {
            flushList(String(lIdx));
            const level = headingMatch[1].length;
            const text = headingMatch[2];
            const sizeCls =
              level === 1
                ? "text-sm font-bold text-white tracking-tight pt-1"
                : level === 2
                  ? "text-[13px] font-bold text-cyan-200 tracking-tight pt-1"
                  : "text-xs font-semibold text-slate-100 pt-0.5";
            nodes.push(
              <div key={`h-${sIdx}-${lIdx}`} className={sizeCls}>
                {renderInline(text)}
              </div>,
            );
            return;
          }

          const bulletMatch = /^[-*•]\s+(.+)$/.exec(trimmed);
          if (bulletMatch) {
            if (listItems.length > 0 && listItems[0].ordered) {
              flushList(String(lIdx));
            }
            listItems.push({ ordered: false, text: bulletMatch[1] });
            return;
          }

          const numMatch = /^\d+[.)]\s+(.+)$/.exec(trimmed);
          if (numMatch) {
            if (listItems.length > 0 && !listItems[0].ordered) {
              flushList(String(lIdx));
            }
            listItems.push({ ordered: true, text: numMatch[1] });
            return;
          }

          flushList(String(lIdx));
          nodes.push(
            <p
              key={`p-${sIdx}-${lIdx}`}
              className={compact ? "leading-snug" : "leading-relaxed"}
            >
              {renderInline(trimmed)}
            </p>,
          );
        });

        flushList("end");
        return <React.Fragment key={sIdx}>{nodes}</React.Fragment>;
      })}
    </div>
  );
};

export default FormattedText;

