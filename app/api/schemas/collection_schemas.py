from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class CollectionBase(BaseModel):
    display_name: str = Field(..., description="The display name of the collection.")
    description: Optional[str] = Field(
        None, description="A brief description of the collection's content."
    )
    notes: Optional[str] = Field(
        None, description="Notes or rules for how the agent should use this collection."
    )


class CollectionCreate(CollectionBase):
    pass


class Collection(CollectionBase):
    id: str
    name: str
    status: str
    file_type: Optional[str] = None
    chunk_count: int
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CollectionCreateRequest(BaseModel):
    """Request model for creating a new collection"""

    name: str = Field(..., description="Display name for the collection")
    description: Optional[str] = Field(
        None, description="Description of the collection content"
    )
    notes: Optional[str] = Field(
        None, description="Additional notes or usage instructions"
    )
    text_content: Optional[str] = Field(
        None, description="Text content to be ingested (alternative to file upload)"
    )


class CollectionResponse(BaseModel):
    """Response model for collection operations"""

    id: str
    agent_id: str
    name: str
    display_name: str
    description: Optional[str]
    notes: Optional[str]
    file_path: Optional[str]
    file_type: Optional[str]
    content_type: Optional[str]
    chunk_count: int
    chroma_collection_name: str
    status: str
    error_message: Optional[str]
    active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CollectionListResponse(BaseModel):
    """Response model for listing collections"""

    collections: list[CollectionResponse]
    total: int


class CollectionCreateResponse(BaseModel):
    """Response model for collection creation"""

    success: bool
    collection: Optional[CollectionResponse] = None
    message: str
    error: Optional[str] = None
