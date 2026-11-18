"""Busca lexical (full-text PostgreSQL) com escopo e proveniência.

O escopo (event_id) e a validade (somente documentos ACTIVE) são aplicados no SQL,
nunca no prompt: o agente não consegue recuperar trechos de outro evento."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.knowledge.models import KnowledgeChunk, KnowledgeDocument
from app.knowledge.text import terms


def search(db: DbSession, *, event_id: str, query: str, limit: int = 4) -> list[dict]:
    words = terms(query)
    if not words:
        return []
    tsquery = func.to_tsquery("portuguese", " | ".join(words))
    rank = func.ts_rank_cd(KnowledgeChunk.tsv, tsquery).label("rank")
    stmt = (
        select(KnowledgeChunk, KnowledgeDocument, rank)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(
            KnowledgeChunk.event_id == event_id,
            KnowledgeDocument.event_id == event_id,
            KnowledgeDocument.status == "ACTIVE",
            KnowledgeChunk.tsv.op("@@")(tsquery),
        )
        .order_by(rank.desc())
        .limit(limit)
    )
    out = []
    for chunk, doc, score in db.execute(stmt):
        out.append(
            {
                "chunk_id": chunk.id,
                "section": chunk.section,
                "heading": chunk.heading,
                "content": chunk.content,
                "score": round(float(score), 4),
                "evidence": {
                    "source_id": doc.source_id,
                    "title": doc.title,
                    "section": chunk.section,
                    "version": doc.version,
                    "updated_at": doc.updated_at.date().isoformat(),
                    "trust": doc.trust,
                    "source_path": doc.source_path,
                },
            }
        )
    return out


def list_documents(db: DbSession, event_id: str, include_superseded: bool = False) -> list[KnowledgeDocument]:
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.event_id == event_id)
    if not include_superseded:
        stmt = stmt.where(KnowledgeDocument.status == "ACTIVE")
    return list(db.scalars(stmt.order_by(KnowledgeDocument.title)))
