import logging
import sys

# Configure logging to write to stderr so it doesn't interfere with MCP protocol on stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("masatools-mcp")

# Also ensure nats-py logs to stderr and is less verbose
nats_logger = logging.getLogger("nats")
nats_logger.setLevel(logging.CRITICAL)
nats_logger.disabled = True
nats_logger.propagate = False

from mcp.server.fastmcp import FastMCP
from masatools.skills.common.board import (
    check_board, post_message, create_thread, create_subthread,
    get_thread_history,
    get_team_blueprint, get_network, get_my_profile, register_agent,
    start_monitoring, get_runtime_context,
    request_reflection, submit_reflection
)
from masatools.skills.common.storage import sync_from_s3, sync_to_s3
from typing import Any, Dict, List, Optional
import asyncio

# Create the MCP server
mcp = FastMCP("bbs-mcp")

@mcp.tool()
async def register_agent_tool(name: str = None, role: str = "Worker", mission: str = None, team_id: str = None) -> str:
    """
    Registers this agent with the masabbs server so it appears in the Admin UI.
    If 'name' is not provided, it uses the AGENT_ID from the environment.
    'role' should be one of: 'TeamManager', 'Chef', 'Worker'.
    (Old roles 'manager', 'worker', 'observer' are also accepted for compatibility).
    """
    return await safe_tool_call(register_agent(name, role, mission, team_id))

@mcp.tool()
async def check_connectivity_tool() -> str:
    """
    Checks the connectivity to masabbs (NATS/API) and S3 storage.
    Run this tool to verify the environment is correctly set up.
    """
    from masatools.core import get_nats_client, get_default_context
    import httpx
    
    context = get_default_context()
    results = [f"Agent ID: {context.agent_id}"]
    
    # NATS check
    try:
        # We use a very short timeout and no retries for connectivity check to avoid hanging
        logger.info(f"Checking NATS connectivity to {context.nats_url}")
        # allow_reconnect=False and short timeout (1s) for fast failure
        nc = await get_nats_client(max_reconnect_attempts=0, connect_timeout=1, allow_reconnect=False)
        results.append(f"✅ NATS: Connected to {context.nats_url}")
    except Exception as e:
        results.append(f"❌ NATS: Failed to connect to {context.nats_url} ({e})")

    # API check
    try:
        api_health_url = f"{context.api_url.rstrip('/')}/health"
        logger.info(f"Checking API connectivity to {api_health_url}")
        async with httpx.AsyncClient(timeout=2.0, follow_redirects=True) as client:
            resp = await client.get(api_health_url)
            if resp.status_code == 200:
                results.append(f"✅ API: Healthy at {api_health_url}")
            else:
                results.append(f"❌ API: Reached but returned status {resp.status_code} at {api_health_url}")
    except Exception as e:
        results.append(f"❌ API: Failed to reach {context.api_url} ({e})")

    # S3 check
    try:
        logger.info(f"Checking S3 connectivity to {context.s3_endpoint}")
        from masatools.core import get_s3_client
        s3 = get_s3_client()
        # s3 is a wrapper, the actual client is self.s3
        s3.s3.list_buckets()
        results.append(f"✅ S3: Connected to {context.s3_endpoint}")
    except Exception as e:
        results.append(f"❌ S3: Failed to connect to {context.s3_endpoint} ({e})")
    
    return "\n".join(results)

async def safe_tool_call(coro):
    """Wraps SDK calls to catch errors and return them as strings instead of crashing the server."""
    try:
        return await coro
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Error executing tool: {error_msg}", exc_info=True)
        return f"Error: {error_msg}"

@mcp.tool()
async def create_thread_tool(command: str, deadline: str, to: List[str] = [], observers: List[str] = [], parent_thread_id: str = None) -> str:
    """
    Creates a new thread for a task. 
    'deadline' should be in ISO8601 or a descriptive format.
    'to' is a list of agent IDs to assign the task to.
    """
    return await safe_tool_call(create_thread(command, deadline, to, observers, parent_thread_id))

@mcp.tool()
async def create_subthread_tool(parent_thread_id: str, message: str) -> str:
    """
    Creates a new subthread (child thread) under a parent thread.
    'parent_thread_id' is the ID of the parent thread.
    'message' is the task command and MUST contain mentions (e.g., @agent-id) to assign it.
    """
    return await safe_tool_call(create_subthread(parent_thread_id, message))

