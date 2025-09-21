from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class OrderItemSchema(BaseModel):
    id: int
    name: str
    quantity: int
    price: float
    note: Optional[str] = None

    class Config:
        from_attributes = True


class OrderItemCreateSchema(BaseModel):
    name: str
    quantity: int
    price: float
    note: Optional[str] = None


class OrderItemUpdateSchema(BaseModel):
    name: str
    quantity: int
    price: float
    note: Optional[str] = None


class OrderSchema(BaseModel):
    id: str
    conversation_id: str
    customer_phone: Optional[str] = None
    customer_name: Optional[str] = None
    status: str
    total_price: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    order_items: List[OrderItemSchema] = []

    class Config:
        from_attributes = True


class OrderCreateSchema(BaseModel):
    conversation_id: str = Field(..., description="The ID of the conversation associated with the order.")
    customer_phone: Optional[str] = Field(None, description="The customer's phone number.")
    customer_name: Optional[str] = Field(None, description="The customer's name.")
    status: str = Field("new", description="The status of the order.")
    total_price: Optional[float] = Field(None, description="The total price of the order.")
    order_items: List[OrderItemCreateSchema] = Field([], description="A list of items in the order.")


class OrderUpdateSchema(BaseModel):
    customer_phone: Optional[str] = Field(None, description="The customer's phone number.")
    customer_name: Optional[str] = Field(None, description="The customer's name.")
    status: Optional[str] = Field(None, description="The status of the order.")
    total_price: Optional[float] = Field(None, description="The total price of the order.")
