"""Adapters from existing scheduler/orchestrator payloads to frontend schemas."""

from __future__ import annotations

from typing import Any

from apps.backend.schemas import (
    DecisionLogEntry,
    DecisionLogStep,
    EquityMetricPoint,
    HoldingRow,
    RankingRow,
    StockCandidate,
    TradeRow,
)


def decision_logs_from_result(result: dict[str, Any], run_id: str) -> list[DecisionLogEntry]:
    """Convert orchestrator decisions into collapsible UI log cards."""
    entries: list[DecisionLogEntry] = []
    run_date = _competition(result).get("run_date", "")
    for agent in _agents(result):
        agent_id = str(agent.get("agent_id", ""))
        llm_model = str(agent.get("llm_model", ""))
        for index, decision in enumerate(_list(agent.get("decisions"))):
            stock_code = str(decision.get("stock_code", ""))
            action = str(decision.get("action", "HOLD"))
            steps = [
                DecisionLogStep(
                    id=f"{agent_id}-{stock_code}-scores",
                    agent_id=agent_id,
                    title="多 Agent 评分",
                    summary="技术、基本面、舆情和风控评分摘要",
                    details={
                        "technical_score": _float(decision.get("technical_score")),
                        "fundamental_score": _float(decision.get("fundamental_score")),
                        "sentiment_score": _float(decision.get("sentiment_score")),
                        "risk_score": _float(decision.get("risk_score")),
                    },
                ),
                DecisionLogStep(
                    id=f"{agent_id}-{stock_code}-llm-review",
                    agent_id=agent_id,
                    title="LLM 复核",
                    summary=str(decision.get("llm_review", {}).get("reason", "")) if isinstance(decision.get("llm_review"), dict) else "",
                    details={"llm_review": decision.get("llm_review", {})},
                ),
            ]
            entries.append(
                DecisionLogEntry(
                    id=f"{run_id or run_date}-{agent_id}-{stock_code}-{index}",
                    run_id=run_id,
                    timestamp=str(decision.get("timestamp", run_date)),
                    agent_id=agent_id,
                    llm_model=llm_model,
                    stock_code=stock_code,
                    stock_name=str(decision.get("stock_name", "")),
                    action=action,
                    confidence=_float(decision.get("confidence")),
                    position_size=_float(decision.get("position_size")),
                    summary=f"{llm_model or agent_id} 对 {stock_code} 给出 {action} 决策",
                    reasons=[str(item) for item in _list(decision.get("reasons"))],
                    risks=[str(item) for item in _list(decision.get("risk_notes"))],
                    steps=steps,
                    raw=decision,
                )
            )
    return entries


def stock_board_from_result(result: dict[str, Any]) -> tuple[list[HoldingRow], list[StockCandidate], list[TradeRow]]:
    """Return holdings, candidates, and trades for the stock board."""
    holdings: list[HoldingRow] = []
    candidates_by_code: dict[str, StockCandidate] = {}
    trades: list[TradeRow] = []
    for agent in _agents(result):
        agent_id = str(agent.get("agent_id", ""))
        llm_model = str(agent.get("llm_model", ""))
        for position in _list(agent.get("positions")):
            stock_code = str(position.get("stock_code", ""))
            if not stock_code:
                continue
            holdings.append(
                HoldingRow(
                    agent_id=agent_id,
                    llm_model=llm_model,
                    stock_code=stock_code,
                    shares=int(_float(position.get("shares"))),
                    cost_basis=_float(position.get("cost_basis")),
                    current_price=_float(position.get("current_price")),
                    market_value=_float(position.get("market_value")),
                    unrealized_return=_float(position.get("unrealized_return")),
                )
            )
        for trade in _list(agent.get("trades")):
            stock_code = str(trade.get("stock_code", ""))
            if not stock_code:
                continue
            trades.append(
                TradeRow(
                    agent_id=agent_id,
                    llm_model=llm_model,
                    date=str(trade.get("date", "")),
                    stock_code=stock_code,
                    side=str(trade.get("side", trade.get("action", ""))),
                    price=_float(trade.get("price")),
                    shares=int(_float(trade.get("shares"))),
                    amount=_float(trade.get("amount")) or _float(trade.get("price")) * _float(trade.get("shares")),
                    realized_pnl=_float(trade.get("realized_pnl")),
                    reason=str(trade.get("reason", "")),
                )
            )
        for decision in _list(agent.get("decisions")):
            stock_code = str(decision.get("stock_code", ""))
            if not stock_code or stock_code in candidates_by_code:
                continue
            score = max(
                _float(decision.get("technical_score")),
                _float(decision.get("fundamental_score")),
                _float(decision.get("sentiment_score")),
                _float(decision.get("risk_score")),
            )
            candidates_by_code[stock_code] = StockCandidate(
                stock_code=stock_code,
                stock_name=str(decision.get("stock_name", "")),
                score=score,
                action=str(decision.get("action", "HOLD")),
                confidence=_float(decision.get("confidence")),
                reasons=[str(item) for item in _list(decision.get("reasons"))],
                risks=[str(item) for item in _list(decision.get("risk_notes"))],
            )
    return holdings, list(candidates_by_code.values()), trades


def equity_metrics_from_result(result: dict[str, Any]) -> list[EquityMetricPoint]:
    """Build one chart point per ranking row from the latest run."""
    run_date = str(_competition(result).get("run_date", ""))
    return [
        EquityMetricPoint(
            date=run_date,
            agent_id=str(row.get("agent_id", "")),
            llm_model=str(row.get("llm_model", "")),
            equity=_float(row.get("equity")),
            cash=_float(row.get("cash")),
            daily_pnl=_float(row.get("daily_pnl")),
            total_return=_float(row.get("total_return")),
            max_drawdown=_float(row.get("max_drawdown")),
        )
        for row in _list(_competition(result).get("rankings"))
    ]


def rankings_from_result(result: dict[str, Any]) -> list[RankingRow]:
    """Normalize orchestrator ranking rows for the leaderboard endpoint."""
    rows: list[RankingRow] = []
    for index, row in enumerate(_list(_competition(result).get("rankings")), start=1):
        rows.append(
            RankingRow(
                rank=int(_float(row.get("rank"), index)),
                agent_id=str(row.get("agent_id", "")),
                llm_model=str(row.get("llm_model", "")),
                total_return=_float(row.get("total_return")),
                max_drawdown=_float(row.get("max_drawdown")),
                win_rate=_float(row.get("win_rate")),
                total_trades=int(_float(row.get("total_trades"))),
                equity=_float(row.get("equity")),
                cash=_float(row.get("cash")),
                daily_pnl=_float(row.get("daily_pnl")),
                skipped_execution=bool(row.get("skipped_execution", False)),
                skip_reason=str(row.get("skip_reason", "")),
            )
        )
    return rows


def _competition(result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("payload", {}) if isinstance(result, dict) else {}
    competition = payload.get("competition", {}) if isinstance(payload, dict) else {}
    return competition if isinstance(competition, dict) else {}


def _agents(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _list(_competition(result).get("agents")) if isinstance(item, dict)]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
