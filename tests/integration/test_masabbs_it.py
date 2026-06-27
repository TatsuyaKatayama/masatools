import os
import time
import subprocess
import pytest
import httpx
import asyncio
import re
from masatools.skills.common.board import create_thread, create_subthread, check_board, send_offer, send_assign, post_message, request_reflection, submit_reflection
import masatools.core.context
import masatools.core

# パスの設定
BBS_DIR = os.getenv("MASABBS_PATH", os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..", "masabbs")))
API_URL = "http://localhost:8080/api/v1"
NATS_URL = "nats://localhost:4222"

@pytest.fixture(scope="module", autouse=True)
def masabbs_services():
    """Dockerコンテナの起動と初期化、サーバーの実行を管理するフィクスチャ"""
    print("\n[Setup] Starting Docker containers...")
    subprocess.run(["docker", "compose", "up", "-d"], cwd=BBS_DIR, check=True)
    
    # DBの起動待ち
    print("[Setup] Waiting for database to be ready...")
    time.sleep(20)
    
    # テストデータの投入
    print("[Setup] Seeding database...")
    seed_sql = """
    INSERT INTO teams (id, name) VALUES ('team-a', 'Team A') ON CONFLICT DO NOTHING;
    INSERT INTO teams (id, name) VALUES ('team-b', 'Team B') ON CONFLICT DO NOTHING;
    INSERT INTO agents (id, name, role, team_id) VALUES ('manager-1', 'Manager 1', 'TeamManager', 'team-a') ON CONFLICT DO NOTHING;
    INSERT INTO agents (id, name, role, team_id) VALUES ('worker-1', 'Worker 1', 'Worker', 'team-a') ON CONFLICT DO NOTHING;
    INSERT INTO agents (id, name, role, team_id) VALUES ('chef-1', 'Chef 1', 'Chef', 'team-a') ON CONFLICT DO NOTHING;
    INSERT INTO agents (id, name, role, team_id) VALUES ('chef-2', 'Chef 2', 'Chef', 'team-b') ON CONFLICT DO NOTHING;
    """
    subprocess.run([
        "docker", "compose", "exec", "-T", "db", 
        "psql", "-U", "user", "-d", "masabbs", "-c", seed_sql
    ], cwd=BBS_DIR, check=True)

    # サーバーの起動
    print("[Setup] Starting masabbs server...")
    env = os.environ.copy()
    env["PORT"] = "8080"
    env["DATABASE_URL"] = "postgres://user:password@localhost:5432/masabbs?sslmode=disable"
    env["NATS_URL"] = NATS_URL
    env["MINIO_ENDPOINT"] = "localhost:9000"
    env["SKIP_SIG_VERIFY"] = "true" # 統合テスト用に署名検証をスキップ
    
    # バックグラウンドで実行。出力はログファイルに。
    with open("bbs_server.log", "w") as log_file:
        server_proc = subprocess.Popen(
            ["go", "run", "cmd/server/main.go"],
            cwd=BBS_DIR,
            env=env,
            stdout=log_file,
            stderr=log_file,
            preexec_fn=os.setsid # プロセスグループを作成して終了を容易にする
        )
    
    # ヘルスチェック
    print("[Setup] Waiting for API health check...")
    max_retries = 60
    ready = False
    BASE_URL = API_URL.replace("/api/v1", "")
    for i in range(max_retries):
        try:
            resp = httpx.get(f"{BASE_URL}/health")
            if resp.status_code == 200:
                print(f"[Setup] Server is ready after {i} seconds.")
                ready = True
                break
        except Exception:
            pass
        time.sleep(1)
    
    if not ready:
        print("[Setup] Server failed to start. Logs:")
        with open("bbs_server.log", "r") as f:
            print(f.read())
        import signal
        os.killpg(os.getpgid(server_proc.pid), signal.SIGTERM)
        subprocess.run(["docker", "compose", "down", "-v"], cwd=BBS_DIR)
        pytest.fail("masabbs server health check failed")

    yield server_proc

    # クリーンアップ
    print("\n[Teardown] Shutting down server and containers...")
    import signal
    try:
        os.killpg(os.getpgid(server_proc.pid), signal.SIGTERM)
        server_proc.wait(timeout=10)
    except Exception:
        os.killpg(os.getpgid(server_proc.pid), signal.SIGKILL)
    
    subprocess.run(["docker", "compose", "down", "-v"], cwd=BBS_DIR, check=True)

@pytest.mark.asyncio
async def test_masabbs_integration_workflow():
    """masabbsとmasatoolsのフルワークフローテスト"""
    # 環境変数の設定
    os.environ["API_URL"] = API_URL
    os.environ["NATS_URL"] = NATS_URL
    
    # 状態の初期化
    masatools.core.context._default_context = None
    masatools.core._default_nats_client = None

    # 1. Thread作成 (Manager)
    print("\n--- Step 1: Create Thread (Manager) ---")
    os.environ["AGENT_ID"] = "manager-1"
    res = await create_thread("Integration Test Mission @worker-1", "2026-12-31T23:59:59Z")
    assert "Thread created" in res
    thread_id = re.search(r"Thread created: ([\w\-]+)", res).group(1)
    print(f"Thread ID: {thread_id}")

    # サーバー側のDB記録を確認
    print("Waiting for Archiver to persist 'task' to DB...")
    async with httpx.AsyncClient() as client:
        for _ in range(20): # 20秒に延長
            await asyncio.sleep(1)
            try:
                resp = await client.get(f"{API_URL}/tasks")
                tasks = resp.json()
                if tasks and any(t["type"] == "task" and t.get("thread_id") == thread_id for t in tasks):
                    break
            except Exception as e:
                print(f"Error fetching tasks: {e}")
        else:
            print("[Error] Task persistence timeout. Server logs:")
            try:
                with open("bbs_server.log", "r") as f:
                    print(f.read())
            except:
                print("Could not read bbs_server.log")
            pytest.fail(f"Task with thread_id {thread_id} not found in DB. Tasks: {tasks}")

    # 2. タスク確認 (Worker)
    print("\n--- Step 2: Check Board (Worker) ---")
    os.environ["AGENT_ID"] = "worker-1"
    masatools.core.context._default_context = None
    masatools.core._default_nats_client = None
    
    await asyncio.sleep(2) # JetStreamへの反映待ち
    res = await check_board(wait_seconds=5)
    assert f"Thread: {thread_id}" in res

    # 3. 立候補送信 (Worker)
    print("\n--- Step 3: Send Offer (Worker) ---")
    res = await send_offer(eta_seconds=1800, confidence=0.95, thread_id=thread_id)
    assert "Offer sent" in res

    # サーバー側の確認
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_URL}/tasks")
        tasks = resp.json()
        assert any(t["type"] == "offer" and t["from"] == "worker-1" and t["thread_id"] == thread_id for t in tasks)

    # 4. 割り当て (Manager)
    print("\n--- Step 4: Assign (Manager) ---")
    os.environ["AGENT_ID"] = "manager-1"
    masatools.core.context._default_context = None
    masatools.core._default_nats_client = None
    res = await send_assign(to=["worker-1"], reason="Approved", thread_id=thread_id)
    assert "Assignment sent" in res

    # 5. 結果報告 (Worker)
    print("\n--- Step 5: Post Result (Worker) ---")
    os.environ["AGENT_ID"] = "worker-1"
    masatools.core.context._default_context = None
    masatools.core._default_nats_client = None
    res = await post_message(
        message="Integration test completed successfully @manager-1.",
        output_dir=f"tasks/{thread_id}/output/",
        thread_id=thread_id,
    )
    assert "Message posted" in res

    # 最終確認 (サーバー側DB)
    print("\n--- Step 6: Final DB Verification ---")
    expected_types = ["task", "offer", "assign", "result"]
    async with httpx.AsyncClient() as client:
        for _ in range(10):
            resp = await client.get(f"{API_URL}/tasks")
            tasks = resp.json()
            msg_types = [t["type"] for t in tasks if t["thread_id"] == thread_id]
            if all(t in msg_types for t in expected_types):
                break
            await asyncio.sleep(1)
        else:
            print(f"Recorded message types: {msg_types}")
            for t in expected_types:
                assert t in msg_types, f"Message type '{t}' missing from DB. Current: {msg_types}"

    print("\nIntegration test passed successfully!")


