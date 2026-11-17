"""
Suíte de testes automatizados para F.R.Y.I.Vs.
Cobre: resolução de nomes de apps, controles de sistema, roteamento semântico de skills e memória vetorial.
Usa mocks para evitar dependências externas (ChromaDB, PyAutoGUI, pygetwindow, Ollama).
"""

from __future__ import annotations

import os
import sys
import unittest
from typing import Any
from unittest.mock import MagicMock, patch, call

# Garante que o diretório raiz do projeto esteja no path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ─────────────────────────────────────────────────────────────────────────────
#  TESTS: skills/open_app.py – normalize_app_name & resolve_program_name
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeAppName(unittest.TestCase):
    """Testa normalização de nomes com acentos, separadores e extensões."""

    def setUp(self):
        from skills.open_app import normalize_app_name
        self.normalize = normalize_app_name

    def test_remove_extension_exe(self):
        self.assertEqual(self.normalize("notepad.exe"), "notepad")

    def test_lowercase(self):
        self.assertEqual(self.normalize("Bloco de Notas"), "bloco de notas")

    def test_underscore_to_space(self):
        self.assertEqual(self.normalize("bloco_de_notas"), "bloco de notas")

    def test_hyphen_to_space(self):
        self.assertEqual(self.normalize("google-chrome"), "google chrome")

    def test_remove_accents(self):
        self.assertEqual(self.normalize("Calculadora"), "calculadora")
        self.assertEqual(self.normalize("Configurações"), "configuracoes")

    def test_strip_whitespace(self):
        self.assertEqual(self.normalize("  notepad  "), "notepad")

    def test_exe_and_underscore_combined(self):
        self.assertEqual(self.normalize("bloco_de_notas.exe"), "bloco de notas")


class TestResolveProgramName(unittest.TestCase):
    """Testa a resolução de apelidos populares para executáveis do Windows."""

    def setUp(self):
        from skills.open_app import resolve_program_name
        self.resolve = resolve_program_name

    def test_bloco_de_notas_underscore_exe(self):
        self.assertEqual(self.resolve("bloco_de_notas.exe"), "notepad.exe")

    def test_bloco_de_notas_natural_language(self):
        self.assertEqual(self.resolve("Bloco de Notas"), "notepad.exe")

    def test_notepad_lowercase(self):
        self.assertEqual(self.resolve("notepad"), "notepad.exe")

    def test_calculadora(self):
        self.assertEqual(self.resolve("calculadora"), "calc.exe")

    def test_calc_exe(self):
        self.assertEqual(self.resolve("calc.exe"), "calc.exe")

    def test_google_chrome_alias(self):
        resolved = self.resolve("Google Chrome")
        self.assertTrue(resolved == "chrome.exe" or resolved.lower().endswith("chrome.exe"))

    def test_prompt_de_comando(self):
        self.assertEqual(self.resolve("prompt de comando"), "cmd.exe")

    def test_gerenciador_de_tarefas(self):
        self.assertEqual(self.resolve("gerenciador de tarefas"), "taskmgr.exe")

    def test_explorer_alias(self):
        self.assertEqual(self.resolve("explorador de arquivos"), "explorer.exe")

    def test_vscode_alias(self):
        self.assertEqual(self.resolve("vscode"), "code")

    def test_unknown_program_passthrough(self):
        """Programas desconhecidos devem ser retornados como estão."""
        self.assertEqual(self.resolve("meu_programa_custom"), "meu_programa_custom")

    def test_empty_string_passthrough(self):
        """Strings vazias devem ser passadas através sem crash."""
        result = self.resolve("")
        self.assertIsInstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
#  TESTS: skills/open_app.py – abrir_programa (com mock de os.startfile)
# ─────────────────────────────────────────────────────────────────────────────

