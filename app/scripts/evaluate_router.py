import json
from collections import Counter, defaultdict
from pathlib import Path

from openai import OpenAI

from app.config.settings import settings
from app.multi_agent.router import Router


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASE_FILE = PROJECT_ROOT / "experiments" / "router_cases.json"


def main():
    with CASE_FILE.open("r", encoding="utf-8") as file:
        cases = json.load(file)

    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )

    router = Router(client, settings.model_name)

    correct = 0
    total = 0
    per_class = defaultdict(lambda: [0, 0])
    confusion = Counter()

    print(f"测试问题数：{len(cases)}")
    print("=" * 55)

    for case in cases:
        query = case["query"]
        expected = case["expected_agent"]

        try:
            predicted = router.route(query)
        except Exception as exc:
            print(f"\n调用失败：{query}")
            print(f"原因：{exc}")
            continue

        total += 1
        is_correct = predicted == expected

        if is_correct:
            correct += 1

        per_class[expected][1] += 1
        if is_correct:
            per_class[expected][0] += 1

        confusion[(expected, predicted)] += 1

        print(f"\n问题：{query}")
        print(f"预期：{expected}")
        print(f"预测：{predicted}")
        print(f"结果：{'正确' if is_correct else '错误'}")

    print("\n" + "=" * 55)
    print("评测汇总")
    print("=" * 55)

    if total == 0:
        print("没有成功完成的测试，无法计算准确率。")
        return

    print(f"整体路由准确率：{correct}/{total} = {correct / total:.2%}")

    for label, (hits, count) in sorted(per_class.items()):
        accuracy = hits / count if count else 0
        print(f"{label}：{hits}/{count} = {accuracy:.2%}")

    print("\n混淆明细（预期标签 → 预测标签）")
    for (expected, predicted), count in sorted(confusion.items()):
        print(f"{expected} → {predicted}: {count}")


if __name__ == "__main__":
    main()