@pytest.mark.asyncio
async def test_masabbs_subthread_permissions():
    """Step 5: Subthread creation permissions and team inheritance."""
    # 1. TeamManager creates top-level thread
    print("\n--- Subthread Test: Create Parent Thread (Manager) ---")
    os.environ["AGENT_ID"] = "manager-1"
    masatools.core.context._default_context = None
    masatools.core._default_nats_client = None
    
    # We must include mention to pass validation
    res = await create_thread("Parent Task for UI team @chef-1", "2026-12-31T23:59:59Z")
    assert "Thread created" in res
    parent_thread_id = re.search(r"Thread created: ([\w\-]+)", res).group(1)
    print(f"Parent Thread ID: {parent_thread_id}")

    # 2. TeamManager creates subthread
    print("\n--- Subthread Test: TeamManager creates subthread (Succeeds) ---")
    os.environ["AGENT_ID"] = "manager-1"
    masatools.core.context._default_context = None
    masatools.core._default_nats_client = None
    
    # Must include mention to pass validation
    sub_res = await create_subthread(parent_thread_id, "Subtask API development @worker-1")
    assert "Thread created" in sub_res
    sub_thread_id = re.search(r"Thread created: ([\w\-]+)", sub_res).group(1)
    print(f"Subthread ID: {sub_thread_id}")

    # 3. Chef tries to create subthread (Fails)
    print("\n--- Subthread Test: Chef trying to create subthread (Fails) ---")
    os.environ["AGENT_ID"] = "chef-2"
    masatools.core.context._default_context = None
    masatools.core._default_nats_client = None
    
    fail_res = await create_subthread(parent_thread_id, "Different Team Subtask @worker-1")
    assert "Error: Failed to create thread. Status: 403" in fail_res
    assert "only TeamManager can create subthreads" in fail_res

    # 4. Worker tries to create subthread (Fails)
    print("\n--- Subthread Test: Worker trying to create subthread (Fails) ---")
    os.environ["AGENT_ID"] = "worker-1"
    masatools.core.context._default_context = None
    masatools.core._default_nats_client = None
    
    fail_res2 = await create_subthread(parent_thread_id, "Worker Subtask @chef-1")
    assert "Error: Failed to create thread. Status: 403" in fail_res2
    assert "only TeamManager can create subthreads" in fail_res2


