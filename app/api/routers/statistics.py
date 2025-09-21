from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from app.models.database import get_db, Agent
from app.api.dependencies import validate_agent_access
from app.services.statistics_service import StatisticsService
from app.api.schemas.statistics_schemas import AgentStatistics

router = APIRouter()


@router.get("/{agent_id}/statistics/", response_model=AgentStatistics)
def get_agent_statistics(
    agent: Agent = Depends(validate_agent_access),
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format"),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive statistics for an agent within a date range.

    - **agent_id**: The ID of the agent to get statistics for
    - **start_date**: Start date (YYYY-MM-DD). Defaults to today.
    - **end_date**: End date (YYYY-MM-DD). Defaults to today.

    Returns statistics with comparison to the previous period of the same length.

    Examples:
    - Today only: `/agents/{agent_id}/statistics/`
    - Last 7 days: `/agents/{agent_id}/statistics/?start_date=2025-09-14&end_date=2025-09-20`
    - Specific day: `/agents/{agent_id}/statistics/?start_date=2025-09-15&end_date=2025-09-15`
    """

    # Parse dates if provided
    parsed_start_date = None
    parsed_end_date = None

    if start_date:
        try:
            parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD")

    if end_date:
        try:
            parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD")

    # Validate date range
    if parsed_start_date and parsed_end_date and parsed_start_date > parsed_end_date:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")

    # Get statistics
    statistics_service = StatisticsService(db)
    return statistics_service.get_agent_statistics(
        agent_id=agent.id,
        start_date=parsed_start_date,
        end_date=parsed_end_date
    )
