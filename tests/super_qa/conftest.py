"""
conftest.py - Configuração compartilhada da suíte Super QA de 250 testes da F.R.Y.I.Vs
Sandbox isolada: FRYIVS_TESTES/ — todos os testes operam exclusivamente dentro dela.
"""
import os
import sys
import time
import shutil
from pathlib import Path
import pytest

# ── Raiz do projeto e sandbox ────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent
SANDBOX = PROJECT_ROOT / "FRYIVS_TESTES"
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session", autouse=True)
def prepare_sandbox():
    """Cria a sandbox antes de todos os testes e preserva evidências ao final."""
    SANDBOX.mkdir(parents=True, exist_ok=True)
    yield
    # Sandbox preservada para auditoria de evidências


@pytest.fixture
def sandbox():
    """Fixture de sandbox por teste: subpasta isolada dentro de FRYIVS_TESTES/."""
    test_dir = SANDBOX / f"test_{int(time.time() * 1000)}"
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir


@pytest.fixture
def sandbox_root():
    """Retorna o caminho raiz da sandbox compartilhada."""
    return SANDBOX


def measure(func, *args, **kwargs):
    """Executa func e retorna (resultado, tempo_em_ms)."""
    t0 = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return result, elapsed_ms
