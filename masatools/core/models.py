from typing import List, Optional, Any, Union
from pydantic import BaseModel, Field, field_validator, ConfigDict
from ulid import ULID
import time

class TaskPayload(BaseModel):
    command: str
    input_dir: str
    deadline: str

class OfferPayload(BaseModel):
    eta_seconds: int
    confidence: float

class AssignPayload(BaseModel):
    reason: Optional[str] = None

class ResultPayload(BaseModel):
    output_dir: str
    exit_code: int
    error: Optional[str] = None

class StatusPayload(BaseModel):
    progress: int
    state: str # running, paused, error

class ShutdownPayload(BaseModel):
    reason: str

class EventPayload(BaseModel):
    data: Any

PayloadType = Union[
    TaskPayload, 
    OfferPayload, 
    AssignPayload, 
    ResultPayload, 
    StatusPayload, 
    ShutdownPayload, 
    EventPayload
]

class MessageEnvelope(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: str
    thread_id: str
    from_agent: str = Field(..., alias="from")
    to: List[str] = []
    observers: List[str] = []
    timestamp: int = Field(default_factory=lambda: int(time.time()))
    payload: Any # Detailed validation can be done based on 'type'
    signature: Optional[str] = None

    @field_validator("thread_id")
    @classmethod
    def validate_ulid(cls, v):
        try:
            ULID.from_str(v)
        except ValueError:
            raise ValueError("thread_id must be a valid ULID")
        return v
