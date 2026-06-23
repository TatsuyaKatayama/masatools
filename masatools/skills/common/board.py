import os
import asyncio
import httpx
from datetime import datetime, timedelta, timezone
import math
from typing import Optional, List, Any, Dict
from ...core import get_nats_client, get_default_context
from ...core.models import MessageEnvelope
from ...core.mentions import resolve_mentions

_monitor_started_at: Optional[datetime] = None
_monitor_until: Optional[datetime] = None
_monitor_duration_seconds: Optional[int] = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _format_datetime(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


def _remaining_seconds_value(now: Optional[datetime] = None) -> Optional[float]:
    if _monitor_until is None:
        return None
    current = now or _now()
    remaining = (_monitor_until - current).total_seconds()
    return max(0, remaining)


def _remaining_seconds(now: Optional[datetime] = None) -> Optional[int]:
    remaining = _remaining_seconds_value(now)
    if remaining is None:
        return None
    return math.ceil(remaining)


def start_monitoring(duration_seconds: int) -> str:
    """
    Starts an in-process monitoring session for the current MCP server.
    """
    global _monitor_started_at, _monitor_until, _monitor_duration_seconds

    duration = max(0, int(duration_seconds))
    started_at = _now()
    _monitor_started_at = started_at
    _monitor_until = started_at + timedelta(seconds=duration)
    _monitor_duration_seconds = duration

    return (
        "Monitoring started\n"
        f"Duration seconds: {duration}\n"
        f"Monitor until: {_format_datetime(_monitor_until)}"
    )


def get_runtime_context() -> Dict[str, Any]:
    """
    Returns current runtime context for the monitoring session.
    """
    remaining = _remaining_seconds()
    return {
        "is_monitoring": _monitor_until is not None and (remaining or 0) > 0,
        "monitor_started_at": _format_datetime(_monitor_started_at),
        "monitor_until": _format_datetime(_monitor_until),
        "duration_seconds": _monitor_duration_seconds,
        "remaining_seconds": remaining,
    }

async def register_agent(name: Optional[str] = None, role: str = "Worker", mission: Optional[str] = None, team_id: Optional[str] = None) -> str:
    """
    Registers the current agent with the masabbs server.
    If 'name' is not provided, it defaults to the agent's ID from the environment.
    """
    context = get_default_context()
    url = f"{context.api_url}/agents"
    
    payload = {
        "id": context.agent_id,
        "name": name or context.agent_id,
        "role": role,
    }
    if mission:
        payload["mission"] = mission
    if team_id:
        payload["team_id"] = team_id

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            if response.status_code == 201:
                return f"Agent '{context.agent_id}' registered successfully as '{role}'."
            elif response.status_code == 409:
                return f"Agent '{context.agent_id}' is already registered."
            else:
                return f"Error: Failed to register agent. Status: {response.status_code}, Body: {response.text}"
        except Exception as e:
            return f"Error during agent registration: {e}"

async def create_thread(command: str, deadline: str, to: List[str] = [], observers: List[str] = [], parent_thread_id: str = None, team_id: str = None) -> str:
    """
    Creates a new thread via the masabbs REST API.
    """
    context = get_default_context()
    url = f"{context.api_url}/threads"
    
    payload = {
        "command": command,
        "created_by_agent": context.agent_id,
        "deadline": deadline,
        "to": to,
        "observers": observers
    }
    if team_id:
        payload["team_id"] = team_id
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

async def create_subthread(parent_thread_id: str, message: str) -> str:
    """
    Creates a new subthread (child thread) under a parent thread.
    Mentions like @agent-id or @team in the message will automatically assign the thread.
    """
    return await create_thread(command=message, deadline="", parent_thread_id=parent_thread_id)

async def check_board(wait_seconds: int = 60, interval_seconds: int = 5) -> str:
    """
    Checks the NATS board for a new task.
    Polls until a task is found or wait_seconds elapses.
    """
    client = await get_nats_client()
    context = get_default_context()
    deadline = asyncio.get_running_loop().time() + max(0, wait_seconds)
    interval = max(1, interval_seconds)

    while True:
        remaining_monitor_seconds = _remaining_seconds_value()
        if remaining_monitor_seconds == 0:
            return "Monitoring finished"

        envelope = await client.pull_task(
            stream="board_tasks",
            subject="board.task.*",
            durable=f"worker-{context.agent_id}",
            target_agent_id=context.agent_id
        )

        if envelope:
            context.current_thread_id = envelope.thread_id
            return f"Task found: {envelope.type} (Thread: {envelope.thread_id})\nPayload: {envelope.payload}"

        now = asyncio.get_running_loop().time()
        remaining_wait_seconds = deadline - now
        if remaining_wait_seconds <= 0:
            return "No messages found"

        sleep_seconds = min(interval, remaining_wait_seconds)
        if remaining_monitor_seconds is not None:
            sleep_seconds = min(sleep_seconds, remaining_monitor_seconds)

        if sleep_seconds <= 0:
            return "Monitoring finished"

        await asyncio.sleep(sleep_seconds)

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

async def post_response(output_dir: Optional[str] = None, exit_code: int = 0, message: Optional[str] = None, error: Optional[str] = None, thread_id: str = None) -> str:
    """
    Posts a final result to the NATS board.
    """
    client = await get_nats_client()
    context = get_default_context()
    
    tid = thread_id or context.current_thread_id
    if not tid:
        return "Error: No active thread_id found in context."
    
    payload = {
        "exit_code": exit_code,
    }
    if output_dir:
        payload["output_dir"] = output_dir
    if message:
        payload["message"] = message
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

async def post_message(
    message: str,
    thread_id: str = None,
    output_dir: Optional[str] = None,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    to: Optional[List[str]] = None,
    observers: Optional[List[str]] = None,
) -> str:
    """
    Posts a conversation message to the current thread via REST API.
    Server handles mention resolution and NATS publishing.
    """
    if message is None or not message.strip():
        return "Error: message is required."

    context = get_default_context()
    tid = thread_id or context.current_thread_id
    if not tid:
        return "Error: No active thread_id found in context."

    url = f"{context.api_url}/threads/{tid}/messages"
    payload = {
        "from_agent": context.agent_id,
        "message": message.strip(),
    }
    if to:
        payload["to"] = to
    if observers:
        payload["observers"] = observers
    if output_dir:
        payload["output_dir"] = output_dir
    if error:
        payload["error"] = error
    if metadata:
        payload["metadata"] = metadata

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            if response.status_code == 201:
                return f"Message posted to thread {tid}"
            else:
                try:
                    err_data = response.json()
                    err_msg = err_data.get("error", response.text)
                    return f"Error: {err_msg}"
                except Exception:
                    return f"Error: Status {response.status_code}, Body: {response.text}"
        except Exception as e:
            return f"Error connecting to masabbs: {e}"

async def get_thread_history(thread_id: str = None) -> str:
    """
    Fetches the message history for a specific thread.
    Returns a formatted string of the conversation.
    """
    context = get_default_context()
    tid = thread_id or context.current_thread_id
    if not tid:
        return "Error: No active thread_id found in context."

    url = f"{context.api_url}/threads/{tid}/tasks"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            if response.status_code != 200:
                return f"Error: Failed to fetch history. Status: {response.status_code}"
            
            tasks = response.json()
            if not tasks:
                return f"No history found for thread {tid}"
            
            lines = [f"History for thread {tid}:"]
            for t in tasks:
                from_agent = t.get("from", "unknown")
                msg_type = t.get("type", "message")
                payload = t.get("payload", {})
                
                content = ""
                if msg_type == "task":
                    content = payload.get("command", "")
                elif msg_type == "result":
                    content = f"COMPLETED (Exit: {payload.get('exit_code')})"
                    if payload.get("message"):
                        content += f" - {payload.get('message')}"
                    if payload.get("output_dir"):
                        content += f" (Files: {payload.get('output_dir')})"
                else:
                    content = str(payload)
                
                lines.append(f"- {from_agent} ({msg_type}): {content}")
            
            return "\n".join(lines)
        except Exception as e:
            return f"Error fetching history: {e}"

async def get_my_profile() -> str:
    """
    Retrieves the current agent's profile, including role and mission.
    """
    context = get_default_context()
    url = f"{context.api_url}/agents/{context.agent_id}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            if response.status_code != 200:
                return f"Error: Failed to fetch profile. Status: {response.status_code}"
            
            data = response.json()
            agent = data.get("agent", {})
            team_mission = data.get("team_mission")
            
            lines = [
                f"Agent ID: {agent.get('id')}",
                f"Name: {agent.get('name')}",
                f"System Role: {agent.get('role')}",
                f"Your Contribution Mission: {agent.get('mission') or 'Not assigned'}",
            ]
            if team_mission:
                lines.append(f"Team Mission: {team_mission}")
                
            return "\n".join(lines)
        except Exception as e:
            return f"Error fetching profile: {e}"

async def get_team_blueprint(team_id: Optional[str] = None) -> str:
    """
    Retrieves the team's organization structure as a Mermaid diagram and member list.
    If team_id is not provided, it uses the current agent's team.
    """
    context = get_default_context()
    
    # If team_id is not provided, we need to get it from our profile first
    if not team_id:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{context.api_url}/agents/{context.agent_id}")
                if resp.status_code == 200:
                    team_id = resp.json().get("agent", {}).get("team_id")
            except Exception:
                pass
    
    if not team_id:
        return "Error: team_id could not be determined. Please provide it explicitly."

    url = f"{context.api_url}/teams/{team_id}/blueprint"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            if response.status_code != 200:
                return f"Error: Failed to fetch blueprint. Status: {response.status_code}"
            
            data = response.json()
            mermaid = data.get("structure_mermaid", "No diagram available")
            members = data.get("members", [])
            
            lines = [
                f"Team ID: {team_id}",
                "Structure (Mermaid):",
                "```mermaid",
                mermaid,
                "```",
                "\nMembers:",
            ]
            for m in members:
                lines.append(f"- {m.get('id')}: {m.get('name')} ({m.get('role')}) - Mission: {m.get('mission') or 'None'}")
                
            return "\n".join(lines)
        except Exception as e:
            return f"Error fetching team blueprint: {e}"

async def get_network() -> str:
    """
    Retrieves the local network of agents related to the current agent.
    Shows who are 'leaders', 'subordinates', or 'coworkers' from the current agent's perspective.
    """
    context = get_default_context()
    url = f"{context.api_url}/agents/{context.agent_id}/network"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            if response.status_code != 200:
                return f"Error: Failed to fetch network. Status: {response.status_code}"
            
            members = response.json()
            if not members:
                return "Your network is currently empty (no direct relations found)."
            
            lines = ["Your Local Network:"]
            for m in members:
                agent_id = m.get("agent_id")
                relation = m.get("relation", {})
                rel_type = relation.get("type", "unknown")
                rel_cat = relation.get("category", "unknown")
                status = m.get("status", "unknown")
                mission = m.get("mission", "No mission")
                
                lines.append(f"- {agent_id} ({rel_type}/{rel_cat}): Status: {status}, Mission: {mission}")
                
            return "\n".join(lines)
        except Exception as e:
            return f"Error fetching network: {e}"

async def request_reflection(thread_id: str, due_at: Optional[str] = None) -> str:
    """
    Requests a reflection task for a completed thread by creating a dedicated subthread
    and alerting all involved team members.
    """
    context = get_default_context()
    url = f"{context.api_url}/threads/{thread_id}/reflection-requests"
    
    payload = {
        "requested_by_agent": context.agent_id,
    }
    if due_at:
        payload["due_at"] = due_at
        
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            if response.status_code != 201:
                return f"Error: Failed to request reflection. Status: {response.status_code}, Body: {response.text}"
            
            data = response.json()
            return f"Reflection requested successfully!\nRequest ID: {data.get('request_id')}\nReflection Subthread ID: {data.get('reflection_thread_id')}"
        except Exception as e:
            return f"Error during reflection request: {e}"

async def submit_reflection(request_id: str, target_agent_id: str, dimension: str, score: int, reason: str, suggestion: Optional[str] = None) -> str:
    """
    Submits a structured reflection evaluation for another agent within your team.
    'dimension' should be a valid dimension, e.g., 'clarity', 'collaboration', etc.
    'score' must be -1, 0, or 1.
    """
    context = get_default_context()
    url = f"{context.api_url}/reflections"
    
    payload = {
        "request_id": request_id,
        "from_agent_id": context.agent_id,
        "target_agent_id": target_agent_id,
        "dimension": dimension,
        "score": score,
        "reason": reason,
    }
    if suggestion:
        payload["suggestion"] = suggestion
        
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            if response.status_code != 201:
                return f"Error: Failed to submit reflection. Status: {response.status_code}, Body: {response.text}"
            
            data = response.json()
            return f"Reflection submitted successfully!\nReflection ID: {data.get('id')}"
        except Exception as e:
            return f"Error during reflection submission: {e}"
