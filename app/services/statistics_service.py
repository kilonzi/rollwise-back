from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models.database import Conversation
from app.api.schemas.statistics_schemas import (
    AgentStatistics,
    ConversationStats,
    DurationStats,
    CallerStats,
    StatisticValue,
    MinutesStatistic,
    DateRangeInfo,
)


class StatisticsService:
    """Service for generating agent statistics and analytics"""

    def __init__(self, db: Session):
        self.db = db

    def get_agent_statistics(
        self,
        agent_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> AgentStatistics:
        """
        Get comprehensive statistics for an agent within a date range.
        Defaults to current day if no dates provided.
        """
        # Set default date range to today
        if not end_date:
            end_date = datetime.now().replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
        if not start_date:
            start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Calculate comparison period (same duration, preceding the current period)
        period_duration = end_date - start_date
        previous_end = start_date - timedelta(seconds=1)
        previous_start = previous_end - period_duration

        # Get current period stats
        current_stats = self._get_period_stats(agent_id, start_date, end_date)

        # Get previous period stats
        previous_stats = self._get_period_stats(agent_id, previous_start, previous_end)

        # Build response
        return AgentStatistics(
            agent_id=agent_id,
            date_range=DateRangeInfo(
                current_start=start_date,
                current_end=end_date,
                previous_start=previous_start,
                previous_end=previous_end,
                period_days=(end_date - start_date).days + 1,
            ),
            conversations=self._build_conversation_stats(current_stats, previous_stats),
            duration_minutes=self._build_duration_stats(current_stats, previous_stats),
            callers=self._build_caller_stats(current_stats, previous_stats),
            raw_data={
                "current_period": current_stats,
                "previous_period": previous_stats,
            },
        )

    def _get_period_stats(
        self, agent_id: str, start_date: datetime, end_date: datetime
    ) -> Dict[str, Any]:
        """Get raw statistics for a specific period"""

        # Base conversation query for the period
        base_query = self.db.query(Conversation).filter(
            and_(
                Conversation.agent_id == agent_id,
                Conversation.created_at >= start_date,
                Conversation.created_at <= end_date,
                Conversation.active == True,
            )
        )

        # Total conversations
        total_conversations = base_query.count()

        # Conversations by type
        voice_conversations = base_query.filter(
            Conversation.conversation_type == "voice"
        ).count()

        message_conversations = base_query.filter(
            or_(
                Conversation.conversation_type == "sms",
                Conversation.conversation_type == "message",
            )
        ).count()

        # Duration calculations (only for voice calls)
        voice_durations = (
            self.db.query(Conversation.duration_seconds)
            .filter(
                and_(
                    Conversation.agent_id == agent_id,
                    Conversation.conversation_type == "voice",
                    Conversation.created_at >= start_date,
                    Conversation.created_at <= end_date,
                    Conversation.duration_seconds.isnot(None),
                    Conversation.active == True,
                )
            )
            .all()
        )

        # Convert duration strings to minutes
        total_voice_minutes = 0.0
        for duration_tuple in voice_durations:
            duration_str = duration_tuple[0]
            if duration_str:
                try:
                    # Assuming duration_seconds is stored as string
                    total_voice_minutes += float(duration_str) / 60.0
                except (ValueError, TypeError):
                    continue

        # Unique caller analysis
        unique_callers = (
            self.db.query(Conversation.caller_phone)
            .filter(
                and_(
                    Conversation.agent_id == agent_id,
                    Conversation.created_at >= start_date,
                    Conversation.created_at <= end_date,
                    Conversation.active == True,
                )
            )
            .distinct()
            .count()
        )

        # Get all callers in this period
        current_callers = set(
            row[0]
            for row in self.db.query(Conversation.caller_phone)
            .filter(
                and_(
                    Conversation.agent_id == agent_id,
                    Conversation.created_at >= start_date,
                    Conversation.created_at <= end_date,
                    Conversation.active == True,
                )
            )
            .distinct()
            .all()
        )

        # Get callers who called before this period (returning callers)
        previous_callers = set(
            row[0]
            for row in self.db.query(Conversation.caller_phone)
            .filter(
                and_(
                    Conversation.agent_id == agent_id,
                    Conversation.created_at < start_date,
                    Conversation.active == True,
                )
            )
            .distinct()
            .all()
        )

        returning_callers = len(current_callers.intersection(previous_callers))
        new_callers = len(current_callers - previous_callers)

        return {
            "total_conversations": total_conversations,
            "voice_conversations": voice_conversations,
            "message_conversations": message_conversations,
            "total_voice_minutes": total_voice_minutes,
            "total_minutes": total_voice_minutes,  # Same as voice for now
            "unique_callers": unique_callers,
            "returning_callers": returning_callers,
            "new_callers": new_callers,
            "current_callers": current_callers,
            "period_start": start_date,
            "period_end": end_date,
        }

    def _calculate_change(
        self, current: float, previous: float
    ) -> Tuple[float, Optional[float]]:
        """Calculate absolute and percentage change"""
        change = current - previous
        change_percent = None
        if previous > 0:
            change_percent = round((change / previous) * 100, 2)
        return change, change_percent

    def _build_conversation_stats(
        self, current: Dict, previous: Dict
    ) -> ConversationStats:
        """Build conversation statistics with comparisons"""

        # All conversations
        all_change, all_percent = self._calculate_change(
            current["total_conversations"], previous["total_conversations"]
        )

        # Voice conversations
        voice_change, voice_percent = self._calculate_change(
            current["voice_conversations"], previous["voice_conversations"]
        )

        # Message conversations
        msg_change, msg_percent = self._calculate_change(
            current["message_conversations"], previous["message_conversations"]
        )

        return ConversationStats(
            all=StatisticValue(
                current=current["total_conversations"],
                previous=previous["total_conversations"],
                change=int(all_change),
                change_percent=all_percent,
            ),
            voice=StatisticValue(
                current=current["voice_conversations"],
                previous=previous["voice_conversations"],
                change=int(voice_change),
                change_percent=voice_percent,
            ),
            messages=StatisticValue(
                current=current["message_conversations"],
                previous=previous["message_conversations"],
                change=int(msg_change),
                change_percent=msg_percent,
            ),
        )

    def _build_duration_stats(self, current: Dict, previous: Dict) -> DurationStats:
        """Build duration statistics with comparisons"""

        # All duration (same as voice for now)
        all_change, all_percent = self._calculate_change(
            current["total_minutes"], previous["total_minutes"]
        )

        # Voice duration
        voice_change, voice_percent = self._calculate_change(
            current["total_voice_minutes"], previous["total_voice_minutes"]
        )

        return DurationStats(
            all=MinutesStatistic(
                current=round(current["total_minutes"], 2),
                previous=round(previous["total_minutes"], 2),
                change=round(all_change, 2),
                change_percent=all_percent,
            ),
            voice=MinutesStatistic(
                current=round(current["total_voice_minutes"], 2),
                previous=round(previous["total_voice_minutes"], 2),
                change=round(voice_change, 2),
                change_percent=voice_percent,
            ),
        )

    def _build_caller_stats(self, current: Dict, previous: Dict) -> CallerStats:
        """Build caller statistics with comparisons"""

        # Unique callers
        unique_change, unique_percent = self._calculate_change(
            current["unique_callers"], previous["unique_callers"]
        )

        # Returning callers
        returning_change, returning_percent = self._calculate_change(
            current["returning_callers"], previous["returning_callers"]
        )

        # New callers
        new_change, new_percent = self._calculate_change(
            current["new_callers"], previous["new_callers"]
        )

        return CallerStats(
            unique_callers=StatisticValue(
                current=current["unique_callers"],
                previous=previous["unique_callers"],
                change=int(unique_change),
                change_percent=unique_percent,
            ),
            returning_callers=StatisticValue(
                current=current["returning_callers"],
                previous=previous["returning_callers"],
                change=int(returning_change),
                change_percent=returning_percent,
            ),
            new_callers=StatisticValue(
                current=current["new_callers"],
                previous=previous["new_callers"],
                change=int(new_change),
                change_percent=new_percent,
            ),
        )
