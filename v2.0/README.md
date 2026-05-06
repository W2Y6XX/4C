# 负熵引擎 v2.0

面向高自驱个人的多智能体认知外骨骼系统，核心闭环：记录 → 量化 → 复盘 → 决策。

## 架构概览

```
输入层（飞书 Bot / CLI / 边缘设备）
    │
    ▼
Gateway（FeishuGateway）
    │
    ▼
Orchestrator（自研调度核心）
    │
    ├──→ KimiProvider（Kimi 2.6）
    ├──→ QuantEngine（四象限量化）
    └──→ DecisionEngine（复盘/决策）
    │
    ▼
Storage（SQLite + SelfModel 快照 + 决策审计）
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
export KIMI_API_KEY="your-kimi-api-key"
export FEISHU_APP_ID="your-feishu-app-id"
export FEISHU_APP_SECRET="your-feishu-app-secret"
```

或创建 `.env` 文件。

### 3. 初始化数据库

```bash
python -c "from src.storage.db import DatabaseManager; DatabaseManager().init_db()"
```

### 4. 运行 CLI 演示

```bash
python scripts/demo.py
```

### 5. 启动飞书 Gateway

```bash
python scripts/run_feishu.py
```

## 项目结构

```
v2.0/
├── src/
│   ├── core/          # 配置 + Orchestrator
│   ├── llm/           # LLMProvider + KimiProvider
│   ├── quant/         # QuantEngine（四象限量化）
│   ├── decision/      # DecisionEngine（复盘/决策）
│   ├── gateway/       # FeishuGateway
│   ├── storage/       # SQLAlchemy 模型 + DB 管理
│   └── v01_compat/    # V0.1 数据兼容层
├── config/
│   └── settings.yaml  # 配置文件
├── scripts/           # 入口脚本
├── tests/             # 测试
└── docs/              # 文档
```

## 自研核心模块

1. **NegEntropy.Orchestrator** —— 多 Agent 调度策略
2. **NegEntropy.QuantEngine** —— 四象限熵指标计算
3. **NegEntropy.DecisionEngine** —— 复盘与决策引擎
4. **KimiProvider** —— Kimi 2.6 API 适配器

## 许可证

MIT License —— 详见 LICENSE 文件。

## 第三方声明

详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
