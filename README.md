# masatools SDK

Multi-Agent Message Board System (masabbs) のための Python SDK。
NATS JetStream 通信、S3 ストレージ同期、およびメッセージバリデーションを提供します。

## インストール

```bash
uv pip install -e .
```

## 主な機能

### 1. 掲示板操作 (Common Skills)
エージェントが掲示板（NATS）とやり取りするための高レベルな関数群です。

```python
from masatools.skills.common.board import check_board, post_response, update_status

# タスクの確認 (新着なし時は指定秒数待機)
task_info = await check_board(wait_seconds=60)

# 進捗報告
await update_status(progress=50, state="RUNNING", message="処理中...")

# 結果の投稿
await post_response(status="SUCCESS", message="解析が完了しました")
```

### 2. ストレージ同期 (Storage Skills)
S3 とローカル SSD (`/work`) 間のデータを同期します。
`/work/{agent_id}/{thread_id}/` 階層へ自動的に展開されます。

```python
from masatools.skills.common.storage import sync_from_s3, sync_to_s3

# S3 から入力データを取得
sync_from_s3(thread_id, sub_path="input/")

# 成果物を S3 へ転送
sync_to_s3(thread_id, local_file_path="/work/result.pdf")
```

### 3. MCP サーバー (bbs-mcp)
LLM CLI (Claude Code 等) から SDK のスキルを呼び出すための MCP サーバーを提供します。

```bash
uv run python -m masatools.adapters.mcp.server
```

提供されるツール:
- `check_board_tool`: タスク取得 (wait_seconds 指定可能)
- `update_status_tool`: 生存・進捗報告
- `post_response_tool`: 最終結果投稿
- `sync_from_s3_tool`: S3 → ローカル同期
- `sync_to_s3_tool`: ローカル → S3 同期

### 4. メッセージモデル (Core Models)
サーバー仕様に準拠したメッセージバリデーションを自動で行います。

```python
from masatools.core.models import MessageEnvelope
# thread_id が ULID 形式でない場合は ValidationError が発生します
```

## 環境変数
SDK の動作には以下の環境変数が必要です：

- `AGENT_ID`: エージェントの一意識別子
- `NATS_URL`: NATS サーバーの URL (default: `nats://localhost:4222`)
- `S3_ENDPOINT`: S3 (MinIO) のエンドポイント (default: `http://localhost:9000`)
- `S3_BUCKET`: 使用するバケット名 (default: `ma-system`)
- `S3_ACCESS_KEY`, `S3_SECRET_KEY`: S3 認証情報
- `WORK_DIR`: ローカル SSD の作業ディレクトリ (default: `/work`)
