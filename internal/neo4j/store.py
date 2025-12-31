"""Neo4j GraphStore implementation"""
from neo4j import GraphDatabase
from typing import List
import logging
from internal.types import Tuple
from internal.neo4j.schema import infer_node_label, PERMISSION_RULES

logger = logging.getLogger(__name__)

class Neo4jStore:
    """Neo4j-backed GraphStore implementation"""
    
    def __init__(self, uri: str, user: str, password: str):
        """
        Initialize Neo4j connection.
        
        Args:
            uri: Bolt URI (bolt://localhost:7687)
            user: Neo4j username
            password: Neo4j password
        """
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        logger.info(f"Connected to Neo4j: {uri}")
    
    def write_tuple(self, tuple_: Tuple) -> bool:
        """Create nodes and relationship in Neo4j"""
        s_label = infer_node_label(tuple_.subject).value
        o_label = infer_node_label(tuple_.object).value
        
        query = """
        MERGE (subject:`%s` {id: $subject_id})
        MERGE (object:`%s` {id: $object_id})
        MERGE (subject)-[rel:`%s`]->(object)
        RETURN rel
        """ % (s_label, o_label, tuple_.relation)
        
        logger.debug(f"Neo4j write: {tuple_}")
        with self.driver.session() as session:
            result = session.run(query, 
                               subject_id=tuple_.subject, 
                               object_id=tuple_.object)
            return result.single() is not None
    
    def read_tuples(self, subject: str) -> List[Tuple]:
        """Read all outgoing relationships for subject"""
        query = """
        MATCH (subject {id: $subject_id})-[rel]->(target)
        RETURN subject.id as subject_id, type(rel) as relation, target.id as object_id
        """
        
        result: List[Tuple] = []
        with self.driver.session() as session:
            records = session.run(query, subject_id=subject)
            for record in records:
                result.append(Tuple(
                    subject=record["subject_id"],
                    relation=record["relation"],
                    object=record["object_id"]
                ))
        return result
    
    def check(self, subject: str, action: str, object: str) -> bool:
        """Check authorization via direct relationship match"""
        allowed_rels = PERMISSION_RULES.get(action, [])
        if not allowed_rels:
            logger.warning(f"Unknown action: {action}")
            return False
        
        query = """
        MATCH (subject {id: $subject})- [rel]->(target {id: $object})
        WHERE type(rel) IN $allowed_rels
        RETURN count(rel) > 0 as authorized
        """
        
        with self.driver.session() as session:
            result = session.run(query, 
                               subject=subject, 
                               object=object,
                               allowed_rels=[r.value for r in allowed_rels])
            record = result.single()
            authorized = record["authorized"] if record else False
            logger.debug(f"Neo4j check result: {authorized}")
            return authorized
    
    def close(self) -> None:
        """Close Neo4j driver"""
        self.driver.close()
        logger.info("Neo4j connection closed")

