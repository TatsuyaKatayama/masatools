import os
import time
import subprocess
import pytest
import httpx
import asyncio
import re
from masatools.skills.common.board import create_thread, check_board, send_offer, send_assign, update_status, post_response
import masatools.core.context
import masatools.core

# パスの設定
BBS_DIR = os.getenv("MASABBS_PATH", os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..", "masabbs")))
API_URL = "http://localhost:8080"
NATS_URL = "nats://localhost:4222"

@pytest.fixture(scope="module", autouse=True)
def masabbs_services():
    """Dockerコンテナの起動と初期化、サーバーの実行を管理するフィクスチャ"""
    print("\n[Setup] Starting Docker containers...")
    subprocess.run(["docker", "compose", "up", "-d"], cwd=BBS_DIR, check=True)
    
    # DBの起動待ち
    print("[Setup] Waiting for database to be ready...")
    time.sleep(10)
    
    # テストデータの投入
    print("[Setup] Seeding database...")
    seed_sql = """
    INSERT INTO teams (id, name) VALUES ('team-a', 'Team A') ON CONFLICT DO NOTHING;
    INSERT INTO agents (id, name, role, team_id) VALUES ('manager-1', 'Manager 1', 'manager', 'team-a') ON CONFLICT DO NOTHING;
    INSERT INTO agents (id, name, role, team_id) VALUES ('worker-1', 'Worker 1', 'worker', 'team-a') ON CONFLICT DO NOTHING;
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
    max_retries = 30
    ready = False
    for i in range(max_retries):
        try:
            resp = httpx.get(f"{API_URL}/health")
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
    res = await create_thread("Integration Test Mission", "2026-12-31T23:59:59Z")
    assert "Thread created" in res
    thread_id = re.search(r"Thread created: ([\w\-]+)", res).group(1)
    print(f"Thread ID: {thread_id}")

    # サーバー側のDB記録を確認
    print("Waiting for Archiver to persist 'task' to DB...")
    async with httpx.AsyncClient() as client:
        for _ in range(10):
            await asyncio.sleep(1)
            resp = await client.get(f"{API_URL}/api/v1/tasks")
            tasks = resp.json()
            if tasks and any(t["type"] == "task" and t.get("thread_id") == thread_id for t in tasks):
                break
        else:
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
        resp = await client.get(f"{API_URL}/api/v1/tasks")
        tasks = resp.json()
        assert any(t["type"] == "offer" and t["from"] == "worker-1" and t["thread_id"] == thread_id for t in tasks)

    # 4. 割り当て (Manager)
    print("\n--- Step 4: Assign (Manager) ---")
    os.environ["AGENT_ID"] = "manager-1"
    masatools.core.context._default_context = None
    masatools.core._default_nats_client = None
    res = await send_assign(to=["worker-1"], reason="Approved", thread_id=thread_id)
    assert "Assignment sent" in res

    # 5. ステータス更新 (Worker)
    print("\n--- Step 5: Update Status (Worker) ---")
    os.environ["AGENT_ID"] = "worker-1"
    masatools.core.context._default_context = None
    masatools.core._default_nats_client = None
    res = await update_status(progress=50, state="PROCESSING", thread_id=thread_id)
    assert "Status updated" in res

    # 6. 結果報告 (Worker)
    print("\n--- Step 6: Post Result (Worker) ---")
    res = await post_response(output_dir=f"tasks/{thread_id}/output/", exit_code=0, thread_id=thread_id)
    assert "Result posted" in res

    # 最終確認 (サーバー側DB)
    print("\n--- Step 7: Final DB Verification ---")
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_URL}/api/v1/tasks")
        tasks = resp.json()
        
        # 全てのステップのメッセージが揃っているか確認
        msg_types = [t["type"] for t in tasks if t["thread_id"] == thread_id]
        print(f"Recorded message types: {msg_types}")
        for t in ["task", "offer", "assign", "status", "result"]:
            assert t in msg_types, f"Message type '{t}' missing from DB"

    print("\nIntegration test passed successfully!")
