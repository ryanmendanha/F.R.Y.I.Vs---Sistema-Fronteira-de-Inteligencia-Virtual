"""
Testes da máquina de estados do `VoiceDaemon` (`core/voice_daemon.py`).
"""

import numpy as np

from core.stt import CHUNK_SIZE
from core.voice_daemon import VoiceDaemon


def _bloco_fala(amplitude: float = 0.15) -> np.ndarray:
    return np.full(CHUNK_SIZE, amplitude, dtype="float32")


def _bloco_silencio() -> np.ndarray:
    return np.zeros(CHUNK_SIZE, dtype="float32")


class TestVoiceDaemonStateMachine:
    """Valida transições de estado, 'Senhor?', execução direta, timeout e half-duplex."""

    def test_fluxo_wake_word_responde_senhor_e_executa_pedido(self):
        senhor_tocado = []
        comandos_executados = []
        eventos_ws = []

        daemon = VoiceDaemon(
            transcrever_wake_fn=lambda _a: "Frives",
            transcrever_cmd_fn=lambda _a: "crie uma planilha de vendas",
            tocar_senhor_fn=lambda: senhor_tocado.append(True),
            executar_comando_fn=lambda cmd: comandos_executados.append(cmd),
            notificar_fn=lambda ev: eventos_ws.append(ev),
            tocando_fn=lambda: False,
        )

        assert daemon.estado == "DORMINDO"

        for _ in range(4):
            daemon.processar_chunk(_bloco_fala())
        for _ in range(4):
            daemon.processar_chunk(_bloco_silencio())

        assert len(senhor_tocado) == 1
        assert daemon.estado == "OUVINDO_PEDIDO"
        assert any(e.get("type") == "wake_detected" and e.get("response") == "Senhor?" for e in eventos_ws)

        for _ in range(6):
            daemon.processar_chunk(_bloco_fala())
        for _ in range(8):
            daemon.processar_chunk(_bloco_silencio())

        assert comandos_executados == ["crie uma planilha de vendas"]
        assert daemon.estado == "DORMINDO"
        assert daemon.historico_estados == [
            "DORMINDO",
            "VERIFICANDO",
            "SENHOR_Q",
            "OUVINDO_PEDIDO",
            "PROCESSANDO",
            "DORMINDO",
        ]

    def test_fluxo_direto_quando_wake_word_e_pedido_na_mesma_frase(self):
        senhor_tocado = []
        comandos_executados = []

        daemon = VoiceDaemon(
            transcrever_wake_fn=lambda _a: "Frives abra o bloco de notas",
            transcrever_cmd_fn=lambda _a: "Frives, abra o bloco de notas",
            tocar_senhor_fn=lambda: senhor_tocado.append(True),
            executar_comando_fn=lambda cmd: comandos_executados.append(cmd),
            tocando_fn=lambda: False,
        )

        for _ in range(5):
            daemon.processar_chunk(_bloco_fala())
        for _ in range(4):
            daemon.processar_chunk(_bloco_silencio())

        assert senhor_tocado == []
        assert comandos_executados == ["abra o bloco de notas"]
        assert daemon.estado == "DORMINDO"

    def test_ignora_fala_sem_wake_word(self):
        senhor_tocado = []
        comandos_executados = []

        daemon = VoiceDaemon(
            transcrever_wake_fn=lambda _a: "bom dia pessoal tudo certo",
            transcrever_cmd_fn=lambda _a: "bom dia pessoal tudo certo",
            tocar_senhor_fn=lambda: senhor_tocado.append(True),
            executar_comando_fn=lambda cmd: comandos_executados.append(cmd),
            tocando_fn=lambda: False,
        )

        for _ in range(5):
            daemon.processar_chunk(_bloco_fala())
        for _ in range(4):
            daemon.processar_chunk(_bloco_silencio())

        assert senhor_tocado == []
        assert comandos_executados == []
        assert daemon.estado == "DORMINDO"

    def test_timeout_em_ouvindo_pedido_retorna_para_dormindo(self):
        daemon = VoiceDaemon(
            transcrever_wake_fn=lambda _a: "Fraives",
            transcrever_cmd_fn=lambda _a: "",
            tocar_senhor_fn=lambda: None,
            executar_comando_fn=lambda _cmd: None,
            tocando_fn=lambda: False,
        )
        daemon.timeout_pedido_chunks = 10

        for _ in range(4):
            daemon.processar_chunk(_bloco_fala())
        for _ in range(4):
            daemon.processar_chunk(_bloco_silencio())

        assert daemon.estado == "OUVINDO_PEDIDO"

        for _ in range(10):
            daemon.processar_chunk(_bloco_silencio())

        assert daemon.estado == "DORMINDO"

    def test_half_duplex_ignora_microfone_enquanto_tocando(self):
        transcricoes = []
        daemon = VoiceDaemon(
            transcrever_wake_fn=lambda _a: transcricoes.append(1) or "Frives",
            tocar_senhor_fn=lambda: None,
            executar_comando_fn=lambda _cmd: None,
            tocando_fn=lambda: True,
        )

        for _ in range(6):
            daemon.processar_chunk(_bloco_fala())
        for _ in range(6):
            daemon.processar_chunk(_bloco_silencio())

        assert transcricoes == []
        assert daemon.estado == "DORMINDO"

    def test_warmup_startup_ignora_ruido_inicial_sem_dizer_senhor(self):
        senhor_tocado = []
        transcricoes = []
        daemon = VoiceDaemon(
            transcrever_wake_fn=lambda _a: transcricoes.append(1) or "Frives",
            tocar_senhor_fn=lambda: senhor_tocado.append(True),
            executar_comando_fn=lambda _cmd: None,
            tocando_fn=lambda: False,
        )
        daemon._warmup_restante = 10

        for _ in range(10):
            daemon.processar_chunk(_bloco_fala(0.25))

        assert daemon._warmup_restante == 0
        assert transcricoes == []
        assert senhor_tocado == []
        assert daemon.estado == "DORMINDO"

    def test_ruido_curto_isolado_nao_aciona_whisper_nem_senhor(self):
        senhor_tocado = []
        transcricoes = []
        daemon = VoiceDaemon(
            transcrever_wake_fn=lambda _a: transcricoes.append(1) or "Frives",
            tocar_senhor_fn=lambda: senhor_tocado.append(True),
            executar_comando_fn=lambda _cmd: None,
            tocando_fn=lambda: False,
        )

        daemon.processar_chunk(_bloco_fala(0.15))
        daemon.processar_chunk(_bloco_fala(0.15))
        for _ in range(5):
            daemon.processar_chunk(_bloco_silencio())

        assert transcricoes == []
        assert senhor_tocado == []
        assert daemon.estado == "DORMINDO"

    def test_descarta_alucinacao_repetitiva_whisper_sem_executar(self):
        from core.stt import eh_alucinacao_whisper

        assert eh_alucinacao_whisper("genios genios genios genios genios genios") is True
        assert eh_alucinacao_whisper("frives fraives frives fraives frives frives") is True
        assert eh_alucinacao_whisper(
            "Comandos de voz em português brasileiro para automação de computador, planilhas Excel"
        ) is True
        assert eh_alucinacao_whisper("Abra o Chrome e pesquise sobre Python") is False
        assert eh_alucinacao_whisper("Abra o primeiro link") is False

        comandos_executados = []
        daemon = VoiceDaemon(
            transcrever_wake_fn=lambda _a: "Frives",
            transcrever_cmd_fn=lambda _a: "genios genios genios genios genios genios",
            tocar_senhor_fn=lambda: None,
            executar_comando_fn=lambda cmd: comandos_executados.append(cmd),
            tocando_fn=lambda: False,
        )

        for _ in range(4):
            daemon.processar_chunk(_bloco_fala())
        for _ in range(4):
            daemon.processar_chunk(_bloco_silencio())
        assert daemon.estado == "OUVINDO_PEDIDO"

        for _ in range(6):
            daemon.processar_chunk(_bloco_fala())
        for _ in range(8):
            daemon.processar_chunk(_bloco_silencio())

        assert comandos_executados == []
        assert daemon.estado == "DORMINDO"


