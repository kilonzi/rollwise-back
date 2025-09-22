import os
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, UserPayload
from app.api.schemas.collection_schemas import (
    CollectionResponse,
    CollectionListResponse,
    CollectionCreateResponse,
)
from app.models import get_db, Agent
from app.services.collection_service import CollectionService
from app.utils.logging_config import app_logger

router = APIRouter()


@router.post("/{agent_id}/collections/", response_model=CollectionCreateResponse)
async def create_collection(
    agent_id: str,
    name: str = Form(..., description="Display name for the collection"),
    description: Optional[str] = Form(
        None, description="Description of the collection content"
    ),
    notes: Optional[str] = Form(
        None, description="Additional notes or usage instructions"
    ),
    text_content: Optional[str] = Form(None, description="Text content to be ingested"),
    file: Optional[UploadFile] = File(None, description="File to upload and process"),
    current_user: UserPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new collection for an agent with either file upload or text content.

    Supports:
    - File uploads (PDF, TXT, CSV)
    - Direct text input
    - Automatic content type detection
    - ChromaDB integration for semantic search
    """
    try:
        # Verify agent exists and belongs to current user
        agent = (
            db.query(Agent)
            .filter(
                Agent.id == agent_id,
                Agent.user_id == current_user.id,
                Agent.active == True,
            )
            .first()
        )

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found or you don't have permission to access it",
            )

        # Validate input - must have either file or text_content
        if not file and not text_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either file upload or text_content must be provided",
            )

        # Handle file upload
        file_path = None
        file_type = None

        if file:
            # Validate file type
            allowed_extensions = {".pdf", ".txt", ".csv"}
            file_extension = os.path.splitext(file.filename)[1].lower()

            if file_extension not in allowed_extensions:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}",
                )

            # Create upload directory
            upload_dir = os.path.join("store", "uploads", agent_id)
            os.makedirs(upload_dir, exist_ok=True)

            # Generate unique filename
            file_id = str(uuid.uuid4())
            filename = f"{file_id}{file_extension}"
            file_path = os.path.join(upload_dir, filename)

            # Save file
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)

            file_type = file_extension[1:]  # Remove the dot
            app_logger.info(f"Uploaded file {file.filename} saved as {file_path}")

        # Create collection using the service
        collection_service = CollectionService(db)

        collection = await collection_service.create_collection(
            agent_id=agent_id,
            name=name,
            description=description or "",
            notes=notes or "",
            file_path=file_path,
            text_content=text_content,
            file_type=file_type,
        )

        app_logger.info(f"Created collection {collection.id} for agent {agent_id}")

        return CollectionCreateResponse(
            success=True,
            collection=CollectionResponse.model_validate(collection),
            message="Collection created successfully and content is being processed",
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error creating collection for agent {agent_id}: {str(e)}")

        # Clean up uploaded file if creation failed
        if "file_path" in locals() and file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

        return CollectionCreateResponse(
            success=False, message="Failed to create collection", error=str(e)
        )


@router.get("/{agent_id}/collections/", response_model=CollectionListResponse)
async def list_collections(
    agent_id: str,
    current_user: UserPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all collections for an agent"""
    try:
        # Verify agent exists and belongs to current user
        agent = (
            db.query(Agent)
            .filter(
                Agent.id == agent_id,
                Agent.user_id == current_user.id,
                Agent.active == True,
            )
            .first()
        )

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found or you don't have permission to access it",
            )

        collection_service = CollectionService(db)
        collections = collection_service.get_agent_collections(agent_id)

        return CollectionListResponse(
            collections=[CollectionResponse.model_validate(col) for col in collections],
            total=len(collections),
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error listing collections for agent {agent_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve collections",
        )


@router.get(
    "/{agent_id}/collections/{collection_id}", response_model=CollectionResponse
)
async def get_collection(
    agent_id: str,
    collection_id: str,
    current_user: UserPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get details of a specific collection"""
    try:
        # Verify agent exists and belongs to current user
        agent = (
            db.query(Agent)
            .filter(
                Agent.id == agent_id,
                Agent.user_id == current_user.id,
                Agent.active == True,
            )
            .first()
        )

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found or you don't have permission to access it",
            )

        collection_service = CollectionService(db)
        collection = collection_service.get_collection_by_id(collection_id)

        if not collection or collection.agent_id != agent_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found"
            )

        return CollectionResponse.model_validate(collection)

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error getting collection {collection_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve collection",
        )


@router.delete("/{agent_id}/collections/{collection_id}")
async def delete_collection(
    agent_id: str,
    collection_id: str,
    current_user: UserPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a collection"""
    try:
        # Verify agent exists and belongs to current user
        agent = (
            db.query(Agent)
            .filter(
                Agent.id == agent_id,
                Agent.user_id == current_user.id,
                Agent.active == True,
            )
            .first()
        )

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found or you don't have permission to access it",
            )

        collection_service = CollectionService(db)
        result = collection_service.delete_collection(agent_id, collection_id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found"
            )

        return {"success": True, "message": "Collection deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error deleting collection {collection_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete collection",
        )


@router.put(
    "/{agent_id}/collections/{collection_id}", response_model=CollectionCreateResponse
)
async def update_collection(
    agent_id: str,
    collection_id: str,
    name: str = Form(..., description="Display name for the collection"),
    description: Optional[str] = Form(
        None, description="Description of the collection content"
    ),
    notes: Optional[str] = Form(
        None, description="Additional notes or usage instructions"
    ),
    text_content: Optional[str] = Form(None, description="Text content to be ingested"),
    file: Optional[UploadFile] = File(None, description="File to upload and process"),
    current_user: UserPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update an existing collection for an agent with either file upload or text content.
    This will delete the current ChromaDB collection and create a new one with updated data.

    Supports:
    - File uploads (PDF, TXT, CSV)
    - Direct text input
    - Automatic content type detection
    - ChromaDB integration for semantic search
    """
    try:
        # Verify agent exists and belongs to current user
        agent = (
            db.query(Agent)
            .filter(
                Agent.id == agent_id,
                Agent.user_id == current_user.id,
                Agent.active == True,
            )
            .first()
        )

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found or you don't have permission to access it",
            )

        # Get existing collection
        collection_service = CollectionService(db)
        existing_collection = collection_service.get_collection_by_id(collection_id)

        if not existing_collection or existing_collection.agent_id != agent_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found"
            )

        # Validate input - must have either file or text_content
        if not file and not text_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either file upload or text_content must be provided",
            )

        # Store old file path for cleanup
        old_file_path = existing_collection.file_path

        # Handle file upload
        file_path = None
        file_type = None

        if file:
            # Validate file type
            allowed_extensions = {".pdf", ".txt", ".csv"}
            file_extension = os.path.splitext(file.filename)[1].lower()

            if file_extension not in allowed_extensions:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}",
                )

            # Create upload directory
            upload_dir = os.path.join("store", "uploads", agent_id)
            os.makedirs(upload_dir, exist_ok=True)

            # Generate unique filename
            file_id = str(uuid.uuid4())
            filename = f"{file_id}{file_extension}"
            file_path = os.path.join(upload_dir, filename)

            # Save file
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)

            file_type = file_extension[1:]  # Remove the dot
            app_logger.info(f"Uploaded file {file.filename} saved as {file_path}")

        # Delete old ChromaDB collection
        try:
            old_chroma_name = existing_collection.chroma_collection_name
            collection_service.chroma_client.delete_collection(name=old_chroma_name)
            app_logger.info(f"Deleted old ChromaDB collection: {old_chroma_name}")
        except Exception as e:
            app_logger.warning(f"Could not delete old ChromaDB collection: {e}")

        # Generate new ChromaDB collection name
        new_chroma_collection_name = (
            f"collection__{collection_id}_{uuid.uuid4().hex[:8]}"
        )

        # Update collection in database with new information
        existing_collection.name = collection_service.slugify_name(name)
        existing_collection.display_name = name
        existing_collection.description = description or ""
        existing_collection.notes = notes or ""
        existing_collection.file_path = file_path
        existing_collection.file_type = file_type or "text"
        existing_collection.chroma_collection_name = new_chroma_collection_name
        existing_collection.status = "processing"
        existing_collection.error_message = None
        existing_collection.chunk_count = 0

        db.commit()

        # Process content and create new ChromaDB collection
        try:
            await collection_service._process_collection_content(
                existing_collection, file_path, text_content
            )
            existing_collection.status = "ready"
            app_logger.info(
                f"Updated collection {collection_id} with new ChromaDB collection: {new_chroma_collection_name}"
            )
        except Exception as e:
            existing_collection.status = "error"
            existing_collection.error_message = str(e)
            app_logger.error(f"Error processing updated collection content: {str(e)}")

        db.commit()

        # Clean up old file if it exists and we have a new file
        if (
            old_file_path
            and file_path
            and old_file_path != file_path
            and os.path.exists(old_file_path)
        ):
            try:
                os.remove(old_file_path)
                app_logger.info(f"Cleaned up old file: {old_file_path}")
            except Exception as e:
                app_logger.warning(f"Could not delete old file: {e}")

        return CollectionCreateResponse(
            success=True,
            collection=CollectionResponse.model_validate(existing_collection),
            message="Collection updated successfully and content is being processed",
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(
            f"Error updating collection {collection_id} for agent {agent_id}: {str(e)}"
        )

        # Clean up new uploaded file if update failed
        if "file_path" in locals() and file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

        return CollectionCreateResponse(
            success=False, message="Failed to update collection", error=str(e)
        )
