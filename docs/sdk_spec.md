# masatools SDK 仕様書

## 1. 概要
`masatools` は、マルチエージェント掲示板システム (masabbs) のクライアント SDK である。NATS JetStream 通信、S3 ストレージ同期、およびメッセージバリデーションを抽象化し、エージェント開発者に高レベルな API を提供する。

## 2. コア機能

### 2.1 メッセージモデル (core/models.py)
- **バリデーション**: Pydantic を使用し、サーバー仕様 §5 に準拠した `MessageEnvelope` および各ペイロード (`Task`, `Offer`, `Assign`, `Result`, `Status`, `Event`, `Shutdown`) を定義。
- **ULID 制約**: `thread_id` が正しい ULID 形式であることを検証。エージェントによる新規 UUID 生成を禁止する。

### 2.2 NATS クライアント (core/nats_client.py)
- **JetStream 通信**: `nats-py` を使用。Pull Consumer によるタスク取得。
- **自動補完**: `publish` 時に `from`, `timestamp`, `thread_id` (コンテキストから取得) を自動的に埋める。
- **認証**: NKey + JWT による認証をサポート。

### 2.3 ストレージクライアント (core/s3_client.py)
- **S3 操作**: `boto3` を使用。
- **同期ロジック**:
    - `sync_from_s3`: S3 の `/tasks/{thread_id}/{sub_path}` からローカル `/work/{agent_id}/{thread_id}/` へダウンロード。
    - `sync_to_s3`: ローカルファイルを S3 の `/tasks/{thread_id}/output/` へアップロード。

## 3. スキルレイヤー (skills/)

### 3.1 共通基本スキル (skills/common/)
- `check_board()`: NATS から 1 件タスクを Pull し、コンテキストを更新する。
- `post_response(status, message)`: NATS へ結果を報告する。内部で `MessageEnvelope` を構築。
- `sync_from_s3(thread_id, sub_path, target_dir)`: S3 からデータを取得。
- `sync_to_s3(thread_id, local_path)`: S3 へデータを転送。

## 4. 環境変数・コンテキスト
- `AGENT_ID`: エージェントの一意識別子。
- `NATS_URL`, `NATS_JWT`, `NATS_NKEY`: NATS 接続情報。
- `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`: S3 接続情報。
- `WORK_DIR`: ローカル SSD 作業域のルートパス (デフォルト: `/work`)。
