"""Sentiment analysis agent with smart-search and offline fallbacks."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from astock_agent_system.config import Settings, load_settings
from astock_agent_system.llm import LLMClient
from astock_agent_system.models import AnalysisResult


POSITIVE_KEYWORDS = ["增长", "超预期", "回购", "增持", "中标", "突破", "创新高", "盈利", "订单", "利好"]
NEGATIVE_KEYWORDS = ["下滑", "亏损", "减持", "处罚", "调查", "暴雷", "违约", "风险", "裁员", "利空"]


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _label(score: float) -> str:
    if score >= 0.70:
        return "偏正面"
    if score >= 0.55:
        return "略正面"
    if score >= 0.40:
        return "中性"
    return "偏负面"


class SentimentAnalyst:
    """Use smart-search when enabled, otherwise return deterministic neutral sentiment."""

    def __init__(self, settings: Settings | None = None, llm_client: LLMClient | None = None) -> None:
        self.settings = settings or load_settings()
        self.llm_client = llm_client or LLMClient(self.settings)

    def analyze(self, stock_code: str, stock_name: str = "", sector: str = "") -> AnalysisResult:
        if not self.settings.smart_search.enabled:
            return AnalysisResult(
                agent_name="SentimentAnalyst",
                stock_code=stock_code,
                score=0.50,
                label="中性",
                reasons=["smart-search 未启用，使用离线中性舆情基线"],
                metadata={"source": "offline", "sector": sector},
            )

        query = f"{stock_name or stock_code} {stock_code} A股 最新新闻 舆情 风险"
        search_payload = self._run_smart_search(query)
        text = _summarize_search_payload(search_payload)
        if not text:
            return AnalysisResult(
                agent_name="SentimentAnalyst",
                stock_code=stock_code,
                score=0.50,
                label="中性",
                reasons=["smart-search 未返回可解析摘要，回退到中性舆情"],
                risks=["舆情数据缺失，需人工复核"],
                metadata={"source": "smart-search-empty", "query": query},
            )

        llm_score = self._score_with_llm(stock_code, text)
        score = llm_score if llm_score is not None else _keyword_sentiment_score(text)
        reasons = ["已通过 smart-search 获取舆情摘要"]
        risks: list[str] = []
        if any(keyword in text for keyword in NEGATIVE_KEYWORDS):
            risks.append("舆情摘要中出现负面风险关键词")
        if any(keyword in text for keyword in POSITIVE_KEYWORDS):
            reasons.append("舆情摘要中出现正向事件关键词")
        return AnalysisResult(
            agent_name="SentimentAnalyst",
            stock_code=stock_code,
            score=round(_clamp(score), 4),
            label=_label(score),
            reasons=reasons,
            risks=risks,
            metadata={"source": "smart-search", "query": query, "summary": text[:1000]},
        )

    def _run_smart_search(self, query: str) -> dict[str, Any]:
        command = ["smart-search", "search", query, "--validation", "fast", "--format", "json"]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.settings.smart_search.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"error": str(exc)}
        if result.returncode != 0:
            return {"error": result.stderr.strip() or f"smart-search exit code {result.returncode}"}
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return {"content": result.stdout.strip()}
        return payload if isinstance(payload, dict) else {"content": str(payload)}

    def _score_with_llm(self, stock_code: str, text: str) -> float | None:
        if not self.llm_client.is_configured or not self.llm_client.settings.default_model:
            return None
        try:
            result = self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": "你是A股舆情分析助手，只输出JSON。"},
                    {
                        "role": "user",
                        "content": (
                            f"请对 {stock_code} 的舆情摘要打分，输出 {{\"score\": 0到1, \"label\": \"...\"}}。摘要：\n{text[:3000]}"
                        ),
                    },
                ]
            )
        except Exception:
            return None
        value = result.parsed.get("score")
        try:
            return _clamp(float(value))
        except (TypeError, ValueError):
            return None


def _summarize_search_payload(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("content", "answer", "summary"):
        value = payload.get(key)
        if isinstance(value, str):
            parts.append(value)
    for key in ("primary_sources", "extra_sources", "sources", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value[:5]:
                if isinstance(item, dict):
                    title = str(item.get("title", ""))
                    snippet = str(item.get("snippet", item.get("content", "")))
                    parts.append(" ".join(part for part in [title, snippet] if part))
                elif isinstance(item, str):
                    parts.append(item)
    return "\n".join(part for part in parts if part).strip()


def _keyword_sentiment_score(text: str) -> float:
    positive = sum(text.count(keyword) for keyword in POSITIVE_KEYWORDS)
    negative = sum(text.count(keyword) for keyword in NEGATIVE_KEYWORDS)
    if positive == 0 and negative == 0:
        return 0.50
    return _clamp(0.50 + (positive - negative) * 0.06)
