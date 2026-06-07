"""Sentiment analysis agent with smart-search and offline fallbacks."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from astock_agent_system.agent_descriptor import load_agent_descriptor
from astock_agent_system.agent_learning import load_experiences
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
        try:
            self.descriptor = load_agent_descriptor("sentiment_analyst")
        except (FileNotFoundError, OSError, ValueError):
            self.descriptor = None

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
        system_prompt = "你是A股舆情分析助手，只输出JSON。"
        user_prompt = f"请对 {stock_code} 的舆情摘要打分，输出 {{\"score\": 0到1, \"label\": \"...\"}}。摘要：\n{text[:3000]}"
        if self.descriptor is not None and self.descriptor.prompt_template:
            system_prompt = self.descriptor.system_prompt or system_prompt
            user_prompt = self.descriptor.render_prompt(
                {
                    "stock_code": stock_code,
                    "text": text[:3000],
                    "learning_context": _recent_learning_context(),
                }
            )
        try:
            result = self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
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


def _recent_learning_context(limit: int = 5) -> str:
    entries = load_experiences(limit=limit)
    if not entries:
        return "暂无足够历史经验。"
    lines: list[str] = []
    for entry in entries:
        outcome = entry.get("outcome", {}) if isinstance(entry.get("outcome", {}), dict) else {}
        lines.append(
            f"- {entry.get('date', '')} {entry.get('stock_code', '')}: "
            f"模型={entry.get('llm_model', '')}, "
            f"收益={outcome.get('return_pct', 0)}%, "
            f"结果={outcome.get('result', '')}"
        )
    return "\n".join(lines)