class TestAbrirPrograma(unittest.TestCase):
    """Testa a função de abertura de programas com mock do sistema operacional."""

    def setUp(self):
        from skills.open_app import abrir_programa
        self.abrir = abrir_programa

    def test_empty_nome_returns_error(self):
        result = self.abrir("")
        self.assertIn("Erro", result)

    def test_whitespace_nome_returns_error(self):
        result = self.abrir("   ")
        self.assertIn("Erro", result)

    @patch("skills.open_app.os.startfile")
    def test_opens_notepad_via_alias(self, mock_startfile):
        """Deve resolver 'Bloco de Notas' para 'notepad.exe' e chamar startfile."""
        result = self.abrir("Bloco de Notas")
        mock_startfile.assert_called_once_with("notepad.exe")
        self.assertIn("sucesso", result.lower())

    @patch("skills.open_app.os.startfile")
    def test_opens_calc_via_alias(self, mock_startfile):
        result = self.abrir("calculadora")
        mock_startfile.assert_called_once_with("calc.exe")
        self.assertIn("sucesso", result.lower())

    @patch("skills.open_app.os.startfile", side_effect=FileNotFoundError("[WinError 2]"))
    @patch("skills.open_app.shutil.which", return_value=None)
    @patch("skills.open_app.subprocess.Popen")
    def test_fallback_to_popen_shell(self, mock_popen, mock_which, mock_startfile):
        """Quando startfile falha, deve tentar subprocess com shell=True."""
        result = self.abrir("programa_invalido")
        self.assertTrue(mock_popen.called)

    @patch("skills.open_app.os.startfile", side_effect=FileNotFoundError("[WinError 2]"))
    @patch("skills.open_app.shutil.which", return_value=r"C:\tools\mytool.exe")
    @patch("skills.open_app.subprocess.Popen")
    def test_fallback_to_which_popen(self, mock_popen, mock_which, mock_startfile):
        """Quando startfile falha mas which encontra o executável, usa Popen."""
        result = self.abrir("mytool")
        mock_popen.assert_called_once_with([r"C:\tools\mytool.exe"], shell=False)
        self.assertIn("sucesso", result.lower())


# ─────────────────────────────────────────────────────────────────────────────
#  TESTS: skills/system_controls.py – _parse_keys
# ─────────────────────────────────────────────────────────────────────────────

class TestParseKeys(unittest.TestCase):
    """Testa normalização de atalhos de teclado em variados formatos."""

    def setUp(self):
        from skills.system_controls import _parse_keys
        self.parse = _parse_keys

    def test_list_input(self):
        self.assertEqual(self.parse(["ctrl", "c"]), ["ctrl", "c"])

    def test_string_plus_delimiter(self):
        self.assertEqual(self.parse("ctrl+c"), ["ctrl", "c"])

    def test_string_with_spaces_around_plus(self):
        self.assertEqual(self.parse("ctrl + v"), ["ctrl", "v"])

    def test_string_comma_delimiter(self):
        self.assertEqual(self.parse("alt,tab"), ["alt", "tab"])

    def test_single_key_string(self):
        self.assertEqual(self.parse("enter"), ["enter"])

    def test_uppercase_normalized(self):
        result = self.parse(["CTRL", "C"])
        self.assertEqual(result, ["ctrl", "c"])


class TestPressionarAtalho(unittest.TestCase):
    """Testa execução de atalhos com mock de pyautogui."""

    def setUp(self):
        from skills.system_controls import pressionar_atalho
        self.pressionar = pressionar_atalho

    @patch("skills.system_controls.pyautogui")
    def test_list_keys(self, mock_pag):
        result = self.pressionar(["ctrl", "c"])
        mock_pag.hotkey.assert_called_once_with("ctrl", "c")
        self.assertIn("sucesso", result.lower())

    @patch("skills.system_controls.pyautogui")
    def test_string_keys_with_plus(self, mock_pag):
        result = self.pressionar("ctrl+v")
        mock_pag.hotkey.assert_called_once_with("ctrl", "v")
        self.assertIn("sucesso", result.lower())

    @patch("skills.system_controls.pyautogui", None)
    def test_no_pyautogui_returns_error(self):
        result = self.pressionar(["ctrl", "c"])
        self.assertIn("Erro", result)

    @patch("skills.system_controls.pyautogui")
    def test_empty_keys_returns_error(self, mock_pag):
        result = self.pressionar([])
        self.assertIn("Erro", result)
        mock_pag.hotkey.assert_not_called()


