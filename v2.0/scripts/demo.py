"""v2.0 CLI 演示脚本。

演示流程：
1. 初始化数据库
2. 模拟用户输入
3. 调用 Orchestrator 解析
4. 显示候选结果
5. 模拟确认/修订/取消
"""

import asyncio
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.orchestrator import Orchestrator
from src.decision.engine import DecisionEngine
from src.llm.mock_provider import MockProvider
from src.quant.engine import QuantEngine
from src.storage.db import DatabaseManager
from src.v01_compat.adapter import V01Adapter


async def demo_basic_flow():
    """演示基础流程：输入 → 解析 → 确认。"""
    print("=" * 60)
    print("负熵引擎 v2.0 - CLI 演示")
    print("=" * 60)

    # 1. 初始化数据库
    print("\n[1/5] 初始化数据库...")
    db = DatabaseManager()
    db.init_db()
    print("✅ 数据库已初始化")

    # 2. 创建 Orchestrator（使用 MockProvider 避免依赖真实 API Key）
    print("\n[2/5] 创建 Orchestrator...")
    orch = Orchestrator(user_id="demo_user", db=db)
    orch.llm = MockProvider({})  # 注入 MockProvider
    print("✅ Orchestrator 已创建（使用 MockProvider）")

    # 3. 模拟多条用户输入（产生足够记录供量化分析）
    print("\n[3/5] 模拟用户输入...")
    test_inputs = [
        "今晚九点左右推进了 RAG 方案整理，有点疲劳",
        "早上锻炼了 45 分钟，做了力量训练",
        "下午学习力学题目 2 小时，专注度不错",
        "明天准备整理教学反馈",
        "今天刷了很多资料但没产出",
        "晚上和团队讨论了项目计划",
        "睡前反思：今天效率一般，需要调整",
    ]
    for text in test_inputs:
        print(f"\n用户输入: {text}")
        plan = await orch.start_session(raw_input=text, source="cli")
        commit_plan = await orch.commit_session(plan.session_id)
        print(f"  ✅ {commit_plan.message_to_user}")

    # 5. 量化分析
    print("\n[5/5] 量化分析...")
    quant = QuantEngine(db=db)
    metrics = quant.compute(user_id="demo_user", use_cache=False)
    print(f"\n四象限指标:")
    print(metrics.summary)

    # 6. 决策建议
    print("\n[6/6] 生成决策建议...")
    decision = DecisionEngine(db=db, llm=orch.llm)
    suggestion = await decision.generate_suggestions("demo_user", metrics)
    print(f"\n{suggestion.content}")

    # 清理
    await orch.close()
    quant.close()
    await decision.close()

    print("\n" + "=" * 60)
    print("演示完成")
    print("=" * 60)


async def demo_v01_compat():
    """演示 V0.1 数据兼容。"""
    print("\n" + "=" * 60)
    print("V0.1 数据兼容演示")
    print("=" * 60)

    adapter = V01Adapter()

    # 检查 V0.1 数据库是否存在
    if not adapter.db_path.exists():
        print(f"⚠️ V0.1 数据库未找到: {adapter.db_path}")
        print("跳过兼容演示")
        return

    stats = adapter.get_stats()
    print(f"\nV0.1 数据统计:")
    print(f"  总记录数: {stats['total_records']}")
    print(f"  总会话数: {stats['total_sessions']}")
    print(f"  类型分布: {stats['type_distribution']}")
    print(f"  通道分布: {stats['channel_distribution']}")

    adapter.close()


async def main():
    await demo_basic_flow()
    await demo_v01_compat()


if __name__ == "__main__":
    asyncio.run(main())
