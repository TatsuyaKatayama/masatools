import os
from ...core import get_nats_client, get_default_context
from ...core.models import MessageEnvelope

async def check_board() -> str:
    """
    Checks the NATS board for a new task.
    Returns a summary of the task if found, otherwise 'No tasks found'.
    """
    client = await get_nats_client()
    context = get_default_context()
    
    # We pull from board.task.* using a durable consumer named after the agent
    # Subject: board.task.*
    # Stream: board_tasks
    envelope = await client.pull_task(
        stream="board_tasks",
        subject="board.task.*",
        durable=f"worker-{context.agent_id}"
    )
    
    if envelope:
        # Update context with current thread_id (in a real scenario, this might be handled via a state manager)
        context.current_thread_id = envelope.thread_id
        return f"Task found: {envelope.type} (Thread: {envelope.thread_id})\nPayload: {envelope.payload}"
    
    return "No tasks found"

async def post_response(status: str, message: str, thread_id: str = None) -> str:
    """
    Posts a result or status back to the NATS board.
    """
    client = await get_nats_client()
    context = get_default_context()
    
    tid = thread_id or context.current_thread_id
    if not tid:
        return "Error: No active thread_id found in context."
    
    payload = {
        "state": status.lower(),
        "progress": 100 if status.upper() == "SUCCESS" else 0,
        "message": message
    }
    
    # Subject: board.result.{thread_id} or board.status.{agent_id}
    # For simplicity, we'll use board.result.{tid} for SUCCESS/ERROR
    subject = f"board.result.{tid}"
    await client.publish(
        subject=subject,
        message_type="result",
        payload=payload,
        thread_id=tid
    )
    
    return f"Response posted to {subject}"
