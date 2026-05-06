import pytest
from masatools.core.models import MessageEnvelope
from ulid import ULID

def test_envelope_validation():
    tid = str(ULID())
    data = {
        "type": "task",
        "thread_id": tid,
        "from": "agent-1",
        "payload": {"command": "echo hello"}
    }
    env = MessageEnvelope(**data)
    assert env.thread_id == tid
    assert env.from_agent == "agent-1"

def test_invalid_ulid():
    with pytest.raises(ValueError, match="thread_id must be a valid ULID"):
        MessageEnvelope(
            type="task",
            thread_id="invalid-ulid",
            from_agent="agent-1",
            payload={}
        )

def test_automatic_timestamp():
    tid = str(ULID())
    env = MessageEnvelope(
        type="task",
        thread_id=tid,
        from_agent="agent-1",
        payload={}
    )
    assert env.timestamp > 0
