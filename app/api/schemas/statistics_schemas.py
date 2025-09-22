from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class StatisticValue(BaseModel):
    """A statistic value with comparison to previous period"""

    current: int
    previous: int
    change: int
    change_percent: Optional[float] = None


class MinutesStatistic(BaseModel):
    """Duration statistics in minutes with comparison"""

    current: float
    previous: float
    change: float
    change_percent: Optional[float] = None


class ConversationStats(BaseModel):
    """Conversation statistics by type"""

    all: StatisticValue
    voice: StatisticValue
    messages: StatisticValue


class DurationStats(BaseModel):
    """Duration statistics by type (in minutes)"""

    all: MinutesStatistic
    voice: MinutesStatistic


class CallerStats(BaseModel):
    """Unique caller statistics"""

    unique_callers: StatisticValue
    returning_callers: StatisticValue
    new_callers: StatisticValue


class DateRangeInfo(BaseModel):
    """Information about the date ranges"""

    current_start: datetime
    current_end: datetime
    previous_start: datetime
    previous_end: datetime
    period_days: int


class AgentStatistics(BaseModel):
    """Complete agent statistics response"""

    agent_id: str
    date_range: DateRangeInfo
    conversations: ConversationStats
    duration_minutes: DurationStats
    callers: CallerStats
    raw_data: Dict[str, Any]  # Additional raw metrics for frontend flexibility
