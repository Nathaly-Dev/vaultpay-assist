"""Compara o piloto do ADR 0005 (select-v1) com a linha de base (answer-v1) no recorte do piloto.

A biblioteca do piloto só cobre Conta Digital, Pix MED e Cartão. Por isso o recorte é:
- com base: perguntas cuja fonte principal é uma dessas políticas;
- sem base: perguntas em que a busca traz algum trecho delas (nas outras, o piloto nem chama o
  modelo, e contá-las facilitaria a nota).
Uso: python -m vaultpay_copilot.evaluation.pilot_report <base.json> <piloto.json>
"""

import json
import statistics
import sys
from pathlib import Path

PILOT_POLICIES = {"politica-conta-digital", "politica-pix-med", "politica-cartao"}


def main(base_file: Path, pilot_file: Path) -> None:
    import psycopg
    from pgvector.psycopg import register_vector

    from vaultpay_copilot.config import Settings
    from vaultpay_copilot.evaluation.run_eval import DEFAULT_CASES, load_cases
    from vaultpay_copilot.ingestion.embedder import QueryEmbedder
    from vaultpay_copilot.rag.pii import mask_pii
    from vaultpay_copilot.rag.retriever import search

    runs = {}
    for name, path in (("linha de base", base_file), ("piloto", pilot_file)):
        report = json.loads(path.read_text(encoding="utf-8"))
        runs[f"{name} ({report['prompt']})"] = {c["id"]: c for c in report["casos"]}
    cases = load_cases(DEFAULT_CASES)

    embed = QueryEmbedder()
    with psycopg.connect(Settings.from_env().conninfo()) as conn:
        register_vector(conn)
        touches = {}
        for case in cases:
            masked = mask_pii(case.question).text
            found = search(conn, masked, embed(masked), embed.model_name)
            touches[case.id] = any(c.slug in PILOT_POLICIES for c in found)

    with_answer = [
        c.id for c in cases if c.has_answer and c.expected_sources[0][0] in PILOT_POLICIES
    ]
    without = [c.id for c in cases if not c.has_answer and touches[c.id]]
    print(f"recorte: {len(with_answer)} com base, {len(without)} sem base")
    for name, run in runs.items():
        answered = sum(run[i]["outcome"] == "answered" for i in with_answer)
        source_ok = sum(run[i]["source_ok"] is True for i in with_answer)
        wrong = [i for i in without if run[i]["outcome"] == "answered"]
        decision = sum(run[i]["decision_ok"] for i in with_answer + without)
        # Acima de 1 s: o modelo foi chamado (sem ele, a resposta sai em milissegundos).
        times = [run[i]["latency_ms"] for i in with_answer + without if run[i]["latency_ms"] > 1000]
        print(f"\n{name}")
        print(f"  com base respondeu: {answered}/{len(with_answer)}; fonte certa: {source_ok}")
        print(f"  sem base respondeu (erro): {len(wrong)}/{len(without)} {wrong}")
        print(f"  decisão certa: {decision}/{len(with_answer) + len(without)}")
        print(f"  tempo mediano com o modelo: {statistics.median(times) / 1000:.1f} s")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(
            "uso: python -m vaultpay_copilot.evaluation.pilot_report <base.json> <piloto.json>"
        )
    main(Path(sys.argv[1]), Path(sys.argv[2]))
