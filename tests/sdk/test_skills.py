import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from masatools.skills.common.board import check_board, post_response, create_thread, send_offer, send_assign
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
        
        result = await post_response("results/dir", exit_code=0, thread_id=tid)
        assert f"Result posted to board.result.{tid}" in result
        mock_client.publish.assert_called_once()
        # Verify message type is result
        args, kwargs = mock_client.publish.call_args
        assert kwargs["message_type"] == "result"
        assert kwargs["payload"]["output_dir"] == "results/dir"
        assert kwargs["payload"]["exit_code"] == 0

@pytest.mark.asyncio
async def test_create_thread_success():
    tid = str(ULID())
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"thread_id": tid, "input_dir": "tasks/input"}
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        result = await create_thread("do something", "2026-12-31")
        assert f"Thread created: {tid}" in result
        mock_post.assert_called_once()
        # Check payload
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["command"] == "do something"

@pytest.mark.asyncio
async def test_send_offer_success():
    tid = str(ULID())
    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_get_nats:
        mock_client = mock_get_nats.return_value
        
        result = await send_offer(3600, 0.9, thread_id=tid)
        assert f"Offer sent for thread {tid}" in result
        mock_client.publish.assert_called_once()
        args, kwargs = mock_client.publish.call_args
        assert kwargs["message_type"] == "offer"
        assert kwargs["payload"]["eta_seconds"] == 3600

@pytest.mark.asyncio
async def test_send_assign_success():
    tid = str(ULID())
    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_get_nats:
        mock_client = mock_get_nats.return_value
        
        result = await send_assign(["agent-b"], reason="Best candidate", thread_id=tid)
        assert f"Assignment sent to ['agent-b'] for thread {tid}" in result
        mock_client.publish.assert_called_once()
        args, kwargs = mock_client.publish.call_args
        assert kwargs["message_type"] == "assign"
        assert kwargs["to"] == ["agent-b"]

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
