"""Testes rodam contra um PostgreSQL real (banco academic_events_test), porque as regras dependem
dele: UPDATE condicional, índice único parcial, full-text search e statement_timeout."""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core import database

TEST_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://academic:academic_pass@localhost:5432/academic_events_test")
TZ = ZoneInfo("America/Campo_Grande")


def _ensure_database(url: str) -> None:
    u = make_url(url)
    with psycopg.connect(host=u.host, port=u.port or 5432, user=u.username, password=u.password, dbname="postgres", autocommit=True) as conn:
        if not conn.execute("select 1 from pg_database where datname = %s", (u.database,)).fetchone():
            conn.execute(f'create database "{u.database}"')


@pytest.fixture(scope="session", autouse=True)
def _database():
    _ensure_database(TEST_URL)
    database.configure(TEST_URL)
    import app.models  # noqa: F401

    database.Base.metadata.drop_all(database.engine())
    database.create_all()
    yield


@pytest.fixture(autouse=True)
def _clean():
    tables = ", ".join(t.name for t in reversed(database.Base.metadata.sorted_tables))
    with database.engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    from app.agentic.providers import set_model_override

    set_model_override(None)
    yield


@pytest.fixture
def db():
    s = database.session_factory()()
    yield s
    s.rollback()
    s.close()


def future(days: int = 10, hm: str = "08:00") -> datetime:
    h, m = map(int, hm.split(":"))
    base = datetime.now(TZ).replace(hour=h, minute=m, second=0, microsecond=0)
    return base + timedelta(days=days)


@pytest.fixture
def world(db):
    """Mundo pequeno e conhecido: 1 evento, 3 salas, 2 palestrantes, 5 sessões, 2 organizadores, participantes."""
    from app.core.security import hash_password
    from app.modules.auth.models import Role, User
    from app.modules.events.models import Event, Room, Session, SessionKind, Speaker

    pwd = hash_password("x")
    users = {
        key: User(name=key.title(), email=f"{key}@t.dev", password_hash=pwd, role=role)
        for key, role in [("org", Role.ORGANIZER), ("org2", Role.ORGANIZER), ("staff", Role.STAFF), ("admin", Role.ADMIN),
                          ("alice", Role.PARTICIPANT), ("bob", Role.PARTICIPANT), ("carol", Role.PARTICIPANT)]
    }
    db.add_all(users.values())
    db.flush()
    ev = Event(slug="evt-test", title="Evento Teste", location="FACOM", start_at=future(10, "07:00"), end_at=future(12, "20:00"), max_minicursos_per_participant=2)
    ev.organizers.extend([users["org"], users["staff"]])
    other = Event(slug="evt-other", title="Outro Evento", location="X", start_at=future(20, "07:00"), end_at=future(21, "20:00"))
    other.organizers.append(users["org2"])
    db.add_all([ev, other])
    db.flush()
    rooms = {n: Room(event_id=ev.id, name=n, capacity=c) for n, c in [("Sala A", 50), ("Sala B", 50), ("Lab", 3)]}
    spk = {n: Speaker(event_id=ev.id, name=n) for n in ["Dra. Helena", "Prof. Caio"]}
    db.add_all([*rooms.values(), *spk.values()])
    db.flush()

    def mk(code, kind, day, start, end, room, cap, speakers):
        s = Session(event_id=ev.id, code=code, title=f"Sessão {code}", kind=kind, room_id=rooms[room].id, start_at=future(day, start),
                    end_at=future(day, end), max_capacity=cap, available_spots=cap, speakers=[spk[n] for n in speakers])
        db.add(s)
        return s

    sessions = {
        "S1": mk("S1", SessionKind.PALESTRA, 10, "08:00", "10:00", "Sala A", 40, ["Dra. Helena"]),
        "S2": mk("S2", SessionKind.PALESTRA, 10, "09:00", "11:00", "Sala B", 40, ["Prof. Caio"]),  # conflita com S1
        "M1": mk("M1", SessionKind.MINICURSO, 11, "08:00", "12:00", "Lab", 3, ["Prof. Caio"]),
        "M2": mk("M2", SessionKind.MINICURSO, 11, "14:00", "18:00", "Sala A", 10, ["Dra. Helena"]),
        "M3": mk("M3", SessionKind.MINICURSO, 12, "08:00", "12:00", "Sala B", 10, ["Prof. Caio"]),
    }
    other_room = Room(event_id=other.id, name="Sala Z", capacity=10)
    db.add(other_room)
    db.commit()
    return {"event": ev, "other": other, "users": users, "rooms": rooms, "speakers": spk, "sessions": sessions}
