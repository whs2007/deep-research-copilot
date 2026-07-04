"""
Research State — LangGraph 状态定义

State 围绕"报告生成"设计，不是消息堆积。
每个字段服务于调研报告的最终产出。
"""
from typing import TypedDict


class SearchQuery(TypedDict):
    """单条搜索查询"""
    query: str           # 搜索关键词
    source: str          # 信息来源描述
    priority: str        # high / medium / low


class Evidence(TypedDict):
    """证据条目"""
    fact: str            # 事实陈述
    source: str          # 来源 URL 或文档名
    relevance: str       # 与调研问题的关联说明
    confidence: str      # high / medium / low


class ResearchState(TypedDict):
    """一次调研任务的核心状态"""

    # ── 输入 ──
    research_topic: str          # 用户原始调研问题

    # ── Planner 产出 ──
    research_plan: list[str]     # 调研计划（分解后的子问题列表）
    search_queries: list[SearchQuery]  # 搜索查询列表

    # ── Search 产出 ──
    evidence_pool: list[Evidence]      # 证据池（所有搜索结果汇总）

    # ── Critic 产出 ──
    verified_facts: list[Evidence]     # 通过质量审核的证据
    rejected_facts: list[Evidence]     # 被拒绝的证据（含拒绝原因）
    missing_angles: list[str]          # 缺失的调研角度
    fact_quality_score: float          # 证据质量评分 (0.0 - 1.0)

    # ── Synthesizer 产出 ──
    final_report: str                  # 最终结构化调研报告

    # ── 流程控制 ──
    iteration_count: int               # loop-back 次数
    report_ready: bool                 # 终止条件：报告是否就绪
    max_iterations: int                # 最大 loop-back 次数（固定 3）
