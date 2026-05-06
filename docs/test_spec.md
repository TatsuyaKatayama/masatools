# masatools SDK テスト仕様書

## 1. テスト方針
`masatools` SDK の各機能が仕様通り動作し、不正なメッセージや設定を適切に拒否できることを検証する。

## 2. 単体テスト (Unit Test)

### 2.1 メッセージバリデーション
- **UT-VAL-SDK-001**: 正しい ULID を持つ `MessageEnvelope` が受理されること。
- **UT-VAL-SDK-002**: 異常な形式の ULID (UUID 等) が拒否されること。
- **UT-VAL-SDK-003**: 必須フィールドが欠落したペイロードが拒否されること。

### 2.2 自動補完ロジック
- **UT-AUTO-SDK-001**: `publish` 時に `agent_id`, `timestamp` が正しく自動注入されること。

## 3. 結合テスト (Integration Test)

### 3.1 NATS 通信
- **IT-NATS-SDK-001**: Mock NATS または Testcontainers を使用し、メッセージの Publish/Pull が正常に行えること。
- **IT-NATS-SDK-002**: レート制限超過時に SDK 側でエラーハンドリングまたはリトライが行われること。

### 3.2 S3 同期
- **IT-S3-SDK-001**: LocalStack または MinIO コンテナに対し、`sync_from_s3`/`sync_to_s3` が正しく動作すること。
- **IT-S3-SDK-002**: 存在しないパスへのアクセスで適切なエラーが返されること。
