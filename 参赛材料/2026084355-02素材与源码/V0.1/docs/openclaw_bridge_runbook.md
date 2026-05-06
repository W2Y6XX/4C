# OpenClaw Bridge Runbook

## 目标
本桥接层只做本地最小串联，不引入 HTTP 服务、不改主数据库 schema、不改冻结协议。  
它的职责只有一件事：把 OpenClaw 侧的一次会话输入，桥接到当前 MVP 的本地流程里。

桥接闭环如下：

`start -> parse -> revise -> commit / cancel`

## 边界
- 不修改 `schema.sql`、`validator.py`、`flow_manager.py`、`db.py`
- 不新增字段、状态、类型、来源
- 不实现 webhook server / FastAPI / HTTP listener
- 桥接状态只保存在独立目录，不污染主数据库 schema

## 关键身份区分
桥接层里有两套会话标识，必须明确区分：

1. `flow_session`
说明：`FlowManager.start_session()` 返回的内存会话快照。  
用途：继续做 `parse`、`revise`、`commit`、`cancel` 时，恢复当前流程上下文。

2. `db_session_id`
说明：`db.insert_flow_session()` 写入 SQLite 后生成的 `flow_sessions.session_id`。  
用途：更新 `candidate_payload`、推进数据库里的 `flow_state`。

桥接层不允许假设这两者天然一致。

## 默认路径
这些路径都集中定义在 `scripts/openclaw_bridge.py` 顶部：

- 项目根目录：脚本自动按仓库位置解析
- 数据库路径：`/opt/negative-entropy/v0.1/data/mvp.sqlite3`
- schema 路径：`<project_root>/sql/schema.sql`
- 状态目录：`/opt/negative-entropy/v0.1/data/bridge_state`
- 日志路径：`/opt/negative-entropy/v0.1/logs/bridge.log`

如需本地覆盖，可使用环境变量：

- `NEGATIVE_ENTROPY_DB_PATH`
- `NEGATIVE_ENTROPY_BRIDGE_STATE_DIR`
- `NEGATIVE_ENTROPY_BRIDGE_LOG_PATH`

## 状态文件
每个 OpenClaw 会话键会对应一个独立 JSON 文件，保存在：

`data/bridge_state/<session_key>.json`

其中保存：
- `session_key`
- `flow_session`
- `db_session_id`
- `bundle_id`
- `latest_candidate_summary`
- `persisted_record_ids`

这允许桥接层在没有 HTTP 服务和没有额外数据库表的前提下，继续执行 `revise`、`commit`、`cancel`。

## 命令说明
### 1. start
用途：输出当前冻结版 FSYQ 模板，供 OpenClaw 直接回显给用户。

示例：
```bash
python scripts/openclaw_bridge.py start
```

### 2. parse
用途：创建桥接会话、生成候选、写入 `flow_sessions`、保存桥接状态。

示例：
```bash
python scripts/openclaw_bridge.py parse --session-key demo-a --raw-input "今晚九点左右推进了协议字段整理，有点疲劳"
```

执行步骤：
1. `FlowManager.start_session(raw_input)`
2. `FlowManager.parse_session(flow_session)`
3. `db.insert_flow_session(...)`
4. `db.update_candidate_payload(..., flow_state="awaiting_confirmation")`
5. 保存桥接状态 JSON

### 3. revise
用途：读取桥接状态，应用用户修订，并覆盖保存最新候选版本。

示例：
```bash
python scripts/openclaw_bridge.py revise --session-key demo-a --revision-text "2026-03-30 21:00 推进了协议字段整理与校验规则"
```

执行步骤：
1. 读取桥接状态
2. `FlowManager.apply_user_revision(...)`
3. `db.update_candidate_payload(...)`
4. 覆盖桥接状态中的 `flow_session` 与候选摘要

### 4. commit
用途：确认最新候选并正式写入 `records`。

示例：
```bash
python scripts/openclaw_bridge.py commit --session-key demo-a
```

执行步骤：
1. 读取桥接状态
2. `FlowManager.confirm_candidates(...)`
3. `db.update_flow_session_state(..., "committed")`
4. `db.insert_records(...)`
5. 保存 `record_ids`

### 5. cancel
用途：取消当前桥接会话，并把数据库中的会话状态改成 `cancelled`。

示例：
```bash
python scripts/openclaw_bridge.py cancel --session-key demo-a
```

执行步骤：
1. 读取桥接状态
2. `FlowManager.cancel_session(...)`
3. `db.update_flow_session_state(..., "cancelled")`
4. 覆盖桥接状态

## 预期输出
桥接命令的输出都保持简洁，适合直接给 OpenClaw 做文本回显。典型信息包括：
- `session_key`
- `flow_session_id`
- `db_session_id`
- `bundle_id`
- `flow_state`
- `main_type`
- `record_count`
- `record_ids`

## 最小验收标准
- `parse` 生成的 `candidate_payload` 通过 `validate_candidate_payload(...)`
- `revise` 后 `flow_sessions.candidate_payload` 被最新版本覆盖
- `commit` 后 `records.source` 固定为 `openclaw`
- `commit` 后 `related_to` 不残留 `temp_n`
- `cancel` 后数据库会话状态为 `cancelled`
- 整个桥接过程始终区分 `flow_session` 与 `db_session_id`
