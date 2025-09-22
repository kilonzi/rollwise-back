"""
MenuItem schemas for API validation and serialization
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class MenuItemBase(BaseModel):
    """Base schema for MenuItem with common fields"""

    number: Optional[str] = Field(None, description="Unique identifier/menu number")
    name: str = Field(..., min_length=1, max_length=200, description="Dish/drink name")
    description: Optional[str] = Field(None, description="Short details about the item")
    category: str = Field(
        ..., description="Category: Appetizer, Entree, Drink, Dessert"
    )
    price: float = Field(..., ge=0, description="Selling price")
    allergens: Optional[str] = Field(
        None, description="Allergen information (e.g., contains nuts, dairy-free)"
    )
    ingredients: Optional[str] = Field(None, description="Base ingredients")
    prep_time: Optional[int] = Field(
        None, ge=0, description="Preparation time in minutes"
    )
    notes: Optional[str] = Field(None, description="Additional notes")

    # Action flags/toggles
    available: bool = Field(True, description="Available for ordering")
    is_popular: bool = Field(False, description="Mark as popular/trending")
    is_special: bool = Field(False, description="Daily or seasonal special")
    is_new: bool = Field(False, description="Recently added item")
    is_limited_time: bool = Field(False, description="Temporary offering")
    is_hidden: bool = Field(False, description="Hidden from customer menu (staff only)")
    requires_age_check: bool = Field(
        False, description="Requires age verification (alcohol)"
    )
    has_discount: bool = Field(False, description="Item has special pricing/discount")


class MenuItemCreate(MenuItemBase):
    """Schema for creating a new MenuItem"""

    pass


class MenuItemUpdate(BaseModel):
    """Schema for updating a MenuItem (all fields optional)"""

    number: Optional[str] = Field(None, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    allergens: Optional[str] = None
    ingredients: Optional[str] = None
    prep_time: Optional[int] = Field(None, ge=0)
    notes: Optional[str] = None

    # Action flags/toggles
    available: Optional[bool] = None
    is_popular: Optional[bool] = None
    is_special: Optional[bool] = None
    is_new: Optional[bool] = None
    is_limited_time: Optional[bool] = None
    is_hidden: Optional[bool] = None
    requires_age_check: Optional[bool] = None
    has_discount: Optional[bool] = None


class MenuItemResponse(MenuItemBase):
    """Schema for MenuItem API responses"""

    id: str
    agent_id: str
    active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MenuItemListResponse(BaseModel):
    """Schema for paginated MenuItem list responses"""

    items: List[MenuItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class MenuItemFilter(BaseModel):
    """Schema for filtering MenuItems"""

    category: Optional[str] = None
    available: Optional[bool] = None
    is_popular: Optional[bool] = None
    is_special: Optional[bool] = None
    is_new: Optional[bool] = None
    is_limited_time: Optional[bool] = None
    is_hidden: Optional[bool] = None
    requires_age_check: Optional[bool] = None
    has_discount: Optional[bool] = None
    search: Optional[str] = Field(
        None, description="Search in name, description, or ingredients"
    )


class MenuItemBulkUpdate(BaseModel):
    """Schema for bulk updating MenuItems"""

    item_ids: List[str] = Field(
        ..., min_items=1, description="List of MenuItem IDs to update"
    )
    updates: MenuItemUpdate = Field(
        ..., description="Updates to apply to all selected items"
    )