@pytest.mark.asyncio
async def test_masabbs_reflection_integration():
    """Step 6: Reflection request (subthread creation, NATS task publish) and submission integration."""
    # 1. TeamManager creates parent thread
    print("\n--- Reflection Test: Create Parent Thread (Manager) ---")
    os.environ["AGENT_ID"] = "manager-1"
    masatools.core.context._default_context = None
    masatools.core._default_nats_client = None
    
    res = await create_thread("Parent Task @worker-1", "2026-12-31T23:59:59Z")
    assert "Thread created" in res
    parent_thread_id = re.search(r"Thread created: ([\w\-]+)", res).group(1)
    
    # 2. Request Reflection
    print("\n--- Reflection Test: Request Reflection (Manager) ---")
    req_res = await request_reflection(parent_thread_id)
    assert "Reflection requested successfully" in req_res
    request_id = re.search(r"Request ID: ([\w\-]+)", req_res).group(1)
    reflection_thread_id = re.search(r"Reflection Subthread ID: ([\w\-]+)", req_res).group(1)
    
    print(f"Request ID: {request_id}")
    print(f"Reflection Subthread ID: {reflection_thread_id}")

    # 3. Pull the reflection request on NATS via check_board
    print("\n--- Reflection Test: Pull Request (Worker) ---")
    os.environ["AGENT_ID"] = "worker-1"
    masatools.core.context._default_context = None
    masatools.core._default_nats_client = None
    
    await asyncio.sleep(2) # Wait for JetStream persistence
    found = False
    board_res = ""
    for _ in range(10):
        board_res = await check_board(wait_seconds=3)
        if f"Thread: {reflection_thread_id}" in board_res:
            found = True
            break
        await asyncio.sleep(1)
    assert found, f"Reflection task {reflection_thread_id} not found in board. Last response: {board_res}"

    # 4. Submit Reflection (Succeeds)
    print("\n--- Reflection Test: Submit Reflection (Succeeds) ---")
    sub_res = await submit_reflection(
        request_id=request_id,
        target_agent_id="chef-1", # Same team colleague/boss
        dimension="collaboration",
        score=1,
        reason="Exceeded expectations",
        suggestion="Keep doing great work",
    )
    assert "Reflection submitted successfully" in sub_res

    # 5. Submit Reflection on unrelated agent (Fails)
    print("\n--- Reflection Test: Submit Reflection to unrelated agent (Fails) ---")
    unrelated_res = await submit_reflection(
        request_id=request_id,
        target_agent_id="chef-2", # Chef on team-b (unrelated)
        dimension="collaboration",
        score=1,
        reason="Unrelated",
    )
    assert "Error: Failed to submit reflection" in unrelated_res
    assert "INVALID_TARGET_AGENT" in unrelated_res

