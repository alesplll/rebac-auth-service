"""ReBAC Auth Service entrypoint"""
import logging
from concurrent import futures
import grpc
from grpc_reflection.v1alpha import reflection
from internal.gen import authz_pb2, authz_pb2_grpc
from internal.rebac.model import PermissionService
from internal.neo4j.store import Neo4jStore
from internal.types import Tuple 
from internal.cache.redis_cache import RedisDecisionCache
from internal.kafka.producer import AuditProducer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NEO4J_URI = "bolt://localhost:7687"
REDIS_HOST = "localhost"
REDIS_PORT = 6379
KAFKA_BOOTSTRAP = "localhost:9092"

class PermissionServiceServicer(authz_pb2_grpc.PermissionServiceServicer):
    """gRPC service implementation"""
    
    def __init__(self):
        # Dependency injection: Neo4jStore → PermissionService
        neo4j_store = Neo4jStore(
            uri=NEO4J_URI,
            user="neo4j",
            password="password123"
        )
        cache = RedisDecisionCache(host=REDIS_HOST, port=REDIS_PORT)
        audit_producer = AuditProducer(KAFKA_BOOTSTRAP)
        self.rebac = PermissionService(
            store=neo4j_store, 
            cache=cache,
            audit_producer=audit_producer
        )
    
    def Check(self, request, context):
        allowed = self.rebac.check(
            request.subject, request.action, request.object
        )
        return authz_pb2.CheckResponse(
            allowed=allowed,
            reason="Stage 3: Neo4j-backed ReBAC"
        )
    
    def WriteTuple(self, request, context):
        tuple_ = Tuple(request.subject, request.relation, request.object)
        success = self.rebac.write_tuple(tuple_)
        return authz_pb2.WriteTupleResponse(success=success)
    
    def Read(self, request, context):
        tuples = self.rebac.read_tuples(request.subject)
        response = authz_pb2.ReadResponse()
        for t in tuples:
            response.tuples.add(
                subject=t.subject,
                relation=t.relation,
                object=t.object
            )
        return response

def serve():
    """Start gRPC server"""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    authz_pb2_grpc.add_PermissionServiceServicer_to_server(
        PermissionServiceServicer(), server
    )
    
    # Enable reflection for grpcurl
    SERVICE_NAMES = (
        authz_pb2.DESCRIPTOR.services_by_name['PermissionService'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)
    
    server.add_insecure_port('[::]:50051')
    server.start()
    logger.info("🚀 Stage 4: Neo4j + Redis ReBAC Auth Service (:50051)")
    try:
        server.wait_for_termination()
    finally:
        logger.info("Shutting down...")

if __name__ == '__main__':
    serve()

