import os
import asyncio
import httpx
from typing import Optional, List
from ...core import get_nats_client, get_default_context
from ...core.models import MessageEnvelope

async def register_agent(name: str, role: str, mission: Optional[str] = None, team_id: Optional[str] = None) -> str:
    """
    Registers the current agent with the masabbs server.
    This makes the agent visible in the Admin UI and allows it to participate in the team.
    """
    context = get_default_context()
    url = f"{context.api_url}/agents"
    
    payload = {
        "id": context.agent_id,
        "name": name,
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

async def create_thread(command: str, deadline: str, to: List[str] = [], observers: List[str] = [], parent_thread_id: str = None) -> str:
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
                elif msg_type == "status":
                    content = f"[{payload.get('state')}] {payload.get('message', '')}"
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
