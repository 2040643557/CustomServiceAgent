"""意图路由器：分析用户消息，决定分发给哪个子 Agent。"""

from typing import List, Optional
import logging
from openai import OpenAI

from app.config.settings import settings
from app.prompts.agents import ROUTER_PROMPT

VALID_AGENTS = {"presale", "postsale", "complaint"}
logger = logging.getLogger(__name__)


def parse_agent_label(raw: str | None) -> str | None:
    """只接受合法的 Agent 标签，避免错误内容被误识别。"""
    label = (raw or "").strip().lower()
    label = label.strip("`'\" \t\r\n.!。")

    if label in VALID_AGENTS:
        return label

    return None
DEFAULT_AGENT = "postsale"


class Router:
    """使用 LLM 对用户意图分类，路由到对应的子 Agent。"""

    def __init__(self, client: OpenAI, model: str):
        self.client = client
        self.model = model

    def route(self, user_input: str, history: Optional[List[dict]] = None) -> str:
        """返回子 Agent 标识: "presale" / "postsale" / "complaint"。"""
        recent_context = ""
        if history:
            recent = [
                m for m in history[-4:]
                if m.get("role") in ("user", "assistant")
            ]
            if recent:
                lines = []
                for m in recent:
                    role = "用户" if m["role"] == "user" else "客服"
                    content = m.get("content", "")
                    if content and len(content) < 200:
                        lines.append(f"{role}: {content}")
                if lines:
                    recent_context = "\n最近对话：\n" + "\n".join(lines) + "\n"

        prompt = ROUTER_PROMPT.format(user_input=user_input)
        if recent_context:
            prompt = recent_context + "\n" + prompt

        for attempt in range(2):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                temperature=0.0,
                max_tokens=32,
                extra_body=settings.thinking_extra_body(),
            )

            choice = response.choices[0]

            # print(f"\n[Router Debug] 原始内容：{choice.message.content!r}")
            # print(f"[Router Debug] 结束原因：{choice.finish_reason}")
            #
            # reasoning = getattr(choice.message, "reasoning_content", None)
            # if reasoning:
            #     print(f"[Router Debug] 推理内容：{reasoning[:200]!r}")

            raw = choice.message.content or ""

            agent_key = parse_agent_label(raw)

            if agent_key is not None:
                return agent_key

            logger.warning(
                "Router 输出无效：raw=%r, finish_reason=%s, attempt=%s",
                raw,
                choice.finish_reason,
                attempt + 1,
            )

            if attempt == 0:
                prompt += (
                    "\n请严格只输出一个标签："
                    "presale、postsale 或 complaint。"
                    "不要输出解释或其他文字。"
                )

        logger.error("Router 重试后仍无法识别输出，使用默认路由。")
        return DEFAULT_AGENT


