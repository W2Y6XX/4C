# 负熵引擎 MVP v0.1 构建计划

## 模块 1：协议与配置固化
**目标：** 把冻结协议沉淀为可直接引用的规则文档与配置文件，先锁住实现边界。  
**产物：**
- `docs/protocol_rules.md`
- `config/enums.yaml`
- `config/fsyq_template.txt`

**完成标准：**
- `protocol_rules.md` 覆盖首轮冻结协议的核心口径。
- `enums.yaml` 只保留冻结枚举，不混入业务规则。
- FSYQ 模板原文完整落盘，不增删改字段或选项。

## 模块 2：候选结构与 SQLite 表结构
**目标：** 定义候选交换格式与最小持久化结构，保证候选和入库口径一致。  
**产物：**
- `schemas/candidate_schema.json`
- `sql/schema.sql`

**完成标准：**
- 候选 payload 顶层只包含 `schema_version`、`bundle_id`、`records`。
- 每条候选记录仅包含冻结字段，且 `parse_note` 恒定存在。
- `records` 与 `flow_sessions` 表字段严格贴合协议，不新增额外状态或辅助字段。
- SQL 对关键枚举、主标签非空、`value/unit` 成对、`task.status` 范围等基础约束有明确表达。

## 模块 3：校验器
**目标：** 在 Python 层尽早拦截非法候选记录和非法 payload。  
**产物：**
- `src/validator.py`

**完成标准：**
- 提供记录级与 payload 级校验入口。
- 覆盖 `type`、`status`、`parse_note`、主标签、`value/unit`、`related_to`、主候选唯一性等规则。
- 对 `subject=待定`、临时时间/时长、主标签占位说明等场景给出明确错误信息。

## 模块 4：流程管理器
**目标：** 提供从原始输入到最新候选 payload 的最小流程编排。  
**产物：**
- `src/flow_manager.py`

**完成标准：**
- 能启动 session、解析输入、应用修订、确认提交、取消会话。
- `flow_state` 只使用六态：`awaiting_input`、`parsing`、`awaiting_confirmation`、`revising`、`committed`、`cancelled`。
- 候选 `type` 基于输入做保守判断，不默认固定为 `action`。
- 状态描述会拆成独立 `type=state` 记录，并通过 `related_to` 指向主候选。
- `_build_candidate_payload()` 生成后即校验，非法 payload 直接抛错。

## 模块 5：数据库适配层
**目标：** 用标准库 `sqlite3` 提供最小持久化接口，不引入 ORM。  
**产物：**
- `src/db.py`

**完成标准：**
- 能初始化 schema、插入会话、更新 `flow_state`、覆盖更新 `candidate_payload`。
- 能将确认后的记录写入 `records` 表，并按 `bundle_id` 查询。
- `record_id`、`bundle_id`、`session_id` 基于数据库当前最大值加 1 生成。
- `related_to=temp_n` 在入库时必须映射为正式 `rec_n`；若无法映射，立即报错。

## 模块 6：最小测试骨架
**目标：** 用 `unittest` 为首轮闭环提供基础回归保护。  
**产物：**
- `tests/test_validator.py`
- `tests/test_flow_manager.py`
- `tests/test_db.py`

**完成标准：**
- `python -m unittest discover -s tests -v` 可运行。
- 测试覆盖校验器的关键规则违规场景。
- 测试覆盖流程层的候选生成、状态拆分、修订覆盖和生成即校验。
- 测试覆盖数据库层的 ID 生成、`candidate_payload` 覆盖保存、`related_to` 映射和 bundle 查询。
