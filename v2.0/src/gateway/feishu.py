"""飞书（Feishu/Lark）Gateway 实现。

功能：
1. 接收飞书 Bot @消息和私聊
2. 调用 Orchestrator 处理输入
3. 发送飞书卡片（候选确认 / 周报 / 建议）
4. 处理按钮回调（确认 / 修改 / 取消）

技术方案：
- 使用飞书开放平台 Webhook + Event Subscription
- 如需实时推送，使用 FastAPI 接收飞书事件回调
- 如需简化部署，使用轮询模式（开发阶段）

文档：https://open.feishu.cn/document/home/index
"""

import asyncio
import json
from typing import Any

import httpx

from src.core.config import get_config
from src.core.orchestrator import Orchestrator


class FeishuBot:
    """飞书 Bot HTTP 客户端。

    封装发送消息、发送卡片的 API。
    """

    def __init__(self):
        self.config = get_config()
        self.app_id = self.config.get("feishu.app_id", "")
        self.app_secret = self.config.get("feishu.app_secret", "")
        self.webhook_url = self.config.get("feishu.webhook_url", "")
        self._tenant_access_token: str | None = None
        self._token_expires: float = 0
        self._client = httpx.AsyncClient(timeout=30)

    async def _ensure_token(self) -> None:
        """获取 tenant_access_token。"""
        if self._tenant_access_token and asyncio.get_event_loop().time() < self._token_expires:
            return

        resp = await self._client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        resp.raise_for_status()
        data = resp.json()
        self._tenant_access_token = data["tenant_access_token"]
        self._token_expires = asyncio.get_event_loop().time() + data["expire"] - 60

    async def send_text(self, chat_id: str, text: str) -> dict[str, Any]:
        """发送纯文本消息。"""
        await self._ensure_token()
        resp = await self._client.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            headers={"Authorization": f"Bearer {self._tenant_access_token}"},
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def send_interactive_card(
        self,
        chat_id: str,
        title: str,
        elements: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """发送交互式卡片。

        elements 示例：
        [
            {"tag": "div", "text": {"tag": "plain_text", "content": "内容"}},
            {"tag": "action", "actions": [
                {"tag": "button", "text": {"tag": "plain_text", "content": "确认"},
                 "type": "primary", "value": {"action": "commit", "session_id": "xxx"}}
            ]}
        ]
        """
        await self._ensure_token()
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue",
            },
            "elements": elements,
        }
        resp = await self._client.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            headers={"Authorization": f"Bearer {self._tenant_access_token}"},
            json={
                "receive_id": chat_id,
                "msg_type": "interactive",
                "content": json.dumps(card),
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def reply_to_message(
        self, message_id: str, text: str
    ) -> dict[str, Any]:
        """回复特定消息。"""
        await self._ensure_token()
        resp = await self._client.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
            headers={"Authorization": f"Bearer {self._tenant_access_token}"},
            json={
                "content": json.dumps({"text": text}),
                "msg_type": "text",
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        await self._client.aclose()


class FeishuGateway:
    """飞书 Gateway —— 连接飞书 Bot 与 Orchestrator。

    支持两种模式：
    1. Webhook 模式：FastAPI 接收飞书事件推送（生产环境）
    2. 轮询模式：定期拉取消息（开发/测试环境）
    """

    def __init__(self):
        self.config = get_config()
        self.bot = FeishuBot()
        self._orchestrators: dict[str, Orchestrator] = {}

    def _get_orchestrator(self, user_id: str) -> Orchestrator:
        """获取或创建用户的 Orchestrator。"""
        if user_id not in self._orchestrators:
            self._orchestrators[user_id] = Orchestrator(user_id=user_id)
        return self._orchestrators[user_id]

    async def handle_message(self, event: dict[str, Any]) -> None:
        """处理飞书消息事件。

        event 格式（飞书事件推送）：
        {
            "sender": {"sender_id": {"open_id": "ou_xxx"}},
            "message": {
                "message_id": "om_xxx",
                "chat_id": "oc_xxx",
                "message_type": "text",
                "content": {"text": "用户输入内容"}
            }
        }
        """
        sender = event.get("sender", {})
        user_id = sender.get("sender_id", {}).get("open_id", "unknown")
        message = event.get("message", {})
        chat_id = message.get("chat_id", "")
        message_id = message.get("message_id", "")
        content = message.get("content", {})
        text = content.get("text", "") if isinstance(content, dict) else ""

        # 过滤非文本消息
        if not text:
            return

        # 过滤 @Bot 前缀（如 "@负熵引擎 今晚推进了..."）
        text = self._strip_mention(text)

        orchestrator = self._get_orchestrator(user_id)

        # 启动会话
        plan = await orchestrator.start_session(raw_input=text, source="feishu")

        # 发送卡片
        await self._send_candidate_card(
            chat_id=chat_id,
            session_id=plan.session_id,
            candidate=plan.candidate,
            records=plan.records_to_insert,
        )

    async def handle_card_callback(self, event: dict[str, Any]) -> None:
        """处理卡片按钮回调。

        event 格式：
        {
            "open_id": "ou_xxx",
            "token": "xxx",
            "action": {
                "value": {"action": "commit", "session_id": "ses_xxx"}
            }
        }
        """
        user_id = event.get("open_id", "")
        action_value = event.get("action", {}).get("value", {})
        action_type = action_value.get("action", "")
        session_id = action_value.get("session_id", "")

        if not session_id:
            return

        orchestrator = self._get_orchestrator(user_id)

        if action_type == "commit":
            plan = await orchestrator.commit_session(session_id)
            # 发送确认消息
            chat_id = self._find_chat_id_for_user(user_id)
            if chat_id:
                await self.bot.send_text(chat_id, plan.message_to_user)

        elif action_type == "cancel":
            plan = await orchestrator.cancel_session(session_id)
            chat_id = self._find_chat_id_for_user(user_id)
            if chat_id:
                await self.bot.send_text(chat_id, plan.message_to_user)

        elif action_type == "revise":
            # 用户点击修改，发送提示让用户输入修改内容
            chat_id = self._find_chat_id_for_user(user_id)
            if chat_id:
                await self.bot.send_text(
                    chat_id,
                    "请直接回复修改后的内容，格式：\n"
                    "修改: [新的事件描述]\n"
                    "例如：修改: 今晚九点半推进了 RAG 方案整理"
                )

    async def handle_revision_text(
        self, user_id: str, chat_id: str, text: str
    ) -> None:
        """处理用户的修改文本。

        用户回复格式："修改: 新的描述"
        """
        if not text.startswith("修改:"):
            return

        new_text = text[3:].strip()
        orchestrator = self._get_orchestrator(user_id)

        # 找到用户最近的 awaiting_confirmation 会话
        # 简化处理：使用用户最新的会话（实际应该通过状态管理）
        # 这里简化：重新解析为新的候选
        plan = await orchestrator.start_session(raw_input=new_text, source="feishu")

        await self._send_candidate_card(
            chat_id=chat_id,
            session_id=plan.session_id,
            candidate=plan.candidate,
            records=plan.records_to_insert,
        )

    def _strip_mention(self, text: str) -> str:
        """去除 @Bot 的前缀。"""
        # 飞书 @ 格式: "<at id=\"ou_xxx\">@BotName</at> 实际内容"
        import re

        text = re.sub(r"<at[^>]*>[^<]*</at>", "", text)
        return text.strip()

    async def _send_candidate_card(
        self,
        chat_id: str,
        session_id: str,
        candidate: dict[str, Any],
        records: list[dict[str, Any]],
    ) -> None:
        """发送候选确认卡片。"""
        elements: list[dict[str, Any]] = []

        # 记录列表
        for rec in records:
            emoji = {
                "task": "📌",
                "action": "✅",
                "state": "😊",
                "idea": "💡",
                "review_note": "📝",
            }.get(rec.get("record_type"), "•")
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"{emoji} **{rec['record_type']}**: {rec['content']}\n"
                    f"通道: {rec.get('primary_channel', '')} | 价值: {rec.get('primary_value_tag', '')}",
                },
            })

        # 按钮
        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "✅ 确认"},
                    "type": "primary",
                    "value": {"action": "commit", "session_id": session_id},
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "✏️ 修改"},
                    "type": "default",
                    "value": {"action": "revise", "session_id": session_id},
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "❌ 取消"},
                    "type": "danger",
                    "value": {"action": "cancel", "session_id": session_id},
                },
            ],
        })

        await self.bot.send_interactive_card(
            chat_id=chat_id,
            title="📋 记录确认",
            elements=elements,
        )

    def _find_chat_id_for_user(self, user_id: str) -> str | None:
        """根据 user_id 查找 chat_id（简化版，实际需要维护映射）。"""
        # TODO: 维护 user_id -> chat_id 的映射
        return None

    async def close(self) -> None:
        await self.bot.close()
        for orch in self._orchestrators.values():
            await orch.close()
