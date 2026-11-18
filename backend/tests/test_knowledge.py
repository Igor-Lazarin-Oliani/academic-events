from app.knowledge import graph
from app.knowledge.ingest import ingest_document, split_sections
from app.knowledge.search import search
from app.modules.tickets import service as tickets
from tests.conftest import future

DOC = """# Regulamento

## 4. Certificados

### 4.1 Direito ao certificado

O certificado é emitido para quem fez o check-in.

### 4.2 Carga horária

Minicursos valem 4 horas de certificado.

## 5. Horários

O credenciamento abre às 7h30.
"""


def test_split_sections_keeps_numbers():
    secs = split_sections(DOC)
    assert [s["section"] for s in secs] == ["4.1", "4.2", "5"]
    assert secs[1]["heading"] == "Carga horária"


def test_search_returns_provenance_and_is_accent_insensitive(db, world):
    ingest_document(db, event_id=world["event"].id, source_id="REG-T", title="Regulamento", source_path="x.md", content=DOC)
    db.commit()
    hits = search(db, event_id=world["event"].id, query="quantas horas vale o certificado do minicurso?")
    assert hits[0]["evidence"]["source_id"] == "REG-T" and hits[0]["section"] == "4.2"
    assert search(db, event_id=world["event"].id, query="horario credenciamento")[0]["section"] == "5"


def test_search_is_scoped_to_the_event(db, world):
    ingest_document(db, event_id=world["other"].id, source_id="REG-O", title="Outro", source_path="o.md", content=DOC)
    db.commit()
    assert search(db, event_id=world["event"].id, query="certificado") == []


def test_new_version_supersedes_old(db, world):
    ev = world["event"].id
    ingest_document(db, event_id=ev, source_id="REG-T", title="v1", source_path="x.md", content=DOC)
    ingest_document(db, event_id=ev, source_id="REG-T", title="v2", source_path="x.md", content=DOC.replace("4 horas", "6 horas"))
    db.commit()
    hits = search(db, event_id=ev, query="carga horaria minicurso")
    assert {h["evidence"]["version"] for h in hits} == {2}
    assert "6 horas" in hits[0]["content"]


def test_impact_of_room_within_time_window(db, world):
    s, u = world["sessions"], world["users"]
    tickets.issue_ticket(db, user=u["alice"], session_id=s["S1"].id)
    tickets.issue_ticket(db, user=u["alice"], session_id=s["M2"].id)
    tickets.issue_ticket(db, user=u["bob"], session_id=s["M2"].id)
    db.commit()
    all_day = graph.impact(db, world["event"].id, node_type="room", key="sala a")
    assert [a["session_code"] for a in all_day["affected_sessions"]] == ["S1", "M2"]
    assert all_day["affected_participants"] == 2  # alice conta uma vez só
    afternoon = graph.impact(db, world["event"].id, node_type="room", key="Sala A", start=future(11, "13:00"), end=future(11, "19:00"))
    assert [a["session_code"] for a in afternoon["affected_sessions"]] == ["M2"]
    assert afternoon["affected_participants"] == 2


def test_impact_of_speaker_lists_related_rooms(db, world):
    r = graph.impact(db, world["event"].id, node_type="speaker", key="Helena")
    assert {a["session_code"] for a in r["affected_sessions"]} == {"S1", "M2"}
    assert {x["label"] for x in r["related"] if x["type"] == "room"} == {"Sala A"}