class TestControlarVolume(unittest.TestCase):
    """Testa ações de controle de volume."""

    def setUp(self):
        from skills.system_controls import controlar_volume
        self.controlar = controlar_volume

    @patch("skills.system_controls.pyautogui")
    def test_aumentar_volume(self, mock_pag):
        result = self.controlar("aumentar")
        self.assertEqual(mock_pag.press.call_count, 5)
        mock_pag.press.assert_called_with("volumeup")
        self.assertIn("aumentado", result.lower())

    @patch("skills.system_controls.pyautogui")
    def test_diminuir_volume(self, mock_pag):
        result = self.controlar("diminuir")
        self.assertEqual(mock_pag.press.call_count, 5)
        mock_pag.press.assert_called_with("volumedown")
        self.assertIn("diminuído", result.lower())

    @patch("skills.system_controls.pyautogui")
    def test_mutar_volume(self, mock_pag):
        result = self.controlar("mutar")
        mock_pag.press.assert_called_once_with("volumemute")
        # A mensagem retornada é "mutado/desmutado com sucesso"
        self.assertTrue(
            "mutado" in result.lower() or "mute" in result.lower(),
            f"Esperava 'mutado' ou 'mute' em: {result!r}"
        )

    @patch("skills.system_controls.pyautogui")
    def test_alias_silenciar(self, mock_pag):
        result = self.controlar("silenciar")
        mock_pag.press.assert_called_once_with("volumemute")

    @patch("skills.system_controls.pyautogui")
    def test_acao_invalida(self, mock_pag):
        result = self.controlar("explode")
        self.assertIn("desconhecida", result.lower())
        mock_pag.press.assert_not_called()

    @patch("skills.system_controls.pyautogui", None)
    def test_no_pyautogui(self):
        result = self.controlar("aumentar")
        self.assertIn("Erro", result)


class TestDigitarTexto(unittest.TestCase):
    """Testa digitação automática de texto."""

    def setUp(self):
        from skills.system_controls import digitar_texto
        self.digitar = digitar_texto

    @patch("skills.system_controls.pyautogui")
    @patch("skills.system_controls.time.sleep")
    def test_basic_typing(self, mock_sleep, mock_pag):
        result = self.digitar("Olá Mundo")
        mock_pag.write.assert_called_once_with("Olá Mundo", interval=0.03)
        self.assertIn("sucesso", result.lower())
        self.assertIn("9", result)  # 9 caracteres

    @patch("skills.system_controls.pyautogui")
    @patch("skills.system_controls.time.sleep")
    def test_empty_text_returns_warning(self, mock_sleep, mock_pag):
        result = self.digitar("")
        self.assertIn("nenhum", result.lower())
        mock_pag.write.assert_not_called()

    @patch("skills.system_controls.pyautogui", None)
    def test_no_pyautogui(self):
        result = self.digitar("Texto")
        self.assertIn("Erro", result)


class TestListarJanelas(unittest.TestCase):
    """Testa listagem de janelas com mock de pygetwindow."""

    def setUp(self):
        from skills.system_controls import listar_janelas
        self.listar = listar_janelas

    @patch("skills.system_controls.gw")
    def test_lists_windows(self, mock_gw):
        mock_gw.getAllTitles.return_value = ["Notepad", "Chrome", "", "  "]
        result = self.listar()
        self.assertIn("Notepad", result)
        self.assertIn("Chrome", result)
        self.assertIn("2 encontradas", result)

    @patch("skills.system_controls.gw")
    def test_no_windows(self, mock_gw):
        mock_gw.getAllTitles.return_value = ["", " "]
        result = self.listar()
        self.assertIn("Nenhuma", result)

    @patch("skills.system_controls.gw", None)
    def test_no_pygetwindow(self):
        result = self.listar()
        self.assertIn("Erro", result)


