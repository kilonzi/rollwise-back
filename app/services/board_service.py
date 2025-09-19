from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.models import Agent, Board, BoardItem
from app.utils.logging_config import app_logger


class BoardService:
    """Service for managing agent boards and board items"""

    @staticmethod
    def get_or_create_board(db: Session, agent_id: str) -> Board:
        """Get existing board for agent or create a default one"""
        try:
            # First check if board exists
            board = db.query(Board).filter(Board.agent_id == agent_id, Board.active).first()

            if board:
                return board

            # Verify agent exists
            agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active).first()
            if not agent:
                raise ValueError(f"Agent with ID {agent_id} not found")

            # Create default board
            board = Board(
                agent_id=agent_id,
                name="Agent Board",
                lanes=[
                    {"id": "new", "name": "New", "color": "#2196F3", "wipLimit": None},
                    {"id": "in_progress", "name": "In Progress", "color": "#FF9800", "wipLimit": 5},
                    {"id": "done", "name": "Done", "color": "#4CAF50", "wipLimit": None}
                ],
                labels=[
                    {"id": "urgent", "name": "Urgent", "color": "#F44336"},
                    {"id": "vip", "name": "VIP Customer", "color": "#9C27B0"},
                    {"id": "delivery", "name": "Delivery", "color": "#607D8B"},
                    {"id": "takeout", "name": "Takeout", "color": "#795548"}
                ]
            )
            
            db.add(board)
            db.commit()
            db.refresh(board)
            
            app_logger.info(f"Created new board for agent {agent_id}")
            return board
            
        except Exception as e:
            db.rollback()
            app_logger.error(f"Error creating board for agent {agent_id}: {str(e)}")
            raise

    @staticmethod
    def get_board_with_items(db: Session, agent_id: str, 
                           start_date: Optional[str] = None, 
                           end_date: Optional[str] = None) -> Dict[str, Any]:
        """Get board and its items with optional date filtering"""
        try:
            board = BoardService.get_or_create_board(db, agent_id)
            
            # Build query for items
            items_query = db.query(BoardItem).filter(
                BoardItem.board_id == board.id,
                BoardItem.active
            )
            
            # Apply date filters if provided
            if start_date:
                start_datetime = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                items_query = items_query.filter(BoardItem.created_at >= start_datetime)
            
            if end_date:
                end_datetime = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                items_query = items_query.filter(BoardItem.created_at <= end_datetime)
            
            items = items_query.order_by(BoardItem.created_at.desc()).all()
            
            # Convert to response format
            board_data = {
                "id": board.id,
                "name": board.name,
                "lanes": board.lanes,
                "labels": board.labels
            }
            
            items_data = []
            for item in items:
                item_data = {
                    "id": item.id,
                    "title": item.title,
                    "description": item.description,
                    "laneId": item.lane_id,
                    "labels": item.labels,
                    "priority": item.priority,
                    "assignee": item.assignee,
                    "dueDate": item.due_date.isoformat() if item.due_date else None,
                    "metadata": item.item_metadata,
                    "createdAt": item.created_at.isoformat() if item.created_at else None,
                    "updatedAt": item.updated_at.isoformat() if item.updated_at else None
                }
                items_data.append(item_data)
            
            return {
                "board": board_data,
                "items": items_data
            }
            
        except Exception as e:
            app_logger.error(f"Error getting board for agent {agent_id}: {str(e)}")
            raise

    @staticmethod
    def move_item(db: Session, agent_id: str, item_id: str, to_lane_id: str) -> Dict[str, Any]:
        """Move a board item to a different lane"""
        try:
            # Verify the board exists and belongs to the agent
            board = BoardService.get_or_create_board(db, agent_id)
            
            # Get the item
            item = db.query(BoardItem).filter(
                BoardItem.id == item_id,
                BoardItem.board_id == board.id,
                BoardItem.active
            ).first()
            
            if not item:
                raise ValueError(f"Board item {item_id} not found")
            
            # Verify the target lane exists
            valid_lanes = [lane["id"] for lane in board.lanes]
            if to_lane_id not in valid_lanes:
                raise ValueError(f"Invalid lane ID: {to_lane_id}")
            
            # Update the item
            item.lane_id = to_lane_id
            item.updated_at = datetime.utcnow()
            
            db.commit()
            db.refresh(item)
            
            app_logger.info(f"Moved item {item_id} to lane {to_lane_id}")
            
            return {
                "id": item.id,
                "laneId": item.lane_id,
                "updatedAt": item.updated_at.isoformat()
            }
            
        except Exception as e:
            db.rollback()
            app_logger.error(f"Error moving item {item_id}: {str(e)}")
            raise

    @staticmethod
    def update_item(db: Session, agent_id: str, item_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update a board item"""
        try:
            # Verify the board exists and belongs to the agent
            board = BoardService.get_or_create_board(db, agent_id)
            
            # Get the item
            item = db.query(BoardItem).filter(
                BoardItem.id == item_id,
                BoardItem.board_id == board.id,
                BoardItem.active
            ).first()
            
            if not item:
                raise ValueError(f"Board item {item_id} not found")
            
            # Update allowed fields
            allowed_fields = ['title', 'description', 'labels', 'priority', 'assignee', 'due_date', 'item_metadata']
            
            for field, value in updates.items():
                if field in allowed_fields:
                    if field == 'due_date' and value:
                        # Handle date conversion
                        if isinstance(value, str):
                            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    
                    setattr(item, field, value)
            
            item.updated_at = datetime.utcnow()
            
            db.commit()
            db.refresh(item)
            
            app_logger.info(f"Updated item {item_id}")
            
            # Return updated item
            return {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "laneId": item.lane_id,
                "labels": item.labels,
                "priority": item.priority,
                "assignee": item.assignee,
                "dueDate": item.due_date.isoformat() if item.due_date else None,
                "metadata": item.item_metadata,
                "updatedAt": item.updated_at.isoformat()
            }
            
        except Exception as e:
            db.rollback()
            app_logger.error(f"Error updating item {item_id}: {str(e)}")
            raise

    @staticmethod
    def update_board_settings(db: Session, agent_id: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Update board settings (lanes, labels)"""
        try:
            board = BoardService.get_or_create_board(db, agent_id)
            
            # Update allowed settings
            if 'lanes' in settings:
                board.lanes = settings['lanes']
            
            if 'labels' in settings:
                board.labels = settings['labels']
            
            if 'name' in settings:
                board.name = settings['name']
            
            board.updated_at = datetime.utcnow()
            
            db.commit()
            db.refresh(board)
            
            app_logger.info(f"Updated board settings for agent {agent_id}")
            
            return {
                "id": board.id,
                "name": board.name,
                "lanes": board.lanes,
                "labels": board.labels,
                "updatedAt": board.updated_at.isoformat()
            }
            
        except Exception as e:
            db.rollback()
            app_logger.error(f"Error updating board settings for agent {agent_id}: {str(e)}")
            raise

    @staticmethod
    def create_board_item(db: Session, agent_id: str, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new board item"""
        try:
            board = BoardService.get_or_create_board(db, agent_id)
            
            # Create new item
            item = BoardItem(
                board_id=board.id,
                title=item_data.get('title', 'New Item'),
                description=item_data.get('description'),
                lane_id=item_data.get('lane_id', 'new'),
                labels=item_data.get('labels', []),
                priority=item_data.get('priority', 'medium'),
                assignee=item_data.get('assignee'),
                due_date=datetime.fromisoformat(item_data['due_date'].replace('Z', '+00:00')) if item_data.get('due_date') else None,
                item_metadata=item_data.get('metadata', {})
            )
            
            db.add(item)
            db.commit()
            db.refresh(item)
            
            app_logger.info(f"Created new board item {item.id} for agent {agent_id}")
            
            return {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "laneId": item.lane_id,
                "labels": item.labels,
                "priority": item.priority,
                "assignee": item.assignee,
                "dueDate": item.due_date.isoformat() if item.due_date else None,
                "metadata": item.item_metadata,
                "createdAt": item.created_at.isoformat(),
                "updatedAt": item.updated_at.isoformat()
            }
            
        except Exception as e:
            db.rollback()
            app_logger.error(f"Error creating board item for agent {agent_id}: {str(e)}")
            raise
