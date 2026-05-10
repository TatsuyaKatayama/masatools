import os
import asyncio
import httpx
from typing import Optional, List
from ...core import get_nats_client, get_default_context
from ...core.models import MessageEnvelope

async def create_thread(command: str, deadline: str, to: List[str] = [], observers: List[str] = [], parent_thread_id: str = None) -> str:
    """
    Creates a new thread via the masabbs REST API.
    """
    context = get_default_context()
    url = f"{context.api_url}/api/v1/threads"
    
    payload = {
        "command": command,
        "created_by_agent": context.agent_id,
        "deadline": deadline,
        "to": to,
        "observers": observers
    }
    if parent_thread_id:
        payload["parent_thread_id"] = parent_thread_id
    elif context.current_thread_id:
        payload["parent_thread_id"] = context.current_thread_id

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        if response.status_code != 201:
            return f"Error: Failed to create thread. Status: {response.status_code}, Body: {response.text}"
        
        data = response.json()
        thread_id = data.get("thread_id")
        if thread_id:
            context.current_thread_id = thread_id
            return f"Thread created: {thread_id}\nInput Directory: {data.get('input_dir')}"
        else:
            return f"Error: thread_id not found in response: {data}"

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

async def send_offer(eta_seconds: int, confidence: float, thread_id: str = None) -> str:
    """
    Sends an offer to perform a task.
    'eta_seconds' is the estimated time to completion.
    'confidence' is a value between 0.0 and 1.0.
    """
    client = await get_nats_client()
    context = get_default_context()
    
    tid = thread_id or context.current_thread_id
    if not tid:
        return "Error: No active thread_id found in context."
    
    payload = {
        "eta_seconds": eta_seconds,
        "confidence": confidence
    }
    
    # Subject: board.offer.{thread_id}
    subject = f"board.offer.{tid}"
    await client.publish(
        subject=subject,
        message_type="offer",
        payload=payload,
        thread_id=tid
    )
    
    return f"Offer sent for thread {tid}"

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

async def send_assign(to: List[str], reason: Optional[str] = None, thread_id: str = None) -> str:
    """
    Assigns a task to specific agents.
    """
    client = await get_nats_client()
    context = get_default_context()
    
    tid = thread_id or context.current_thread_id
    if not tid:
        return "Error: No active thread_id found in context."
    
    payload = {
        "reason": reason
    }
    
    # Subject: board.assign.{thread_id}
    subject = f"board.assign.{tid}"
    await client.publish(
        subject=subject,
        message_type="assign",
        payload=payload,
        thread_id=tid,
        to=to
    )
    
    return f"Assignment sent to {to} for thread {tid}"

async def post_response(output_dir: str, exit_code: int = 0, error: Optional[str] = None, thread_id: str = None) -> str:
    """
    Posts a final result to the NATS board.
    """
    client = await get_nats_client()
    context = get_default_context()
    
    tid = thread_id or context.current_thread_id
    if not tid:
        return "Error: No active thread_id found in context."
    
    payload = {
        "output_dir": output_dir,
        "exit_code": exit_code,
    }
    if error:
        payload["error"] = error
        
    # Subject: board.result.{thread_id}
    subject = f"board.result.{tid}"
    await client.publish(
        subject=subject,
        message_type="result",
        payload=payload,
        thread_id=tid
    )
    
    return f"Result posted to {subject} (exit_code: {exit_code})"
