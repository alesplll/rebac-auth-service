"""Neo4j schema: Node labels and relationship types"""
from enum import Enum
from typing import List, Dict

class NodeLabel(str, Enum):
    """Graph node labels"""
    USER = "User"
    GROUP = "Group"
    DOCUMENT = "Document"
    FOLDER = "Folder"
    RESOURCE = "Resource"

class RelationType(str, Enum):
    """ReBAC relationship types"""
    MEMBER_OF = "MEMBER_OF"
    OWNER_OF = "OWNER_OF"
    VIEWER = "VIEWER"
    PARENT_OF = "PARENT_OF"

# Action → allowed relations mapping
PERMISSION_RULES: Dict[str, List[RelationType]] = {
    "read": [RelationType.VIEWER, RelationType.OWNER_OF],
    "write": [RelationType.OWNER_OF],
    "delete": [RelationType.OWNER_OF],
    "admin": [RelationType.OWNER_OF],
}

def infer_node_label(entity_id: str) -> NodeLabel:
    """Infer node label from entity ID prefix"""
    if entity_id.startswith("user:"):
        return NodeLabel.USER
    if entity_id.startswith("group:"):
        return NodeLabel.GROUP
    if entity_id.startswith("doc:"):
        return NodeLabel.DOCUMENT
    if entity_id.startswith("folder:"):
        return NodeLabel.FOLDER
    return NodeLabel.RESOURCE


