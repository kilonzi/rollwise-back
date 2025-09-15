import os
import shutil
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import get_db, BusinessDataset, Agent, Tenant
from app.services.business_dataset_service import BusinessDatasetService

router = APIRouter(prefix="/datasets", tags=["datasets"])

# Create uploads directory if it doesn't exist
UPLOAD_DIR = "store/uploads/datasets"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# Pydantic models for API
class DatasetResponse(BaseModel):
    id: int
    tenant_id: str
    agent_id: str
    label: str
    file_name: str
    file_type: str
    record_count: int
    uploaded_at: datetime
    processed_at: Optional[datetime]
    extra_info: dict
    active: bool

    class Config:
        from_attributes = True


class DatasetSearchRequest(BaseModel):
    label: str
    query: Optional[str] = ""
    top_k: Optional[int] = 5
    return_all: Optional[bool] = False


class DatasetSearchResponse(BaseModel):
    success: bool
    count: int
    results: Optional[dict] = None
    error: Optional[str] = None


@router.post("/upload/{agent_id}", response_model=DatasetResponse)
async def upload_dataset(
        agent_id: str,
        label: str = Form(..., description="Dataset label (e.g., clients, hours, inventory)"),
        file: UploadFile = File(...),
        replace_existing: bool = Form(False, description="Replace existing dataset with same label"),
        db: Session = Depends(get_db)
):
    """Upload a business dataset file for an agent"""

    # Verify agent exists and is active
    agent = (
        db.query(Agent)
        .join(Tenant)
        .filter(Agent.id == agent_id, Agent.active, Tenant.active)
        .first()
    )

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found or inactive")

    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    file_extension = file.filename.split('.')[-1].lower()
    if file_extension not in ['csv', 'txt', 'pdf']:
        raise HTTPException(
            status_code=400,
            detail="Only CSV, TXT, and PDF files are supported"
        )

    # Create unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = label.replace(" ", "_").lower()
    unique_filename = f"{agent.tenant_id}_{agent_id}_{safe_label}_{timestamp}.{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    try:
        # Save uploaded file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Process with service
        service = BusinessDatasetService(db)

        if replace_existing:
            dataset = service.replace_dataset(
                tenant_id=str(agent.tenant_id),
                agent_id=agent_id,
                label=label,
                file_path=file_path,
                file_name=file.filename,
                file_type=file_extension
            )
        else:
            dataset = service.upload_dataset(
                tenant_id=str(agent.tenant_id),
                agent_id=agent_id,
                label=label,
                file_path=file_path,
                file_name=file.filename,
                file_type=file_extension
            )

        return DatasetResponse.from_orm(dataset)

    except Exception as e:
        # Clean up file if processing failed
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Failed to process dataset: {str(e)}")


@router.get("/agent/{agent_id}", response_model=List[DatasetResponse])
async def list_agent_datasets(
        agent_id: str,
        label: Optional[str] = None,
        db: Session = Depends(get_db)
):
    """List all datasets for an agent"""

    # Verify agent exists
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    service = BusinessDatasetService(db)
    datasets = service.list_datasets(
        tenant_id=agent.tenant_id,
        agent_id=agent_id,
        label=label
    )

    return [DatasetResponse.from_orm(dataset) for dataset in datasets]


@router.get("/tenant/{tenant_id}", response_model=List[DatasetResponse])
async def list_tenant_datasets(
        tenant_id: str,
        agent_id: Optional[str] = None,
        label: Optional[str] = None,
        db: Session = Depends(get_db)
):
    """List all datasets for a tenant"""

    # Verify tenant exists
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.active).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    service = BusinessDatasetService(db)
    datasets = service.list_datasets(
        tenant_id=tenant_id,
        agent_id=agent_id,
        label=label
    )

    return [DatasetResponse.from_orm(dataset) for dataset in datasets]


@router.post("/search/{agent_id}", response_model=DatasetSearchResponse)
async def search_dataset(
        agent_id: str,
        search_request: DatasetSearchRequest,
        db: Session = Depends(get_db)
):
    """Search datasets for an agent"""

    # Verify agent exists
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    service = BusinessDatasetService(db)
    results = service.search_agent_dataset(
        tenant_id=str(agent.tenant_id),
        agent_id=agent_id,
        label=search_request.label,
        query=search_request.query,
        top_k=search_request.top_k,
        return_all=search_request.return_all
    )

    return DatasetSearchResponse(**results)


@router.get("/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(
        dataset_id: int,
        db: Session = Depends(get_db)
):
    """Get a specific dataset by ID"""

    service = BusinessDatasetService(db)
    dataset = service.get_dataset(dataset_id)

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return DatasetResponse.from_orm(dataset)


@router.delete("/{dataset_id}")
async def delete_dataset(
        dataset_id: int,
        db: Session = Depends(get_db)
):
    """Delete a dataset"""

    service = BusinessDatasetService(db)
    success = service.delete_dataset(dataset_id)

    if not success:
        raise HTTPException(status_code=404, detail="Dataset not found or could not be deleted")

    return JSONResponse(
        content={
            "message": "Dataset deleted successfully",
            "dataset_id": dataset_id
        },
        status_code=200
    )


@router.get("/labels/{agent_id}")
async def get_dataset_labels(
        agent_id: str,
        db: Session = Depends(get_db)
):
    """Get all unique labels for an agent's datasets"""

    # Verify agent exists
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Get unique labels
    labels = (
        db.query(BusinessDataset.label)
        .filter(
            BusinessDataset.tenant_id == agent.tenant_id,
            BusinessDataset.agent_id == agent_id,
            BusinessDataset.active
        )
        .distinct()
        .all()
    )

    return {"labels": [label[0] for label in labels]}
