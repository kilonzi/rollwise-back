from datetime import datetime, date, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas.order import OrderSchema, OrderCreateSchema
from app.models import get_db
from app.services.order_service import OrderService

router = APIRouter()


@router.post(
    "/{agent_id}/orders",
    response_model=OrderSchema,
    summary="Create a new order for a specific agent",
    status_code=201,
)
def create_agent_order(
    agent_id: str,
    order_data: OrderCreateSchema,
    db: Session = Depends(get_db),
):
    """
    Creates a new order and associates it directly with the agent.
    """
    try:
        order_dict = order_data.model_dump()
        order = OrderService.create_order(db, agent_id, order_dict)
        return order
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create order: {str(e)}")


@router.get(
    "/{agent_id}/orders",
    response_model=List[OrderSchema],
    summary="Get all orders for a specific agent",
)
def get_agent_orders(
    agent_id: str,
    start_date: Optional[date] = Query(
        None,
        description="Start date for filtering orders (YYYY-MM-DD). Defaults to today.",
    ),
    end_date: Optional[date] = Query(
        None,
        description="End date for filtering orders (YYYY-MM-DD). Defaults to today.",
    ),
    db: Session = Depends(get_db),
):
    """
    Retrieves all orders associated with a specific agent, with optional date filtering.
    By default, it returns orders for the current day.
    """
    try:
        if start_date is None:
            start_date = datetime.now(timezone.utc).date()
        if end_date is None:
            end_date = datetime.now(timezone.utc).date()

        orders = OrderService.get_agent_orders(db, agent_id, start_date, end_date)
        return orders
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to retrieve orders: {str(e)}"
        )