# ─────────────────────────────────────────────────────────────────────────────
#  TESTS: skills/__init__.py – execute_skill
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteSkill(unittest.TestCase):
    """Testa o despachante central de skills."""

    def setUp(self):
        from skills import execute_skill
        self.execute = execute_skill

    def test_unknown_skill_returns_error(self):
        result = self.execute("skill_inexistente", {})
        self.assertIn("Erro", result)
        self.assertIn("skill_inexistente", result)

    def test_empty_name_returns_error(self):
        result = self.execute("", {})
        self.assertIn("Erro", result)

    @patch("skills.SKILLS_REGISTRY", {"mock_skill": lambda: "OK"})
    def test_known_skill_no_args(self):
        result = self.execute("mock_skill", {})
        self.assertEqual(result, "OK")

    @patch("skills.SKILLS_REGISTRY", {"echo": lambda x: f"echo:{x}"})
    def test_known_skill_with_args(self):
        result = self.execute("echo", {"x": "hello"})
        self.assertEqual(result, "echo:hello")

    @patch("skills.SKILLS_REGISTRY", {"bad_skill": lambda: 1 / 0})
    def test_exception_is_caught(self):
        result = self.execute("bad_skill", {})
        self.assertIn("Erro", result)
        self.assertIn("bad_skill", result)

    @patch("skills.SKILLS_REGISTRY", {"typed_skill": lambda name: f"Hi {name}"})
    def test_wrong_args_caught(self):
        result = self.execute("typed_skill", {"wrong_param": "value"})
        self.assertIn("Erro", result)


# ─────────────────────────────────────────────────────────────────────────────
#  TESTS: core/skill_router.py – SkillRouter
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillRouter(unittest.TestCase):
    """Testa o roteamento semântico de skills via ChromaDB."""

    def _build_router(self) -> Any:
        """Cria um SkillRouter com ChromaDB em memória (ephemeral) para isolamento de testes."""
        import chromadb
        from core.skill_router import SkillRouter

        class IsolatedSkillRouter(SkillRouter):
            def __init__(self):
                import chromadb
                from chromadb.config import Settings
                client = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))
                self.collection_name = "test_skills"
                self.collection = client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
                self._schemas_by_name = {
                    schema.get("function", {}).get("name", ""): schema
                    for schema in __import__("skills").ALL_SKILL_SCHEMAS
                    if "function" in schema
                }
                self.ensure_skills_indexed()

        return IsolatedSkillRouter()

    def test_skills_are_indexed(self):
        router = self._build_router()
        count = router.collection.count()
        self.assertGreater(count, 0, "Nenhuma skill foi indexada no ChromaDB")

    def test_semantic_search_finds_notepad(self):
        router = self._build_router()
        # Query com vocabulário enriquecido garante hit semântico alto
        results = router.search_relevant_skills(
            "abrir programa bloco de notas notepad iniciar aplicativo",
            top_k=3,
            threshold=1.0
        )
        names = [r.get("function", {}).get("name") for r in results]
        self.assertIn("abrir_programa", names, f"'abrir_programa' não encontrada. Resultados: {names}")

    def test_semantic_search_finds_volume(self):
        router = self._build_router()
        results = router.search_relevant_skills("Aumente o volume do computador", top_k=3, threshold=1.0)
        names = [r.get("function", {}).get("name") for r in results]
        self.assertIn("controlar_volume", names, f"'controlar_volume' não encontrada. Resultados: {names}")

    def test_semantic_search_finds_screenshot(self):
        router = self._build_router()
        results = router.search_relevant_skills("Tire um print da tela", top_k=3, threshold=1.0)
        names = [r.get("function", {}).get("name") for r in results]
        self.assertIn("tirar_screenshot", names, f"'tirar_screenshot' não encontrada. Resultados: {names}")

    def test_conversational_query_at_strict_threshold(self):
        """Perguntas sem intenção de skill clara devem retornar pouco ou nada com threshold baixo."""
        router = self._build_router()
        results = router.search_relevant_skills("O que é o universo?", top_k=2, threshold=0.30)
        # A consulta é filosófica; com threshold restrito, deve retornar vazio
        self.assertEqual(len(results), 0, f"Skills inesperadas retornadas: {results}")

    def test_returns_valid_schemas(self):
        """Resultados devem ter a estrutura correta de schema OpenAI."""
        router = self._build_router()
        results = router.search_relevant_skills("abrir programa", top_k=3, threshold=1.0)
        for schema in results:
            self.assertIn("type", schema)
            self.assertIn("function", schema)
            self.assertIn("name", schema["function"])

    def test_empty_query_returns_empty(self):
        router = self._build_router()
        results = router.search_relevant_skills("", top_k=3, threshold=1.0)
        self.assertEqual(results, [])

    def test_get_all_skills_returns_all(self):
        router = self._build_router()
        all_skills = router.get_all_skills()
        self.assertGreater(len(all_skills), 0)


