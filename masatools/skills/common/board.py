import os
import asyncio
from typing import Optional
from ...core import get_nats_client, get_default_context
from ...core.models import MessageEnvelope

async def check_board(wait_seconds: int = 60) -> str:
    """
    Checks the NATS board for a new task.
    If no task is found, it waits for wait_seconds before returning.
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
        # Update context with current thread_id
        context.current_thread_id = envelope.thread_id
        return f"Task found: {envelope.type} (Thread: {envelope.thread_id})\nPayload: {envelope.payload}"
    
    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)
    
    return "No tasks found"

async def update_status(progress: int, state: str, message: Optional[str] = None, thread_id: str = None) -> str:
    """
    Sends a status report (heartbeat/progress).
    """
    client = await get_nats_client()
    context = get_default_context()
    
    tid = thread_id or context.current_thread_id
    if not tid:
        return "Error: No active thread_id found in context."
    
    payload = {
        "progress": progress,
        "state": state,
    }
    if message:
        payload["message"] = message
        
    subject = f"board.status.{context.agent_id}"
    await client.publish(
        subject=subject,
        message_type="status",
        payload=payload,
        thread_id=tid
    )
    
    return f"Status updated: {state} ({progress}%)"

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
