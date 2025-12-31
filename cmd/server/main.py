import asyncio
import logging
from concurrent import futures
import grpc
from grpc_reflection.v1alpha import reflection
from internal.gen import authz_pb2, authz_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PermissionServiceServicer(authz_pb2_grpc.PermissionServiceServicer):
    def Check(self, request, context):
        logger.info(f"Check: {request.subject} {request.action} {request.object}")
        return authz_pb2.CheckResponse(
            allowed=True,
            reason="Stage 1: hardcoded ALLOW (no DB yet)"
        )
    
    def WriteTuple(self, request, context):
        logger.info(f"WriteTuple: {request.subject} {request.relation} {request.object}")
        return authz_pb2.WriteTupleResponse(success=True)
    
    def Read(self, request, context):
        logger.info(f"Read: {request.subject}")
        return authz_pb2.ReadResponse(tuples=[])

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    authz_pb2_grpc.add_PermissionServiceServicer_to_server(
        PermissionServiceServicer(), server
    )
    
    SERVICE_NAMES = (
        authz_pb2.DESCRIPTOR.services_by_name['PermissionService'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)
    
    server.add_insecure_port('[::]:50051')
    server.start()
    logger.info("🚀 ReBAC Auth Service running on :50051 (with Reflection)")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()

