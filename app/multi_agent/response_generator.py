"""根据任务执行结果生成最终回答。"""

import json
from typing import Any

from app.config.settings import settings


class ResponseGenerator:
    """将工具执行结果整理成用户容易理解的回答。"""

    def __init__(self, client: Any, model: str):
        self.client = client
        self.model = model

    def generate(
        self,
        user_request: str,
        execution_result: dict,
        memory_context: str = "",
    ) -> str:
        """根据原始需求与实际执行结果生成回答。"""

        result_json = json.dumps(
            execution_result,
            ensure_ascii=False,
            indent=2,
        )

        system_content = (
            "你是电商客服助手，负责总结任务执行结果。"
            "必须严格依据提供的实际执行结果回答，"
            "不能编造订单状态、物流信息或工具执行结果。"
            "如果某一步被跳过，要向用户解释原因。"
            "如果执行失败，要明确说明失败，不得假装成功。"
            "使用简洁、自然的中文回答。"
        )

        user_content = (
            f"用户原始需求：\n{user_request}\n\n"
            f"实际执行结果（JSON）：\n{result_json}\n\n"
            "请根据实际结果向用户作答。"
        )

        if memory_context:
            user_content = (
                f"用户记忆与历史上下文：\n{memory_context}\n\n"
                + user_content
            )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=500,
            extra_body=settings.thinking_extra_body(),
        )

        answer = response.choices[0].message.content

        if not answer or not answer.strip():
            raise RuntimeError("模型没有返回有效的最终回答。")

        return answer.strip()