# ─────────────────────────────────────────────────────────────────────────────
#  TESTS: core/memory.py – salvar, buscar e deletar
# ─────────────────────────────────────────────────────────────────────────────

class TestMemory(unittest.TestCase):
    """Testa persistência semântica de memória com ChromaDB ephemeral."""

    def setUp(self):
        """Configura coleção ephemeral isolada para cada teste."""
        import chromadb
        from chromadb.config import Settings

        self._client = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))
        self._col = self._client.get_or_create_collection(
            "test_mem",
            metadata={"hnsw:space": "cosine"}
        )

        import core.memory as mem_module
        self._original_fn = mem_module._get_memory_collection
        mem_module._get_memory_collection = lambda: self._col
        import core.memory
        self.mem = core.memory

    def tearDown(self):
        import core.memory as mem_module
        mem_module._get_memory_collection = self._original_fn

    def test_save_and_retrieve_memory(self):
        ok = self.mem.salvar_memoria("O usuário pediu para abrir o Notepad.", "id-001")
        self.assertTrue(ok)
        resultado = self.mem.buscar_contexto("abrir bloco de notas", threshold=1.0)
        self.assertIn("Notepad", resultado)

    def test_empty_text_not_saved(self):
        ok = self.mem.salvar_memoria("", "id-002")
        self.assertFalse(ok)

    def test_delete_memory(self):
        self.mem.salvar_memoria("Texto para deletar.", "id-003")
        ok = self.mem.deletar_memoria("id-003")
        self.assertTrue(ok)
        resultado = self.mem.buscar_contexto("Texto para deletar", threshold=1.0)
        self.assertEqual(resultado, "")

    def test_buscar_contexto_empty_db(self):
        resultado = self.mem.buscar_contexto("qualquer coisa")
        self.assertEqual(resultado, "")

    def test_buscar_contexto_empty_query(self):
        resultado = self.mem.buscar_contexto("")
        self.assertEqual(resultado, "")

    def test_listar_memorias(self):
        self.mem.salvar_memoria("Memória A", "id-a")
        self.mem.salvar_memoria("Memória B", "id-b")
        lista = self.mem.listar_memorias()
        self.assertEqual(len(lista), 2)
        ids = [m["id"] for m in lista]
        self.assertIn("id-a", ids)
        self.assertIn("id-b", ids)

    def test_listar_memorias_empty(self):
        """Usa uma coleção completamente limpa e nova para garantir isolamento."""
        import chromadb
        from chromadb.config import Settings
        import core.memory as mem_module

        fresh_client = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))
        empty_col = fresh_client.get_or_create_collection(
            "test_mem_empty",
            metadata={"hnsw:space": "cosine"}
        )
        mem_module._get_memory_collection = lambda: empty_col
        lista = self.mem.listar_memorias()
        self.assertEqual(lista, [])


# ─────────────────────────────────────────────────────────────────────────────
#  TESTS: core/vector_db.py – get_or_create_collection cache
# ─────────────────────────────────────────────────────────────────────────────

