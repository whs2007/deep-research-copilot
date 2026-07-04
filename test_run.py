"""
本地测试入口 — 直接运行验证完整调研流程
"""
import asyncio
import json
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from app.agent.graph import graph
from app.agent.state import ResearchState


async def main():
    topic = "2026年中国新能源汽车市场竞争格局"

    state: ResearchState = {
        "research_topic": topic,
        "research_plan": [],
        "search_queries": [],
        "evidence_pool": [],
        "verified_facts": [],
        "rejected_facts": [],
        "missing_angles": [],
        "fact_quality_score": 0.0,
        "final_report": "",
        "iteration_count": 0,
        "report_ready": False,
        "max_iterations": 3,
    }

    print(f"\n{'='*60}")
    print(f"调研任务: {topic}")
    print(f"最大迭代: {state['max_iterations']} 轮")
    print(f"{'='*60}\n")

    iteration = 0
    async for chunk in graph.astream(state, stream_mode="custom"):
        if isinstance(chunk, dict):
            event_type = chunk.get("type", "")
            if event_type == "progress":
                print(f"[{chunk.get('node', '')}] {chunk.get('message', '')}")
            elif event_type == "iteration":
                iteration += 1
                print(f"\n--- 第 {iteration} 轮迭代 ---\n")

    # 获取最终结果
    final = await graph.ainvoke(state)
    report = final.get("final_report", "")
    if report:
        print(f"\n{'='*60}")
        print("最终报告")
        print(f"{'='*60}\n")
        print(report)

        # 保存到文件
        path = f"report_{topic[:20]}.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n报告已保存: {path}")
    else:
        print("未生成报告")


if __name__ == "__main__":
    asyncio.run(main())
