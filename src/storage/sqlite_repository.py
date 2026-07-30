# src/storage/sqlite_repository.py
"""SQLite fallback repository for when MongoDB is unavailable."""
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Column, String, JSON, DateTime, create_engine, MetaData, Table, insert

from src.storage.utils import sanitize_for_mongo

logger = logging.getLogger(__name__)


class SQLiteResultRepository:
    """SQLite-based result repository for development/testing environments.
    
    Used as a fallback when MongoDB is not available (MONGO_URI is None).
    """
    
    def __init__(self, db_path: str = "data/testai_executions.db"):
        self.db_path = db_path
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        self.metadata = MetaData()
        self._define_tables()
        self.metadata.create_all(self.engine)
        logger.info(f"SQLiteResultRepository initialized at {db_path}")
    
    def _define_tables(self):
        """Define execution_results table for SQLite."""
        self.execution_results_table = Table(
            "execution_results",
            self.metadata,
            Column("step_id", String(64), primary_key=True),
            Column("results", JSON, default={}),
            Column("timestamp", DateTime, default=datetime.utcnow),
        )
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass  # SQLite connection is stateless per query
    
    async def save_execution(self, step_id: str, results: dict) -> None:
        """Save execution result to SQLite."""
        try:
            clean_results = sanitize_for_mongo(results)
            
            # Handle datetime serialization for SQLite
            clean_results = self._serialize_for_sqlite(clean_results)
            
            document = {
                "step_id": step_id,
                "results": clean_results,
                "timestamp": datetime.utcnow(),
            }
            
            with self.engine.connect() as conn:
                conn.execute(
                    insert(self.execution_results_table).values(**document)
                )
                conn.commit()
            
            logger.info(f"Successfully saved execution result to SQLite: {step_id}")
            
        except Exception as e:
            logger.error(f"SQLite persistence failure for {step_id}: {str(e)}")
            raise ConnectionError(f"SQLite database write failed: {e}") from e
    
    def _serialize_for_sqlite(self, obj: Any) -> Any:
        """Serialize objects for SQLite JSON storage."""
        if isinstance(obj, dict):
            return {k: self._serialize_for_sqlite(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._serialize_for_sqlite(item) for item in obj]
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj
