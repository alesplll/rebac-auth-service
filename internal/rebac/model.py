"""ReBAC core model and service"""
from dataclasses import dataclass
from typing import List, Optional
import logging
from internal.rebac.interfaces import GraphStore
from internal.types import Tuple

logger = logging.getLogger(__name__)

class PermissionService:
    """ReBAC authorization service"""
    
    def __init__(self, store: Optional[GraphStore] = None):
        """
        Initialize with graph store implementation.
        
        Args:
            store: GraphStore implementation (Neo4jStore, MemoryStore, etc.)
        """
        self._store = store
    
    def write_tuple(self, tuple_: Tuple) -> bool:
        """Write relationship tuple"""
        if not self._store:
            raise RuntimeError("No storage configured")
        logger.info(f"Write tuple: {tuple_}")
        return self._store.write_tuple(tuple_)
    
    def read_tuples(self, subject: str) -> List[Tuple]:
        """Read all outgoing relationships for subject"""
        if not self._store:
            return []
        logger.debug(f"Read tuples for: {subject}")
        return self._store.read_tuples(subject)
    
    def check(self, subject: str, action: str, object: str) -> bool:
        """Check if subject can perform action on object"""
        if not self._store:
            logger.warning("No storage - denying access")
            return False
        
        logger.info(f"Check: {subject} {action}? {object}")
        result = self._store.check(subject, action, object)
        logger.info(f"Authorization result: {'ALLOW' if result else 'DENY'}")
        return result
    
    def close(self) -> None:
        """Close underlying storage"""
        if self._store:
            self._store.close()

