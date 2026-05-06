# 素材与源码

## 源码结构

本目录包含负熵引擎的核心源代码，分为两个版本：

### V0.1 — 早期 MVP 版本

包含基础功能模块：
- `src/db.py` — 数据库管理
- `src/flow_manager.py` — 流程管理器
- `src/validator.py` — 数据校验器
- `scripts/openclaw_bridge.py` — OpenClaw 桥接脚本
- `scripts/demo_mvp.py` — MVP 演示
- `tests/` — 单元测试

### v2.0 — 核心引擎架构（当前主版本）

采用模块化分层设计：
- `src/core/orchestrator.py` — 多 Agent 调度核心
- `src/llm/` — LLM Provider（Kimi 2.6 / Mock）
- `src/quant/engine.py` — 四象限熵指标量化引擎
- `src/decision/engine.py` — 复盘与决策引擎
- `src/gateway/feishu.py` — 飞书 Bot 网关
- `src/storage/` — SQLite + SelfModel 数据层
- `src/v01_compat/` — V0.1 数据兼容层

## 快速运行

```bash
cd v2.0
pip install -r requirements.txt
python scripts/demo.py
```

详见 [v2.0/README.md](v2.0/README.md)。

---

> 参赛编号：2026084355  
> 作品名称：负熵引擎-多智能体驱动的认知辅助决策系统
