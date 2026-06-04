import os
from typing import Optional
from dataclasses import dataclass

@dataclass
class AgentContext:
    agent_id: str
    nats_url: str
    api_url: str
    nats_jwt: Optional[str] = None
    nats_nkey: Optional[str] = None
    s3_endpoint: str = "http://localhost/s3"
    s3_bucket: str = "ma-system"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    work_dir: str = "/work"
    current_thread_id: Optional[str] = None

_default_context: Optional[AgentContext] = None

def get_default_context() -> AgentContext:
    global _default_context
    if _default_context is None:
        agent_id = os.getenv("AGENT_ID") or "unknown-agent"
        nats_url = os.getenv("NATS_URL") or "nats://localhost:4222"
        api_url = os.getenv("API_URL") or "http://localhost/api/v1"
        s3_endpoint = os.getenv("S3_ENDPOINT") or "http://localhost/s3"
        s3_bucket = os.getenv("S3_BUCKET") or "ma-system"
        s3_access_key = os.getenv("S3_ACCESS_KEY") or os.getenv("AWS_ACCESS_KEY_ID") or "minioadmin"
        s3_secret_key = os.getenv("S3_SECRET_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY") or "minioadmin"
        work_dir = os.getenv("WORK_DIR") or "/work"

        _default_context = AgentContext(
            agent_id=agent_id,
            nats_url=nats_url,
            api_url=api_url,
            nats_jwt=os.getenv("NATS_JWT"),
            nats_nkey=os.getenv("NATS_NKEY"),
            s3_endpoint=s3_endpoint,
            s3_bucket=s3_bucket,
            s3_access_key=s3_access_key,
            s3_secret_key=s3_secret_key,
            work_dir=work_dir
        )
    return _default_context
