import uuid

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Text,
    Boolean,
    JSON,
    ForeignKey,
    Integer,
    Float,
)
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func

from app.config.settings import settings

Base = declarative_base()

DATABASE_URL = settings.DATABASE_URL
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=True)
    email = Column(String, unique=True, nullable=False)
    firebase_uid = Column(String, unique=True, nullable=False)
    email_verified = Column(Boolean, nullable=False, default=False)
    phone_number = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    provider = Column(String, nullable=True)
    user_metadata = Column(JSON, nullable=True)
    global_role = Column(String, default="user")  # user, platform_admin
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    agent_associations = relationship("AgentUser", back_populates="user")
    agents = relationship(
        "Agent", secondary="agent_users", back_populates="users", viewonly=True
    )


class AgentUser(Base):
    __tablename__ = "agent_users"
    agent_id = Column(String, ForeignKey("agents.id"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    role = Column(String, nullable=False, default="viewer")  # owner, editor, viewer

    agent = relationship("Agent", back_populates="user_associations")
    user = relationship("User", back_populates="agent_associations")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, nullable=True)
    greeting = Column(Text, default="Hello! How can I help you today?")
    voice_model = Column(
        String, default="aura-2-thalia-en"
    )  # Deepgram voice model (fallback)
    eleven_labs_voice_id = Column(String, nullable=True)  # ElevenLabs voice ID
    voice_provider = Column(
        String, default="eleven_labs"
    )  # "eleven_labs" or "deepgram"
    system_prompt = Column(Text, default="You are a helpful AI assistant.")
    language = Column(String, default="en")
    tools = Column(JSON, default=list)  # List of enabled tool names

    # Calendar Integration
    calendar_id = Column(String, nullable=True)  # Google Calendar ID
    timezone = Column(
        String, default="America/New_York"
    )  # Agent's timezone (e.g., "America/New_York", "Europe/London")
    business_hours = Column(
        JSON,
        default=lambda: {
            "mon": {"enabled": True, "open": "09:00", "close": "17:00"},
            "tue": {"enabled": True, "open": "09:00", "close": "17:00"},
            "wed": {"enabled": True, "open": "09:00", "close": "17:00"},
            "thu": {"enabled": True, "open": "09:00", "close": "17:00"},
            "fri": {"enabled": True, "open": "09:00", "close": "17:00"},
            "sat": {"enabled": False, "open": "", "close": ""},
            "sun": {"enabled": False, "open": "", "close": ""},
        },
    )  # Day-based business hours structure
    after_hours_behavior = Column(
        String, default="voicemail"
    )  # voicemail, hangup, transfer, custom_message
    after_hours_message = Column(Text, default="")  # Custom message for after hours
    transfer_settings = Column(
        JSON, nullable=True
    )  # Transfer settings for call routing
    default_slot_duration = Column(Integer, default=30)  # minutes
    max_slot_appointments = Column(
        Integer, default=1
    )  # max appointments per time slot to prevent overbooking
    buffer_time = Column(Integer, default=10)  # minutes between appointments
    blocked_dates = Column(
        JSON, nullable=True
    )  # ["2024-12-25", "2024-01-01"] - dates when agent is unavailable
    invitees = Column(
        JSON, nullable=True
    )  # [{"name": "John Doe", "email": "john@example.com", "availability": "always"}] - default invitees for all events
    booking_enabled = Column(
        Boolean, default=True
    )  # Whether calendar booking is enabled for this agent
    closed = Column(
        Boolean, default=False
    )  # Temporarily disable new conversations/orders
    closed_message = Column(Text, nullable=True)  # Message to play when agent is closed

    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user_associations = relationship("AgentUser", back_populates="agent")
    users = relationship(
        "User", secondary="agent_users", back_populates="agents", viewonly=True
    )
    conversations = relationship("Conversation", back_populates="agent")
    orders = relationship("Order", back_populates="agent")
    menu_items = relationship("MenuItem", back_populates="agent")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
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
    agent = relationship("Agent", back_populates="conversations")
    messages = relationship(
        "Message", back_populates="conversation", order_by="Message.sequence_number"
    )
    tool_calls = relationship("ToolCall", back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)  # Message content
    audio_file_path = Column(
        String, nullable=True
    )  # Path to audio file for this message
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


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    customer_phone = Column(String, nullable=True)
    customer_name = Column(String, nullable=True)
    status = Column(
        String, nullable=False, default="new"
    )  # e.g., new, in_progress, ready, completed
    total_price = Column(Float, nullable=True)
    active = Column(Boolean, default=True)
    pickup_time = Column(String, nullable=True)  # scheduled pickup time
    special_requests = Column(Text, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)  # when order was completed
    payment_status = Column(String, default="unpaid")  # unpaid, paid, refunded
    payment_method = Column(String, nullable=True)  # cash, card, online
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    agent = relationship("Agent", back_populates="orders")
    conversation = relationship("Conversation")
    order_items = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False)
    name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    note = Column(Text, nullable=True)

    # Relationships
    order = relationship("Order", back_populates="order_items")


class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False, index=True)
    number = Column(String, nullable=True, index=True)  # unique identifier/menu number
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    category = Column(
        String(50), nullable=False, index=True
    )  # Appetizer, Entree, Drink, Dessert
    price = Column(Float, nullable=False)
    allergens = Column(Text, nullable=True)  # JSON array or comma-separated
    ingredients = Column(Text, nullable=True)
    prep_time = Column(Integer, nullable=True)  # minutes
    notes = Column(Text, nullable=True)

    # Action flags/toggles
    available = Column(Boolean, default=True)
    is_popular = Column(Boolean, default=False)
    is_special = Column(Boolean, default=False)
    is_new = Column(Boolean, default=False)
    is_limited_time = Column(Boolean, default=False)
    is_hidden = Column(Boolean, default=False)
    requires_age_check = Column(Boolean, default=False)
    has_discount = Column(Boolean, default=False)

    # Metadata
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    agent = relationship("Agent", back_populates="menu_items")


def get_db_session():
    return SessionLocal()


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()
