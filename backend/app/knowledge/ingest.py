"""Ingestão de documentos Markdown: um trecho por seção (## ou ###), com número de seção para citação."""

import re

from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.core.database import utcnow
from app.knowledge.models import KnowledgeChunk, KnowledgeDocument
from app.knowledge.text import normalize

_HEADING = re.compile(r"^(#{1,3})\s+(.*)$")
_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(.*)$")


def split_sections(markdown: str) -> list[dict]:
    sections, current = [], None
    for line in markdown.splitlines():
        m = _HEADING.match(line)
        if m and len(m.group(1)) >= 2:
            if current and current["content"].strip():
                sections.append(current)
            heading = m.group(2).strip()
            num = _NUMBER.match(heading)
            current = {"section": num.group(1) if num else str(len(sections) + 1), "heading": num.group(2) if num else heading, "content": ""}
        elif current is not None:
            current["content"] += line + "\n"
    if current and current["content"].strip():
        sections.append(current)
    return sections


def ingest_document(
    db: DbSession, *, event_id: str, source_id: str, title: str, source_path: str, content: str, trust: str = "OFFICIAL", uploaded_by: str | None = None
) -> KnowledgeDocument:
    """Uma nova versão do mesmo source_id torna a anterior SUPERSEDED (validade do contexto)."""
    previous = db.scalar(
        select(KnowledgeDocument.version).where(KnowledgeDocument.event_id == event_id, KnowledgeDocument.source_id == source_id).order_by(KnowledgeDocument.version.desc())
    )
    db.execute(
        update(KnowledgeDocument)
        .where(KnowledgeDocument.event_id == event_id, KnowledgeDocument.source_id == source_id, KnowledgeDocument.status == "ACTIVE")
        .values(status="SUPERSEDED")
    )
    doc = KnowledgeDocument(event_id=event_id, source_id=source_id, title=title, source_path=source_path, content=content,
                            trust=trust, uploaded_by=uploaded_by, version=(previous or 0) + 1, updated_at=utcnow())
    for s in split_sections(content):
        body = s["content"].strip()
        doc.chunks.append(KnowledgeChunk(event_id=event_id, section=s["section"], heading=s["heading"], content=body,
                                         search_text=normalize(f"{s['heading']} {body}")))
    db.add(doc)
    db.flush()
    return doc
