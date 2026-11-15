"""Biblioteca de respostas aprovadas (ADR 0005): textos revisados pela Nathaly, cada um com fonte.

O atendente por escolha só entrega estes textos. Arquivo publicado é imutável: mudou, vira v2.
"""

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from vaultpay_copilot.rag.retriever import RetrievedChunk, chunk_source

Source = tuple[str, int]  # (slug da política, número do artigo)

LIBRARY = Path(__file__).resolve().parents[3] / "data" / "answers" / "respostas-v2.csv"
_ID = re.compile(r"R\d{3}")
_SOURCE = re.compile(r"([a-z0-9-]+), Art\. (\d+)")


@dataclass(frozen=True)
class ApprovedAnswer:
    id: str
    text: str
    sources: tuple[Source, ...]


def load_library(path: Path = LIBRARY) -> dict[str, ApprovedAnswer]:
    """Lê e confere a biblioteca. Erro de formato derruba na hora, nunca vira resposta."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    library: dict[str, ApprovedAnswer] = {}
    for row in rows:
        answer_id, text = row["id"].strip(), row["resposta"].strip()
        if not _ID.fullmatch(answer_id):
            raise ValueError(f"id fora do formato R000: {answer_id!r}")
        if answer_id in library:
            raise ValueError(f"id repetido na biblioteca: {answer_id}")
        if not text:
            raise ValueError(f"{answer_id}: resposta vazia")
        sources = []
        for part in row["fontes"].split("|"):
            match = _SOURCE.fullmatch(part.strip())
            if not match:
                raise ValueError(f"{answer_id}: fonte fora do formato 'slug, Art. N': {part!r}")
            sources.append((match.group(1), int(match.group(2))))
        library[answer_id] = ApprovedAnswer(answer_id, text, tuple(sources))
    return library


def candidates(
    library: dict[str, ApprovedAnswer], chunks: list[RetrievedChunk]
) -> list[ApprovedAnswer]:
    """Respostas ligadas aos artigos achados pela busca, na ordem dos trechos."""
    found = [chunk_source(c) for c in chunks]
    ranked = []
    for source in dict.fromkeys(found):
        ranked += [a for a in library.values() if source in a.sources and a not in ranked]
    return ranked
