# 第三方开源组件声明

> 本文件随参赛作品一同提交，列明所有使用的第三方开源代码、库、框架及其许可证信息。

## 一、运行时依赖（Python 包）

| 包名 | 版本 | 许可证 | 用途 |
|------|------|--------|------|
| pydantic | >=2.0.0 | MIT | 数据模型校验 |
| PyYAML | >=6.0 | MIT | YAML 配置解析 |
| python-dotenv | >=1.0.0 | BSD-3-Clause | 环境变量管理 |
| httpx | >=0.27.0 | BSD-3-Clause | 异步 HTTP 客户端 |
| SQLAlchemy | >=2.0.0 | MIT | ORM 与数据库操作 |
| alembic | >=1.13.0 | MIT | 数据库迁移 |
| fastapi | >=0.110.0 | MIT | Web 框架（Gateway） |
| uvicorn | >=0.27.0 | BSD-3-Clause | ASGI 服务器 |
| lark-oapi | >=1.0.0 | MIT | 飞书开放平台 SDK |
| APScheduler | >=3.10.0 | MIT | 定时任务调度 |
| pytest | >=8.0.0 | MIT | 测试框架 |
| pytest-asyncio | >=0.23.0 | Apache-2.0 | 异步测试支持 |

## 二、参考/借鉴的开源项目

| 项目 | URL | License | 使用方式 | 修改比例 |
|------|-----|---------|----------|----------|
| NousResearch/hermes-agent | https://github.com/NousResearch/hermes-agent | MIT | 参考其 Gateway 架构设计，复用飞书 Gateway 概念 | 未直接引用代码，仅架构参考 |
| alchaincyf/nuwa-skill | https://github.com/alchaincyf/nuwa-skill | MIT | 参考 SKILL.md 的决策启发式结构，自研解析器 | 自研解析器（100% 新写） |
| msitarzewski/agency-agents | https://github.com/msitarzewski/agency-agents | MIT | 参考 Agent 人格 frontmatter 格式，自研解析器 | 自研解析器（100% 新写） |

## 三、自研核心模块声明

以下模块为本团队独立设计与实现，不依赖上述第三方项目的代码：

1. `src/core/orchestrator.py` —— NegEntropy.Orchestrator 多 Agent 调度核心
2. `src/quant/engine.py` —— NegEntropy.QuantEngine 四象限量化引擎
3. `src/decision/engine.py` —— NegEntropy.DecisionEngine 复盘与决策引擎
4. `src/llm/kimi_provider.py` —— Kimi 2.6 API 适配器（基于 httpx 独立实现）
5. `src/gateway/feishu.py` —— 飞书 Bot Gateway（基于飞书开放 API 独立实现）

## 四、许可证兼容性说明

本项目使用的所有第三方依赖均为 MIT / BSD / Apache-2.0 许可证，与 MIT 许可证完全兼容，不存在 GPL/AGPL 传染风险。
