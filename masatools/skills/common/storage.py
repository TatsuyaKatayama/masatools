import os
from ...core import get_s3_client, get_default_context

def sync_from_s3(thread_id: str, sub_path: str = "input/") -> str:
    """
    Syncs data from S3 to the local work directory.
    """
    client = get_s3_client()
    context = get_default_context()
    
    target_dir = os.path.join(context.work_dir, context.agent_id, thread_id, sub_path.strip("/"))
    os.makedirs(target_dir, exist_ok=True)
    
    client.download_directory(thread_id, sub_path, target_dir)
    return f"Synced S3 path 'tasks/{thread_id}/{sub_path}' to '{target_dir}'"

def sync_to_s3(thread_id: str, local_file_path: str) -> str:
    """
    Syncs a local file to the S3 output directory.
    """
    client = get_s3_client()
    
    if not os.path.exists(local_file_path):
        return f"Error: Local file '{local_file_path}' not found."
    
    client.upload_file(thread_id, local_file_path)
    return f"Uploaded '{local_file_path}' to S3 output for thread {thread_id}"
