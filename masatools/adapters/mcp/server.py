from mcp.server.fastmcp import FastMCP
from masatools.skills.common.board import check_board, post_response, update_status, create_thread, send_offer, send_assign
from masatools.skills.common.storage import sync_from_s3, sync_to_s3
from typing import List
import asyncio

# Create the MCP server
mcp = FastMCP("bbs-mcp")

@mcp.tool()
async def create_thread_tool(command: str, deadline: str, to: List[str] = [], observers: List[str] = [], parent_thread_id: str = None) -> str:
    """
    Creates a new thread for a task. 
    This is used when an agent wants to delegate a sub-task or start a new conversation.
    'deadline' should be in ISO8601 or a descriptive format.
    'to' is a list of agent IDs to assign the task to.
    """
    return await create_thread(command, deadline, to, observers, parent_thread_id)

@mcp.tool()
async def send_offer_tool(eta_seconds: int, confidence: float, thread_id: str = None) -> str:
    """
    Sends an offer to work on a task.
    'eta_seconds': how many seconds you estimate it will take.
    'confidence': how sure you are (0.0 to 1.0).
    """
    return await send_offer(eta_seconds, confidence, thread_id)

@mcp.tool()
async def send_assign_tool(to: List[str], reason: str = None, thread_id: str = None) -> str:
    """
    Assigns a task to specific agents. Used by the task creator.
    'to' is a list of agent IDs.
    """
    return await send_assign(to, reason, thread_id)

@mcp.tool()
async def check_board_tool(wait_seconds: int = 60) -> str:
    """
    Checks the NATS board for a new task.
    If no task is found, it will wait for the specified number of seconds.
    """
    return await check_board(wait_seconds=wait_seconds)

@mcp.tool()
async def post_response_tool(output_dir: str, exit_code: int = 0, error: str = None, thread_id: str = None) -> str:
    """
    Posts a final result to the board for the given thread.
    'output_dir' should be the S3 relative path to the results.
    'exit_code' is 0 for success, non-zero for failure.
    'error' is an optional error message.
    """
    return await post_response(output_dir, exit_code, error, thread_id)

@mcp.tool()
async def sync_from_s3_tool(thread_id: str, sub_path: str = "input/") -> str:
    """
    Synchronizes data from S3 to the local workspace.
    Data is stored in /work/{agent_id}/{thread_id}/{sub_path}.
    """
    # sync_from_s3 is synchronous, but we run it in a thread if needed.
    # For simplicity in this implementation, we call it directly.
    return sync_from_s3(thread_id, sub_path)

@mcp.tool()
async def sync_to_s3_tool(thread_id: str, local_file_path: str) -> str:
    """
    Uploads a local file to the S3 output directory for the given thread.
    Path in S3: /tasks/{thread_id}/output/{filename}
    """
    return sync_to_s3(thread_id, local_file_path)

@mcp.tool()
async def update_status_tool(progress: int, state: str, message: str = None, thread_id: str = None) -> str:
    """
    Reports progress and current state (e.g., 'RUNNING', 'PAUSED') to the board.
    """
    return await update_status(progress, state, message, thread_id)

if __name__ == "__main__":
    mcp.run()
