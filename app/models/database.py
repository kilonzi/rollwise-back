import uuid

from sqlalchemy import (
    create_engine,
    Column,
    String,
    DateTime,
    Text,
    Boolean,
    JSON,
    ForeignKey,
    Integer,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func

from app.config.settings import settings

Base = declarative_base()


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    business_type = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    email = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user_tenants = relationship("UserTenant", back_populates="tenant")
    agents = relationship("Agent", back_populates="tenant")
    conversations = relationship("Conversation", back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)
    global_role = Column(String, default="user")  # user, platform_admin
    access_token = Column(String, nullable=True)
    refresh_token = Column(String, nullable=True)
    reset_token = Column(String, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)
    email_verified = Column(Boolean, default=False)
    email_verification_token = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user_tenants = relationship("UserTenant", back_populates="user")


class UserTenant(Base):
    __tablename__ = "user_tenants"

    user_id = Column(String, ForeignKey('users.id'), primary_key=True)
    tenant_id = Column(String, ForeignKey('tenants.id'), primary_key=True)
    role = Column(String, default='user')  # owner, user, platform_admin
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User")
    tenant = relationship("Tenant")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, nullable=True)
    greeting = Column(Text, default="Hello! How can I help you today?")
    voice_model = Column(String, default="aura-2-thalia-en")  # Deepgram voice model (fallback)
    eleven_labs_voice_id = Column(String, nullable=True)  # ElevenLabs voice ID
    voice_provider = Column(String, default="eleven_labs")  # "eleven_labs" or "deepgram"
    system_prompt = Column(Text, default="You are a helpful AI assistant.")
    language = Column(String, default="en")
    tools = Column(JSON, default=list)  # List of enabled tool names

    # Calendar Integration
    calendar_id = Column(String, nullable=True)  # Google Calendar ID
    business_hours = Column(JSON, nullable=True)  # {"start": "09:00", "end": "17:00", "timezone": "UTC", "days": [1,2,3,4,5]}
    default_slot_duration = Column(Integer, default=30)  # minutes
    max_slot_appointments = Column(Integer, default=1)  # max appointments per time slot to prevent overbooking
    buffer_time = Column(Integer, default=10)  # minutes between appointments
    blocked_dates = Column(JSON, nullable=True)  # ["2024-12-25", "2024-01-01"] - dates when agent is unavailable
    invitees = Column(JSON, nullable=True)  # [{"name": "John Doe", "email": "john@example.com", "availability": "always"}] - default invitees for all events
    booking_enabled = Column(Boolean, default=True)  # Whether calendar booking is enabled for this agent


    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    tenant = relationship("Tenant", back_populates="agents")
    conversations = relationship("Conversation", back_populates="agent")
    board = relationship("Board", back_populates="agent", uselist=False)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False)
    session_name = Column(String, nullable=False)  # e.g., "Call with +1234567890"
    conversation_type = Column(String, nullable=False)  # voice, message
    caller_phone = Column(String, nullable=False)
    twilio_sid = Column(String, nullable=True)  # CallSid or MessageSid
    status = Column(String, default="active")  # active, completed, failed
    started_at = Column(DateTime, default=func.now())
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    tenant = relationship("Tenant", back_populates="conversations")
    agent = relationship("Agent", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", order_by="Message.sequence_number")
    tool_calls = relationship("ToolCall", back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)  # Message content
    audio_file_path = Column(String, nullable=True)  # Path to audio file for this message
    sequence_number = Column(Integer, nullable=False)  # For chronological ordering
    message_type = Column(String, default="conversation")  # conversation, system, etc.
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    tool_name = Column(String, nullable=False)
    parameters = Column(JSON, nullable=False)
    result = Column(JSON, nullable=True)
    status = Column(String, default="pending")  # pending, success, failed
    executed_at = Column(DateTime, default=func.now())
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    conversation = relationship("Conversation", back_populates="tool_calls")


class Board(Base):
    __tablename__ = "boards"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False, unique=True)
    name = Column(String, nullable=False, default="Agent Board")
    lanes = Column(JSON, default=lambda: [
        {"id": "new", "name": "New", "color": "#2196F3", "wipLimit": None},
        {"id": "in_progress", "name": "In Progress", "color": "#FF9800", "wipLimit": 5},
        {"id": "done", "name": "Done", "color": "#4CAF50", "wipLimit": None}
    ])
    labels = Column(JSON, default=lambda: [
        {"id": "urgent", "name": "Urgent", "color": "#F44336"},
        {"id": "vip", "name": "VIP Customer", "color": "#9C27B0"},
        {"id": "delivery", "name": "Delivery", "color": "#607D8B"},
        {"id": "takeout", "name": "Takeout", "color": "#795548"}
    ])
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    agent = relationship("Agent", back_populates="board")
    items = relationship("BoardItem", back_populates="board", cascade="all, delete-orphan")


class BoardItem(Base):
    __tablename__ = "board_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    board_id = Column(String, ForeignKey("boards.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    lane_id = Column(String, nullable=False, default="new")
    labels = Column(JSON, default=list)  # List of label IDs from board labels
    priority = Column(String, default="medium")  # low, medium, high, urgent
    assignee = Column(String, nullable=True)
    due_date = Column(DateTime, nullable=True)
    item_metadata = Column(JSON, default=dict)  # Additional data like conversation_id, caller_info, etc.
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    board = relationship("Board", back_populates="items")


class Collection(Base):
    __tablename__ = "collections"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False, index=True)
    name = Column(String, nullable=False, index=True)  # slugified with underscores
    display_name = Column(String, nullable=False)  # original user input
    description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    file_path = Column(String(500), nullable=True)  # store/collections/{id}.{ext}
    file_type = Column(String(10), nullable=True)  # pdf, txt, csv, text
    content_type = Column(String(50), nullable=True)  # auto-detected: menu, policy, faq, etc.
    chunk_count = Column(Integer, default=0)
    chroma_collection_name = Column(String, nullable=False)  # collection__{id}
    status = Column(String(20), default="processing")  # processing, ready, error
    error_message = Column(Text, nullable=True)  # error details if processing failed
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    agent = relationship("Agent")


# Database setup
# Database setup with connection pooling
engine_kwargs = {
    "echo": False,
    "pool_pre_ping": True,  # Validate connections before use
    "pool_recycle": 300,    # Recycle connections every 5 minutes
}

# Add connection pooling for non-SQLite databases
if not settings.DATABASE_URL.startswith("sqlite"):
    engine_kwargs.update({
        "pool_size": 20,        # Connection pool size
        "max_overflow": 30,     # Max connections beyond pool_size
        "pool_timeout": 30,     # Timeout for getting connection
    })

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Database dependency for FastAPI with enhanced error handling"""
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_db_session():
    """Get a database session for non-FastAPI usage"""
    return SessionLocal()
