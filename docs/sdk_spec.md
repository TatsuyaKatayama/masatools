# masatools SDK & MCP サーバー仕様書 (V11 対応)

## 1. 概要
`masatools` は、自律型エージェントの「手足」となるツール群を提供する。V11 では、LLM CLI が MCP クライアントとして動作するため、`masatools` は MCP サーバー（`bbs-mcp`）としてのインターフェースを主軸とする。

## 2. メッセージモデル (core/models.py)
- **バリデーション**: 通信仕様書 §2 に準拠した `MessageEnvelope` および各ペイロードを Pydantic で実装。
- **ULID 制約**: `thread_id` が必ず ULID 形式であることを厳格に検証。

## 3. MCP サーバー仕様 (bbs-mcp)

LLM CLI に対し、以下のツールを MCP (stdio) 経由で公開する。

### 3.1 ツール一覧
| ツール名 | 説明 | 特記事項 |
|:---|:---|:---|
| `start_monitoring` | 監視セッションを開始 | MCP server の process memory に `monitor_until` を保持 |
| `get_runtime_context` | runtime context を取得 | `remaining_seconds`, `is_monitoring` 等を返す |
| `check_board` | NATS からタスクを取得 | `wait_seconds` の間、`interval_seconds` ごとに polling。監視期限切れなら `Monitoring finished` |
| `post_response` | 結果を投稿 | `thread_id`, `from`, `to` 等を内部で自動補完 |
| `sync_from_s3` | S3 → ローカル展開 | `/work/{agent_id}/{thread_id}/` 階層へ |
| `sync_to_s3` | ローカル → S3 アップロード | `/tasks/{thread_id}/output/` へ |

### 3.2 内部ロジック
- **レート制限**: NATS の制限（60 msg/分）を超えないよう、`post_response` 等の内部で流量制御を行う。
- **自動補完**: `post_response` 時に、直前の `check_board` で得た `thread_id` や環境変数の `AGENT_ID` を使用してメッセージを完成させる。
- **監視セッション**: `start_monitoring` 後、`check_board` は残り時間を超えて待機しない。期限切れ時は `Monitoring finished` を返す。

## 4. ストレージ操作 (core/s3_client.py)
- **ハイブリッド構造**: 巨大データはローカル `/work` に「居座り」、軽量サマリーのみを S3 に転送する。
- **パス管理**: `/tasks/{thread_id}/` 体系を遵守。

## 5. 専門スキル (skills/specialized/)
- `run_simulation`, `analyze_huge_data`, `generate_summary_plots` を MCP ツールとして公開可能にする。
