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
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "ma-system"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    work_dir: str = "/work"
    current_thread_id: Optional[str] = None

_default_context: Optional[AgentContext] = None

def get_default_context() -> AgentContext:
    global _default_context
    if _default_context is None:
        _default_context = AgentContext(
            agent_id=os.getenv("AGENT_ID", "unknown-agent"),
            nats_url=os.getenv("NATS_URL", "nats://localhost:4222"),
            api_url=os.getenv("API_URL", "http://localhost:8080"),
            nats_jwt=os.getenv("NATS_JWT"),
            nats_nkey=os.getenv("NATS_NKEY"),
            s3_endpoint=os.getenv("S3_ENDPOINT", "http://localhost:9000"),
            s3_bucket=os.getenv("S3_BUCKET", "ma-system"),
            s3_access_key=os.getenv("S3_ACCESS_KEY", "minioadmin"),
            s3_secret_key=os.getenv("S3_SECRET_KEY", "minioadmin"),
            work_dir=os.getenv("WORK_DIR", "/work")
        )
    return _default_context
