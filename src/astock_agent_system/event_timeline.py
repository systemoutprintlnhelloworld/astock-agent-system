"""User-facing event timeline for the modern Agent console.

The first implementation is intentionally dependency-light: it exposes a
stable event contract and safe offline/system events, while leaving live news
and announcement polling to later provider-specific adapters.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from astock_agent_system.config import Settings, load_settings


@dataclass(slots=True)
class TimelineEvent:
    """One market/system event that can be displayed or routed to Agents."""

    id: str
    timestamp: str
    source: str
    category: str
    severity: str
    title: str
    summary: str = ""
    stock_code: str = ""
    url: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventTimelineService:
    """Build timeline events without requiring online market credentials."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def poll(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return newest events.

        This method is safe in offline mode. It currently emits system and
        configuration events so the UI can already show the hybrid event flow;
        provider-backed news/announcement events can be appended later without
        changing the API shape.
        """
        now = _now_iso()
        events = [
            TimelineEvent(
                id=f"system-config-{now}",
                timestamp=now,
                source="system",
                category="configuration",
                severity="info",
                title="运行配置已加载",
                summary=(
                    f"数据模式={self.settings.data.mode}，"
                    f"模型数={len(self.settings.scheduler.models) or 1}，"
                    f"每日运行时间={self.settings.scheduler.daily_run_time}"
                ),
                payload={
                    "data_mode": self.settings.data.mode,
                    "models": self.settings.scheduler.models,
                    "daily_run_time": self.settings.scheduler.daily_run_time,
                },
            ),
            TimelineEvent(
                id=f"event-router-{now}",
                timestamp=now,
                source="event-router",
                category="agent_input",
                severity="info",
                title="事件路由处于混合模式",
                summary="重大事件可立即进入 Agent 决策链，普通新闻和公告按批次进入时间线。",
                payload={"mode": "hybrid", "immediate_categories": ["critical_news", "risk_alert"]},
            ),
        ]
        if self.settings.data.mode == "offline":
            events.append(
                TimelineEvent(
                    id=f"offline-data-{now}",
                    timestamp=now,
                    source="data-agent",
                    category="data_source",
                    severity="warning",
                    title="当前为离线数据模式",
                    summary="新闻、公告和实时行情轮询会使用空态/样例提示；切换 online 后可接入 Tushare/AkShare。",
                    payload={"offline_data_path": self.settings.data.offline_data_path},
                )
            )
        else:
            events.append(
                TimelineEvent(
                    id=f"online-data-{now}",
                    timestamp=now,
                    source="data-agent",
                    category="data_source",
                    severity="info",
                    title="当前为在线数据模式",
                    summary="后续将按配置轮询 Tushare 公告、AkShare 新闻和价格异常事件。",
                    payload={"has_tushare_token": bool(self.settings.data.tushare_token)},
                )
            )
        return [event.to_dict() for event in events[: max(1, limit)]]


def filter_timeline_events(
    events: list[dict[str, Any]],
    *,
    category: str | None = None,
    source: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Apply lightweight filters used by the API endpoint."""
    filtered = []
    for event in events:
        if category and str(event.get("category", "")) != category:
            continue
        if source and str(event.get("source", "")) != source:
            continue
        filtered.append(event)
        if len(filtered) >= max(1, limit):
            break
    return filtered


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
