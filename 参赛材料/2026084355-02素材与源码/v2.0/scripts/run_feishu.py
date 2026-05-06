"""启动飞书 Bot Gateway。

支持两种模式：
1. Webhook 模式：FastAPI 接收飞书事件推送（生产环境）
2. 轮询模式：定期拉取消息（开发/测试环境）

使用方式：
    python scripts/run_feishu.py --mode webhook
    python scripts/run_feishu.py --mode poll
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.gateway.feishu import FeishuGateway


async def run_webhook():
    """启动 FastAPI Webhook 服务器。"""
    try:
        from fastapi import FastAPI, Request
        import uvicorn
    except ImportError:
        print("错误：请安装 fastapi 和 uvicorn")
        print("  pip install fastapi uvicorn")
        return

    app = FastAPI(title="负熵引擎 - 飞书 Gateway")
    gateway = FeishuGateway()

    @app.post("/webhook/feishu")
    async def feishu_webhook(request: Request):
        """接收飞书事件推送。"""
        event = await request.json()
        # 处理不同类型的事件
        event_type = event.get("header", {}).get("event_type", "")

        if event_type == "im.message.receive_v1":
            await gateway.handle_message(event.get("event", {}))
        elif event_type == "card.action.trigger":
            await gateway.handle_card_callback(event.get("event", {}))

        return {"code": 0, "msg": "success"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    print("启动飞书 Webhook 服务器: http://0.0.0.0:8000")
    print("Webhook URL: http://your-domain/webhook/feishu")
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def run_poll():
    """轮询模式（简化版，仅用于开发测试）。"""
    print("轮询模式暂未实现")
    print("建议使用 Webhook 模式或 ngrok 进行本地开发测试")


async def main():
    parser = argparse.ArgumentParser(description="负熵引擎飞书 Gateway")
    parser.add_argument(
        "--mode",
        choices=["webhook", "poll"],
        default="webhook",
        help="运行模式",
    )
    args = parser.parse_args()

    if args.mode == "webhook":
        await run_webhook()
    else:
        await run_poll()


if __name__ == "__main__":
    asyncio.run(main())
