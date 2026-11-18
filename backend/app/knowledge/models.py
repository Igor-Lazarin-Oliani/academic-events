"""Base de conhecimento: documentos versionados por evento, divididos em trechos com proveniência.
A busca lexical usa o full-text do PostgreSQL sobre um texto normalizado (sem acentos)."""

from datetime import datetime

from sqlalchemy import Computed, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, new_id, utcnow


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(String(40))   # ex.: REG-FACOM-2026 (estável entre versões)
    title: Mapped[str] = mapped_column(String(200))
    source_path: Mapped[str] = mapped_column(String(300))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")  # ACTIVE | SUPERSEDED
    trust: Mapped[str] = mapped_column(String(12), default="OFFICIAL")  # OFFICIAL | UNVERIFIED
    content: Mapped[str] = mapped_column(Text)
    uploaded_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (Index("ix_knowledge_chunks_tsv", "tsv", postgresql_using="gin"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str] = mapped_column(String(36), index=True)
    section: Mapped[str] = mapped_column(String(20))   # ex.: "4.2"
    heading: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text)  # minúsculas e sem acento
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('portuguese', search_text)", persisted=True))

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")
