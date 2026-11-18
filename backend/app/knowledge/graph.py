"""Grafo do evento, projetado a partir das tabelas relacionais.

Nós: event, session, room, speaker, track. Arestas: HAS_SESSION, HELD_IN, PRESENTED_BY, BELONGS_TO.
Os participantes entram como atributo agregado da sessão (contagem), nunca como dados pessoais.
A análise de impacto percorre o grafo e devolve o caminho e a evidência de cada sessão afetada."""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession, selectinload

from app.core.errors import NotFound
from app.knowledge.text import normalize
from app.modules.events.models import Event, Room, Session, SessionStatus, Speaker
from app.modules.tickets.models import Ticket, TicketStatus


def _sessions(db: DbSession, event_id: str) -> list[Session]:
    return list(db.scalars(
        select(Session).where(Session.event_id == event_id).options(selectinload(Session.room), selectinload(Session.speakers)).order_by(Session.start_at)
    ))


def build_graph(db: DbSession, event_id: str) -> dict:
    event = db.get(Event, event_id)
    if not event:
        raise NotFound("Event not found")
    sessions = _sessions(db, event_id)
    counts = dict(db.execute(
        select(Ticket.session_id, func.count(Ticket.id)).where(Ticket.event_id == event_id, Ticket.status != TicketStatus.CANCELLED).group_by(Ticket.session_id)
    ).all())
    nodes, edges = {}, []

    def node(nid, ntype, label, **attrs):
        nodes.setdefault(nid, {"id": nid, "type": ntype, "label": label, "attrs": attrs})

    node(f"event:{event.id}", "event", event.title)
    for r in db.scalars(select(Room).where(Room.event_id == event_id)):
        node(f"room:{r.id}", "room", r.name, capacity=r.capacity, available=r.available, building=r.building)
    for s in sessions:
        sid = f"session:{s.id}"
        node(sid, "session", f"{s.code} · {s.title}", code=s.code, kind=s.kind, status=s.status, start_at=s.start_at.isoformat(),
             end_at=s.end_at.isoformat(), registrations=counts.get(s.id, 0), capacity=s.max_capacity)
        edges.append({"source": f"event:{event.id}", "target": sid, "relation": "HAS_SESSION"})
        if s.room:
            edges.append({"source": sid, "target": f"room:{s.room.id}", "relation": "HELD_IN"})
        for sp in s.speakers:
            node(f"speaker:{sp.id}", "speaker", sp.name, affiliation=sp.affiliation)
            edges.append({"source": sid, "target": f"speaker:{sp.id}", "relation": "PRESENTED_BY"})
        node(f"track:{s.track}", "track", s.track)
        edges.append({"source": sid, "target": f"track:{s.track}", "relation": "BELONGS_TO"})
    return {"nodes": list(nodes.values()), "edges": edges}


def resolve_node(db: DbSession, event_id: str, node_type: str, key: str) -> tuple[str, str]:
    """Aceita nomes legíveis ("Sala 105", "S12", "Dra. Helena") e devolve (id do nó, rótulo)."""
    k = normalize(key.strip())
    if node_type == "session":
        for s in _sessions(db, event_id):
            if normalize(s.code) == k or s.id == key or normalize(s.title) == k:
                return f"session:{s.id}", s.code
    elif node_type == "room":
        rooms = list(db.scalars(select(Room).where(Room.event_id == event_id)))
        for r in rooms:
            if normalize(r.name) == k or r.id == key:
                return f"room:{r.id}", r.name
        for r in rooms:
            if k in normalize(r.name):
                return f"room:{r.id}", r.name
    elif node_type == "speaker":
        for sp in db.scalars(select(Speaker).where(Speaker.event_id == event_id)):
            if k in normalize(sp.name) or sp.id == key:
                return f"speaker:{sp.id}", sp.name
    raise NotFound(f"{node_type} '{key}' not found in this event", code="node_not_found")


def impact(db: DbSession, event_id: str, *, node_type: str, key: str, start: datetime | None = None, end: datetime | None = None) -> dict:
    """Quem é afetado se o nó mudar? Sala/palestrante -> sessões ligadas a ele -> inscritos.
    De cada sessão afetada saem também os nós relacionados (outra sala, palestrantes)."""
    graph = build_graph(db, event_id)
    start_id, label = resolve_node(db, event_id, node_type, key)
    nodes = {n["id"]: n for n in graph["nodes"]}
    neighbors = defaultdict(list)  # só as arestas que propagam impacto
    for e in graph["edges"]:
        if e["relation"] in ("HELD_IN", "PRESENTED_BY"):
            neighbors[e["source"]].append((e["target"], e["relation"]))
            neighbors[e["target"]].append((e["source"], e["relation"]))

    def hop(a: str, b: str, rel: str) -> str:
        return f"{nodes[a]['label']} -{rel}- {nodes[b]['label']}"

    if node_type == "session":
        session_paths = {start_id: nodes[start_id]["label"]}
    else:
        session_paths = {sid: hop(start_id, sid, rel) for sid, rel in neighbors[start_id] if nodes[sid]["type"] == "session"}

    affected, related = [], {}
    for sid, path in session_paths.items():
        n = nodes[sid]
        if n["attrs"]["status"] == SessionStatus.CANCELLED:
            continue
        s_start, s_end = datetime.fromisoformat(n["attrs"]["start_at"]), datetime.fromisoformat(n["attrs"]["end_at"])
        if start and end and not (s_start < end and s_end > start):
            continue
        affected.append({
            "session_code": n["attrs"]["code"],
            "title": n["label"].split(" · ", 1)[-1],
            "start_at": n["attrs"]["start_at"],
            "end_at": n["attrs"]["end_at"],
            "registrations": n["attrs"]["registrations"],
            "path": path,
            "evidence": {"source": "sessions", "session_id": sid.split(":", 1)[1]},
        })
        for other, rel in neighbors[sid]:
            if other != start_id:
                related.setdefault(other, {"type": nodes[other]["type"], "label": nodes[other]["label"], "relation": rel, "via": n["attrs"]["code"]})

    affected.sort(key=lambda a: a["start_at"])
    session_ids = [a["evidence"]["session_id"] for a in affected]
    distinct = 0
    if session_ids:
        distinct = db.scalar(select(func.count(func.distinct(Ticket.user_id))).where(Ticket.session_id.in_(session_ids), Ticket.status != TicketStatus.CANCELLED))
    return {
        "node": {"type": node_type, "label": label},
        "window": {"start": start.isoformat() if start else None, "end": end.isoformat() if end else None},
        "affected_sessions": affected,
        "affected_participants": distinct,
        "related": list(related.values()),
    }
