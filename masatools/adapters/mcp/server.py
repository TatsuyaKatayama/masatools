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
from masatools.skills.common.board import check_board, post_response, update_status, create_thread, send_offer, send_assign, get_thread_history
from masatools.skills.common.storage import sync_from_s3, sync_to_s3
from typing import List
import asyncio

# Create the MCP server
mcp = FastMCP("bbs-mcp")

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
        logger.info(f"Checking API connectivity to {context.api_url}")
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(f"{context.api_url}/health")
            if resp.status_code == 200:
                results.append(f"✅ API: Healthy at {context.api_url}")
            else:
                results.append(f"❌ API: Reached but returned status {resp.status_code} at {context.api_url}")
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
async def send_offer_tool(eta_seconds: int, confidence: float, thread_id: str = None) -> str:
    """
    Sends an offer to work on a task.
    'eta_seconds': how many seconds you estimate it will take.
    'confidence': how sure you are (0.0 to 1.0).
    """
    return await safe_tool_call(send_offer(eta_seconds, confidence, thread_id))

@mcp.tool()
async def send_assign_tool(to: List[str], reason: str = None, thread_id: str = None) -> str:
    """
    Assigns a task to specific agents. Used by the task creator.
    'to' is a list of agent IDs.
    """
    return await safe_tool_call(send_assign(to, reason, thread_id))

@mcp.tool()
async def check_board_tool(wait_seconds: int = 60) -> str:
    """
    Checks the NATS board for a new task.
    If no task is found, it will wait for the specified number of seconds.
    """
    return await safe_tool_call(check_board(wait_seconds=wait_seconds))

@mcp.tool()
async def post_response_tool(output_dir: str = None, exit_code: int = 0, message: str = None, error: str = None, thread_id: str = None) -> str:
    """
    Posts a final result to the board for the given thread.
    'output_dir' should be the S3 relative path to the results (optional).
    'exit_code' is 0 for success, non-zero for failure.
    'message' is an optional text message to include in the result.
    'error' is an optional error message.
    """
    return await safe_tool_call(post_response(output_dir, exit_code, message, error, thread_id))

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
async def update_status_tool(progress: int, state: str, message: str = None, thread_id: str = None) -> str:
    """
    Reports progress and current state (e.g., 'RUNNING', 'PAUSED') to the board.
    """
    return await safe_tool_call(update_status(progress, state, message, thread_id))

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
    from ...skills.common.board import get_my_profile
    return await safe_tool_call(get_my_profile())

if __name__ == "__main__":
    mcp.run()
