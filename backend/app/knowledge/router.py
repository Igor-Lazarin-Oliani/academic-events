from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.core.deps import ensure_can_manage_event, require_roles
from app.knowledge import graph, search
from app.knowledge.ingest import ingest_document
from app.modules.auth.models import User
from app.modules.events.service import get_event

router = APIRouter(tags=["knowledge"])
manager = require_roles("organizer", "admin")


class DocumentOut(BaseModel):
    id: str
    source_id: str
    title: str
    source_path: str
    version: int
    status: str
    trust: str
    updated_at: datetime
    sections: int


class DocumentIn(BaseModel):
    source_id: str = Field(pattern=r"^[A-Z0-9-]{3,40}$")
    title: str
    content: str = Field(min_length=20)
    trust: str = Field(default="OFFICIAL", pattern="^(OFFICIAL|UNVERIFIED)$")


@router.get("/events/{event_id}/knowledge", response_model=list[DocumentOut])
def list_docs(event_id: str, include_superseded: bool = False, db: DbSession = Depends(get_db)):
    event = get_event(db, event_id)
    return [DocumentOut(id=d.id, source_id=d.source_id, title=d.title, source_path=d.source_path, version=d.version, status=d.status,
                        trust=d.trust, updated_at=d.updated_at, sections=len(d.chunks))
            for d in search.list_documents(db, event.id, include_superseded)]


@router.post("/events/{event_id}/knowledge", response_model=DocumentOut, status_code=201)
def upload_doc(event_id: str, body: DocumentIn, user: User = Depends(manager), db: DbSession = Depends(get_db)):
    event = get_event(db, event_id)
    ensure_can_manage_event(db, user, event.id)
    d = ingest_document(db, event_id=event.id, source_id=body.source_id, title=body.title, source_path=f"upload/{body.source_id}.md",
                        content=body.content, trust=body.trust, uploaded_by=user.id)
    db.commit()
    return DocumentOut(id=d.id, source_id=d.source_id, title=d.title, source_path=d.source_path, version=d.version, status=d.status,
                       trust=d.trust, updated_at=d.updated_at, sections=len(d.chunks))


@router.get("/events/{event_id}/knowledge/search")
def search_docs(event_id: str, q: str, db: DbSession = Depends(get_db)):
    event = get_event(db, event_id)
    return search.search(db, event_id=event.id, query=q)


@router.get("/events/{event_id}/graph")
def event_graph(event_id: str, user: User = Depends(manager), db: DbSession = Depends(get_db)):
    event = get_event(db, event_id)
    ensure_can_manage_event(db, user, event.id)
    return graph.build_graph(db, event.id)


@router.get("/events/{event_id}/graph/impact")
def event_impact(event_id: str, node_type: str, key: str, start: datetime | None = None, end: datetime | None = None,
                 user: User = Depends(manager), db: DbSession = Depends(get_db)):
    event = get_event(db, event_id)
    ensure_can_manage_event(db, user, event.id)
    return graph.impact(db, event.id, node_type=node_type, key=key, start=start, end=end)


@router.get("/events/{event_id}/knowledge/{doc_id}")
def get_doc(event_id: str, doc_id: str, db: DbSession = Depends(get_db)):
    from app.core.errors import NotFound
    from app.knowledge.models import KnowledgeDocument

    event = get_event(db, event_id)
    d = db.get(KnowledgeDocument, doc_id)
    if not d or d.event_id != event.id:
        raise NotFound("Document not found")
    return {"id": d.id, "source_id": d.source_id, "title": d.title, "version": d.version, "status": d.status, "trust": d.trust,
            "updated_at": d.updated_at, "content": d.content}
