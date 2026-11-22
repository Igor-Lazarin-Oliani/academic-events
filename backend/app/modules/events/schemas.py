from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    building: str
    capacity: int
    resources: list
    available: bool


class SpeakerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    affiliation: str
    bio: str


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    event_id: str
    code: str
    title: str
    description: str
    kind: str
    track: str
    start_at: datetime
    end_at: datetime
    max_capacity: int
    available_spots: int
    workload_hours: int
    status: str
    room: RoomOut | None = None
    speakers: list[SpeakerOut] = []


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    slug: str
    title: str
    description: str
    category: str
    modality: str
    location: str
    start_at: datetime
    end_at: datetime
    status: str
    cover_url: str | None = None
    max_minicursos_per_participant: int


class EventSummaryOut(EventOut):
    sessions_count: int = 0
    total_capacity: int = 0
    total_registered: int = 0


class EventDetailOut(EventOut):
    sessions: list[SessionOut] = []
    rooms: list[RoomOut] = []
    speakers: list[SpeakerOut] = []


class EventIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9-]{3,80}$")
    title: str = Field(min_length=3, max_length=200)
    description: str = ""
    category: str = "ACADEMIC"
    modality: str = "IN_PERSON"
    location: str
    start_at: datetime
    end_at: datetime
    cover_url: str | None = None
    max_minicursos_per_participant: int = Field(default=3, ge=1, le=20)


class EventUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    location: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: str | None = None
    cover_url: str | None = None


class SessionIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=3, max_length=200)
    description: str = ""
    kind: str = "PALESTRA"
    track: str = "Geral"
    room_id: str | None = None
    start_at: datetime
    end_at: datetime
    max_capacity: int = Field(gt=0)
    workload_hours: int = Field(default=2, ge=0, le=40)
    speaker_ids: list[str] = []


class EventCreateIn(EventIn):
    """Evento com a programação inicial: tudo é criado numa única transação."""

    sessions: list[SessionIn] = Field(default=[], max_length=200)


class SessionUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    room_id: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    max_capacity: int | None = Field(default=None, gt=0)
