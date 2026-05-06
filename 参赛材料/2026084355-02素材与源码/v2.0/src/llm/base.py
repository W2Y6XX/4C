"""LLM Provider 抽象基类。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class Message:
    """标准消息格式，兼容 OpenAI 风格。"""

    role: str  # system / user / assistant / tool
    content: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None  # for tool role


@dataclass
class ToolCall:
    """工具调用定义。"""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass
class LLMResponse:
    """LLM 统一响应格式。"""

    content: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""


class LLMProvider(ABC):
    """LLM Provider 抽象接口。

    所有具体 LLM 后端（Kimi/GLM4/DeepSeek）必须实现此接口。
    设计目标：
    1. 统一不同国产 LLM 的调用差异
    2. 支持 Function Calling（工具调用）
    3. 支持流式输出（预留）
    4. 暴露 Token 用量统计
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.model = config.get("model", "")
        self.api_key = config.get("api_key", "")
        self.api_base = config.get("api_base", "")
        self.temperature = config.get("temperature", 0.3)
        self.max_tokens = config.get("max_tokens", 4096)
        self.timeout = config.get("timeout", 30)

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolCall] | None = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        """发送聊天请求，返回结构化响应。"""
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[ToolCall] | None = None,
    ) -> AsyncIterator[str]:
        """流式输出（预留接口）。"""
        ...  # type: ignore[return]
        yield ""

    async def parse_fsyq(self, raw_input: str) -> dict[str, Any]:
        """将自然语言解析为 FSYQ 候选结构。

        默认实现：通过标准 prompt + JSON mode 调用。
        子类可覆盖以利用模型原生 function calling。
        """
        system_prompt = """你是一个行为结构化解析器。请将用户的自然语言输入解析为 FSYQ 格式。

FSYQ 格式要求：
- main_type: task/action/state/idea/review_note 之一
- main_subject: 行为/事件的核心对象
- event_time: ISO 8601 格式的时间，如不确定请推断
- duration_minutes: 时长（分钟），如提及
- primary_channel: llm_engineering/body_management/teaching/exam_prep/mechanics_learning/system_building/daily_maintenance
- primary_value_tag: high_value/low_value/neutral
- description: 用户原始描述
- state_description: 如用户提到状态（疲劳、专注等），填写此处

必须返回合法 JSON，不要有任何 markdown 标记。"""

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=raw_input),
        ]
        resp = await self.chat(messages)
        import json

        try:
            return json.loads(resp.content or "{}")
        except json.JSONDecodeError:
            return {"error": "parse_failed", "raw": resp.content}

    async def generate_report(
        self,
        records_summary: str,
        quadrant_metrics: dict[str, Any],
        report_type: str = "weekly",
    ) -> str:
        """基于记录摘要和四象限指标生成周报/月报。"""
        system_prompt = f"""你是一个个人行为复盘助手。请基于以下数据生成{report_type}报告。

要求：
1. 分析各主通道的时间分布和价值分布
2. 识别高价值行为和低价值消耗
3. 关联状态与产出（如疲劳是否影响了高价值行为）
4. 给出下周/下月的具体建议
5. 使用 Markdown 格式，简洁有力"""

        user_content = f"""记录摘要：
{records_summary}

四象限指标：
{quadrant_metrics}
"""
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_content),
        ]
        resp = await self.chat(messages)
        return resp.content or ""
