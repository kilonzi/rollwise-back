"""
MenuItem API endpoints for restaurant menu management
"""

import csv
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from sqlalchemy.orm import Session

from app.api.schemas.menu_item import (
    MenuItemCreate,
    MenuItemUpdate,
    MenuItemResponse,
    MenuItemListResponse,
    MenuItemFilter,
    MenuItemBulkUpdate,
)
from app.models import get_db
from app.services.menu_item_service import MenuItemService
from app.utils.logging_config import app_logger

router = APIRouter()


@router.post(
    "/{agent_id}/menu-items",
    response_model=MenuItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_menu_item(
        agent_id: str, menu_item: MenuItemCreate, db: Session = Depends(get_db)
):
    """Create a new menu item for an agent"""
    try:
        created_item = MenuItemService.create_menu_item(db, agent_id, menu_item)
        return MenuItemResponse.model_validate(created_item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        app_logger.error(f"Error creating menu item: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{agent_id}/menu-items", response_model=MenuItemListResponse)
async def get_menu_items(
        agent_id: str,
        db: Session = Depends(get_db),
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(50, ge=1, le=100, description="Items per page"),
        category: Optional[str] = Query(None, description="Filter by category"),
        available: Optional[bool] = Query(None, description="Filter by availability"),
        is_popular: Optional[bool] = Query(None, description="Filter by popular items"),
        is_special: Optional[bool] = Query(None, description="Filter by special items"),
        is_new: Optional[bool] = Query(None, description="Filter by new items"),
        is_limited_time: Optional[bool] = Query(
            None, description="Filter by limited time items"
        ),
        is_hidden: Optional[bool] = Query(None, description="Filter by hidden items"),
        requires_age_check: Optional[bool] = Query(
            None, description="Filter by age check requirement"
        ),
        has_discount: Optional[bool] = Query(None, description="Filter by discount items"),
        search: Optional[str] = Query(
            None, description="Search in name, description, or ingredients"
        ),
):
    """Get paginated list of menu items with optional filtering"""
    try:
        filters = MenuItemFilter(
            category=category,
            available=available,
            is_popular=is_popular,
            is_special=is_special,
            is_new=is_new,
            is_limited_time=is_limited_time,
            is_hidden=is_hidden,
            requires_age_check=requires_age_check,
            has_discount=has_discount,
            search=search,
        )

        result = MenuItemService.get_menu_items(db, agent_id, filters, page, page_size)

        return MenuItemListResponse(
            items=[MenuItemResponse.model_validate(item) for item in result["items"]],
            total=result["total"],
            page=result["page"],
            page_size=result["page_size"],
            total_pages=result["total_pages"],
        )
    except Exception as e:
        app_logger.error(f"Error getting menu items: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{agent_id}/menu-items/{item_id}", response_model=MenuItemResponse)
async def get_menu_item(agent_id: str, item_id: str, db: Session = Depends(get_db)):
    """Get a specific menu item by ID"""
    try:
        menu_item = MenuItemService.get_menu_item(db, agent_id, item_id)
        if not menu_item:
            raise HTTPException(status_code=404, detail="Menu item not found")
        return MenuItemResponse.model_validate(menu_item)
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error getting menu item: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{agent_id}/menu-items/{item_id}", response_model=MenuItemResponse)
async def update_menu_item(
        agent_id: str, item_id: str, updates: MenuItemUpdate, db: Session = Depends(get_db)
):
    """Update a menu item"""
    try:
        updated_item = MenuItemService.update_menu_item(db, agent_id, item_id, updates)
        return MenuItemResponse.model_validate(updated_item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        app_logger.error(f"Error updating menu item: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete(
    "/{agent_id}/menu-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_menu_item(agent_id: str, item_id: str, db: Session = Depends(get_db)):
    """Delete a menu item (soft delete)"""
    try:
        success = MenuItemService.delete_menu_item(db, agent_id, item_id)
        if not success:
            raise HTTPException(status_code=404, detail="Menu item not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        app_logger.error(f"Error deleting menu item: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/{agent_id}/menu-items/bulk-update", response_model=List[MenuItemResponse]
)
async def bulk_update_menu_items(
        agent_id: str, bulk_update: MenuItemBulkUpdate, db: Session = Depends(get_db)
):
    """Bulk update multiple menu items"""
    try:
        updated_items = MenuItemService.bulk_update_menu_items(
            db, agent_id, bulk_update.item_ids, bulk_update.updates
        )
        return [MenuItemResponse.model_validate(item) for item in updated_items]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        app_logger.error(f"Error bulk updating menu items: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{agent_id}/menu/categories", response_model=List[str], tags=["Menu"])
async def get_menu_categories(agent_id: str, db: Session = Depends(get_db)):
    """Get all unique menu categories for an agent"""
    try:
        categories = MenuItemService.get_menu_categories(db, agent_id)
        return categories  # Filter out empty categories
    except Exception as e:
        app_logger.error(f"Error getting menu categories: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put(
    "/{agent_id}/menu-items/{item_id}/toggle-availability",
    response_model=MenuItemResponse,
)
async def toggle_menu_item_availability(
        agent_id: str, item_id: str, db: Session = Depends(get_db)
):
    """Toggle the availability status of a menu item"""
    try:
        updated_item = MenuItemService.toggle_availability(db, agent_id, item_id)
        return MenuItemResponse.model_validate(updated_item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        app_logger.error(f"Error toggling menu item availability: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{agent_id}/menu/upload-csv", response_model=dict, tags=["Menu"])
async def upload_menu_items_csv(
        agent_id: str,
        file: UploadFile = File(..., description="CSV file with menu items"),
        skip_errors: bool = Query(
            False, description="Skip invalid rows and continue processing"
        ),
        db: Session = Depends(get_db),
):
    """
    Upload menu items from a CSV file

    Expected CSV columns (case-insensitive):
    - name (required): Dish/drink name
    - description: Short details about the item
    - category (required): Appetizer, Entree, Drink, Dessert
    - price (required): Selling price
    - number: Menu item number/ID
    - allergens: Allergen information
    - ingredients: Base ingredients
    - prep_time: Preparation time in minutes
    - notes: Additional notes
    - available: true/false (default: true)
    - is_popular: true/false (default: false)
    - is_special: true/false (default: false)
    - is_new: true/false (default: false)
    - is_limited_time: true/false (default: false)
    - is_hidden: true/false (default: false)
    - requires_age_check: true/false (default: false)
    - has_discount: true/false (default: false)
    """
    try:
        # Validate file type
        if not file.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="File must be a CSV file")

        # Read file content
        content = await file.read()
        csv_content = content.decode("utf-8")

        # Parse CSV
        csv_reader = csv.DictReader(io.StringIO(csv_content))

        # Normalize column names (convert to lowercase and remove spaces)
        fieldnames = [
            field.lower().strip().replace(" ", "_") for field in csv_reader.fieldnames
        ]

        # Required columns
        required_columns = ["name", "category", "price"]
        missing_columns = [col for col in required_columns if col not in fieldnames]
        if missing_columns:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required columns: {', '.join(missing_columns)}",
            )

        # Process rows
        created_items = []
        errors = []
        row_number = 1

        for row in csv_reader:
            row_number += 1
            try:
                # Normalize row keys
                normalized_row = {
                    key.lower().strip().replace(" ", "_"): value.strip()
                    if isinstance(value, str)
                    else value
                    for key, value in row.items()
                }

                # Helper function to convert string to boolean
                def str_to_bool(value, default=False):
                    if not value or value.strip() == "":
                        return default
                    return value.lower().strip() in ["true", "1", "yes", "y", "on"]

                # Helper function to convert string to float
                def str_to_float(value, field_name):
                    if not value or value.strip() == "":
                        raise ValueError(f"{field_name} is required")
                    try:
                        return float(value.strip())
                    except ValueError:
                        raise ValueError(f"Invalid {field_name}: {value}")

                # Helper function to convert string to int
                def str_to_int(value, default=None):
                    if not value or value.strip() == "":
                        return default
                    try:
                        return int(float(value.strip()))
                    except ValueError:
                        return default

                # Build menu item data
                menu_item_data = MenuItemCreate(
                    name=normalized_row.get("name", "").strip(),
                    description=normalized_row.get("description", "").strip() or None,
                    category=normalized_row.get("category", "").strip(),
                    price=str_to_float(normalized_row.get("price"), "price"),
                    number=normalized_row.get("number", "").strip() or None,
                    allergens=normalized_row.get("allergens", "").strip() or None,
                    ingredients=normalized_row.get("ingredients", "").strip() or None,
                    prep_time=str_to_int(normalized_row.get("prep_time")),
                    notes=normalized_row.get("notes", "").strip() or None,
                    available=str_to_bool(normalized_row.get("available"), True),
                    is_popular=str_to_bool(normalized_row.get("is_popular"), False),
                    is_special=str_to_bool(normalized_row.get("is_special"), False),
                    is_new=str_to_bool(normalized_row.get("is_new"), False),
                    is_limited_time=str_to_bool(
                        normalized_row.get("is_limited_time"), False
                    ),
                    is_hidden=str_to_bool(normalized_row.get("is_hidden"), False),
                    requires_age_check=str_to_bool(
                        normalized_row.get("requires_age_check"), False
                    ),
                    has_discount=str_to_bool(normalized_row.get("has_discount"), False),
                )

                # Validate required fields
                if not menu_item_data.name:
                    raise ValueError("Name is required")
                if not menu_item_data.category:
                    raise ValueError("Category is required")

                # Create menu item
                created_item = MenuItemService.create_menu_item(
                    db, agent_id, menu_item_data
                )
                created_items.append(MenuItemResponse.model_validate(created_item))

            except Exception as e:
                error_msg = f"Row {row_number}: {str(e)}"
                errors.append(error_msg)
                app_logger.warning(f"CSV upload error - {error_msg}")

                if not skip_errors:
                    raise HTTPException(status_code=400, detail=error_msg)

        # Return results
        result = {
            "success": True,
            "total_processed": row_number - 1,
            "items_created": len(created_items),
            "errors_count": len(errors),
            "created_items": created_items,
        }

        if errors:
            result["errors"] = errors

        app_logger.info(
            f"CSV upload completed for agent {agent_id}: {len(created_items)} items created, {len(errors)} errors"
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error uploading CSV for agent {agent_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to process CSV file: {str(e)}"
        )


@router.get("/{agent_id}/menu/csv-template", tags=["Menu"])
async def get_csv_template(agent_id: str):
    """
    Download a CSV template for menu items upload with proper headers and example data
    """
    try:
        # Create CSV template with headers and example rows
        template_rows = [
            # Header row (will be written by DictWriter)
            {
                "name": "Margherita Pizza",
                "description": "Classic pizza with tomato, mozzarella, and basil",
                "category": "Entree",
                "price": "15.99",
                "number": "P001",
                "allergens": "Contains dairy, gluten",
                "ingredients": "Tomato sauce, mozzarella, basil, pizza dough",
                "prep_time": "15",
                "notes": "Customer favorite",
                "available": "true",
                "is_popular": "true",
                "is_special": "false",
                "is_new": "false",
                "is_limited_time": "false",
                "is_hidden": "false",
                "requires_age_check": "false",
                "has_discount": "false",
            },
            {
                "name": "Caesar Salad",
                "description": "Fresh romaine lettuce with caesar dressing and croutons",
                "category": "Appetizer",
                "price": "8.99",
                "number": "A001",
                "allergens": "Contains dairy, eggs",
                "ingredients": "Romaine lettuce, caesar dressing, croutons, parmesan",
                "prep_time": "5",
                "notes": "Recently added to menu",
                "available": "true",
                "is_popular": "false",
                "is_special": "false",
                "is_new": "true",
                "is_limited_time": "false",
                "is_hidden": "false",
                "requires_age_check": "false",
                "has_discount": "false",
            },
            {
                "name": "House Wine",
                "description": "Red or white wine by the glass",
                "category": "Drink",
                "price": "7.50",
                "number": "D101",
                "allergens": "Contains sulfites",
                "ingredients": "Grape wine",
                "prep_time": "1",
                "notes": "Ask customer for red or white preference",
                "available": "true",
                "is_popular": "false",
                "is_special": "true",
                "is_new": "false",
                "is_limited_time": "false",
                "is_hidden": "false",
                "requires_age_check": "true",
                "has_discount": "true",
            },
        ]

        # Define column order and headers
        fieldnames = [
            "name",
            "description",
            "category",
            "price",
            "number",
            "allergens",
            "ingredients",
            "prep_time",
            "notes",
            "available",
            "is_popular",
            "is_special",
            "is_new",
            "is_limited_time",
            "is_hidden",
            "requires_age_check",
            "has_discount",
        ]

        # Create CSV content
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)

        # Write header row
        writer.writeheader()

        # Write example data rows
        writer.writerows(template_rows)

        csv_content = output.getvalue()
        output.close()

        from fastapi.responses import Response

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=menu_items_template.csv",
                "Content-Type": "text/csv; charset=utf-8",
            },
        )

    except Exception as e:
        app_logger.error(f"Error generating CSV template: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate CSV template")


@router.get("/{agent_id}/menu/download-csv", tags=["Menu"])
async def download_menu_items_csv(
        agent_id: str,
        db: Session = Depends(get_db),
        category: Optional[str] = Query(None, description="Filter by category"),
        available: Optional[bool] = Query(None, description="Filter by availability"),
        is_popular: Optional[bool] = Query(None, description="Filter by popular items"),
        is_special: Optional[bool] = Query(None, description="Filter by special items"),
        is_new: Optional[bool] = Query(None, description="Filter by new items"),
        is_limited_time: Optional[bool] = Query(
            None, description="Filter by limited time items"
        ),
        is_hidden: Optional[bool] = Query(None, description="Filter by hidden items"),
        requires_age_check: Optional[bool] = Query(
            None, description="Filter by age check requirement"
        ),
        has_discount: Optional[bool] = Query(None, description="Filter by discount items"),
        search: Optional[str] = Query(
            None, description="Search in name, description, or ingredients"
        ),
):
    """
    Download menu items as CSV file with optional filtering
    """
    try:
        # Apply filters to get the menu items
        filters = MenuItemFilter(
            category=category,
            available=available,
            is_popular=is_popular,
            is_special=is_special,
            is_new=is_new,
            is_limited_time=is_limited_time,
            is_hidden=is_hidden,
            requires_age_check=requires_age_check,
            has_discount=has_discount,
            search=search,
        )

        # Get all items (no pagination for download)
        result = MenuItemService.get_menu_items(
            db, agent_id, filters, page=1, page_size=10000
        )
        menu_items = result["items"]

        if not menu_items:
            raise HTTPException(status_code=404, detail="No menu items found")

        # Create CSV content
        output = io.StringIO()
        fieldnames = [
            "id",
            # "number",  # Removed as per requirements
            "name",
            "description",
            "category",
            "price",
            "allergens",
            "ingredients",
            "prep_time",
            "notes",
            "available",
            "is_popular",
            "is_special",
            "is_new",
            "is_limited_time",
            "is_hidden",
            "requires_age_check",
            "has_discount",
            "created_at",
            "updated_at",
        ]

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        # Write menu items to CSV
        for item in menu_items:
            writer.writerow(
                {
                    "id": item.id,
                    # "number": item.number or "",  # Removed as per requirements
                    "name": item.name,
                    "description": item.description or "",
                    "category": item.category,
                    "price": item.price,
                    "allergens": item.allergens or "",
                    "ingredients": item.ingredients or "",
                    "prep_time": item.prep_time or "",
                    "notes": item.notes or "",
                    "available": str(item.available).lower(),
                    "is_popular": str(item.is_popular).lower(),
                    "is_special": str(item.is_special).lower(),
                    "is_new": str(item.is_new).lower(),
                    "is_limited_time": str(item.is_limited_time).lower(),
                    "is_hidden": str(item.is_hidden).lower(),
                    "requires_age_check": str(item.requires_age_check).lower(),
                    "has_discount": str(item.has_discount).lower(),
                    "created_at": item.created_at.isoformat(),
                    "updated_at": item.updated_at.isoformat(),
                }
            )

        csv_content = output.getvalue()
        output.close()

        # Generate filename with timestamp
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"menu_items_{agent_id}_{timestamp}.csv"

        from fastapi.responses import Response

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(
            f"Error downloading menu items CSV for agent {agent_id}: {str(e)}"
        )
        raise HTTPException(status_code=500, detail="Failed to generate CSV download")
