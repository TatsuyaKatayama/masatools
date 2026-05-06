from .nats_client import NATSClient
from .s3_client import S3Client
from .context import AgentContext, get_default_context

_default_nats_client = None
_default_s3_client = None

async def get_nats_client() -> NATSClient:
    global _default_nats_client
    if _default_nats_client is None:
        ctx = get_default_context()
        _default_nats_client = NATSClient(ctx)
        await _default_nats_client.connect()
    return _default_nats_client

def get_s3_client() -> S3Client:
    global _default_s3_client
    if _default_s3_client is None:
        ctx = get_default_context()
        _default_s3_client = S3Client(ctx)
    return _default_s3_client
