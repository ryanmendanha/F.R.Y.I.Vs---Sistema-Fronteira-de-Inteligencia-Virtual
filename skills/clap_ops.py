"""
Skill operacional de ativação por duas palmas (Clap_on_Jarvis) para a F.R.Y.I.Vs.
Permite ativar, desativar, consultar status e calibrar a sensibilidade das duas palmas
por comando de voz ou texto.
"""

from __future__ import annotations

from typing import Any, Final
from core.clap_detector import get_clap_detector
from core import voice_daemon


def configurar_ativacao_palmas(
    acao: str = "status",
    sensibilidade: str = "",
) -> str:
    """
    Controla o despertar acústico da F.R.Y.I.Vs por duas palmas (Clap_on_Jarvis).
    """
    detector = get_clap_detector()
    acao_norm = (acao or "status").strip().lower()

    if acao_norm in ("ativar", "ligar", "habilitar", "on", "enable"):
        st = detector.set_enabled(True)
        if sensibilidade and sensibilidade.strip():
            try:
                st = detector.set_sensitivity(sensibilidade)
            except ValueError:
                pass
        voice_daemon.notificar_evento_externo({"type": "clap_config", **st})
        return (
            f"Ativação por duas palmas habilitada (sensibilidade: {st['sensitivity']}). "
            f"Bata duas palmas em até {st['clap_gap_seconds']:.2f}s para me chamar."
        )

    if acao_norm in ("desativar", "desligar", "desabilitar", "off", "disable"):
        st = detector.set_enabled(False)
        voice_daemon.notificar_evento_externo({"type": "clap_config", **st})
        return "Ativação por duas palmas desativada. Continuo atenta ao chamado 'FRYIVS'."

    if acao_norm in ("sensibilidade", "calibrar", "ajustar") or (
        acao_norm == "status" and sensibilidade and sensibilidade.strip()
    ):
        alvo = (sensibilidade or "media").strip()
        try:
            st = detector.set_sensitivity(alvo)
        except ValueError as exc:
            return str(exc)
        voice_daemon.notificar_evento_externo({"type": "clap_config", **st})
        estado_txt = "ativa" if st["enabled"] else "desativada"
        return (
            f"Sensibilidade das duas palmas ajustada para '{st['sensitivity']}' "
            f"(detecção {estado_txt}, pico mínimo {st['min_peak']})."
        )

    st = detector.status()
    estado_txt = "ATIVA" if st["enabled"] else "DESATIVADA"
    return (
        f"Ativação por duas palmas: {estado_txt} | "
        f"Sensibilidade: {st['sensitivity']} | "
        f"Janela: {st['min_interval_seconds']}s–{st['clap_gap_seconds']}s | "
        f"Acionamentos na sessão: {st['total_triggers']}."
    )


CLAP_SCHEMAS: Final[list[dict[str, Any]]] = [
    {
        "type": "function",
        "function": {
            "name": "configurar_ativacao_palmas",
            "description": (
                "Ativa, desativa, consulta o status ou ajusta a sensibilidade ('baixa', 'media', 'alta') "
                "do despertar da F.R.Y.I.Vs ao ouvir duas palmas (Clap on Jarvis)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "acao": {
                        "type": "string",
                        "enum": ["status", "ativar", "desativar", "sensibilidade"],
                        "description": "Operação desejada sobre o detector de duas palmas.",
                    },
                    "sensibilidade": {
                        "type": "string",
                        "enum": ["baixa", "media", "alta"],
                        "description": "Nível de sensibilidade acústica (opcional).",
                    },
                },
                "required": ["acao"],
            },
        },
    }
]

