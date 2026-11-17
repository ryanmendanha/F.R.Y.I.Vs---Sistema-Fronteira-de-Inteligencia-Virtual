"""
Testes automatizados para validar a estrutura de `bench/comandos.jsonl` (B1 e B2)
e a acurácia do roteador sobre todas as 43 skills e 9 categorias.
"""

import json

from bench.avaliar_benchmark import COMANDOS_JSONL_PATH, executar_benchmark
from skills import SKILLS_REGISTRY


def test_benchmark_comandos_jsonl_estrutura_e_acuracia():
    resumo = executar_benchmark()

    assert COMANDOS_JSONL_PATH.exists(), "Arquivo bench/comandos.jsonl não foi criado"
    linhas = [
        json.loads(line)
        for line in COMANDOS_JSONL_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(linhas) >= 95
    for item in linhas:
        assert "id" in item and "categoria" in item and "comando" in item
        assert isinstance(item.get("variantes"), list) and len(item["variantes"]) >= 2

    assert resumo["skills_faltantes"] == [], f"Skills sem cobertura no benchmark: {resumo['skills_faltantes']}"
    assert resumo["skills_cobertas_total"] == len(SKILLS_REGISTRY)

    assert resumo["acuracia_top1_pct"] >= 95.0, (
        f"Acurácia Top-1 abaixo de 95%: {resumo['acuracia_top1_pct']}% | Falhas: {resumo['falhas'][:5]}"
    )
    assert resumo["recall_top3_pct"] >= 98.0, (
        f"Recall Top-3 abaixo de 98%: {resumo['recall_top3_pct']}%"
    )