class TestVectorDB(unittest.TestCase):
    """Testa o gerenciador Multiton do ChromaDB."""

    def tearDown(self):
        from core.vector_db import reset_collection_cache
        reset_collection_cache()

    def test_reset_cache_clears_collections(self):
        from core.vector_db import _COLLECTIONS_CACHE, reset_collection_cache
        _COLLECTIONS_CACHE["fake"] = object()
        reset_collection_cache()
        self.assertEqual(len(_COLLECTIONS_CACHE), 0)

    @patch("core.vector_db.chromadb.PersistentClient")
    def test_multiton_supports_different_db_paths(self, mock_client_cls):
        from core.vector_db import get_chroma_client, reset_chroma_client, _CHROMA_CLIENTS
        
        mock_instance_a = MagicMock(name="client_A")
        mock_instance_b = MagicMock(name="client_B")
        mock_client_cls.side_effect = [mock_instance_a, mock_instance_b]

        reset_chroma_client()
        client_a = get_chroma_client("test_db_a")
        client_b = get_chroma_client("test_db_b")

        # Não deve ignorar silenciosamente o segundo db_path
        self.assertNotEqual(client_a, client_b)
        self.assertEqual(mock_client_cls.call_count, 2)

        # Chamar novamente com o mesmo path deve retornar do cache multiton sem recriar
        client_a_cached = get_chroma_client("test_db_a")
        self.assertEqual(client_a, client_a_cached)
        self.assertEqual(mock_client_cls.call_count, 2)

        # Reset por caminho
        reset_chroma_client("test_db_a")
        norm_a = os.path.abspath(os.path.normpath("test_db_a"))
        norm_b = os.path.abspath(os.path.normpath("test_db_b"))
        self.assertNotIn(norm_a, _CHROMA_CLIENTS)
        self.assertIn(norm_b, _CHROMA_CLIENTS)

        # Reset global
        reset_chroma_client()
        self.assertEqual(len(_CHROMA_CLIENTS), 0)


# ─────────────────────────────────────────────────────────────────────────────
#  TESTS: TirarScreenshot
# ─────────────────────────────────────────────────────────────────────────────

class TestTirarScreenshot(unittest.TestCase):
    """Testa captura de tela com mock de pyautogui e sistema de arquivos."""

    def setUp(self):
        from skills.system_controls import tirar_screenshot
        self.capturar = tirar_screenshot

    @patch("skills.system_controls.os.makedirs")
    @patch("skills.system_controls.pyautogui")
    @patch("skills.system_controls.time.time", return_value=1700000000)
    def test_default_filename_uses_timestamp(self, mock_time, mock_pag, mock_mkdirs):
        mock_screenshot = MagicMock()
        mock_pag.screenshot.return_value = mock_screenshot
        result = self.capturar()
        mock_screenshot.save.assert_called_once()
        saved_path = mock_screenshot.save.call_args[0][0]
        self.assertIn("screenshot_1700000000.png", saved_path)
        self.assertIn("sucesso", result.lower())

    @patch("skills.system_controls.os.makedirs")
    @patch("skills.system_controls.pyautogui")
    @patch("skills.system_controls.time.time", return_value=1700000001)
    def test_custom_filename_used(self, mock_time, mock_pag, mock_mkdirs):
        mock_screenshot = MagicMock()
        mock_pag.screenshot.return_value = mock_screenshot
        result = self.capturar("minha_tela.png")
        saved_path = mock_screenshot.save.call_args[0][0]
        self.assertIn("minha_tela.png", saved_path)

    @patch("skills.system_controls.os.makedirs")
    @patch("skills.system_controls.pyautogui")
    @patch("skills.system_controls.time.time", return_value=1700000002)
    def test_adds_png_extension_if_missing(self, mock_time, mock_pag, mock_mkdirs):
        mock_screenshot = MagicMock()
        mock_pag.screenshot.return_value = mock_screenshot
        result = self.capturar("foto_sem_extensao")
        saved_path = mock_screenshot.save.call_args[0][0]
        self.assertTrue(saved_path.endswith(".png"))

    @patch("skills.system_controls.pyautogui", None)
    def test_no_pyautogui_returns_error(self):
        result = self.capturar()
        self.assertIn("Erro", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
