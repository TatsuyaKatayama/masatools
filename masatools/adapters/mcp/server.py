from mcp.server.fastmcp import FastMCP
from masatools.skills.common.board import check_board, post_response, update_status
from masatools.skills.common.storage import sync_from_s3, sync_to_s3
import asyncio

# Create the MCP server
mcp = FastMCP("bbs-mcp")

@mcp.tool()
async def check_board_tool(wait_seconds: int = 60) -> str:
    """
    Checks the NATS board for a new task.
    If no task is found, it will wait for the specified number of seconds.
    """
    return await check_board(wait_seconds=wait_seconds)

@mcp.tool()
async def post_response_tool(status: str, message: str, thread_id: str = None) -> str:
    """
    Posts a final result or error to the board.
    If thread_id is not provided, the current active thread_id will be used.
    'status' should be 'SUCCESS' or 'ERROR'.
    """
    return await post_response(status, message, thread_id)

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
