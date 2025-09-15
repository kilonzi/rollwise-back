import csv
import os
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List

import chromadb
from chromadb import Collection
from sqlalchemy.orm import Session

from app.models import BusinessDataset


class BusinessDatasetService:
    """Service for managing business datasets with ChromaDB integration"""

    def __init__(self, db: Session):
        self.db = db
        self._client = None
        self._collection = None

    @property
    def client(self):
        """Lazy initialization of ChromaDB client"""
        if self._client is None:
            self._client = chromadb.PersistentClient(path="store/chroma")
        return self._client

    @property
    def collection(self) -> Collection:
        """Get or create the business knowledge collection"""
        if self._collection is None:
            self._collection = self.client.get_or_create_collection("business-knowledge")
        return self._collection

    def upload_dataset(
            self,
            tenant_id: str,
            agent_id: str,
            label: str,
            file_path: str,
            file_name: str,
            file_type: str,
            extra_info: Optional[Dict[str, Any]] = None,
            columns: Optional[List[str]] = None
    ) -> BusinessDataset:
        """Upload and process a dataset file"""

        # Create database record
        dataset = BusinessDataset(
            tenant_id=tenant_id,
            agent_id=agent_id,
            label=label,
            file_name=file_name,
            file_path=file_path,
            file_type=file_type,
            columns=columns or [],
            extra_info={**(extra_info or {}), **({"columns": columns} if columns else {})}
        )

        self.db.add(dataset)
        self.db.commit()
        self.db.refresh(dataset)

        # Process the file based on type
        try:
            if file_type.lower() == "csv":
                record_count = self._ingest_csv(dataset)
            elif file_type.lower() == "txt":
                record_count = self._ingest_txt(dataset)
            elif file_type.lower() == "pdf":
                record_count = self._ingest_pdf(dataset)
            else:
                raise ValueError(f"Unsupported file type: {file_type}")

            # Update dataset with processing info
            dataset.record_count = record_count
            dataset.processed_at = datetime.now()
            self.db.commit()

        except Exception as e:
            print(f"Error processing dataset {dataset.id}: {e}")
            # Mark as failed but keep the record
            dataset.extra_info = {**dataset.extra_info, "processing_error": str(e)}
            self.db.commit()
            raise

        return dataset

    def _normalize_key(self, key: Any) -> str:
        """Safely normalize a key to a lowercase underscore string."""
        try:
            s = str(key) if key is not None else ""
            s = s.strip().lower()
            # Replace spaces and non-alphanumeric with underscores
            import re
            s = re.sub(r"[^a-z0-9]+", "_", s)
            s = s.strip("_")
            return s or "field"
        except Exception:
            return "field"

    def _ingest_csv(self, dataset: BusinessDataset) -> int:
        """Ingest a CSV into ChromaDB, each row becomes a document"""
        record_count = 0

        with open(dataset.file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            documents = []
            metadatas = []
            ids = []

            # Precompute normalized selected columns if provided
            selected_columns = None
            if getattr(dataset, 'columns', None):
                # Use set of normalized column names for quick filter
                selected_columns = {self._normalize_key(c) for c in (dataset.columns or []) if c is not None}

            for row in reader:
                if not any(row.values()):  # Skip empty rows
                    continue

                metadata = {
                    "tenant_id": dataset.tenant_id,
                    "agent_id": dataset.agent_id,
                    "type": dataset.label,
                    "dataset_id": str(dataset.id)
                }

                # Add row values as metadata but only the selected columns if provided
                for k, v in row.items():
                    if v is None:
                        continue
                    norm_key = self._normalize_key(k)
                    if not norm_key:
                        continue
                    if selected_columns is not None and norm_key not in selected_columns:
                        continue
                    try:
                        metadata[norm_key] = str(v)
                    except Exception:
                        # Fallback safe stringify
                        metadata[norm_key] = f"{v}"

                # Create document text from the row
                doc_text = self._create_document_text(row, dataset.label)

                documents.append(doc_text)
                metadatas.append(metadata)
                ids.append(f"{dataset.id}_{str(uuid.uuid4())}")
                record_count += 1

            # Batch insert to ChromaDB
            if documents:
                self.collection.add(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )

        return record_count

    def _ingest_txt(self, dataset: BusinessDataset) -> int:
        """Ingest a text file into ChromaDB, each line becomes a document"""
        record_count = 0

        with open(dataset.file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

            documents = []
            metadatas = []
            ids = []

            for i, line in enumerate(lines):
                line = line.strip()
                if not line:  # Skip empty lines
                    continue

                metadata = {
                    "tenant_id": dataset.tenant_id,
                    "agent_id": dataset.agent_id,
                    "type": dataset.label,
                    "dataset_id": str(dataset.id),
                    "line_number": i + 1
                }

                documents.append(line)
                metadatas.append(metadata)
                ids.append(f"{dataset.id}_line_{i + 1}")
                record_count += 1

            # Batch insert to ChromaDB
            if documents:
                self.collection.add(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )

        return record_count

    def _ingest_pdf(self, dataset: BusinessDataset) -> int:
        """Ingest a PDF file into ChromaDB, each page or section becomes a document"""
        try:
            import PyPDF2
        except ImportError:
            raise ImportError("PyPDF2 is required for PDF processing. Install with: pip install PyPDF2")

        record_count = 0

        try:
            with open(dataset.file_path, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)

                documents = []
                metadatas = []
                ids = []

                for page_num, page in enumerate(pdf_reader.pages):
                    text = page.extract_text()
                    if not text.strip():  # Skip empty pages
                        continue

                    metadata = {
                        "tenant_id": dataset.tenant_id,
                        "agent_id": dataset.agent_id,
                        "type": dataset.label,
                        "dataset_id": str(dataset.id),
                        "page_number": page_num + 1,
                        "file_type": "pdf"
                    }

                    # Clean up text
                    cleaned_text = text.replace('\n', ' ').replace('\r', ' ')
                    cleaned_text = ' '.join(cleaned_text.split())  # Remove extra whitespace

                    if len(cleaned_text) > 50:  # Only process pages with meaningful content
                        documents.append(f"{dataset.label.title()} (Page {page_num + 1}) - {cleaned_text}")
                        metadatas.append(metadata)
                        ids.append(f"{dataset.id}_page_{page_num + 1}")
                        record_count += 1

                # Batch insert to ChromaDB
                if documents:
                    self.collection.add(
                        documents=documents,
                        metadatas=metadatas,
                        ids=ids
                    )

        except Exception as e:
            raise Exception(f"Error processing PDF: {str(e)}")

        return record_count

    def _create_document_text(self, row: Dict[str, str], label: str) -> str:
        """Create a meaningful document text from CSV row"""
        # Create a readable text representation
        parts = []
        for key, value in row.items():
            if value and key:
                parts.append(f"{key}: {value}")

        return f"{label.title()} - " + ", ".join(parts)

    def replace_dataset(
            self,
            tenant_id: str,
            agent_id: str,
            label: str,
            file_path: str,
            file_name: str,
            file_type: str,
            extra_info: Optional[Dict[str, Any]] = None
    ) -> BusinessDataset:
        """Replace an existing dataset (delete old, upload new)"""

        # Delete existing data from ChromaDB
        try:
            self.collection.delete(where={
                "$and": [
                    {"tenant_id": {"$eq": tenant_id}},
                    {"agent_id": {"$eq": agent_id}},
                    {"type": {"$eq": label}}
                ]
            })
        except Exception as e:
            print(f"Error deleting existing data: {e}")

        # Mark existing database records as inactive
        existing_datasets = (
            self.db.query(BusinessDataset)
            .filter(
                BusinessDataset.tenant_id == tenant_id,
                BusinessDataset.agent_id == agent_id,
                BusinessDataset.label == label,
                BusinessDataset.active
            )
            .all()
        )

        for dataset in existing_datasets:
            dataset.active = False

        self.db.commit()

        # Upload new dataset
        return self.upload_dataset(
            tenant_id, agent_id, label, file_path, file_name, file_type, extra_info
        )

    def search_agent_dataset(
            self,
            tenant_id: str,
            agent_id: str,
            label: str,
            query: Optional[str] = "",
            top_k: int = 5,
            return_all: bool = False
    ) -> Dict[str, Any]:
        """Search datasets for an agent"""
        try:
            where_clause = {
                "$and": [
                    {"tenant_id": {"$eq": tenant_id}},
                    {"agent_id": {"$eq": agent_id}},
                    {"type": {"$eq": label}} if label else {}
                ]
            }

            # Handle empty query for return_all case
            query_texts = [query] if query else [""]
            n_results = 100 if return_all else top_k

            results = self.collection.query(
                query_texts=query_texts,
                n_results=n_results,
                where=where_clause,
                include=['documents']
            )

            return {
                "success": True,
                "results": results,
                "count": len(results.get("documents", [None])[0] or [])
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "results": None,
                "count": 0
            }

    def list_datasets(
            self,
            tenant_id: str,
            agent_id: Optional[str] = None,
            label: Optional[str] = None
    ) -> List[BusinessDataset]:
        """List datasets for a tenant/agent"""
        query = self.db.query(BusinessDataset).filter(
            BusinessDataset.tenant_id == tenant_id,
            BusinessDataset.active
        )

        if agent_id:
            query = query.filter(BusinessDataset.agent_id == agent_id)

        if label:
            query = query.filter(BusinessDataset.label == label)

        return query.order_by(BusinessDataset.created_at.desc()).all()

    def get_dataset(self, dataset_id: int) -> Optional[BusinessDataset]:
        """Get a dataset by ID"""
        return (
            self.db.query(BusinessDataset)
            .filter(BusinessDataset.id == dataset_id, BusinessDataset.active)
            .first()
        )

    def delete_dataset(self, dataset_id: int) -> bool:
        """Delete a dataset (soft delete + ChromaDB cleanup)"""
        dataset = self.get_dataset(dataset_id)
        if not dataset:
            return False

        try:
            # Delete from ChromaDB
            self.collection.delete(where={"dataset_id": {"$eq": str(dataset_id)}})

            # Soft delete in database
            dataset.active = False
            self.db.commit()

            # Delete file if it exists
            if os.path.exists(dataset.file_path):
                os.remove(dataset.file_path)

            return True

        except Exception as e:
            print(f"Error deleting dataset {dataset_id}: {e}")
            return False


def search_agent_dataset(
        tenant_id: str,
        agent_id: str,
        label: str,
        query: Optional[str] = "",
        top_k: int = 10,
        return_all: bool = False
) -> Dict[str, Any]:
    """Standalone function for searching agent datasets"""
    from app.models import get_db_session

    db = get_db_session()
    try:
        service = BusinessDatasetService(db)
        return service.search_agent_dataset(tenant_id, agent_id, label, query, top_k, return_all)
    finally:
        db.close()
