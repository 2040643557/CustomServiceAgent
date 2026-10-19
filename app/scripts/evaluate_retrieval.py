"""评估 RAG 检索效果：比较不同 Top-K 的文档命中率。"""

import json
from pathlib import Path

from app.agent.tools.knowledge import search_knowledge


# 当前脚本位于 app/scripts/ 下，向上两级到项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASE_FILE = PROJECT_ROOT / "experiments" / "rag_cases.json"

TOP_K_VALUES = [1, 3, 5]


def load_cases() -> list[dict]:
    """加载人工标注的测试案例。"""
    with CASE_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def main() -> None:
    cases = load_cases()
    records = []

    print(f"测试集：{CASE_FILE}")
    print(f"测试问题数：{len(cases)}")
    print("开始执行检索评测...\n")

    # 每个问题只检索一次 Top-5，再计算不同 K 的结果。
    # 这样可以复用结果，避免重复计算问题向量。
    for case in cases:
        query = case["query"]
        expected_doc = case["expected_doc"]

        result = search_knowledge(query, top_k=5)

        if not result.get("success"):
            raise RuntimeError(
                f"检索失败：{query}\n"
                f"原因：{result.get('error', '未知错误')}"
            )

        records.append({
            "query": query,
            "expected_doc": expected_doc,
            "results": result.get("results", []),
        })

    # 计算文档命中率
    print("=" * 55)
    print("不同 Top-K 的文档命中率")
    print("=" * 55)

    for k in TOP_K_VALUES:
        hit_count = 0

        for record in records:
            # 只看排名前 K 的结果
            top_docs = {
                item.get("doc")
                for item in record["results"][:k]
            }

            if record["expected_doc"] in top_docs:
                hit_count += 1

        hit_rate = hit_count / len(records) * 100

        print(
            f"DocHit@{k}: "
            f"{hit_count}/{len(records)} "
            f"= {hit_rate:.2f}%"
        )

    # 展示 Top-3 的具体检索结果，便于定位失败案例。
    print("\n" + "=" * 55)
    print("Top-3 检索明细")
    print("=" * 55)

    for record in records:
        top3 = record["results"][:3]
        top_docs = [item.get("doc", "") for item in top3]
        hit = record["expected_doc"] in top_docs

        print(f"\n问题：{record['query']}")
        print(f"预期文档：{record['expected_doc']}")
        print(f"实际文档：{top_docs}")
        print(f"是否命中：{'是' if hit else '否'}")

        for item in top3:
            print(
                f"  - {item.get('doc')} / "
                f"{item.get('section')} / "
                f"score={item.get('score')}"
            )


if __name__ == "__main__":
    main()