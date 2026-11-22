"""Cadastro de eventos: só administradores, evento + programação numa única transação."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import create_token
from app.main import app
from app.modules.events.models import Event, Session
from tests.conftest import future


def _payload(**over):
    body = {
        "slug": "evt-novo",
        "title": "Evento Novo",
        "location": "Bloco B",
        "start_at": future(30, "08:00").isoformat(),
        "end_at": future(31, "18:00").isoformat(),
        "sessions": [
            {"code": "P01", "title": "Abertura", "start_at": future(30, "09:00").isoformat(), "end_at": future(30, "10:00").isoformat(), "max_capacity": 100},
            {"code": "M01", "title": "Minicurso de Python", "kind": "MINICURSO", "start_at": future(31, "08:00").isoformat(),
             "end_at": future(31, "12:00").isoformat(), "max_capacity": 20, "workload_hours": 4},
        ],
    }
    body.update(over)
    return body


def _post(world, user_key, role, body):
    token = create_token(world["users"][user_key].id, role)
    return TestClient(app).post("/events", json=body, headers={"Authorization": f"Bearer {token}"})


def test_admin_creates_event_with_sessions(db, world):
    resp = _post(world, "admin", "admin", _payload())
    assert resp.status_code == 201, resp.text
    event_id = resp.json()["id"]
    sessions = list(db.scalars(select(Session).where(Session.event_id == event_id)))
    assert sorted(s.code for s in sessions) == ["M01", "P01"]
    assert all(s.available_spots == s.max_capacity for s in sessions)


def test_only_admin_can_create_event(db, world):
    for key, role in [("org", "organizer"), ("staff", "staff"), ("alice", "participant")]:
        assert _post(world, key, role, _payload()).status_code == 403
    assert db.scalar(select(Event).where(Event.slug == "evt-novo")) is None


def test_invalid_session_rolls_back_whole_event(db, world):
    body = _payload()
    body["sessions"][1]["end_at"] = future(40, "12:00").isoformat()  # fora do período do evento
    resp = _post(world, "admin", "admin", body)
    assert resp.status_code in (400, 409, 422)
    assert db.scalar(select(Event).where(Event.slug == "evt-novo")) is None


def test_duplicate_session_code_is_rejected(db, world):
    body = _payload()
    body["sessions"][1]["code"] = "p01"
    assert _post(world, "admin", "admin", body).status_code in (400, 409, 422)
    assert db.scalar(select(Event).where(Event.slug == "evt-novo")) is None
