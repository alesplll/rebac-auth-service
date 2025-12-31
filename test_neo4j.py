from neo4j import GraphDatabase
import os

URI = "bolt://localhost:7687"
USERNAME = "neo4j"
PASSWORD = "password123"

driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))

def test_connection(tx):
    result = tx.run("RETURN 'Hello Neo4j!' AS message")
    return result.single()["message"]

with driver.session() as session:
    message = session.execute_read(test_connection)
    print(f"✅ Neo4j connected: {message}")

driver.close()
