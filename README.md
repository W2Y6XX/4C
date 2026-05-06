# 负熵引擎 — 多智能体驱动的认知辅助决策系统

> 中国大学生计算机设计大赛（4C）参赛作品  
> 参赛编号：2026084355

面向高自驱个人的多智能体认知外骨骼系统，核心闭环：**记录 → 量化 → 复盘 → 决策**。

---

## 仓库结构

```
.
├── V0.1/                    # 早期 MVP 版本
│   ├── src/                 # 核心模块（bridge, validator, flow_manager）
│   ├── scripts/             # 演示脚本
│   ├── tests/               # 单元测试
│   ├── docs/                # 设计文档
│   ├── config/              # 配置模板
│   └── schemas/             # JSON Schema
│
├── v2.0/                    # 核心引擎架构（当前主版本）
│   ├── src/
│   │   ├── core/            # Orchestrator 调度核心
│   │   ├── llm/             # LLM Provider（Kimi / Mock）
│   │   ├── quant/           # QuantEngine 四象限量化
│   │   ├── decision/        # DecisionEngine 复盘/决策
│   │   ├── gateway/         # FeishuGateway 飞书网关
│   │   ├── storage/         # SQLite + SelfModel 快照
│   │   └── v01_compat/      # V0.1 数据兼容层
│   ├── scripts/             # 入口脚本
│   ├── config/              # 运行时配置
│   └── README.md            # v2.0 详细说明
│
└── 参赛材料/                 # 4C 参赛文档
    ├── 01-作品与答辩材料/
    │   ├── 2026084355-作品报告.docx
    │   ├── 2026084355-作品信息概要表.docx
    │   └── 2026084355-AI工具使用说明.docx
    └── 03-设计与开发文档/
        ├── 2026084355-架构与参赛方案.md
        ├── 2026084355-完整技术资产总册.docx
        └── 2026084355-系统性投产指南.docx
```

---

## 快速开始

```bash
# 进入 v2.0 主版本
cd v2.0

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
export KIMI_API_KEY="your-kimi-api-key"
export FEISHU_APP_ID="your-feishu-app-id"
export FEISHU_APP_SECRET="your-feishu-app-secret"

# 运行 CLI 演示
python scripts/demo.py
```

详见 [v2.0/README.md](v2.0/README.md)。

---

## 自研核心模块

| 模块 | 职责 | 位置 |
|------|------|------|
| NegEntropy.Orchestrator | 多 Agent 调度策略 | `v2.0/src/core/orchestrator.py` |
| NegEntropy.QuantEngine | 四象限熵指标计算 | `v2.0/src/quant/engine.py` |
| NegEntropy.DecisionEngine | 复盘与决策引擎 | `v2.0/src/decision/engine.py` |
| KimiProvider | Kimi 2.6 API 适配器 | `v2.0/src/llm/kimi_provider.py` |
| FeishuGateway | 飞书 Bot 网关 | `v2.0/src/gateway/feishu.py` |

---

## 许可证

MIT License

详见 [v2.0/THIRD_PARTY_NOTICES.md](v2.0/THIRD_PARTY_NOTICES.md)。