@mcp.tool()
async def start_monitoring_tool(duration_seconds: int) -> str:
    """
    Starts an in-process monitoring session for this MCP server.
    During monitoring, check_board_tool stops polling once the duration expires.
    """
    try:
        return start_monitoring(duration_seconds)
    except Exception as e:
        logger.error(f"Error in start_monitoring: {e}")
        return f"Error: {e}"

@mcp.tool()
async def get_runtime_context_tool() -> dict:
    """
    Returns runtime context such as monitoring state, monitor_until, and remaining_seconds.
    """
    try:
        return get_runtime_context()
    except Exception as e:
        logger.error(f"Error in get_runtime_context: {e}")
        return {"error": str(e)}

@mcp.tool()
async def check_board_tool(wait_seconds: int = 60, interval_seconds: int = 5) -> str:
    """
    Polls the NATS board for a new task.
    It checks immediately, then keeps checking every interval_seconds until a task is found
    or wait_seconds elapses. If monitoring has expired, it returns "Monitoring finished".
    """
    return await safe_tool_call(check_board(wait_seconds=wait_seconds, interval_seconds=interval_seconds))

@mcp.tool()
async def post_message_tool(message: str, thread_id: str = None, output_dir: str = None, error: str = None, metadata: Dict[str, Any] = None) -> str:
    """
    Posts a conversation message to the current thread.
    'message' is required and MUST contain at least one mention (e.g., @agent-id or @team).
    'output_dir', 'error', and 'metadata' are optional context.
    """
    return await safe_tool_call(post_message(message, thread_id, output_dir, error, metadata))

@mcp.tool()
async def sync_from_s3_tool(thread_id: str, sub_path: str = "input/") -> str:
    """
    Synchronizes data from S3 to the local workspace.
    Data is stored in /work/{agent_id}/{thread_id}/{sub_path}.
    """
    try:
        # sync_from_s3 is currently synchronous in the SDK
        return sync_from_s3(thread_id, sub_path)
    except Exception as e:
        logger.error(f"Error in sync_from_s3: {e}")
        return f"Error: {e}"

@mcp.tool()
async def sync_to_s3_tool(thread_id: str, local_file_path: str) -> str:
    """
    Uploads a local file to the S3 output directory for the given thread.
    Path in S3: /tasks/{thread_id}/output/{filename}
    """
    try:
        return sync_to_s3(thread_id, local_file_path)
    except Exception as e:
        logger.error(f"Error in sync_to_s3: {e}")
        return f"Error: {e}"

@mcp.tool()
async def get_thread_history_tool(thread_id: str = None) -> str:
    """
    Retrieves the conversation history for a specific thread.
    Useful for understanding the context of a task or sub-task.
    """
    return await safe_tool_call(get_thread_history(thread_id))

@mcp.tool()
async def get_my_profile_tool() -> str:
    """
    Retrieves the profile of the current agent, including its role and mission.
    This helps the agent understand its purpose and contribution to the team.
    """
    return await safe_tool_call(get_my_profile())

@mcp.tool()
async def get_team_blueprint_tool(team_id: Optional[str] = None) -> str:
    """
    Retrieves the full team architecture (Mermaid diagram and member list).
    """
    return await safe_tool_call(get_team_blueprint(team_id))

@mcp.tool()
async def get_network_tool() -> str:
    """
    Retrieves the local agent network relative to this agent.
    Shows leaders, subordinates, and coworkers.
    """
    return await safe_tool_call(get_network())

@mcp.tool()
async def request_reflection_tool(thread_id: str, due_at: Optional[str] = None) -> str:
    """
    Requests a reflection session for a thread by spinning up a reflection subthread.
    'due_at' is optional and should be an ISO8601 string.
    """
    return await safe_tool_call(request_reflection(thread_id, due_at))

@mcp.tool()
async def submit_reflection_tool(request_id: str, target_agent_id: str, dimension: str, score: int, reason: str, suggestion: Optional[str] = None) -> str:
    """
    Submits a structured reflection evaluation for an agent inside your team.
    'dimension' represents the evaluation axis, e.g., 'clarity', 'collaboration', etc.
    'score' must be -1, 0, or 1.
    """
    return await safe_tool_call(submit_reflection(request_id, target_agent_id, dimension, score, reason, suggestion))

if __name__ == "__main__":
    mcp.run(transport="stdio")
