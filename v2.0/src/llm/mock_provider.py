"""Mock LLM Provider —— 用于无 API Key 的联调测试。

模拟 Kimi 的行为，返回预定义的解析结果，不调用真实 API。
"""

import json
from datetime import datetime
from typing import Any

from src.llm.base import LLMProvider, LLMResponse, Message


class MockProvider(LLMProvider):
    """模拟 LLM Provider。

    根据输入文本中的关键词返回预解析的 FSYQ 结果。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        # Mock 不需要真实配置
        super().__init__(config or {})
        self.model = "mock"

    async def chat(
        self,
        messages: list[Message],
        tools: Any = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        """模拟聊天响应。"""
        # 提取用户输入
        user_content = ""
        for m in messages:
            if m.role == "user":
                user_content = m.content or ""
                break

        # 模拟解析
        result = self._mock_parse(user_content)

        return LLMResponse(
            content=json.dumps(result, ensure_ascii=False),
            usage={"prompt_tokens": 100, "completion_tokens": 50},
            model="mock",
        )

    async def chat_stream(self, messages: list[Message], tools: Any = None) -> Any:
        """流式输出（Mock 不支持）。"""
        return
        yield ""

    def _mock_parse(self, text: str) -> dict[str, Any]:
        """基于关键词的模拟解析。"""
        text = text.lower()

        # 默认结果
        result = {
            "main_type": "action",
            "main_subject": text[:50],
            "event_time": datetime.utcnow().isoformat(),
            "duration_minutes": None,
            "primary_channel": "daily_maintenance",
            "primary_value_tag": "neutral",
            "description": text,
            "state_description": None,
            "state_related": False,
        }

        # 关键词匹配
        if "疲劳" in text or "累" in text:
            result["state_related"] = True
            result["state_description"] = "疲劳"

        if "推进" in text or "完成" in text or "做了" in text:
            result["main_type"] = "action"
            result["primary_value_tag"] = "high_value"
        elif "明天" in text or "计划" in text:
            result["main_type"] = "task"
        elif "想法" in text or "觉得" in text:
            result["main_type"] = "idea"

        if "rag" in text or "llm" in text or "ai" in text:
            result["primary_channel"] = "llm_engineering"
        elif "力学" in text or "学习" in text or "题目" in text:
            result["primary_channel"] = "mechanics_learning"
        elif "教学" in text or "课" in text:
            result["primary_channel"] = "teaching"
        elif "身体" in text or "锻炼" in text or "睡眠" in text:
            result["primary_channel"] = "body_management"
        elif "系统" in text or "协议" in text:
            result["primary_channel"] = "system_building"

        if "45" in text or "30" in text or "一小时" in text:
            # 提取数字作为分钟
            import re

            match = re.search(r"(\d+)", text)
            if match:
                val = int(match.group(1))
                if val < 10:
                    result["duration_minutes"] = val * 60  # 小时转分钟
                else:
                    result["duration_minutes"] = val

        return result
