"""
Loop Agêntico ReAct Controlado (Multi-Step + Execução Paralela + Auto-Correção) da F.R.Y.I.Vs.

Implementa `run_agent_loop(...)` com:
- Limite rígido de iterações (`max_steps=4`, configurável até o teto de `6`).
- Limite rígido de tempo de parede (`max_wall_time_s=60.0`).
- Execução paralela de múltiplas `tool_calls` independentes no mesmo turno via
  `ThreadPoolExecutor(max_workers=3)`, preservando a ordem original dos resultados.
- Auto-correção automática: quando uma ferramenta retorna erro, devolve a observação
  de erro ao LLM para 1 etapa de recuperação/retentativa controlada antes de falhar.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable, Final

DEFAULT_MAX_STEPS: Final[int] = 4
MAX_ALLOWED_STEPS: Final[int] = 6
DEFAULT_MAX_WALL_TIME_S: Final[float] = 60.0
DEFAULT_MAX_WORKERS: Final[int] = 3
DEFAULT_MAX_ERROR_RETRIES: Final[int] = 1

_ERROR_PREFIXES: Final[tuple[str, ...]] = (
    "erro",
    "error",
    "falha",
    "exception",
    "não foi possível",
    "nao foi possivel",
    "não encontrada",
    "nao encontrada",
)

_ERROR_SUBSTRINGS: Final[tuple[str, ...]] = (
    "não encontrada no registro",
    "nao encontrada no registro",
    "erro ao executar",
    "erro ao criar",
    "erro ao editar",
    "erro:",
    "error:",
    "falha ao criar",
    "falha ao editar",
    "falha ao executar",
    "permissão negada",
    "permissao negada",
    "permission denied",
    "arquivo não encontrado",
    "arquivo nao encontrado",
    "file not found",
    "parâmetro inválido",
    "parametro invalido",
    "traceback",
    "timeout",
)


@dataclass
class AgentLoopResult:
    """Resultado consolidado da execução controlada do loop ReAct."""

    response: str
    executed_tools: list[dict[str, Any]] = field(default_factory=list)
    steps_taken: int = 0
    retries_used: int = 0
    timed_out: bool = False
    stopped_reason: str = "completed"


def is_tool_error(result: Any) -> bool:
    """Identifica se o retorno textual de uma ferramenta representa erro/falha."""
    if result is None:
        return False
    text = str(result).strip().lower()
    if not text:
        return False
    if text.startswith(_ERROR_PREFIXES):
        return True
    return any(sub in text for sub in _ERROR_SUBSTRINGS)


def extract_tool_call(tool: Any) -> tuple[str, dict[str, Any]]:
    """
    Extrai `(nome, argumentos)` de um tool_call (formato dict OpenAI/Ollama/Gemini ou objeto).
    """
    if hasattr(tool, "function"):
        func = tool.function
        name = getattr(func, "name", "") or ""
        raw_args = getattr(func, "arguments", {}) or {}
    elif isinstance(tool, dict):
        if "function" in tool and isinstance(tool["function"], dict):
            func = tool["function"]
            name = func.get("name", "") or ""
            raw_args = func.get("arguments", {}) or {}
        else:
            name = tool.get("name", "") or ""
            raw_args = tool.get("arguments", tool.get("args", {})) or {}
    else:
        name, raw_args = "", {}

    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args)
        except (json.JSONDecodeError, ValueError):
            raw_args = {}

    return str(name), raw_args if isinstance(raw_args, dict) else {}


def _safe_execute_single(
    execute_tool_fn: Callable[[str, dict[str, Any]], Any],
    func_name: str,
    func_args: dict[str, Any],
) -> str:
    try:
        resultado = execute_tool_fn(func_name, func_args)
        return str(resultado) if resultado is not None else ""
    except Exception as exc:
        return f"Erro ao executar '{func_name}': {exc}"


def _execute_tools_batch(
    parsed_calls: list[tuple[str, dict[str, Any]]],
    execute_tool_fn: Callable[[str, dict[str, Any]], Any],
    *,
    max_workers: int,
    deadline: float,
) -> tuple[list[dict[str, Any]], bool]:
    """
    Executa um lote de tool_calls. Para 2+ chamadas independentes, dispara em paralelo
    via ThreadPoolExecutor(max_workers=3) preservando a ordem original.
    Retorna `(registros_executados, houve_timeout)`.
    """
    if not parsed_calls:
        return [], False

    if len(parsed_calls) == 1:
        func_name, func_args = parsed_calls[0]
        res_str = _safe_execute_single(execute_tool_fn, func_name, func_args)
        return [{
            "tool": func_name,
            "arguments": func_args,
            "result": res_str,
        }], False

    workers = max(1, min(int(max_workers), len(parsed_calls)))
    results: list[dict[str, Any]] = []
    timed_out = False

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            (func_name, func_args, executor.submit(_safe_execute_single, execute_tool_fn, func_name, func_args))
            for func_name, func_args in parsed_calls
        ]
        for func_name, func_args, fut in futures:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                fut.cancel()
                res_str = f"Erro: timeout ao executar ferramenta '{func_name}'."
            else:
                try:
                    res_str = fut.result(timeout=remaining)
                except FuturesTimeoutError:
                    timed_out = True
                    fut.cancel()
                    res_str = f"Erro: timeout ao executar ferramenta '{func_name}'."
                except Exception as exc:
                    res_str = f"Erro ao executar '{func_name}': {exc}"
            results.append({
                "tool": func_name,
                "arguments": func_args,
                "result": res_str,
            })

    return results, timed_out


def run_agent_loop(
    prompt: str,
    llm_step_fn: Callable[[list[dict[str, Any]], int, bool], tuple[str, list[dict[str, Any]]]],
    execute_tool_fn: Callable[[str, dict[str, Any]], Any],
    *,
    max_steps: int = DEFAULT_MAX_STEPS,
    max_wall_time_s: float = DEFAULT_MAX_WALL_TIME_S,
    max_error_retries: int = DEFAULT_MAX_ERROR_RETRIES,
    max_workers: int = DEFAULT_MAX_WORKERS,
    extract_tool_call_fn: Callable[[Any], tuple[str, dict[str, Any]]] | None = None,
    initial_messages: list[dict[str, Any]] | None = None,
    fast_template_fn: Callable[[list[dict[str, Any]], str], str | None] | None = None,
) -> AgentLoopResult:
    """
    Executa loop ReAct controlado (Plan -> Parallel Tool Execution -> Observe -> Self-Correct -> Answer).

    Parâmetros:
    - `prompt`: solicitação original do usuário.
    - `llm_step_fn(messages, step, allow_tools) -> (text, tool_calls)`: executa 1 turno do LLM.
    - `execute_tool_fn(tool_name, tool_args) -> Any`: executa uma ferramenta.
    - `max_steps`: máximo de iterações (padrão 4, teto rígido 6).
    - `max_wall_time_s`: tempo limite total em segundos (padrão 60s).
    - `max_error_retries`: quantas rodadas de auto-correção disparar em erro de tool (padrão 1).
    - `max_workers`: concorrência máxima de `ThreadPoolExecutor` para tools paralelas (padrão 3).
    - `initial_messages`: histórico inicial opcional a ser preservado nas chamadas ao LLM.
    - `fast_template_fn`: callback opcional de resposta rápida para System 1 quando todas as tools têm sucesso.
    """
    effective_max_steps = max(1, min(int(max_steps), MAX_ALLOWED_STEPS))
    effective_workers = max(1, min(int(max_workers), DEFAULT_MAX_WORKERS))
    effective_wall_time = max(0.05, float(max_wall_time_s))
    extractor = extract_tool_call_fn or extract_tool_call

    start_mono = time.monotonic()
    deadline = start_mono + effective_wall_time

    messages: list[dict[str, Any]] = (
        list(initial_messages)
        if initial_messages is not None
        else [{"role": "user", "content": prompt}]
    )

    executed_tools: list[dict[str, Any]] = []
    steps_taken = 0
    retries_used = 0
    timed_out = False
    stopped_reason = "completed"
    last_text = ""

    for step in range(1, effective_max_steps + 1):
        if time.monotonic() >= deadline:
            timed_out = True
            stopped_reason = "timeout"
            break

        step_text, raw_tool_calls = llm_step_fn(messages, step, True)
        steps_taken += 1
        last_text = (step_text or "").strip()
        tool_calls = list(raw_tool_calls or [])

        if not tool_calls:
            return AgentLoopResult(
                response=last_text,
                executed_tools=executed_tools,
                steps_taken=steps_taken,
                retries_used=retries_used,
                timed_out=False,
                stopped_reason="completed",
            )

        parsed_calls = [extractor(tc) for tc in tool_calls]
        parsed_calls = [(name, args) for name, args in parsed_calls if name]
        if not parsed_calls:
            return AgentLoopResult(
                response=last_text,
                executed_tools=executed_tools,
                steps_taken=steps_taken,
                retries_used=retries_used,
                timed_out=False,
                stopped_reason="completed",
            )

        messages.append({
            "role": "assistant",
            "content": last_text,
            "tool_calls": [
                {"function": {"name": name, "arguments": args}}
                for name, args in parsed_calls
            ],
        })

        step_records, batch_timed_out = _execute_tools_batch(
            parsed_calls,
            execute_tool_fn,
            max_workers=effective_workers,
            deadline=deadline,
        )
        executed_tools.extend(step_records)

        for rec in step_records:
            messages.append({
                "role": "tool",
                "name": rec["tool"],
                "content": rec["result"],
            })

        if batch_timed_out or time.monotonic() >= deadline:
            timed_out = True
            stopped_reason = "timeout"
            break

        failed_records = [rec for rec in step_records if is_tool_error(rec["result"])]
        if failed_records:
            if retries_used < max_error_retries and step < effective_max_steps:
                retries_used += 1
                err_summary = "; ".join(f"{r['tool']}: {r['result']}" for r in failed_records)
                messages.append({
                    "role": "user",
                    "content": (
                        f"[Auto-Correção #{retries_used}] A execução anterior retornou erro ({err_summary}). "
                        "Analise o erro, corrija os parâmetros ou use uma abordagem alternativa para concluir o pedido do senhor. "
                        "Se não for possível corrigir, explique o ocorrido com clareza."
                    ),
                })
                continue

            # Retentativas esgotadas: tenta síntese final explicativa sem novas tools
            stopped_reason = "error_retries_exhausted"
            break

        # Fast-path opcional (ex.: System 1 OS command único com template determinístico)
        if fast_template_fn is not None:
            templated = fast_template_fn(step_records, last_text)
            if templated is not None:
                return AgentLoopResult(
                    response=templated,
                    executed_tools=executed_tools,
                    steps_taken=steps_taken,
                    retries_used=retries_used,
                    timed_out=False,
                    stopped_reason="completed",
                )

        if step >= effective_max_steps:
            stopped_reason = "max_steps"
            break

    # Síntese final controlada quando o loop parou por max_steps ou erro pós-retry (e ainda há tempo)
    if not timed_out and time.monotonic() < deadline and executed_tools:
        try:
            synth_text, _ = llm_step_fn(messages, steps_taken + 1, False)
            synth_clean = (synth_text or "").strip()
            if (
                synth_clean
                and not synth_clean.startswith("Erro:")
                and not synth_clean.startswith("Não foi possível obter resposta")
            ):
                return AgentLoopResult(
                    response=synth_clean,
                    executed_tools=executed_tools,
                    steps_taken=steps_taken + 1,
                    retries_used=retries_used,
                    timed_out=False,
                    stopped_reason=stopped_reason,
                )
        except Exception:
            pass

    # Fallback determinístico seguro (nunca devolve resposta vazia silenciosa)
    if executed_tools:
        failures = [r for r in executed_tools if is_tool_error(r["result"])]
        if failures and len(failures) == len(executed_tools):
            detalhes_erro = "; ".join(str(r["result"]) for r in failures)
            fallback_msg = f"Não foi possível concluir o comando: {detalhes_erro}, senhor."
        elif timed_out:
            last_res = executed_tools[-1]["result"]
            fallback_msg = f"O tempo limite da operação foi atingido, senhor. Último resultado obtido: {last_res}"
        else:
            combined = "; ".join(f"{r['tool']}: {r['result']}" for r in executed_tools)
            fallback_msg = last_text or f"Protocolo concluído, senhor. {combined}"
    elif timed_out:
        fallback_msg = "O tempo limite de raciocínio foi atingido antes da conclusão, senhor."
    else:
        fallback_msg = last_text or "Às suas ordens, senhor."

    return AgentLoopResult(
        response=fallback_msg,
        executed_tools=executed_tools,
        steps_taken=steps_taken,
        retries_used=retries_used,
        timed_out=timed_out,
        stopped_reason=stopped_reason,
    )
