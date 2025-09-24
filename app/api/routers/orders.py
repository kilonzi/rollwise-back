from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas.order import OrderSchema, OrderUpdateSchema, OrderStatusUpdateSchema, OrderItemUpdateSchema
from app.models import get_db
from app.services.order_service import OrderService

router = APIRouter()


@router.get(
    "/{order_id}",
    response_model=OrderSchema,
    summary="Get a specific order by its ID",
)
def get_order(order_id: str, db: Session = Depends(get_db)):
    """
    Retrieves a single order by its unique ID.
    """
    try:
        order = OrderService.get_order_by_id(db, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        return order
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to retrieve order: {str(e)}"
        )


@router.put(
    "/{order_id}",
    response_model=OrderSchema,
    summary="Update a specific order",
)
def update_order(
    order_id: str,
    order_data: OrderUpdateSchema,
    db: Session = Depends(get_db),
):
    """
    Updates the details of a specific order.
    """
    try:
        order_dict = order_data.model_dump(exclude_unset=True)
        order = OrderService.update_order(db, order_id, order_dict)
        return order
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update order: {str(e)}")


@router.put(
    "/{order_id}/status",
    response_model=OrderSchema,
    summary="Update the status of a specific order",
)
def update_order_status(
    order_id: str,
    status_data: OrderStatusUpdateSchema,
    db: Session = Depends(get_db),
):
    """
    Updates the status of a specific order (e.g., 'pending', 'confirmed', 'completed').
    """
    try:
        order = OrderService.update_order_status(db, order_id, status_data.status)
        return order
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to update order status: {str(e)}"
        )


@router.patch(
    "/order-items/{item_id}",
    summary="Update a specific order item",
)
def update_order_item(
    item_id: str,
    item_data: OrderItemUpdateSchema,
    db: Session = Depends(get_db),
):
    """
    Updates the details of a specific item within an order (e.g., quantity, notes).
    """
    try:
        item_dict = item_data.model_dump(exclude_unset=True)
        updated_item = OrderService.update_order_item(db, item_id, item_dict)
        return updated_item
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to update order item: {str(e)}"
        )


@router.delete(
    "/order-items/{item_id}",
    summary="Delete a specific order item",
    status_code=204,
)
def delete_order_item(item_id: str, db: Session = Depends(get_db)):
    """
    Deletes a specific item from an order.
    """
    try:
        OrderService.delete_order_item(db, item_id)
        return {"message": "Order item deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to delete order item: {str(e)}"
        )
