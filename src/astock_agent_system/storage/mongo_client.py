"""MongoDB client for persisting trading records and agent decisions."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from astock_agent_system.config import Settings, load_settings

logger = logging.getLogger(__name__)


class MongoClient:
    """MongoDB client for A-share agent system."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self._client: Any = None
        self._db: Any = None

    def _get_db(self) -> Any:
        """Lazy load MongoDB database."""
        if self._db is not None:
            return self._db

        try:
            import pymongo
        except ImportError as exc:
            raise ImportError(
                "pymongo is not installed. Run: pip install -e .[storage]"
            ) from exc

        mongo_uri = self.settings.storage.mongo_uri
        mongo_db = self.settings.storage.mongo_db
        timeout_ms = int(getattr(self.settings.storage, "mongo_timeout_ms", 3000))

        self._client = pymongo.MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
        )
        self._client.admin.command("ping")
        self._db = self._client[mongo_db]
        
        # Create indexes for common queries
        self._db.trades.create_index([("agent_id", 1), ("timestamp", -1)])
        self._db.positions.create_index([("agent_id", 1), ("date", -1)])
        self._db.agent_decisions.create_index([("agent_id", 1), ("timestamp", -1)])
        self._db.llm_rankings.create_index([("date", -1)])
        
        logger.info(f"MongoDB connected: {mongo_uri}/{mongo_db}")
        return self._db

    def save_trade(self, trade: dict[str, Any]) -> str:
        """Save a trade record.
        
        Args:
            trade: {
                "agent_id": str,
                "stock_code": str,
                "action": str,  # BUY/SELL/STOP_LOSS
                "price": float,
                "shares": int,
                "amount": float,
                "timestamp": datetime,
                "reason": str
            }
        
        Returns:
            Trade ID
        """
        db = self._get_db()
        
        if "timestamp" not in trade:
            trade["timestamp"] = datetime.now()
        
        result = db.trades.insert_one(trade)
        logger.info(f"Saved trade: {trade['agent_id']} {trade['action']} {trade['stock_code']}")
        return str(result.inserted_id)

    def save_position_snapshot(self, snapshot: dict[str, Any]) -> str:
        """Save a position snapshot.
        
        Args:
            snapshot: {
                "agent_id": str,
                "date": str,  # YYYY-MM-DD
                "equity": float,
                "cash": float,
                "positions": [
                    {
                        "stock_code": str,
                        "shares": int,
                        "cost_basis": float,
                        "market_value": float,
                        "unrealized_pnl": float
                    }
                ],
                "daily_pnl": float,
                "total_pnl": float
            }
        
        Returns:
            Snapshot ID
        """
        db = self._get_db()
        
        if "date" not in snapshot:
            snapshot["date"] = datetime.now().strftime("%Y-%m-%d")
        
        # Update if already exists for this agent and date
        result = db.positions.update_one(
            {"agent_id": snapshot["agent_id"], "date": snapshot["date"]},
            {"$set": snapshot},
            upsert=True
        )
        
        logger.info(f"Saved position snapshot: {snapshot['agent_id']} {snapshot['date']}")
        return str(result.upserted_id) if result.upserted_id else "updated"

    def save_agent_decision(self, decision: dict[str, Any]) -> str:
        """Save an agent's decision log.
        
        Args:
            decision: {
                "agent_id": str,
                "stock_code": str,
                "timestamp": datetime,
                "action": str,  # BUY/HOLD/SELL/REJECT
                "confidence": float,
                "position_size": float,
                "reasons": list[str],
                "technical_score": float,
                "fundamental_score": float,
                "sentiment_score": float,
                "risk_score": float
            }
        
        Returns:
            Decision ID
        """
        db = self._get_db()
        
        if "timestamp" not in decision:
            decision["timestamp"] = datetime.now()
        
        result = db.agent_decisions.insert_one(decision)
        logger.info(f"Saved decision: {decision['agent_id']} {decision['action']} {decision['stock_code']}")
        return str(result.inserted_id)

    def save_llm_ranking(self, ranking: dict[str, Any]) -> str:
        """Save LLM performance ranking.
        
        Args:
            ranking: {
                "date": str,  # YYYY-MM-DD
                "rankings": [
                    {
                        "agent_id": str,
                        "llm_model": str,
                        "total_return": float,
                        "max_drawdown": float,
                        "sharpe_ratio": float,
                        "win_rate": float,
                        "total_trades": int,
                        "equity": float
                    }
                ]
            }
        
        Returns:
            Ranking ID
        """
        db = self._get_db()
        
        if "date" not in ranking:
            ranking["date"] = datetime.now().strftime("%Y-%m-%d")
        
        result = db.llm_rankings.update_one(
            {"date": ranking["date"]},
            {"$set": ranking},
            upsert=True
        )
        
        logger.info(f"Saved LLM ranking: {ranking['date']}")
        return str(result.upserted_id) if result.upserted_id else "updated"

    def get_trades(
        self, 
        agent_id: str | None = None, 
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get trade records."""
        db = self._get_db()
        
        query: dict[str, Any] = {}
        if agent_id:
            query["agent_id"] = agent_id
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = datetime.strptime(start_date, "%Y-%m-%d")
            if end_date:
                query["timestamp"]["$lte"] = datetime.strptime(end_date, "%Y-%m-%d")
        
        cursor = db.trades.find(query).sort("timestamp", -1).limit(limit)
        return list(cursor)

    def get_positions(
        self,
        agent_id: str,
        date: str | None = None
    ) -> dict[str, Any] | None:
        """Get position snapshot for an agent on a specific date."""
        db = self._get_db()
        
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        return db.positions.find_one({"agent_id": agent_id, "date": date})

    def get_latest_position_snapshot(self, agent_id: str) -> dict[str, Any] | None:
        """Get the newest position snapshot for one agent."""
        db = self._get_db()
        return db.positions.find_one({"agent_id": agent_id}, sort=[("date", -1), ("_id", -1)])

    def get_agent_decisions(
        self,
        agent_id: str,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get agent decision history."""
        db = self._get_db()
        
        cursor = db.agent_decisions.find(
            {"agent_id": agent_id}
        ).sort("timestamp", -1).limit(limit)
        return list(cursor)

    def get_latest_ranking(self) -> dict[str, Any] | None:
        """Get the latest LLM ranking."""
        db = self._get_db()
        return db.llm_rankings.find_one(sort=[("date", -1)])

    def get_agent_equity_curve(
        self,
        agent_id: str,
        days: int = 30
    ) -> list[dict[str, Any]]:
        """Get equity curve for an agent."""
        db = self._get_db()
        
        cursor = db.positions.find(
            {"agent_id": agent_id}
        ).sort("date", -1).limit(days)
        
        return list(reversed(list(cursor)))

    def get_latest_position_snapshots(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Get the newest position snapshot for each agent.

        This is used by the automatic stop-loss checker. It intentionally
        returns the latest snapshot per agent rather than every historical row.
        """
        db = self._get_db()
        cursor = db.positions.find({}).sort([("date", -1), ("_id", -1)])
        snapshots: list[dict[str, Any]] = []
        seen_agents: set[str] = set()
        for item in cursor:
            agent_id = str(item.get("agent_id", ""))
            if not agent_id or agent_id in seen_agents:
                continue
            seen_agents.add(agent_id)
            snapshots.append(item)
            if limit is not None and len(snapshots) >= limit:
                break
        return snapshots

    def close(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            logger.info("MongoDB connection closed")
