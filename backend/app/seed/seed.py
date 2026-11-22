"""Seed determinístico da demonstração: Semana Acadêmica FACOM 2026 + Hackathon UFMS 2026.

Todos os dados são FICTÍCIOS (o Gemini free tier pode usar o conteúdo para treinamento).
Uso: python -m app.seed.seed [--reset]"""

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core import database
from app.core.errors import DomainError
from app.core.security import hash_password
from app.knowledge.ingest import ingest_document
from app.modules.auth.models import Role, User
from app.modules.events.models import Event, Room, Session, SessionKind, Speaker
from app.modules.tickets.service import issue_ticket

TZ = ZoneInfo("America/Campo_Grande")
DATA = Path(__file__).parent / "data"
PASSWORD = "senha123"
DEMO_USERS = {
    "admin": "admin@exemplo.com",
    "organizer": "ana.org@exemplo.com",
    "organizer_hackathon": "bruno.org@exemplo.com",
    "staff": "carla.staff@exemplo.com",
    "participant": "participante@exemplo.com",
    "participant2": "maria@exemplo.com",
}

FIRST = ["Ana", "Bruno", "Camila", "Daniel", "Eduarda", "Felipe", "Gabriela", "Henrique", "Isabela", "João", "Larissa", "Mateus", "Natália",
         "Otávio", "Paula", "Rafael", "Sofia", "Tiago", "Vitória", "Yuri", "Beatriz", "Caio", "Débora", "Enzo", "Fernanda", "Gustavo",
         "Helena", "Igor", "Júlia", "Kauã", "Letícia", "Miguel"]
LAST = ["Silva", "Souza", "Oliveira", "Pereira", "Costa", "Rodrigues", "Almeida", "Nascimento", "Lima", "Araújo", "Fernandes", "Carvalho",
        "Gomes", "Martins", "Rocha", "Ribeiro", "Barbosa", "Teixeira"]
COURSES = ["Ciência da Computação", "Engenharia de Software", "Sistemas de Informação", "TADS", "Engenharia de Computação"]


def at(day: int, hm: str) -> datetime:
    """day 0 = segunda, 30/11/2026."""
    h, m = map(int, hm.split(":"))
    return datetime(2026, 11, 30, h, m, tzinfo=TZ) + timedelta(days=day)


ROOMS = [
    ("Anfiteatro FACOM", "Bloco principal", 180, ["projetor", "som", "microfone"]),
    ("Auditório Multiuso", "Bloco principal", 120, ["projetor", "som"]),
    ("Sala 105", "Bloco B", 45, ["projetor"]),
    ("Sala 108", "Bloco B", 45, ["projetor"]),
    ("Sala 201", "Bloco B", 40, ["projetor"]),
    ("LIA-1", "Laboratórios", 30, ["computadores", "projetor"]),
    ("LIA-2", "Laboratórios", 30, ["computadores", "projetor"]),
]

SPEAKERS = [
    ("Dra. Helena Duarte", "FACOM/UFMS", "Pesquisadora em IA aplicada à engenharia de software."),
    ("Prof. Ricardo Menezes", "FACOM/UFMS", "Professor de engenharia de software e arquitetura."),
    ("Marina Okada", "Pantanal Tech (fictícia)", "Desenvolvedora backend e mentora de carreira."),
    ("Thiago Ribeiro", "Cerrado Cloud (fictícia)", "Engenheiro de plataforma e DevOps."),
    ("Dra. Lúcia Fontes", "FACOM/UFMS", "Pesquisadora em segurança da informação."),
    ("Prof. Caio Batista", "FACOM/UFMS", "Professor de bancos de dados."),
    ("Ana Beatriz Lemos", "Ipê Digital (fictícia)", "Desenvolvedora frontend e especialista em UX."),
    ("Pedro Saldanha", "Arara Dados (fictícia)", "Cientista de dados."),
    ("Juliana Prado", "Comissão FACOM", "Coordenadora da comissão organizadora."),
]

