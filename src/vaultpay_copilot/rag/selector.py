"""Atendente por escolha (ADR 0005, piloto): o modelo escolhe uma resposta aprovada, não escreve.

Mesmas travas do atendente que gera texto, adaptadas:
Trava 1: nenhum trecho parecido o bastante, ou nenhuma resposta aprovada ligada aos trechos
achados: encaminha sem chamar o modelo.
Trava 2: a saída do modelo precisa estar no formato combinado (LlmChoice).
Trava 3: o id escolhido precisa ser uma das candidatas que o modelo recebeu.
O cliente só lê textos da biblioteca: o modelo não tem como inventar uma regra.
"""

from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, ConfigDict, ValidationError

from vaultpay_copilot.rag.answers import ApprovedAnswer, candidates
from vaultpay_copilot.rag.assistant import ESCALATION_TEXT, UNAVAILABLE_TEXT, Llm, Reply, Retrieve
from vaultpay_copilot.rag.llm import LlmUnavailable
from vaultpay_copilot.rag.pii import mask_pii
from vaultpay_copilot.rag.retriever import chunk_source

PROMPT_VERSION = "select-v1"
_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text(
    encoding="utf-8"
)


class LlmChoice(BaseModel):
    """O formato que o modelo é obrigado a devolver."""

    model_config = ConfigDict(extra="forbid")

    answer_id: str | None


def choice_schema(options: list[ApprovedAnswer]) -> dict:
    # O Ollama restringe a saída a este formato: só ids das candidatas, ou null.
    return {
        "type": "object",
        "properties": {
            "answer_id": {
                "anyOf": [{"type": "string", "enum": [a.id for a in options]}, {"type": "null"}]
            }
        },
        "required": ["answer_id"],
        "additionalProperties": False,
    }


def build_choice_message(masked_question: str, options: list[ApprovedAnswer]) -> str:
    listed = "\n".join(f"[{a.id}] {a.text}" for a in options)
    # Sem < e > no texto do cliente, ele não consegue fechar as marcações e se passar por regra.
    question = masked_question.replace("<", "(").replace(">", ")")
    return f"<respostas>\n{listed}\n</respostas>\n\n<pergunta>\n{question}\n</pergunta>"


def select(
    question: str,
    retrieve: Retrieve,
    llm: Llm,
    min_similarity: float,
    library: dict[str, ApprovedAnswer],
) -> Reply:
    start = perf_counter()
    masking = mask_pii(question)
    masked = masking.text

    def reply(outcome, text: str, **extra) -> Reply:
        latency_ms = round((perf_counter() - start) * 1000)
        found = tuple(sorted(masking.found))
        return Reply(
            outcome,
            text,
            masked,
            latency_ms=latency_ms,
            pii_found=found,
            prompt_version=PROMPT_VERSION,
            **extra,
        )

    chunks = retrieve(masked)
    # Trava 1, como no atendente que gera texto (olha a maior similaridade).
    if not chunks or max(c.similarity for c in chunks) < min_similarity:
        return reply("escalated", ESCALATION_TEXT, reason="no_context")
    options = candidates(library, chunks)
    if not options:
        return reply("escalated", ESCALATION_TEXT, reason="no_context")

    try:
        raw = llm.chat(
            _SYSTEM_PROMPT, build_choice_message(masked, options), choice_schema(options)
        )
    except LlmUnavailable:
        return reply("error", UNAVAILABLE_TEXT, reason="service_unavailable", llm_model=llm.model)

    # Trava 2
    try:
        parsed = LlmChoice.model_validate_json(raw)
    except ValidationError:
        return reply("escalated", ESCALATION_TEXT, reason="low_confidence", llm_model=llm.model)
    if parsed.answer_id is None:
        return reply("escalated", ESCALATION_TEXT, reason="no_context", llm_model=llm.model)

    # Trava 3
    chosen = next((a for a in options if a.id == parsed.answer_id), None)
    if chosen is None:
        return reply("escalated", ESCALATION_TEXT, reason="low_confidence", llm_model=llm.model)

    sources = [c for c in chunks if chunk_source(c) in chosen.sources]
    return reply("answered", chosen.text, sources=sources, llm_model=llm.model)
