import json

import pytest

from app.multi_agent.executor import PlanExecutor
from app.multi_agent.planner import Planner


ORDER_ID = "ORD-20240115-001"


def make_plan(*tool_names):
    """生成测试用计划。"""
    return {
        "goal": "查询订单和物流",
        "steps": [
            {
                "step": index,
                "tool": tool_name,
                "arguments": {"order_id": ORDER_ID},
                "reason": f"执行步骤 {index}",
            }
            for index, tool_name in enumerate(tool_names, start=1)
        ],
    }


def make_tool_runner(order_result, logistics_result, calls):
    """模拟工具执行，不调用真实业务工具。"""

    def fake_tool_runner(name, arguments):
        calls.append((name, arguments))

        if name == "query_order":
            return json.dumps(order_result, ensure_ascii=False)

        if name == "query_logistics":
            return json.dumps(logistics_result, ensure_ascii=False)

        raise ValueError(f"未知工具：{name}")

    return fake_tool_runner


def test_shipped_order_queries_logistics():
    """已发货：应先查订单，再查物流。"""
    calls = []

    runner = make_tool_runner(
        order_result={
            "success": True,
            "order": {
                "order_id": ORDER_ID,
                "status": "shipped",
                "tracking_number": "SF123456",
            },
        },
        logistics_result={
            "success": True,
            "tracking": ["已揽收", "运输中"],
        },
        calls=calls,
    )

    executor = PlanExecutor(tool_runner=runner)
    result = executor.execute(
        make_plan("query_order", "query_logistics")
    )

    assert result["success"] is True
    assert [name for name, _ in calls] == [
        "query_order",
        "query_logistics",
    ]
    assert [step["status"] for step in result["steps"]] == [
        "success",
        "success",
    ]


def test_pending_order_skips_logistics():
    """尚未发货：应跳过物流查询。"""
    calls = []

    runner = make_tool_runner(
        order_result={
            "success": True,
            "order": {
                "order_id": ORDER_ID,
                "status": "pending",
                "tracking_number": None,
            },
        },
        logistics_result={"success": True},
        calls=calls,
    )

    executor = PlanExecutor(tool_runner=runner)
    result = executor.execute(
        make_plan("query_order", "query_logistics")
    )

    assert result["success"] is True
    assert [name for name, _ in calls] == ["query_order"]
    assert result["steps"][1]["status"] == "skipped"


def test_failed_order_query_stops_execution():
    """订单查询失败：不得继续查物流。"""
    calls = []

    runner = make_tool_runner(
        order_result={
            "success": False,
            "error": "订单不存在",
        },
        logistics_result={"success": True},
        calls=calls,
    )

    executor = PlanExecutor(tool_runner=runner)
    result = executor.execute(
        make_plan("query_order", "query_logistics")
    )

    assert result["success"] is False
    assert [name for name, _ in calls] == ["query_order"]
    assert result["steps"][0]["status"] == "failed"


def test_planner_rejects_unknown_tool():
    """计划不得使用白名单以外的工具。"""
    plan = make_plan("query_order", "delete_account")

    with pytest.raises(ValueError):
        Planner._validate_plan(plan)


def test_planner_rejects_missing_order_id():
    """计划缺少订单号时应被拒绝。"""
    plan = make_plan("query_order")
    plan["steps"][0]["arguments"] = {}

    with pytest.raises(ValueError):
        Planner._validate_plan(plan)