# code, título, tipo, trilha, dia, início, fim, sala, palestrantes, carga horária, inscritos-alvo
SESSIONS = [
    ("S01", "Abertura: Software com Agentes de IA", SessionKind.ABERTURA, "Geral", 0, "08:00", "10:00", "Anfiteatro FACOM", ["Dra. Helena Duarte"], 2, 140),
    ("S02", "Arquitetura de Microsserviços na Prática", SessionKind.PALESTRA, "Engenharia de Software", 0, "10:30", "12:00", "Anfiteatro FACOM", ["Prof. Ricardo Menezes"], 2, 95),
    ("S03", "Minicurso: Docker do Zero ao Deploy", SessionKind.MINICURSO, "DevOps", 0, "14:00", "18:00", "LIA-1", ["Thiago Ribeiro"], 4, 30),
    ("S04", "Minicurso: React com TypeScript", SessionKind.MINICURSO, "Web", 0, "14:00", "18:00", "LIA-2", ["Ana Beatriz Lemos"], 4, 22),
    ("S05", "Segurança em APIs: OWASP Top 10", SessionKind.PALESTRA, "Segurança", 1, "08:00", "10:00", "Sala 105", ["Dra. Lúcia Fontes"], 2, 38),
    ("S06", "Mesa-redonda: Carreira em Tecnologia no MS", SessionKind.MESA_REDONDA, "Carreira", 1, "10:30", "12:00", "Auditório Multiuso", ["Juliana Prado", "Marina Okada"], 2, 70),
    ("S07", "Minicurso: APIs com FastAPI e PostgreSQL", SessionKind.MINICURSO, "Backend", 1, "14:00", "18:00", "LIA-1", ["Marina Okada"], 4, 29),
    ("S08", "Minicurso: Introdução a LLMs e RAG", SessionKind.MINICURSO, "IA", 1, "14:00", "18:00", "LIA-2", ["Pedro Saldanha"], 4, 24),
    ("S09", "Engenharia de Contexto e Grafos de Conhecimento", SessionKind.PALESTRA, "IA", 2, "08:00", "10:00", "Anfiteatro FACOM", ["Dra. Helena Duarte"], 2, 120),
    ("S10", "Bancos de Dados: Índices que Salvam a Produção", SessionKind.PALESTRA, "Dados", 2, "10:30", "12:00", "Sala 105", ["Prof. Caio Batista"], 2, 33),
    ("S11", "Workshop: UX para Desenvolvedores", SessionKind.WORKSHOP, "Web", 2, "14:00", "17:00", "Sala 108", ["Ana Beatriz Lemos"], 3, 25),
    ("S12", "IA Generativa no Desenvolvimento de Software", SessionKind.PALESTRA, "IA", 3, "14:00", "16:00", "Auditório Multiuso", ["Dra. Helena Duarte"], 2, 84),
    ("S13", "Minicurso: Testes Automatizados com pytest", SessionKind.MINICURSO, "Engenharia de Software", 3, "08:00", "12:00", "LIA-1", ["Prof. Ricardo Menezes"], 4, 18),
    ("S14", "Kubernetes para Iniciantes", SessionKind.PALESTRA, "DevOps", 3, "16:30", "18:00", "Auditório Multiuso", ["Thiago Ribeiro"], 2, 52),
    ("S15", "Minicurso: Análise de Dados com Python", SessionKind.MINICURSO, "Dados", 3, "08:00", "12:00", "LIA-2", ["Pedro Saldanha"], 4, 16),
    ("S16", "Encerramento e Premiação", SessionKind.ABERTURA, "Geral", 4, "16:00", "18:00", "Anfiteatro FACOM", ["Juliana Prado"], 1, 60),
    ("S17", "Observabilidade com OpenTelemetry", SessionKind.PALESTRA, "DevOps", 4, "08:00", "10:00", "Sala 105", ["Thiago Ribeiro"], 2, 30),
]

# Inscrições fixas do participante de demonstração (aparece como afetado pela S12)
DEMO_PARTICIPANT_SESSIONS = ["S01", "S04", "S09", "S12"]
DEMO_PARTICIPANT2_SESSIONS = ["S02", "S07"]


def _user(db: DbSession, name: str, email: str, role: str, pwd_hash: str, course: str | None = None) -> User:
    u = User(name=name, email=email, password_hash=pwd_hash, role=role, course=course)
    db.add(u)
    return u


