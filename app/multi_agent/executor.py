"""任务计划执行器：执行工具，并根据实际结果控制后续步骤。"""

import json
from typing import Any, Callable

from app.agent.tools.registry import execute_tool


ALLOWED_TOOLS = {
    "query_order",
    "query_logistics",
}


class PlanExecutor:
    """执行已生成的订单查询计划。"""

    def __init__(
        self,
        tool_runner: Callable[[str, dict], str] = execute_tool,
    ):
        # 允许注入工具执行函数，便于以后编写单元测试。
        self.tool_runner = tool_runner

    def execute(self, plan: dict[str, Any]) -> dict[str, Any]:
        steps = plan.get("steps")

        if not isinstance(steps, list) or not steps:
            raise ValueError("计划必须包含至少一个步骤。")

        if steps[0].get("tool") != "query_order":
            raise ValueError("必须先查询订单，再决定后续操作。")

        order_result = None
        execution_results = []

        for step in steps:
            tool_name = step.get("tool")
            arguments = step.get("arguments", {})

            # 1. 检查工具是否在白名单内。
            if tool_name not in ALLOWED_TOOLS:
                raise ValueError(f"不允许执行工具：{tool_name}")

            if not isinstance(arguments, dict):
                raise ValueError("工具参数必须是字典。")

            order_id = arguments.get("order_id")
            if not isinstance(order_id, str) or not order_id.strip():
                raise ValueError(f"{tool_name} 缺少有效订单号。")

            # 2. 物流查询必须以成功的订单查询为前提。
            if tool_name == "query_logistics":
                if not order_result or not order_result.get("success"):
                    execution_results.append({
                        "tool": tool_name,
                        "status": "skipped",
                        "reason": "订单查询未成功，跳过物流查询。",
                    })
                    continue

                order = order_result.get("order") or {}

                if order.get("order_id") != order_id:
                    raise ValueError("物流查询订单号与已查询订单不一致。")

                if not order.get("tracking_number"):
                    execution_results.append({
                        "tool": tool_name,
                        "status": "skipped",
                        "reason": "订单尚未发货，没有物流单号。",
                    })
                    continue

            # 3. 执行实际工具。
            raw_result = self.tool_runner(tool_name, arguments)

            try:
                result = (
                    json.loads(raw_result)
                    if isinstance(raw_result, str)
                    else raw_result
                )
            except (json.JSONDecodeError, TypeError):
                result = {
                    "success": False,
                    "error": "工具返回的结果不是有效 JSON。",
                }

            if not isinstance(result, dict):
                result = {
                    "success": False,
                    "error": "工具返回格式错误。",
                }

            status = (
                "success"
                if result.get("success") is True
                else "failed"
            )

            execution_results.append({
                "tool": tool_name,
                "status": status,
                "result": result,
            })

            # 4. 保存订单查询结果，供下一步判断。
            if tool_name == "query_order":
                order_result = result

            # 5. 订单查询失败，不再执行后续业务步骤。
            if status == "failed":
                break

        has_failures = any(
            item["status"] == "failed"
            for item in execution_results
        )

        return {
            "goal": plan.get("goal", ""),
            "success": not has_failures,
            "steps": execution_results,
        }