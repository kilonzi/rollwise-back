from datetime import datetime, date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas.order import (
    OrderSchema,
    OrderCreateSchema,
    OrderUpdateSchema,
    OrderItemSchema,
    OrderItemUpdateSchema,
)
from app.models import get_db
from app.services.order_service import OrderService

router = APIRouter()


@router.post(
    "/agents/{agent_id}/orders",
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
    "/orders/{order_id}",
    response_model=OrderSchema,
    summary="Get a specific order by its ID",
)
def get_order(order_id: str, db: Session = Depends(get_db)):
    """
    Retrieves a single order by its unique ID, including its items.
    """
    order = OrderService.get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.put(
    "/orders/{order_id}",
    response_model=OrderSchema,
    summary="Update an existing order",
)
def update_order(
    order_id: str,
    order_update: OrderUpdateSchema,
    db: Session = Depends(get_db),
):
    """
    Updates an order's details, such as status or customer information.
    This does not update order items.
    """
    try:
        update_data = order_update.model_dump(exclude_unset=True)
        order = OrderService.update_order(db, order_id, update_data)
        return order
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update order: {str(e)}")


@router.patch(
    "/order-items/{item_id}",
    response_model=OrderItemSchema,
    summary="Update an existing order item",
)
def update_order_item(
    item_id: int,
    item_update: OrderItemUpdateSchema,
    db: Session = Depends(get_db),
):
    """
    Updates an order item's details, such as name, quantity, or price.
    """
    try:
        update_data = item_update.model_dump(exclude_unset=True)
        order_item = OrderService.update_order_item(db, item_id, update_data)
        return order_item
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update order item: {str(e)}")


@router.delete(
    "/order-items/{item_id}",
    status_code=204,
    summary="Delete an order item",
)
def delete_order_item(item_id: int, db: Session = Depends(get_db)):
    """
    Deletes an order item by its ID.
    """
    try:
        success = OrderService.delete_order_item(db, item_id)
        if not success:
            raise HTTPException(status_code=404, detail="Order item not found")
        return None
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to delete order item: {str(e)}")


@router.get(
    "/agents/{agent_id}/orders",
    response_model=List[OrderSchema],
    summary="Get all orders for a specific agent",
)
def get_agent_orders(
    agent_id: str,
    start_date: Optional[date] = Query(None, description="Start date for filtering orders (YYYY-MM-DD). Defaults to today."),
    end_date: Optional[date] = Query(None, description="End date for filtering orders (YYYY-MM-DD). Defaults to today."),
    db: Session = Depends(get_db),
):
    """
    Retrieves all orders associated with a specific agent, with optional date filtering.
    By default, it returns orders for the current day.
    """
    try:
        if start_date is None:
            start_date = datetime.utcnow().date()
        if end_date is None:
            end_date = datetime.utcnow().date()

        orders = OrderService.get_agent_orders(db, agent_id, start_date, end_date)
        return orders
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to retrieve orders: {str(e)}")


@router.put(
    "/orders/{order_id}/status",
    response_model=OrderSchema,
    summary="Update order status",
)
def update_order_status(
    order_id: str,
    status: str,
    db: Session = Depends(get_db),
):
    """
    Updates an order's status (new, in_progress, ready, completed, cancelled).
    """
    try:
        order = OrderService.update_order_status(db, order_id, status)
        return order
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update order status: {str(e)}")
