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
    voice_model = Column(String, default="aura-2-thalia-en")
    system_prompt = Column(Text, default="You are a helpful AI assistant.")
    language = Column(String, default="en")
    tools = Column(JSON, default=list)  # List of enabled tool names
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    tenant = relationship("Tenant", back_populates="agents")
    conversations = relationship("Conversation", back_populates="agent")


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


class BusinessDataset(Base):
    __tablename__ = "business_datasets"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id: str = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    agent_id: str = Column(String, ForeignKey("agents.id"), nullable=False, index=True)
    label: str = Column(String, nullable=False, index=True)  # clients, hours, inventory, pricing, etc.
    file_name: str = Column(String, nullable=False)
    file_path: str = Column(String, nullable=False)  # where file was stored
    file_type: str = Column(String, nullable=False)  # csv, txt, pdf
    record_count: int = Column(Integer, default=0)  # number of records processed
    uploaded_at: Column = Column(DateTime, default=func.now())
    processed_at: Column = Column(DateTime, nullable=True)  # when ChromaDB ingestion completed
    columns: list = Column(JSON, default=list)  # critical columns to include as metadata
    extra_info: dict = Column(JSON, default=dict)  # additional metadata
    active: bool = Column(Boolean, default=True)
    created_at: Column = Column(DateTime, default=func.now())
    updated_at: Column = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    tenant = relationship("Tenant")
    agent = relationship("Agent")


# Database setup
engine = create_engine(settings.DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Database dependency for FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    """Get a database session for non-FastAPI usage"""
    return SessionLocal()
