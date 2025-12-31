import asyncio
import logging
from concurrent import futures
import grpc
from grpc_reflection.v1alpha import reflection
from internal.gen import authz_pb2, authz_pb2_grpc
from internal.rebac.model import PermissionService, Tuple 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PermissionServiceServicer(authz_pb2_grpc.PermissionServiceServicer):
    def __init__(self):
        self.rebac = PermissionService()  # ← In-memory store

    def Check(self, request, context):
        allowed = self.rebac.check(
            subject=request.subject,
            action=request.action, 
            object=request.object
        )
        return authz_pb2.CheckResponse(
            allowed=allowed,
            reason="Stage 2: in-memory ReBAC"
        )
    
    def WriteTuple(self, request, context):
        tuple_ = Tuple(
            subject=request.subject,
            relation=request.relation,
            object=request.object
        )
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

