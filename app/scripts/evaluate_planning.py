"""Planning 工作流评测：计划、执行、Reflection 与重规划。"""

import json
from pathlib import Path

from openai import OpenAI

from app.config.settings import settings
from app.multi_agent.planner import Planner
from app.multi_agent.executor import PlanExecutor
from app.multi_agent.reflection import Reflector


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASE_FILE = PROJECT_ROOT / "experiments" / "planning_cases.json"
REPORT_FILE = PROJECT_ROOT / "experiments" / "planning_eval_results.json"


def tool_names(execution: dict, statuses: set[str]) -> list[str]:
    """按执行顺序提取指定状态的工具名称。"""
    return [
        item["tool"]
        for item in execution.get("steps", [])
        if item.get("status") in statuses
    ]


def execute_and_reflect(
    planner: Planner,
    executor: PlanExecutor,
    reflector: Reflector,
    query: str,
) -> tuple[dict, dict, dict]:
    """生成计划、执行计划并评估结果。"""

    plan = planner.create_plan(query)
    execution = executor.execute(plan)
    reflection = reflector.evaluate(
        user_request=query,
        plan=plan,
        execution_result=execution,
    )

    return plan, execution, reflection


def main() -> None:
    with CASE_FILE.open("r", encoding="utf-8") as file:
        cases = json.load(file)

    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )

    planner = Planner(client, settings.model_name)
    executor = PlanExecutor()
    reflector = Reflector(client, settings.model_name)

    records = []

    total_plan_attempts = 0
    valid_plan_attempts = 0
    replan_cases = 0
    tool_failure_cases = 0
    total_tool_calls = 0

    print(f"评测案例数：{len(cases)}")
    print("=" * 65)

    for case in cases:
        case_id = case["id"]
        query = case["query"]

        print(f"\n[{case_id}] {query}")

        plan_valid = False
        initial_plan_tools = []
        final_execution = {}
        final_reflection = {}
        execution_history = []
        error = None

        try:
            # 第一次规划
            total_plan_attempts += 1
            plan = planner.create_plan(query)
            valid_plan_attempts += 1
            plan_valid = True

            initial_plan_tools = [
                step["tool"] for step in plan["steps"]
            ]

            execution = executor.execute(plan)
            execution_history.append(execution)

            reflection = reflector.evaluate(
                user_request=query,
                plan=plan,
                execution_result=execution,
            )

            # 最多重新规划一次
            if reflection["status"] == "replan":
                replan_cases += 1

                revised_query = (
                    f"{query}\n\n"
                    f"上次执行后的修正建议："
                    f"{reflection['feedback']}\n"
                    "请生成修正后的任务计划。"
                )

                total_plan_attempts += 1
                plan = planner.create_plan(revised_query)
                valid_plan_attempts += 1

                execution = executor.execute(plan)
                execution_history.append(execution)

                reflection = reflector.evaluate(
                    user_request=query,
                    plan=plan,
                    execution_result=execution,
                )

            final_execution = execution
            final_reflection = reflection

        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            print(f"评测异常：{error}")

        # 汇总实际执行行为
        actual_executed = tool_names(
            final_execution, {"success", "failed"}
        )
        actual_skipped = tool_names(
            final_execution, {"skipped"}
        )

        expected_executed = case["expected_executed_tools"]
        expected_skipped = case["expected_skipped_tools"]

        plan_sequence_correct = (
            plan_valid
            and initial_plan_tools == case["expected_plan_tools"]
        )

        execution_matches = (
            actual_executed == expected_executed
            and actual_skipped == expected_skipped
        )

        reflection_matches = (
            final_reflection.get("status")
            == case["expected_reflection_status"]
        )

        # 这里的 Pass 表示符合该案例的预期行为，
        # 并不等同于通用、开放场景下的任务成功率。
        behavior_pass = (
            plan_valid
            and execution_matches
            and reflection_matches
        )

        failed_tools = any(
            step.get("status") == "failed"
            for run in execution_history
            for step in run.get("steps", [])
        )

        if failed_tools:
            tool_failure_cases += 1

        total_tool_calls += sum(
            len(tool_names(run, {"success", "failed"}))
            for run in execution_history
        )

        record = {
            "id": case_id,
            "query": query,
            "plan_valid": plan_valid,
            "initial_plan_tools": initial_plan_tools,
            "expected_plan_tools": case["expected_plan_tools"],
            "plan_sequence_correct": plan_sequence_correct,
            "actual_executed_tools": actual_executed,
            "expected_executed_tools": expected_executed,
            "actual_skipped_tools": actual_skipped,
            "expected_skipped_tools": expected_skipped,
            "reflection_status": final_reflection.get("status"),
            "expected_reflection_status": case[
                "expected_reflection_status"
            ],
            "reflection_matches": reflection_matches,
            "behavior_pass": behavior_pass,
            "tool_failure": failed_tools,
            "error": error,
        }

        records.append(record)

        print(f"计划：{initial_plan_tools}")
        print(f"预期计划：{case['expected_plan_tools']}")
        print(f"实际执行：{actual_executed}")
        print(f"实际跳过：{actual_skipped}")
        print(f"Reflection：{final_reflection.get('status')}")
        print(f"预期行为：{'PASS' if behavior_pass else 'FAIL'}")

    total_cases = len(cases)

    plan_validity_rate = (
        valid_plan_attempts / total_plan_attempts
        if total_plan_attempts else 0
    )

    plan_sequence_accuracy = (
        sum(r["plan_sequence_correct"] for r in records)
        / total_cases
        if total_cases else 0
    )

    behavior_pass_rate = (
        sum(r["behavior_pass"] for r in records)
        / total_cases
        if total_cases else 0
    )

    complete_cases = [
        r for r in records
        if r["expected_reflection_status"] == "complete"
    ]

    task_success_rate = (
        sum(
            r["behavior_pass"]
            and r["reflection_status"] == "complete"
            for r in complete_cases
        ) / len(complete_cases)
        if complete_cases else 0
    )

    replan_rate = replan_cases / total_cases if total_cases else 0

    tool_failure_rate = (
        tool_failure_cases / total_cases if total_cases else 0
    )

    average_tool_calls = (
        total_tool_calls / total_cases if total_cases else 0
    )

    report = {
        "total_cases": total_cases,
        "plan_attempts": total_plan_attempts,
        "valid_plan_attempts": valid_plan_attempts,
        "plan_validity_rate": plan_validity_rate,
        "plan_sequence_accuracy": plan_sequence_accuracy,
        "expected_behavior_pass_rate": behavior_pass_rate,
        "task_success_rate": task_success_rate,
        "replan_rate": replan_rate,
        "tool_failure_case_rate": tool_failure_rate,
        "average_tool_calls_per_case": average_tool_calls,
        "records": records,
    }

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 65)
    print("Planning 评测汇总")
    print("=" * 65)
    print(f"Plan Validity Rate: {plan_validity_rate:.2%}")
    print(f"Plan Sequence Accuracy: {plan_sequence_accuracy:.2%}")
    print(f"Expected Behavior Pass Rate: {behavior_pass_rate:.2%}")
    print(f"Task Success Rate: {task_success_rate:.2%}")
    print(f"Replan Rate: {replan_rate:.2%}")
    print(f"Tool Failure Case Rate: {tool_failure_rate:.2%}")
    print(f"Average Tool Calls: {average_tool_calls:.2f}")
    print(f"\n详细结果已保存到：{REPORT_FILE}")


if __name__ == "__main__":
    main()