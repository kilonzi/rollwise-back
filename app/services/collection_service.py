"""
Collection Service

Handles document collections with automatic processing, chunking, and ChromaDB storage.
Supports PDF, TXT, CSV files and plain text input with intelligent content analysis.
"""

import os
import re
import uuid
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from app.models import Collection
from app.utils.chroma_utils import get_chroma_client
from app.utils.logging_config import app_logger as logger


class CollectionService:
    """
    Service for managing document collections with ChromaDB integration.

    Features:
    - Document processing (PDF, TXT, CSV, plain text)
    - Smart content chunking and analysis
    - ChromaDB storage with semantic search
    - Content type auto-detection
    - Name slugification
    """

    def __init__(self, db_session: Session):
        self.db_session = db_session
        self._chroma_client = None

    @property
    def chroma_client(self):
        """Lazy initialization of ChromaDB client"""
        if self._chroma_client is None:
            self._chroma_client = chromadb.PersistentClient(path="store/chroma")
        return self._chroma_client

    def slugify_name(self, name: str) -> str:
        """Convert name to slugified format with underscores"""
        # Convert to lowercase and replace spaces with underscores
        slug = re.sub(r'[^\w\s-]', '', name.lower())
        slug = re.sub(r'[-\s]+', '_', slug)
        # Remove leading/trailing underscores
        slug = slug.strip('_')
        # Ensure it's not empty
        if not slug:
            slug = "collection"
        return slug

    def detect_content_type(self, text: str, filename: str = "") -> str:
        """Auto-detect content type based on text analysis"""
        text_lower = text.lower()

        # Check for menu indicators
        menu_keywords = ['menu', 'price', 'dish', 'appetizer', 'entree', 'dessert', 'beverage',
                        'lunch', 'dinner', 'special', 'combo', '$', 'cuisine']
        if any(keyword in text_lower for keyword in menu_keywords):
            return "menu"

        # Check for policy indicators
        policy_keywords = ['policy', 'rule', 'regulation', 'procedure', 'guideline',
                          'terms', 'condition', 'agreement', 'compliance']
        if any(keyword in text_lower for keyword in policy_keywords):
            return "policy"

        # Check for FAQ indicators
        faq_keywords = ['faq', 'frequently asked', 'question', 'answer', 'q:', 'a:']
        if any(keyword in text_lower for keyword in faq_keywords):
            return "faq"

        # Check for contact/hours indicators
        contact_keywords = ['hours', 'contact', 'phone', 'address', 'location', 'open', 'closed']
        if any(keyword in text_lower for keyword in contact_keywords):
            return "contact_info"

        # Check for client/customer data
        client_keywords = ['client', 'customer', 'name', 'email', 'phone']
        if any(keyword in text_lower for keyword in client_keywords):
            return "client_data"

        # Default based on filename
        if filename:
            filename_lower = filename.lower()
            if any(keyword in filename_lower for keyword in ['menu', 'price']):
                return "menu"
            elif any(keyword in filename_lower for keyword in ['policy', 'rule']):
                return "policy"
            elif any(keyword in filename_lower for keyword in ['faq', 'help']):
                return "faq"

        return "general"

    def chunk_text(self, text: str, content_type: str = "general") -> List[Dict[str, Any]]:
        """
        Intelligently chunk text based on content type.

        Returns list of chunks with metadata.
        """
        chunks = []

        # Clean text
        text = text.strip()
        if not text:
            return chunks

        # Different chunking strategies based on content type
        if content_type == "menu":
            chunks = self._chunk_menu_content(text)
        elif content_type == "policy":
            chunks = self._chunk_policy_content(text)
        elif content_type == "faq":
            chunks = self._chunk_faq_content(text)
        else:
            chunks = self._chunk_general_content(text)

        # Add metadata to chunks
        for i, chunk in enumerate(chunks):
            chunk.update({
                "chunk_index": i,
                "content_type": content_type,
                "chunk_id": f"chunk_{i}",
                "word_count": len(chunk["text"].split())
            })

        return chunks

    def _chunk_menu_content(self, text: str) -> List[Dict[str, Any]]:
        """Chunk menu content by categories and items"""
        chunks = []

        # Try to split by sections (appetizers, entrees, etc.)
        section_patterns = [
            r'(?i)(appetizers?|starters?)',
            r'(?i)(entrees?|main courses?|mains?)',
            r'(?i)(desserts?|sweets?)',
            r'(?i)(beverages?|drinks?)',
            r'(?i)(specials?|daily specials?)',
            r'(?i)(lunch|dinner|breakfast)',
        ]

        current_section = "General"
        current_content = []

        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if this line is a section header
            is_section = False
            for pattern in section_patterns:
                if re.search(pattern, line):
                    # Save previous section
                    if current_content:
                        chunks.append({
                            "text": "\n".join(current_content),
                            "section": current_section,
                            "source_section": current_section
                        })
                    current_section = line
                    current_content = [line]
                    is_section = True
                    break

            if not is_section:
                current_content.append(line)

            # If content gets too long, create chunk
            if len(current_content) > 20:  # ~20 lines
                chunks.append({
                    "text": "\n".join(current_content),
                    "section": current_section,
                    "source_section": current_section
                })
                current_content = []

        # Add remaining content
        if current_content:
            chunks.append({
                "text": "\n".join(current_content),
                "section": current_section,
                "source_section": current_section
            })

        return chunks

    def _chunk_policy_content(self, text: str) -> List[Dict[str, Any]]:
        """Chunk policy content by sections and paragraphs"""
        chunks = []

        # Split by numbered sections or headers
        sections = re.split(r'\n(?=\d+\.|\w+:|\n[A-Z][A-Z\s]+\n)', text)

        for section in sections:
            section = section.strip()
            if not section:
                continue

            # If section is too long, split by paragraphs
            if len(section) > 1000:
                paragraphs = section.split('\n\n')
                current_chunk = []
                current_length = 0

                for para in paragraphs:
                    para = para.strip()
                    if not para:
                        continue

                    if current_length + len(para) > 800:  # Max chunk size
                        if current_chunk:
                            chunks.append({
                                "text": "\n\n".join(current_chunk),
                                "section": "Policy Section",
                                "source_section": "Policy"
                            })
                        current_chunk = [para]
                        current_length = len(para)
                    else:
                        current_chunk.append(para)
                        current_length += len(para)

                if current_chunk:
                    chunks.append({
                        "text": "\n\n".join(current_chunk),
                        "section": "Policy Section",
                        "source_section": "Policy"
                    })
            else:
                chunks.append({
                    "text": section,
                    "section": "Policy Section",
                    "source_section": "Policy"
                })

        return chunks

    def _chunk_faq_content(self, text: str) -> List[Dict[str, Any]]:
        """Chunk FAQ content by Q&A pairs"""
        chunks = []

        # Try to identify Q&A patterns
        qa_pattern = r'(?i)(?:^|\n)(?:q:|question:|q\d+:?)\s*(.*?)(?=(?:\n(?:a:|answer:|a\d+:?))|$)'
        a_pattern = r'(?i)(?:^|\n)(?:a:|answer:|a\d+:?)\s*(.*?)(?=(?:\n(?:q:|question:|q\d+:?))|$)'

        questions = re.findall(qa_pattern, text, re.DOTALL)
        answers = re.findall(a_pattern, text, re.DOTALL)

        # Pair questions and answers
        for i, (q, a) in enumerate(zip(questions, answers)):
            chunk_text = f"Q: {q.strip()}\nA: {a.strip()}"
            chunks.append({
                "text": chunk_text,
                "section": f"FAQ Item {i+1}",
                "source_section": "FAQ",
                "question": q.strip(),
                "answer": a.strip()
            })

        # If no Q&A pattern found, use general chunking
        if not chunks:
            return self._chunk_general_content(text)

        return chunks

    def _chunk_general_content(self, text: str) -> List[Dict[str, Any]]:
        """Chunk general content by paragraphs and sentences"""
        chunks = []

        # Split by paragraphs first
        paragraphs = text.split('\n\n')
        current_chunk = []
        current_length = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # If adding this paragraph would exceed limit, save current chunk
            if current_length + len(para) > 500 and current_chunk:
                chunks.append({
                    "text": "\n\n".join(current_chunk),
                    "section": "Content",
                    "source_section": "General"
                })
                current_chunk = [para]
                current_length = len(para)
            else:
                current_chunk.append(para)
                current_length += len(para)

        # Add remaining content
        if current_chunk:
            chunks.append({
                "text": "\n\n".join(current_chunk),
                "section": "Content",
                "source_section": "General"
            })

        return chunks

    def process_pdf_file(self, file_path: str) -> str:
        """Extract text from PDF file"""
        try:
            import pdfplumber

            text_content = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_content.append(text)

            return "\n\n".join(text_content)

        except ImportError:
            raise Exception("pdfplumber not installed. Install with: pip install pdfplumber")
        except Exception as e:
            raise Exception(f"Error processing PDF: {str(e)}")

    def process_csv_file(self, file_path: str) -> str:
        """Convert CSV to natural language description"""
        try:
            import csv

            with open(file_path, 'r', encoding='utf-8') as file:
                # Try to detect dialect
                sample = file.read(1024)
                file.seek(0)
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(sample)

                reader = csv.DictReader(file, dialect=dialect)
                rows = list(reader)

            if not rows:
                return "Empty CSV file"

            # Convert to natural language
            headers = list(rows[0].keys())
            text_parts = [f"Data contains {len(rows)} records with columns: {', '.join(headers)}\n"]

            # Add sample data in natural language
            for i, row in enumerate(rows[:10]):  # First 10 rows as examples
                row_desc = []
                for key, value in row.items():
                    if value and value.strip():
                        row_desc.append(f"{key}: {value}")
                if row_desc:
                    text_parts.append(f"Record {i+1}: {', '.join(row_desc)}")

            if len(rows) > 10:
                text_parts.append(f"\n... and {len(rows) - 10} more records")

            return "\n".join(text_parts)

        except Exception as e:
            raise Exception(f"Error processing CSV: {str(e)}")

    def process_text_file(self, file_path: str) -> str:
        """Read and clean text file"""
        try:
            # Try different encodings
            encodings = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252']

            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as file:
                        return file.read()
                except UnicodeDecodeError:
                    continue

            raise Exception("Could not decode file with any supported encoding")

        except Exception as e:
            raise Exception(f"Error processing text file: {str(e)}")

    async def create_collection(
        self,
        agent_id: str,
        name: str,
        description: str = "",
        notes: str = "",
        file_path: str = None,
        text_content: str = None,
        file_type: str = None
    ) -> Collection:
        """
        Create a new collection with document processing.

        Args:
            agent_id: ID of the agent this collection belongs to
            name: Display name for the collection
            description: Description of the content
            notes: Additional notes
            file_path: Path to uploaded file (optional)
            text_content: Pasted text content (optional)
            file_type: Type of file (pdf, txt, csv, text)

        Returns:
            Created Collection object
        """
        try:
            # Validate agent exists
            agent = self.db_session.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                raise Exception(f"Agent {agent_id} not found")

            # Generate collection ID and slugified name
            collection_id = str(uuid.uuid4())
            slugified_name = self.slugify_name(name)

            # Ensure unique name for this agent
            existing = (
                self.db_session.query(Collection)
                .filter(Collection.agent_id == agent_id, Collection.name == slugified_name)
                .first()
            )
            if existing:
                # Add counter to make unique
                counter = 1
                while existing:
                    new_name = f"{slugified_name}_{counter}"
                    existing = (
                        self.db_session.query(Collection)
                        .filter(Collection.agent_id == agent_id, Collection.name == new_name)
                        .first()
                    )
                    counter += 1
                slugified_name = new_name

            # Create ChromaDB collection name
            chroma_collection_name = f"collection__{collection_id}"

            # Create database record
            collection = Collection(
                id=collection_id,
                agent_id=agent_id,
                name=slugified_name,
                display_name=name,
                description=description,
                notes=notes,
                file_path=file_path,
                file_type=file_type or "text",
                chroma_collection_name=chroma_collection_name,
                status="processing"
            )

            self.db_session.add(collection)
            self.db_session.commit()

            # Process content asynchronously
            try:
                await self._process_collection_content(collection, file_path, text_content)
                collection.status = "ready"
            except Exception as e:
                collection.status = "error"
                collection.error_message = str(e)

            self.db_session.commit()
            return collection

        except Exception as e:
            self.db_session.rollback()
            raise Exception(f"Error creating collection: {str(e)}")

    async def _process_collection_content(
        self,
        collection: Collection,
        file_path: str = None,
        text_content: str = None
    ):
        """Process and store collection content in ChromaDB"""
        try:
            # Extract text content
            if file_path and os.path.exists(file_path):
                if collection.file_type == "pdf":
                    content = self.process_pdf_file(file_path)
                elif collection.file_type == "csv":
                    content = self.process_csv_file(file_path)
                else:  # txt or other
                    content = self.process_text_file(file_path)
            elif text_content:
                content = text_content.strip()
            else:
                raise Exception("No content provided")

            if not content:
                raise Exception("No content extracted from source")

            # Detect content type
            filename = os.path.basename(file_path) if file_path else ""
            content_type = self.detect_content_type(content, filename)
            collection.content_type = content_type

            # Chunk content
            chunks = self.chunk_text(content, content_type)
            if not chunks:
                raise Exception("No chunks generated from content")

            # Create ChromaDB collection
            chroma_collection = self.chroma_client.get_or_create_collection(
                name=collection.chroma_collection_name
            )

            # Prepare data for ChromaDB
            documents = []
            metadatas = []
            ids = []

            for chunk in chunks:
                doc_id = f"{collection.id}_{chunk['chunk_id']}"

                documents.append(chunk["text"])
                metadatas.append({
                    "collection_id": collection.id,
                    "agent_id": collection.agent_id,
                    "chunk_index": chunk["chunk_index"],
                    "content_type": chunk["content_type"],
                    "source_section": chunk.get("source_section", ""),
                    "section": chunk.get("section", ""),
                    "word_count": chunk["word_count"]
                })
                ids.append(doc_id)

            # Store in ChromaDB
            chroma_collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )

            # Update collection with chunk count
            collection.chunk_count = len(chunks)

        except Exception as e:
            raise Exception(f"Error processing collection content: {str(e)}")

    def search_collection(
        self,
        agent_id: str,
        collection_name: str,
        query: str,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Search a collection for relevant chunks.

        Args:
            agent_id: Agent ID for authorization
            collection_name: Slugified collection name
            query: Search query
            limit: Maximum results to return

        Returns:
            Dict with search results and metadata
        """
        try:
            # Find collection
            collection = (
                self.db_session.query(Collection)
                .filter(
                    Collection.agent_id == agent_id,
                    Collection.name == collection_name,
                    Collection.active,
                    Collection.status == "ready"
                )
                .first()
            )

            if not collection:
                return {
                    "success": False,
                    "error": f"Collection '{collection_name}' not found or not ready",
                    "results": []
                }

            # Get ChromaDB collection
            try:
                chroma_collection = self.chroma_client.get_collection(
                    name=collection.chroma_collection_name
                )
            except Exception:
                return {
                    "success": False,
                    "error": "ChromaDB collection not found",
                    "results": []
                }

            # Perform search
            search_results = chroma_collection.query(
                query_texts=[query],
                n_results=min(limit, 50),  # Max 50 as requested
                include=["documents", "metadatas", "distances"]
            )

            # Format results
            results = []
            if search_results["documents"]:
                documents = search_results["documents"][0]
                metadatas = search_results["metadatas"][0] if search_results["metadatas"] else []
                distances = search_results["distances"][0] if search_results["distances"] else []

                for i, doc in enumerate(documents):
                    result = {
                        "text": doc,
                        "relevance_score": 1 - distances[i] if i < len(distances) else 0,
                        "metadata": metadatas[i] if i < len(metadatas) else {}
                    }
                    results.append(result)

            return {
                "success": True,
                "collection_name": collection_name,
                "collection_id": collection.id,
                "query": query,
                "total_results": len(results),
                "results": results
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Search error: {str(e)}",
                "results": []
            }

    def get_agent_collections(self, agent_id: str) -> List[Collection]:
        """Get all collections for an agent"""
        return (
            self.db_session.query(Collection)
            .filter(Collection.agent_id == agent_id, Collection.active)
            .order_by(Collection.created_at.desc())
            .all()
        )

    def get_collection(self, agent_id: str, collection_id: str) -> Optional[Collection]:
        """Get a specific collection"""
        return (
            self.db_session.query(Collection)
            .filter(
                Collection.id == collection_id,
                Collection.agent_id == agent_id,
                Collection.active
            )
            .first()
        )

    def delete_collection(self, agent_id: str, collection_id: str) -> bool:
        """Delete a collection and its ChromaDB data"""
        try:
            collection = self.get_collection(agent_id, collection_id)
            if not collection:
                return False

            # Delete from ChromaDB
            try:
                self.chroma_client.delete_collection(name=collection.chroma_collection_name)
            except Exception as e:
                logger.warning("Could not delete ChromaDB collection: %s", e)

            # Delete files
            if collection.file_path and os.path.exists(collection.file_path):
                try:
                    os.remove(collection.file_path)
                except Exception as e:
                    logger.warning("Could not delete file: %s", e)

            # Mark as inactive in database
            collection.active = False
            self.db_session.commit()

            return True

        except Exception as e:
            self.db_session.rollback()
            logger.exception("Error deleting collection: %s", e)
            return False

    def get_formatted_collection_details(self, agent_id: str) -> str:
        """
        Get formatted collection details for agent prompt.

        Returns a formatted string describing all collections available to the agent
        with instructions on how to use them.
        """
        try:
            collections = self.get_agent_collections(agent_id)

            if not collections:
                return ""

            # Filter only ready collections
            ready_collections = [c for c in collections if c.status == "ready"]

            if not ready_collections:
                return ""

            collection_count = len(ready_collections)

            # Build the formatted prompt
            prompt_parts = [
                f"You have been provided with {collection_count} collection{'s' if collection_count != 1 else ''}. These collections are your only sources of truth.",
                "Do not rely on external information. Do not hallucinate.",
                "",
                "Here are the collections:"
            ]

            for i, collection in enumerate(ready_collections, 1):
                description = collection.description or "General information and data"
                notes = collection.notes or ""

                # Build the collection line
                collection_line = f"{i}. {collection.display_name} — Purpose: {description}."

                if notes:
                    collection_line += f" Key rules: {notes}."

                prompt_parts.append(collection_line)

            prompt_parts.extend([
                "",
                "When answering a user query:",
                "- Select the most relevant collection(s).",
                "- Call `search_collection(collection_name, query, limit=50)` to retrieve results.",
                "- Read the retrieved snippets carefully.",
                "- Answer strictly based on retrieved content.",
                "- If snippets do not contain the answer, say \"I don't know.\"",
                "",
                "Available collection names for search_collection function:"
            ])

            for collection in ready_collections:
                prompt_parts.append(f"- \"{collection.name}\" (for {collection.display_name})")

            return "\n".join(prompt_parts)

        except Exception as e:
            logger.exception("Error formatting collection details: %s", e)
            return ""