def seed(db: DbSession) -> dict:
    if db.scalar(select(Event).limit(1)):
        return {"skipped": True}
    rng = random.Random(42)
    pwd = hash_password(PASSWORD)

    admin = _user(db, "Administrador", DEMO_USERS["admin"], Role.ADMIN, pwd)
    ana = _user(db, "Ana Ferreira (comissão)", DEMO_USERS["organizer"], Role.ORGANIZER, pwd)
    bruno = _user(db, "Bruno Castro (hackathon)", DEMO_USERS["organizer_hackathon"], Role.ORGANIZER, pwd)
    carla = _user(db, "Carla Mendes (credenciamento)", DEMO_USERS["staff"], Role.STAFF, pwd)
    lucas = _user(db, "Lucas Almeida", DEMO_USERS["participant"], Role.PARTICIPANT, pwd, "TADS")
    maria = _user(db, "Maria Santos", DEMO_USERS["participant2"], Role.PARTICIPANT, pwd, "Ciência da Computação")
    crowd = []
    names = [(f, l) for f in FIRST for l in LAST]
    rng.shuffle(names)
    for i, (f, l) in enumerate(names[:160]):
        crowd.append(_user(db, f"{f} {l}", f"participante{i + 1:03d}@exemplo.com", Role.PARTICIPANT, pwd, rng.choice(COURSES)))
    db.flush()

    semana = Event(
        slug="semana-facom-2026", title="Semana Acadêmica FACOM 2026",
        description="Cinco dias de palestras, minicursos e workshops sobre engenharia de software, IA, DevOps, dados e carreira.",
        category="ACADEMIC", modality="IN_PERSON", location="FACOM/UFMS, Cidade Universitária, Campo Grande (MS)",
        start_at=at(0, "08:00"), end_at=at(4, "18:00"), cover_url="/covers/semana-facom.jpg", max_minicursos_per_participant=3,
    )
    semana.organizers.extend([ana, carla])
    db.add(semana)
    db.flush()
    rooms = {name: Room(event_id=semana.id, name=name, building=b, capacity=c, resources=r) for name, b, c, r in ROOMS}
    speakers = {name: Speaker(event_id=semana.id, name=name, affiliation=a, bio=bio) for name, a, bio in SPEAKERS}
    db.add_all([*rooms.values(), *speakers.values()])
    db.flush()
    sessions = {}
    for code, title, kind, track, day, start, end, room, spk, hours, _target in SESSIONS:
        cap = min(rooms[room].capacity, 30 if kind == SessionKind.MINICURSO else rooms[room].capacity)
        s = Session(event_id=semana.id, room_id=rooms[room].id, code=code, title=title, kind=kind, track=track, start_at=at(day, start),
                    end_at=at(day, end), max_capacity=cap, available_spots=cap, workload_hours=hours,
                    description=f"{title}. Trilha {track}.", speakers=[speakers[n] for n in spk])
        db.add(s)
        sessions[code] = s
    db.flush()

    for code in DEMO_PARTICIPANT_SESSIONS:
        issue_ticket(db, user=lucas, session_id=sessions[code].id, source="system")
    for code in DEMO_PARTICIPANT2_SESSIONS:
        issue_ticket(db, user=maria, session_id=sessions[code].id, source="system")

    issued = len(DEMO_PARTICIPANT_SESSIONS) + len(DEMO_PARTICIPANT2_SESSIONS)
    for code, *_rest, target in SESSIONS:
        already = sum(1 for c in DEMO_PARTICIPANT_SESSIONS + DEMO_PARTICIPANT2_SESSIONS if c == code)
        pool = crowd[:]
        rng.shuffle(pool)
        count = already
        for u in pool:
            if count >= target:
                break
            nested = db.begin_nested()
            try:
                issue_ticket(db, user=u, session_id=sessions[code].id, source="system")
                nested.commit()
                count += 1
                issued += 1
            except DomainError:
                nested.rollback()

    for path, source_id, title, trust in [
        ("regulamento-semana-facom-2026.md", "REG-FACOM-2026", "Regulamento da Semana Acadêmica FACOM 2026", "OFFICIAL"),
        ("faq-semana-facom-2026.md", "FAQ-FACOM-2026", "Perguntas frequentes", "OFFICIAL"),
        ("mural-voluntarios.md", "MURAL-VOLUNTARIOS", "Mural de avisos dos voluntários", "UNVERIFIED"),
    ]:
        ingest_document(db, event_id=semana.id, source_id=source_id, title=title, source_path=f"seed/data/{path}",
                        content=(DATA / path).read_text(encoding="utf-8"), trust=trust, uploaded_by=ana.id)

    hack = Event(slug="hackathon-ufms-2026", title="Hackathon UFMS 2026", description="48 horas para criar soluções para a cidade.",
                 category="HACKATHON", modality="IN_PERSON", location="Bloco de Inovação, UFMS", start_at=at(12, "08:00"), end_at=at(13, "18:00"),
                 cover_url="/covers/hackathon.jpg")
    hack.organizers.append(bruno)
    db.add(hack)
    db.flush()
    lab = Room(event_id=hack.id, name="Espaço Maker", building="Bloco de Inovação", capacity=100, resources=["mesas", "tomadas"])
    db.add(lab)
    db.flush()
    db.add_all([
        Session(event_id=hack.id, room_id=lab.id, code="H01", title="Kickoff e formação de equipes", kind=SessionKind.ABERTURA, track="Geral",
                start_at=at(12, "08:00"), end_at=at(12, "10:00"), max_capacity=100, available_spots=100, workload_hours=2),
        Session(event_id=hack.id, room_id=lab.id, code="H02", title="Maratona de desenvolvimento", kind=SessionKind.WORKSHOP, track="Geral",
                start_at=at(12, "10:00"), end_at=at(13, "16:00"), max_capacity=100, available_spots=100, workload_hours=20),
    ])
    ingest_document(db, event_id=hack.id, source_id="REG-HACK-2026", title="Regulamento do Hackathon UFMS 2026",
                    source_path="seed/data/regulamento-hackathon-2026.md", content=(DATA / "regulamento-hackathon-2026.md").read_text(encoding="utf-8"),
                    uploaded_by=bruno.id)
    db.commit()
    return {"users": 6 + len(crowd), "sessions": len(SESSIONS) + 2, "tickets": issued, "admin": admin.email}


def reset_and_seed() -> dict:
    database.Base.metadata.drop_all(database.engine())
    database.create_all()
    with database.session_factory()() as db:
        return seed(db)


if __name__ == "__main__":
    if "--reset" in sys.argv:
        print(reset_and_seed())
    else:
        database.create_all()
        with database.session_factory()() as db:
            print(seed(db))
