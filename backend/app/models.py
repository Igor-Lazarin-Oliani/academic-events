"""Importa todos os modelos para registrar as tabelas no metadata."""

from app.agentic.models import AgentRun, AgentStep, Conversation, ConversationMessage  # noqa: F401
from app.knowledge.models import KnowledgeChunk, KnowledgeDocument  # noqa: F401
from app.modules.activity.models import ActivityLog  # noqa: F401
from app.modules.approvals.models import ActionProposal  # noqa: F401
from app.modules.auth.models import User  # noqa: F401
from app.modules.events.models import Event, Room, Session, Speaker  # noqa: F401
from app.modules.notifications.models import Notification, SupportRequest  # noqa: F401
from app.modules.tickets.models import Ticket  # noqa: F401
