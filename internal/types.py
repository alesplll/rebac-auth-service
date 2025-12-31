"""Shared ReBAC types"""
from dataclasses import dataclass
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class Tuple:
    """Atomic relationship tuple: (subject, relation, object)"""
    subject: str
    relation: str
    object: str

    def __str__(self) -> str:
        return f"({self.subject} {self.relation}→ {self.object})"

