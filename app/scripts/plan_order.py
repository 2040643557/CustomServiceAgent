"""演示：生成任务计划，然后执行计划。"""

import json
import sys

from openai import OpenAI

from app.config.settings import settings
from app.multi_agent.planner import Planner
from app.multi_agent.executor import PlanExecutor
from app.multi_agent.response_generator import ResponseGenerator
from app.multi_agent.reflection import Reflector


def main():
    # 默认使用一个已发货的示例订单。
    # 也可以通过命令行传入订单号。
    order_id = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "ORD-20240115-001"
    )

    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )

    planner = Planner(
        client=client,
        model=settings.model_name,
    )

    executor = PlanExecutor()

    user_request = (
        f"查询订单 {order_id} 是否发货。"
        "如果已经发货，再查询物流进度，"
        "最后总结当前情况。"
    )

    # 第一阶段：生成计划
    plan = planner.create_plan(user_request)

    print("\n========== 初始计划 ==========")
    print(json.dumps(plan, ensure_ascii=False, indent=2))

    # 第二阶段：执行计划
    execution = executor.execute(plan)

    print("\n========== 工具执行结果 ==========")
    print(json.dumps(execution, ensure_ascii=False, indent=2))

    # 第三阶段：反思
    reflector = Reflector(
        client=client,
        model=settings.model_name,
    )

    reflection = reflector.evaluate(
        user_request=user_request,
        plan=plan,
        execution_result=execution,
    )

    print("\n========== Reflection 评估 ==========")
    print(json.dumps(reflection, ensure_ascii=False, indent=2))

    # 第四阶段：如果计划可以修正，最多重新规划一次
    if reflection["status"] == "replan":
        revised_request = (
            f"{user_request}\n\n"
            f"上次执行后的修正建议：{reflection['feedback']}\n"
            "请据此重新检查任务计划。"
            "只使用允许的工具，不要编造执行结果。"
        )

        plan = planner.create_plan(revised_request)
        execution = executor.execute(plan)

        # 重规划后必须重新评估，不能假定第二次一定成功
        reflection = reflector.evaluate(
            user_request=user_request,
            plan=plan,
            execution_result=execution,
        )

        print("\n========== 重规划后的评估 ==========")
        print(json.dumps(reflection, ensure_ascii=False, indent=2))

    # 第五阶段：生成最终回答
    generator = ResponseGenerator(
        client=client,
        model=settings.model_name,
    )

    answer = generator.generate(
        user_request=user_request,
        execution_result=execution,
    )

    print("\n========== 最终客服回答 ==========")
    print(answer)


if __name__ == "__main__":
    main()