"""Human-in-the-loop: quem pode decidir, execução determinística, tudo-ou-nada e idempotência."""

import pytest

from app.core.errors import Conflict, Forbidden
from app.modules.approvals import service
from app.modules.approvals.models import ProposalKind, ProposalStatus
from app.modules.events.models import Room, Session, SessionStatus
from app.modules.notifications.models import Notification
from app.modules.tickets import service as tickets
from app.modules.tickets.models import Ticket, TicketStatus
from tests.conftest import future


def _plan(db, world, steps):
    return service.create_proposal(db, kind=ProposalKind.ACTION_PLAN, requested_by=world["users"]["org"], title="Plano",
                                   payload={"steps": steps}, event_id=world["event"].id)


def test_l2_only_owner_confirms(db, world):
    u = world["users"]
    t = tickets.issue_ticket(db, user=u["alice"], session_id=world["sessions"]["S1"].id)
    p = service.create_proposal(db, kind=ProposalKind.CANCEL_TICKET, requested_by=u["alice"], title="Cancelar", payload={"ticket_id": t.id}, event_id=t.event_id)
    db.commit()
    with pytest.raises(Forbidden):
        service.decide(db, p.id, user=u["bob"], approve=True)
    with pytest.raises(Forbidden):
        service.decide(db, p.id, user=u["org"], approve=True)  # nem o organizador confirma pelo participante
    service.decide(db, p.id, user=u["alice"], approve=True)
    db.commit()
    assert p.status == ProposalStatus.EXECUTED
    assert db.get(Ticket, t.id).status == TicketStatus.CANCELLED


def test_l3_only_organizer_of_the_event(db, world):
    p = _plan(db, world, [{"type": "MARK_ROOM_UNAVAILABLE", "room_name": "Sala B", "reason": "sem energia"}])
    db.commit()
    for who in ("org2", "alice", "staff"):  # organizador de outro evento, participante, staff
        with pytest.raises(Forbidden):
            service.decide(db, p.id, user=world["users"][who], approve=True)
    service.decide(db, p.id, user=world["users"]["org"], approve=True)
    db.commit()
    assert p.status == ProposalStatus.EXECUTED and db.get(Room, world["rooms"]["Sala B"].id).available is False


def test_plan_reschedules_and_notifies_affected(db, world):
    u, s = world["users"], world["sessions"]
    for n in ("alice", "bob"):
        tickets.issue_ticket(db, user=u[n], session_id=s["M2"].id)
    p = _plan(db, world, [
        {"type": "RESCHEDULE_SESSION", "session_code": "M2", "start_at": future(12, "14:00").isoformat(), "end_at": future(12, "18:00").isoformat()},
        {"type": "NOTIFY_PARTICIPANTS", "session_codes": ["M2"], "title": "Mudança de horário", "body": "O minicurso M2 mudou para o último dia, 14h."},
    ])
    db.commit()
    service.decide(db, p.id, user=u["org"], approve=True)
    db.commit()
    db.expire_all()
    assert p.status == ProposalStatus.EXECUTED
    assert db.get(Session, s["M2"].id).start_at == future(12, "14:00")
    assert db.query(Notification).count() == 2
    with pytest.raises(Conflict):
        service.decide(db, p.id, user=u["org"], approve=True)  # decidir de novo não executa de novo
    assert db.query(Notification).count() == 2


def test_plan_is_all_or_nothing(db, world):
    u, s = world["users"], world["sessions"]
    tickets.issue_ticket(db, user=u["alice"], session_id=s["S1"].id)
    p = _plan(db, world, [
        {"type": "CANCEL_SESSION", "session_code": "S1", "reason": "palestrante cancelou"},
        {"type": "CHANGE_ROOM", "session_code": "S2", "room_name": "Lab"},  # Lab já está ocupado? não; mas é pequeno demais? S2 vazio -> ok
        {"type": "CHANGE_ROOM", "session_code": "M3", "room_name": "Sala Inexistente"},  # falha
    ])
    db.commit()
    service.decide(db, p.id, user=u["org"], approve=True)
    db.commit()
    db.expire_all()
    assert p.status == ProposalStatus.FAILED and "not found" in p.error
    assert db.get(Session, s["S1"].id).status == SessionStatus.PUBLISHED  # o 1º passo foi desfeito
    assert db.query(Ticket).filter(Ticket.status == TicketStatus.CANCELLED).count() == 0


def test_dry_run_validates_without_side_effects(db, world):
    s = world["sessions"]
    result = service.dry_run_plan(db, world["event"].id, [
        {"type": "CHANGE_ROOM", "session_code": "S2", "room_name": "Sala A"},  # Sala A ocupada pela S1 no horário
    ], actor=world["users"]["org"])
    assert result["valid"] is False and result["errors"][0]["code"] == "room_busy"
    ok = service.dry_run_plan(db, world["event"].id, [{"type": "CANCEL_SESSION", "session_code": "S1", "reason": "teste"}], actor=world["users"]["org"])
    assert ok["valid"] is True
    db.expire_all()
    assert db.get(Session, s["S1"].id).status == SessionStatus.PUBLISHED


def test_cancel_session_cascades_and_notifies_cancelled(db, world):
    u, s = world["users"], world["sessions"]
    tickets.issue_ticket(db, user=u["alice"], session_id=s["S1"].id)
    p = _plan(db, world, [
        {"type": "CANCEL_SESSION", "session_code": "S1", "reason": "palestrante cancelou"},
        {"type": "NOTIFY_PARTICIPANTS", "session_codes": ["S1"], "title": "Sessão cancelada", "body": "A sessão S1 foi cancelada pela comissão."},
    ])
    db.commit()
    service.decide(db, p.id, user=u["org"], approve=True)
    db.commit()
    assert p.result["steps"][0]["tickets_cancelled"] == 1
    assert p.result["steps"][1]["recipients"] == 1


def test_invalid_step_schema_is_reported(db, world):
    r = service.dry_run_plan(db, world["event"].id, [{"type": "DELETE_EVERYTHING"}], actor=world["users"]["org"])
    assert r["valid"] is False