class TestWebCoPilotNavigation:
    """Valida resolução de links ordinais e roteamento de navegação na aba aberta."""

    def test_resolver_indice_ordinal_links_e_resultados(self):
        from skills.web_automation import _resolver_indice_ordinal

        assert _resolver_indice_ordinal("abra o primeiro link") == 0
        assert _resolver_indice_ordinal("entre no segundo resultado") == 1
        assert _resolver_indice_ordinal("clique no terceiro vídeo") == 2
        assert _resolver_indice_ordinal("link 4") == 3
        assert _resolver_indice_ordinal("último link") == -1
        assert _resolver_indice_ordinal("botão de login") is None

    def test_skill_router_prioriza_interacao_na_aba_aberta(self):
        from core.skill_router import get_skill_router

        router = get_skill_router()
        schemas_link = router.search_relevant_skills("abra o primeiro link", top_k=4)
        nomes_link = [s["function"]["name"] for s in schemas_link]
        assert "clicar_elemento_web" in nomes_link
        assert "abrir_programa" not in nomes_link

        schemas_scroll = router.search_relevant_skills("role a página para baixo", top_k=4)
        nomes_scroll = [s["function"]["name"] for s in schemas_scroll]
        assert "interagir_pagina_web" in nomes_scroll

    def test_resposta_funcao_para_empresas(self):
        from core.llm import ask_fryvis, RESPOSTA_FUNCAO_EMPRESAS, _is_asking_about_companies

        perguntas = [
            "Qual a sua função para as empresas?",
            "Qual a função dela para as empresas?",
            "Como você pode ajudar empresas?",
            "Para que você serve em uma empresa?",
            "O que você faz para as empresas?",
        ]
        for p in perguntas:
            assert _is_asking_about_companies(p) is True
            resp, tools = ask_fryvis(p)
            assert resp == RESPOSTA_FUNCAO_EMPRESAS
            assert tools == []

        assert _is_asking_about_companies("Crie uma planilha de despesas da empresa") is False
        assert _is_asking_about_companies("Pesquise sobre a empresa Microsoft") is False

    def test_bloqueia_escuta_enquanto_esta_falando_ou_processando(self):
        from core import mute_state

        transcricoes = []
        daemon = VoiceDaemon(
            transcrever_wake_fn=lambda _a: transcricoes.append(1) or "Frives",
            tocar_senhor_fn=lambda: None,
            executar_comando_fn=lambda _cmd: None,
            tocando_fn=lambda: True,
        )

        assert daemon.esta_falando() is True
        assert daemon.escuta_habilitada() is False

        for _ in range(8):
            daemon.processar_chunk(_bloco_fala(0.30))
        for _ in range(6):
            daemon.processar_chunk(_bloco_silencio())

        assert transcricoes == []
        assert daemon.estado == "DORMINDO"
        assert daemon.acionar_manual() is False

        daemon_proc = VoiceDaemon(
            transcrever_wake_fn=lambda _a: transcricoes.append(1) or "Frives",
            tocar_senhor_fn=lambda: None,
            executar_comando_fn=lambda _cmd: None,
            tocando_fn=lambda: False,
            processando_fn=lambda: True,
        )

        assert daemon_proc.esta_processando() is True
        assert daemon_proc.escuta_habilitada() is False

        for _ in range(8):
            daemon_proc.processar_chunk(_bloco_fala(0.30))
        for _ in range(6):
            daemon_proc.processar_chunk(_bloco_silencio())

        assert transcricoes == []
        assert daemon_proc.acionar_manual() is False

    def test_escuta_permitida_somente_em_repouso(self):
        from core import mute_state

        mute_state.set_muted(False)
        assert mute_state.is_processing() is False
        assert mute_state.is_speaking() is False
        assert mute_state.escuta_permitida() is True

        mute_state.iniciar_processamento()
        assert mute_state.is_processing() is True
        assert mute_state.escuta_permitida() is False
        mute_state.finalizar_processamento()
        assert mute_state.is_processing() is False
        assert mute_state.escuta_permitida() is True

        mute_state.definir_falando(True)
        assert mute_state.is_speaking() is True
        assert mute_state.escuta_permitida() is False
        mute_state.definir_falando(False, cooldown=0.0)
        assert mute_state.is_speaking() is False
        assert mute_state.escuta_permitida() is True


