from dataclasses import dataclass
from typing import Dict, List, Set
import logging

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class Tuple:
    """Атомарная связь: (user:alice, MEMBER_OF, group:dev)"""
    subject: str
    relation: str
    object: str

    def __str__(self):
        return f"({self.subject} {self.relation}→ {self.object})"

class PermissionService:
    """In-memory ReBAC хранилище"""
    
    def __init__(self):
        # {subject: {relation: {objects}}}
        # Пример: {"user:alice": {"MEMBER_OF": {"group:dev"}, "VIEWER": {"doc:123"}}}
        self._tuples: Dict[str, Dict[str, Set[str]]] = {}
    
    def write_tuple(self, tuple_: Tuple) -> bool:
        """Добавляет связь"""
        logger.info(f"Write: {tuple_}")
        
        if tuple_.subject not in self._tuples:
            self._tuples[tuple_.subject] = {}
        if tuple_.relation not in self._tuples[tuple_.subject]:
            self._tuples[tuple_.subject][tuple_.relation] = set()
        
        self._tuples[tuple_.subject][tuple_.relation].add(tuple_.object)
        return True
    
    def read_tuples(self, subject: str) -> List[Tuple]:
        """Все связи субъекта"""
        if subject not in self._tuples:
            return []
        
        result = []
        for relation, objects in self._tuples[subject].items():
            for obj in objects:
                result.append(Tuple(subject, relation, obj))
        return result
    
    def check(self, subject: str, action: str, object: str) -> bool:
        """
        Stage 2: Простая проверка ПРЯМЫХ связей
        """
        logger.info(f"Check: {subject} {action}? {object}")
        
        if subject not in self._tuples:
            logger.info(f"No tuples for {subject}")
            return False
        
        # Проверяем ВСЕ отношения субъекта
        for relation, objects in self._tuples[subject].items():
            if object in objects:
                # Пока разрешаем ЛЮБЫЕ отношения для ЛЮБЫХ действий
                logger.info(f"✓ Found: {subject} {relation}→ {object}")
                return True
        
        logger.info(f"✗ No direct relation found")
        return False

