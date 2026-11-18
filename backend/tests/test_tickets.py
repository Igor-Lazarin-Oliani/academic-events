"""Regras de inscrição portadas do events-tickets-ms (D1, D2, D3) e as novas (conflito, limite, troca)."""

import threading

import pytest

from app.core import database
from app.core.errors import Conflict, DomainError, Forbidden
from app.modules.events.models import Session, SessionStatus
from app.modules.tickets import service
from app.modules.tickets.models import Ticket, TicketStatus


def spots(db, s):
    db.expire_all()
    return db.get(Session, s.id)


def test_issue_reserves_spot_and_sells_out(db, world):
    u, m1 = world["users"], world["sessions"]["M1"]
    for name in ("alice", "bob", "carol"):
        service.issue_ticket(db, user=u[name], session_id=m1.id)
    db.commit()
    s = spots(db, m1)
    assert s.available_spots == 0 and s.status == SessionStatus.SOLD_OUT
    with pytest.raises(Conflict) as exc:
        service.issue_ticket(db, user=u["org"], session_id=m1.id)
    assert exc.value.code == "sold_out"


def test_concurrent_registrations_never_oversell(world):
    """12 inscrições simultâneas numa sala com 3 vagas: exatamente 3 conseguem (pool padrão = 15 conexões)."""
    from app.core.security import hash_password
    from app.modules.auth.models import User

    with database.session_factory()() as db:
        users = [User(name=f"u{i}", email=f"u{i}@t.dev", password_hash=hash_password("x")) for i in range(12)]
        db.add_all(users)
        db.commit()
        ids = [x.id for x in users]
    m1_id = world["sessions"]["M1"].id
    ok, sold_out, barrier = [], [], threading.Barrier(12, timeout=30)

    def worker(uid):
        with database.session_factory()() as s:
            user = s.get(User, uid)
            barrier.wait()
            try:
                service.issue_ticket(s, user=user, session_id=m1_id)
                s.commit()
                ok.append(uid)
            except Conflict:
                s.rollback()
                sold_out.append(uid)

    threads = [threading.Thread(target=worker, args=(i,)) for i in ids]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(ok) == 3 and len(sold_out) == 9
    with database.session_factory()() as s:
        assert s.get(Session, m1_id).available_spots == 0


def test_issue_is_idempotent_by_ticket_id(db, world):
    u, s1 = world["users"]["alice"], world["sessions"]["S1"]
    t1 = service.issue_ticket(db, user=u, session_id=s1.id, ticket_id="11111111-1111-4111-8111-111111111111")
    t2 = service.issue_ticket(db, user=u, session_id=s1.id, ticket_id="11111111-1111-4111-8111-111111111111")
    db.commit()
    assert t1.id == t2.id
    assert spots(db, s1).available_spots == 39


def test_time_conflict_is_rejected(db, world):
    u = world["users"]["alice"]
    service.issue_ticket(db, user=u, session_id=world["sessions"]["S1"].id)
    with pytest.raises(Conflict) as exc:
        service.issue_ticket(db, user=u, session_id=world["sessions"]["S2"].id)
    assert exc.value.code == "time_conflict" and exc.value.details["conflicting_session"] == "S1"


def test_minicurso_limit(db, world):
    u, s = world["users"]["alice"], world["sessions"]
    service.issue_ticket(db, user=u, session_id=s["M1"].id)
    service.issue_ticket(db, user=u, session_id=s["M2"].id)
    with pytest.raises(Conflict) as exc:
        service.issue_ticket(db, user=u, session_id=s["M3"].id)
    assert exc.value.code == "minicurso_limit"


def test_cancel_releases_spot_once_and_reopens_session(db, world):
    u, m1 = world["users"], world["sessions"]["M1"]
    tickets = [service.issue_ticket(db, user=u[n], session_id=m1.id) for n in ("alice", "bob", "carol")]
    db.commit()
    service.cancel_ticket(db, tickets[0], actor=u["alice"])
    db.commit()
    s = spots(db, m1)
    assert s.available_spots == 1 and s.status == SessionStatus.PUBLISHED
    with pytest.raises(Conflict):
        service.cancel_ticket(db, tickets[0], actor=u["alice"])  # D1: não devolve 2x
    assert spots(db, m1).available_spots == 1


def test_checkin_only_from_confirmed_and_checked_in_cannot_cancel(db, world):
    u = world["users"]
    t = service.issue_ticket(db, user=u["alice"], session_id=world["sessions"]["S1"].id)
    db.commit()
    service.check_in(db, code=t.ticket_code, actor=u["staff"])
    db.commit()
    with pytest.raises(Conflict):
        service.check_in(db, code=t.ticket_code, actor=u["staff"])
    with pytest.raises(Conflict) as exc:
        service.cancel_ticket(db, t, actor=u["alice"])
    assert exc.value.code == "already_checked_in"


def test_swap_is_atomic(db, world):
    u, s = world["users"], world["sessions"]
    for n in ("bob", "carol", "org"):
        service.issue_ticket(db, user=u[n], session_id=s["M1"].id)  # lota o M1
    t = service.issue_ticket(db, user=u["alice"], session_id=s["M2"].id)
    db.commit()
    with pytest.raises(DomainError):
        service.swap_session(db, user=u["alice"], ticket=t, to_session_id=s["M1"].id)
    db.rollback()
    db.expire_all()
    assert db.get(Ticket, t.id).status == TicketStatus.CONFIRMED  # a inscrição original foi mantida

    new = service.swap_session(db, user=u["alice"], ticket=db.get(Ticket, t.id), to_session_id=s["M3"].id)
    db.commit()
    assert db.get(Ticket, t.id).status == TicketStatus.CANCELLED and new.session_id == s["M3"].id


def test_participant_cannot_read_someone_elses_ticket(db, world):
    u = world["users"]
    t = service.issue_ticket(db, user=u["alice"], session_id=world["sessions"]["S1"].id)
    db.commit()
    with pytest.raises(Forbidden) as exc:
        service.get_own_ticket(db, u["bob"], t.ticket_code)
    assert exc.value.code == "ticket_out_of_scope"


def test_activity_is_recorded_with_the_change(db, world):
    from app.modules.activity.service import list_logs

    t = service.issue_ticket(db, user=world["users"]["alice"], session_id=world["sessions"]["S1"].id)
    db.commit()
    actions = {l.action for l in list_logs(db, entity_id=t.id)}
    assert actions == {"ticket.issued"}
