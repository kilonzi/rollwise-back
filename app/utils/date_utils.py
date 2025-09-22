from datetime import datetime, time, timedelta
from typing import Optional


def normalize_date_range(
    date_from: Optional[datetime] = None, date_to: Optional[datetime] = None
) -> tuple[datetime, datetime]:
    """
    Normalize date range to ensure proper filtering:
    - date_from becomes start of day (00:00:00)
    - date_to becomes end of day (23:59:59.999999)
    - If no dates provided, defaults to start of yesterday to end of today
    """

    now = datetime.now()

    # Set defaults if not provided
    if date_to is None:
        date_to = now
    if date_from is None:
        # Default to yesterday using timedelta for proper date handling
        date_from = now - timedelta(days=1)

    # Normalize date_from to start of day
    date_from = datetime.combine(date_from.date(), time.min)

    # Normalize date_to to end of day
    date_to = datetime.combine(date_to.date(), time.max)

    return date_from, date_to


def normalize_date_to_start_of_day(dt: datetime) -> datetime:
    """Convert datetime to start of day (00:00:00)"""
    return datetime.combine(dt.date(), time.min)


def normalize_date_to_end_of_day(dt: datetime) -> datetime:
    """Convert datetime to end of day (23:59:59.999999)"""
    return datetime.combine(dt.date(), time.max)
