import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from masatools.skills.common.board import check_board, post_response
from masatools.skills.common.storage import sync_from_s3, sync_to_s3
from masatools.core.models import MessageEnvelope
from ulid import ULID

@pytest.mark.asyncio
async def test_check_board_found():
    tid = str(ULID())
    mock_envelope = MessageEnvelope(
        type="task",
        thread_id=tid,
        from_agent="server",
        payload={"command": "test"}
    )
    
    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_get_nats:
        mock_client = mock_get_nats.return_value
        mock_client.pull_task.return_value = mock_envelope
        
        result = await check_board()
        assert f"Task found: task (Thread: {tid})" in result
        mock_client.pull_task.assert_called_once()

@pytest.mark.asyncio
async def test_post_response_success():
    tid = str(ULID())
    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_get_nats:
        mock_client = mock_get_nats.return_value
        
        result = await post_response("SUCCESS", "Calculation done", thread_id=tid)
        assert f"Response posted to board.result.{tid}" in result
        mock_client.publish.assert_called_once()
        # Verify message type is result
        args, kwargs = mock_client.publish.call_args
        assert kwargs["message_type"] == "result"
        assert kwargs["payload"]["state"] == "success"

def test_sync_from_s3_path():
    tid = str(ULID())
    with patch("masatools.skills.common.storage.get_s3_client") as mock_get_s3, \
         patch("masatools.skills.common.storage.os.makedirs") as mock_makedirs:
        mock_client = mock_get_s3.return_value
        
        # Test download
        result = sync_from_s3(tid, "input/")
        assert f"tasks/{tid}/input/" in result
        mock_client.download_directory.assert_called_once()
        mock_makedirs.assert_called()

def test_sync_to_s3_upload():
    tid = str(ULID())
    with patch("masatools.skills.common.storage.get_s3_client") as mock_get_s3:
        mock_client = mock_get_s3.return_value
        
        # Mock os.path.exists to return True
        with patch("os.path.exists", return_value=True):
            result = sync_to_s3(tid, "local_file.txt")
            assert "Uploaded 'local_file.txt'" in result
            mock_client.upload_file.assert_called_with(tid, "local_file.txt")
