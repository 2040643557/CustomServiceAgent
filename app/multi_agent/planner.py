"""简单的订单任务规划器：只负责生成和校验计划，不执行工具。"""

import json
from typing import Any

from app.config.settings import settings


ALLOWED_TOOLS = {
    "query_order",
    "query_logistics",
}


PLANNER_PROMPT = """
你是一个电商售后任务规划器。

你的职责是把用户的请求拆分成有顺序的工具调用步骤。
你只负责生成计划，不要实际执行工具，也不要编造查询结果。

允许使用的工具：

1. query_order(order_id: string)
   查询订单状态、商品、金额、发货信息。

2. query_logistics(order_id: string)
   根据订单号查询物流轨迹。

规划规则：
- 只使用上述两个工具，不要发明其他工具。
- 如果需要同时查询订单和物流，必须先查询订单，再查询物流。
- 用户明确要求查询物流时，才安排 query_logistics。
- 用户只询问订单状态时，只安排 query_order。
- 如果用户没有提供订单号，不得自行编造。
- 每个步骤都必须填写执行原因 reason。
- 只返回合法 JSON，不要添加 Markdown 代码块。

返回格式：
{
  "goal": "本次任务目标",
  "steps": [
    {
      "step": 1,
      "tool": "query_order",
      "arguments": {
        "order_id": "ORD-20240115-001"
      },
      "reason": "先查询订单状态"
    }
  ]
}
"""


class Planner:
    """调用 LLM 生成计划，并检查计划是否合法。"""

    def __init__(self, client: Any, model: str):
        self.client = client
        self.model = model

    def create_plan(self, user_request: str) -> dict:
        """根据用户请求生成计划。"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": PLANNER_PROMPT},
                {"role": "user", "content": user_request},
            ],
            temperature=0.0,
            max_tokens=512,
            extra_body=settings.thinking_extra_body(),
        )

        raw = response.choices[0].message.content or ""
        plan = self._parse_json(raw)

        self._validate_plan(plan)

        return plan

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """解析模型返回的 JSON。"""
        raw = raw.strip()

        # 兼容模型偶尔添加 Markdown 代码块的情况。
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0].strip()

        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Planner 返回的不是合法 JSON：{raw!r}"
            ) from exc

        if not isinstance(result, dict):
            raise ValueError("Planner 返回结果必须是 JSON 对象。")

        return result

    @staticmethod
    def _validate_plan(plan: dict) -> None:
        """检查工具白名单、参数和步骤顺序。"""
        goal = plan.get("goal")
        steps = plan.get("steps")

        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("计划缺少有效的 goal。")

        if not isinstance(steps, list) or not 1 <= len(steps) <= 3:
            raise ValueError("steps 必须是包含 1～3 步的列表。")

        tools_seen = []
        order_ids = []

        for expected_step, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                raise ValueError("每个步骤都必须是 JSON 对象。")

            if step.get("step") != expected_step:
                raise ValueError("步骤编号必须从 1 开始连续递增。")

            tool = step.get("tool")

            if tool not in ALLOWED_TOOLS:
                raise ValueError(f"不允许执行的工具：{tool!r}")

            arguments = step.get("arguments")

            if not isinstance(arguments, dict):
                raise ValueError(f"{tool} 的 arguments 必须是对象。")

            order_id = arguments.get("order_id")

            if not isinstance(order_id, str) or not order_id.strip():
                raise ValueError(f"{tool} 缺少有效的 order_id。")

            if not isinstance(step.get("reason"), str):
                raise ValueError(f"{tool} 缺少 reason。")

            tools_seen.append(tool)
            order_ids.append(order_id)

        if tools_seen[0] != "query_order":
            raise ValueError("计划必须先查询订单。")

        if tools_seen.count("query_order") > 1:
            raise ValueError("同一计划暂不允许重复查询订单。")

        if tools_seen.count("query_logistics") > 1:
            raise ValueError("同一计划暂不允许重复查询物流。")

        if "query_logistics" in tools_seen:
            if tools_seen.index("query_logistics") < tools_seen.index("query_order"):
                raise ValueError("必须先查询订单，再查询物流。")

        if len(set(order_ids)) > 1:
            raise ValueError("同一计划中的订单号必须一致。")