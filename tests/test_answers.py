from pathlib import Path

import pytest

from vaultpay_copilot.rag.answers import LIBRARY, ApprovedAnswer, candidates, load_library
from vaultpay_copilot.rag.retriever import RetrievedChunk

POLICIES = Path(__file__).resolve().parents[1] / "data" / "policies"


def chunk(slug: str, article: str, n: int = 1) -> RetrievedChunk:
    return RetrievedChunk(n, slug, "Título", n, f"Título\n{article}\nTexto.", 0.85)


def write_library(tmp_path, *rows: str) -> Path:
    path = tmp_path / "respostas.csv"
    path.write_text("\n".join(["id;resposta;fontes", *rows]), encoding="utf-8")
    return path


@pytest.mark.parametrize(("name", "total"), [("respostas-v1.csv", 25), ("respostas-v2.csv", 71)])
def test_a_biblioteca_publicada_le_sem_erro_e_toda_fonte_existe(name, total):
    library = load_library(LIBRARY.parent / name)

    assert len(library) == total
    for answer in library.values():
        for slug, article in answer.sources:
            text = (POLICIES / f"{slug}.md").read_text(encoding="utf-8")
            assert f"## Art. {article}." in text, (answer.id, slug, article)


def test_le_varias_fontes(tmp_path):
    library = load_library(
        write_library(tmp_path, "R001;Texto.;politica-pix, Art. 2 | tabela-tarifas, Art. 1")
    )

    assert library["R001"].sources == (("politica-pix", 2), ("tabela-tarifas", 1))


@pytest.mark.parametrize(
    ("row", "error"),
    [
        ("X1;Texto.;politica-pix, Art. 2", "formato R000"),
        ("R001;  ;politica-pix, Art. 2", "vazia"),
        ("R001;Texto.;politica-pix Art 2", "fonte fora do formato"),
        ("R001;Texto.;", "fonte fora do formato"),
    ],
)
def test_recusa_linha_mal_formada(tmp_path, row, error):
    with pytest.raises(ValueError, match=error):
        load_library(write_library(tmp_path, row))


def test_recusa_id_repetido(tmp_path):
    path = write_library(tmp_path, "R001;A.;politica-pix, Art. 2", "R001;B.;politica-pix, Art. 3")

    with pytest.raises(ValueError, match="repetido"):
        load_library(path)


A = ApprovedAnswer("R001", "Limite.", (("politica-pix", 2),))
B = ApprovedAnswer("R002", "Chaves.", (("politica-pix", 3),))
C = ApprovedAnswer("R003", "Limite e tarifa.", (("politica-pix", 2), ("tabela-tarifas", 1)))
LIB = {a.id: a for a in (A, B, C)}


def test_candidatas_sao_as_respostas_dos_artigos_achados_na_ordem_da_busca():
    chunks = [
        chunk("tabela-tarifas", "Art. 1. Gratuitos"),
        chunk("politica-pix", "Art. 2. Limites"),
    ]

    assert candidates(LIB, chunks) == [C, A]


def test_artigo_sem_resposta_na_biblioteca_nao_gera_candidata():
    assert candidates(LIB, [chunk("politica-cartao", "Art. 6. Compra")]) == []
