"""Kimi (Moonshot) Provider 实现。"""

import json
from typing import Any, AsyncIterator

import httpx

from src.llm.base import LLMProvider, LLMResponse, Message, ToolCall


class KimiProvider(LLMProvider):
    """Kimi 2.6 (Moonshot) API 适配器。

    文档：https://platform.moonshot.cn/docs
    支持：
    - Chat Completions API
    - Function Calling (tools)
    - JSON Mode (通过 response_format)
    """

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._client = httpx.AsyncClient(
            base_url=self.api_base,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[ToolCall] | None,
        tool_choice: str,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        """构建 OpenAI 兼容的请求体。"""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    **({"tool_calls": m.tool_calls} if m.tool_calls else {}),
                    **({"tool_call_id": m.tool_call_id} if m.tool_call_id else {}),
                    **({"name": m.name} if m.name else {}),
                }
                for m in messages
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            payload["tool_choice"] = tool_choice
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolCall] | None = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        """发送聊天请求。"""
        payload = self._build_payload(messages, tools, tool_choice)
        resp = await self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        message = choice["message"]

        return LLMResponse(
            content=message.get("content"),
            tool_calls=message.get("tool_calls", []),
            usage=data.get("usage", {}),
            model=data.get("model", self.model),
        )

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[ToolCall] | None = None,
    ) -> AsyncIterator[str]:
        """流式输出（Kimi 支持 SSE 流）。"""
        payload = self._build_payload(messages, tools, "auto")
        payload["stream"] = True

        async with self._client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            yield delta["content"]
                    except (json.JSONDecodeError, KeyError):
                        continue

    async def parse_fsyq(self, raw_input: str) -> dict[str, Any]:
        """使用 Kimi JSON Mode 解析 FSYQ。"""
        system_prompt = """你是一个行为结构化解析器。请将用户的自然语言输入解析为 FSYQ 候选格式。

必须返回以下 JSON 结构：
{
  "main_type": "action|task|state|idea|review_note",
  "main_subject": "核心事件描述",
  "event_time": "ISO 8601 时间",
  "duration_minutes": 整数或 null,
  "primary_channel": "llm_engineering|body_management|teaching|exam_prep|mechanics_learning|system_building|daily_maintenance",
  "primary_value_tag": "high_value|low_value|neutral",
  "description": "原始描述",
  "state_description": "状态描述（如有）",
  "state_related": true|false
}

规则：
1. 如果用户提到疲劳、专注、压力等状态，state_related=true，并生成一条独立的 state 记录
2. event_time 如未明确，推断为最近合理时间
3. duration_minutes 如未提及，设为 null
4. 只返回 JSON，不要有 markdown 标记或其他文字"""

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=raw_input),
        ]
        resp = await self.chat(messages, json_mode=True)
        try:
            return json.loads(resp.content or "{}")
        except json.JSONDecodeError:
            return {"error": "parse_failed", "raw": resp.content}

    async def close(self) -> None:
        await self._client.aclose()
