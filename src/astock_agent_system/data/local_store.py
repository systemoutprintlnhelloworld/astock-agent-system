"""SQLite-backed local market data store.

This module supports the Tushare-style "download first, query locally" workflow
without introducing a new database service. The default database path lives
under ``data/market_local/`` and is ignored by Git.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from astock_agent_system.config import PROJECT_ROOT
from astock_agent_system.models import FinancialSnapshot, StockBar, StockIdentity, StockQuote


DEFAULT_LOCAL_MARKET_DB = PROJECT_ROOT / "data" / "market_local" / "market.sqlite"


class LocalMarketStore:
    """Persist and query market data in a small SQLite database."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or DEFAULT_LOCAL_MARKET_DB)

    def initialize(self) -> None:
        """Create tables and indexes if needed."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS stocks (
                    stock_code TEXT PRIMARY KEY,
                    stock_name TEXT NOT NULL,
                    sector TEXT DEFAULT '',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS bars (
                    stock_code TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    amount REAL NOT NULL,
                    turnover REAL DEFAULT 0,
                    source TEXT DEFAULT '',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (stock_code, date)
                );
                CREATE INDEX IF NOT EXISTS idx_bars_stock_date ON bars(stock_code, date);
                CREATE TABLE IF NOT EXISTS quotes (
                    stock_code TEXT PRIMARY KEY,
                    stock_name TEXT NOT NULL,
                    date TEXT NOT NULL,
                    price REAL NOT NULL,
                    change_pct REAL NOT NULL,
                    volume REAL NOT NULL,
                    amount REAL NOT NULL,
                    sector TEXT DEFAULT '',
                    source TEXT DEFAULT '',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS financials (
                    stock_code TEXT PRIMARY KEY,
                    stock_name TEXT NOT NULL,
                    report_date TEXT NOT NULL,
                    pe_ttm REAL NOT NULL,
                    pb REAL NOT NULL,
                    roe REAL NOT NULL,
                    debt_ratio REAL NOT NULL,
                    revenue_growth REAL NOT NULL,
                    profit_growth REAL NOT NULL,
                    market_cap REAL NOT NULL,
                    sector TEXT DEFAULT '',
                    source TEXT DEFAULT '',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    stock_code TEXT DEFAULT '',
                    status TEXT NOT NULL,
                    detail TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def exists(self) -> bool:
        return self.path.exists()

    def upsert_universe(self, stocks: list[StockIdentity]) -> int:
        if not stocks:
            return 0
        self.initialize()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO stocks(stock_code, stock_name, sector, updated_at)
                VALUES(:stock_code, :stock_name, :sector, CURRENT_TIMESTAMP)
                ON CONFLICT(stock_code) DO UPDATE SET
                    stock_name=excluded.stock_name,
                    sector=excluded.sector,
                    updated_at=CURRENT_TIMESTAMP
                """,
                [asdict(item) for item in stocks],
            )
        return len(stocks)

    def get_universe(self, limit: int | None = None) -> list[StockIdentity]:
        if not self.exists():
            return []
        sql = "SELECT stock_code, stock_name, sector FROM stocks ORDER BY stock_code"
        params: tuple[Any, ...] = ()
        if limit and limit > 0:
            sql += " LIMIT ?"
            params = (int(limit),)
        with self._connect(readonly=True) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [StockIdentity(stock_code=row[0], stock_name=row[1], sector=row[2] or "") for row in rows]

    def upsert_history(self, stock_code: str, bars: list[StockBar], *, source: str = "") -> int:
        if not bars:
            return 0
        self.initialize()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO bars(stock_code, date, open, high, low, close, volume, amount, turnover, source, updated_at)
                VALUES(:stock_code, :date, :open, :high, :low, :close, :volume, :amount, :turnover, :source, CURRENT_TIMESTAMP)
                ON CONFLICT(stock_code, date) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    amount=excluded.amount,
                    turnover=excluded.turnover,
                    source=excluded.source,
                    updated_at=CURRENT_TIMESTAMP
                """,
                [{**asdict(item), "source": source} for item in bars],
            )
        return len(bars)

    def get_history(self, stock_code: str, days: int | None = None) -> list[StockBar]:
        if not self.exists():
            return []
        limit = int(days) if days and days > 0 else 0
        sql = """
            SELECT stock_code, date, open, high, low, close, volume, amount, turnover
            FROM bars
            WHERE stock_code = ?
            ORDER BY date DESC
        """
        params: tuple[Any, ...] = (str(stock_code),)
        if limit:
            sql += " LIMIT ?"
            params = (str(stock_code), limit)
        with self._connect(readonly=True) as conn:
            rows = conn.execute(sql, params).fetchall()
        bars = [
            StockBar(
                stock_code=row[0],
                date=row[1],
                open=float(row[2]),
                high=float(row[3]),
                low=float(row[4]),
                close=float(row[5]),
                volume=float(row[6]),
                amount=float(row[7]),
                turnover=float(row[8] or 0.0),
            )
            for row in rows
        ]
        return sorted(bars, key=lambda item: item.date)

    def upsert_quote(self, quote: StockQuote, *, source: str = "") -> int:
        self.initialize()
        payload = {**asdict(quote), "source": source}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO quotes(stock_code, stock_name, date, price, change_pct, volume, amount, sector, source, updated_at)
                VALUES(:stock_code, :stock_name, :date, :price, :change_pct, :volume, :amount, :sector, :source, CURRENT_TIMESTAMP)
                ON CONFLICT(stock_code) DO UPDATE SET
                    stock_name=excluded.stock_name,
                    date=excluded.date,
                    price=excluded.price,
                    change_pct=excluded.change_pct,
                    volume=excluded.volume,
                    amount=excluded.amount,
                    sector=excluded.sector,
                    source=excluded.source,
                    updated_at=CURRENT_TIMESTAMP
                """,
                payload,
            )
        return 1

    def get_quote(self, stock_code: str) -> StockQuote | None:
        if not self.exists():
            return None
        with self._connect(readonly=True) as conn:
            row = conn.execute(
                """
                SELECT stock_code, stock_name, date, price, change_pct, volume, amount, sector
                FROM quotes WHERE stock_code = ?
                """,
                (str(stock_code),),
            ).fetchone()
        if row is None:
            return None
        return StockQuote(
            stock_code=row[0],
            stock_name=row[1],
            date=row[2],
            price=float(row[3]),
            change_pct=float(row[4]),
            volume=float(row[5]),
            amount=float(row[6]),
            sector=row[7] or "",
        )

    def upsert_financial(self, snapshot: FinancialSnapshot, *, source: str = "") -> int:
        self.initialize()
        payload = {**asdict(snapshot), "source": source}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO financials(
                    stock_code, stock_name, report_date, pe_ttm, pb, roe, debt_ratio,
                    revenue_growth, profit_growth, market_cap, sector, source, updated_at
                )
                VALUES(
                    :stock_code, :stock_name, :report_date, :pe_ttm, :pb, :roe, :debt_ratio,
                    :revenue_growth, :profit_growth, :market_cap, :sector, :source, CURRENT_TIMESTAMP
                )
                ON CONFLICT(stock_code) DO UPDATE SET
                    stock_name=excluded.stock_name,
                    report_date=excluded.report_date,
                    pe_ttm=excluded.pe_ttm,
                    pb=excluded.pb,
                    roe=excluded.roe,
                    debt_ratio=excluded.debt_ratio,
                    revenue_growth=excluded.revenue_growth,
                    profit_growth=excluded.profit_growth,
                    market_cap=excluded.market_cap,
                    sector=excluded.sector,
                    source=excluded.source,
                    updated_at=CURRENT_TIMESTAMP
                """,
                payload,
            )
        return 1

    def get_financial(self, stock_code: str) -> FinancialSnapshot | None:
        if not self.exists():
            return None
        with self._connect(readonly=True) as conn:
            row = conn.execute(
                """
                SELECT stock_code, stock_name, report_date, pe_ttm, pb, roe, debt_ratio,
                       revenue_growth, profit_growth, market_cap, sector
                FROM financials WHERE stock_code = ?
                """,
                (str(stock_code),),
            ).fetchone()
        if row is None:
            return None
        return FinancialSnapshot(
            stock_code=row[0],
            stock_name=row[1],
            report_date=row[2],
            pe_ttm=float(row[3]),
            pb=float(row[4]),
            roe=float(row[5]),
            debt_ratio=float(row[6]),
            revenue_growth=float(row[7]),
            profit_growth=float(row[8]),
            market_cap=float(row[9]),
            sector=row[10] or "",
        )

    def record_sync(self, *, source: str, operation: str, stock_code: str = "", status: str, detail: str = "") -> None:
        self.initialize()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sync_runs(source, operation, stock_code, status, detail, created_at)
                VALUES(?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (source, operation, stock_code, status, detail[:500]),
            )

    def stats(self) -> dict[str, Any]:
        if not self.exists():
            return {"path": str(self.path), "exists": False, "stocks": 0, "bars": 0, "quotes": 0, "financials": 0, "sync_runs": 0, "latest_sync_at": ""}
        with self._connect(readonly=True) as conn:
            latest = conn.execute("SELECT created_at FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
            return {
                "path": str(self.path),
                "exists": True,
                "stocks": int(conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]),
                "bars": int(conn.execute("SELECT COUNT(*) FROM bars").fetchone()[0]),
                "quotes": int(conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]),
                "financials": int(conn.execute("SELECT COUNT(*) FROM financials").fetchone()[0]),
                "sync_runs": int(conn.execute("SELECT COUNT(*) FROM sync_runs").fetchone()[0]),
                "latest_sync_at": str(latest[0]) if latest else "",
            }

    def recent_sync_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return recent sync audit rows for CLI local-market status."""
        if not self.exists():
            return []
        safe_limit = max(1, min(int(limit or 10), 50))
        with self._connect(readonly=True) as conn:
            rows = conn.execute(
                """
                SELECT source, operation, stock_code, status, detail, created_at
                FROM sync_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [
            {
                "source": str(row[0]),
                "operation": str(row[1]),
                "stock_code": str(row[2] or ""),
                "status": str(row[3]),
                "detail": str(row[4] or ""),
                "created_at": str(row[5]),
            }
            for row in rows
        ]

    def coverage_summary(self, *, stock_limit: int = 12, date_limit: int = 30) -> dict[str, Any]:
        """Return local-market coverage metrics for CLI dashboards."""
        empty = {
            "exists": self.exists(),
            "stock_count": 0,
            "bars_stock_count": 0,
            "quote_stock_count": 0,
            "financial_stock_count": 0,
            "bar_count": 0,
            "date_count": 0,
            "first_date": "",
            "last_date": "",
            "bar_stock_coverage": 0.0,
            "quote_stock_coverage": 0.0,
            "financial_stock_coverage": 0.0,
            "recent_dates": [],
            "top_stocks": [],
            "sector_coverage": [],
        }
        if not self.exists():
            return empty
        safe_stock_limit = max(1, min(int(stock_limit or 12), 100))
        safe_date_limit = max(1, min(int(date_limit or 30), 120))
        try:
            with self._connect(readonly=True) as conn:
                stock_count = int(conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0])
                bar_count = int(conn.execute("SELECT COUNT(*) FROM bars").fetchone()[0])
                bars_stock_count = int(conn.execute("SELECT COUNT(DISTINCT stock_code) FROM bars").fetchone()[0])
                quote_stock_count = int(conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0])
                financial_stock_count = int(conn.execute("SELECT COUNT(*) FROM financials").fetchone()[0])
                date_row = conn.execute("SELECT MIN(date), MAX(date), COUNT(DISTINCT date) FROM bars").fetchone()
                recent_rows = conn.execute(
                    """
                    SELECT date, COUNT(DISTINCT stock_code) AS stock_count, COUNT(*) AS bar_count
                    FROM bars
                    GROUP BY date
                    ORDER BY date DESC
                    LIMIT ?
                    """,
                    (safe_date_limit,),
                ).fetchall()
                top_rows = conn.execute(
                    """
                    SELECT b.stock_code, COALESCE(s.stock_name, ''), COALESCE(s.sector, ''),
                           COUNT(*) AS bar_count, MIN(b.date), MAX(b.date),
                           MAX(q.date) IS NOT NULL AS has_quote,
                           MAX(f.report_date) IS NOT NULL AS has_financial
                    FROM bars b
                    LEFT JOIN stocks s ON s.stock_code = b.stock_code
                    LEFT JOIN quotes q ON q.stock_code = b.stock_code
                    LEFT JOIN financials f ON f.stock_code = b.stock_code
                    GROUP BY b.stock_code
                    ORDER BY bar_count DESC, b.stock_code
                    LIMIT ?
                    """,
                    (safe_stock_limit,),
                ).fetchall()
                sector_rows = conn.execute(
                    """
                    SELECT COALESCE(NULLIF(s.sector, ''), '(未分类)') AS sector,
                           COUNT(DISTINCT s.stock_code) AS stock_count,
                           COUNT(b.date) AS bar_count,
                           COUNT(DISTINCT b.stock_code) AS bars_stock_count
                    FROM stocks s
                    LEFT JOIN bars b ON b.stock_code = s.stock_code
                    GROUP BY sector
                    ORDER BY bar_count DESC, stock_count DESC
                    LIMIT 12
                    """
                ).fetchall()
        except sqlite3.Error:
            return empty
        denominator = max(stock_count, bars_stock_count, quote_stock_count, financial_stock_count, 1)
        return {
            "exists": True,
            "stock_count": stock_count,
            "bars_stock_count": bars_stock_count,
            "quote_stock_count": quote_stock_count,
            "financial_stock_count": financial_stock_count,
            "bar_count": bar_count,
            "date_count": int(date_row[2] or 0) if date_row else 0,
            "first_date": str(date_row[0] or "") if date_row else "",
            "last_date": str(date_row[1] or "") if date_row else "",
            "bar_stock_coverage": bars_stock_count / denominator,
            "quote_stock_coverage": quote_stock_count / denominator,
            "financial_stock_coverage": financial_stock_count / denominator,
            "recent_dates": [
                {"date": str(row[0]), "stocks": int(row[1] or 0), "bars": int(row[2] or 0)}
                for row in reversed(recent_rows)
            ],
            "top_stocks": [
                {
                    "stock_code": str(row[0]),
                    "stock_name": str(row[1] or ""),
                    "sector": str(row[2] or ""),
                    "bars": int(row[3] or 0),
                    "first_date": str(row[4] or ""),
                    "last_date": str(row[5] or ""),
                    "has_quote": bool(row[6]),
                    "has_financial": bool(row[7]),
                }
                for row in top_rows
            ],
            "sector_coverage": [
                {
                    "sector": str(row[0]),
                    "stocks": int(row[1] or 0),
                    "bars": int(row[2] or 0),
                    "bars_stock_count": int(row[3] or 0),
                }
                for row in sector_rows
            ],
        }

    def scan_candidates(
        self,
        *,
        limit: int = 30,
        as_of_date: str | None = None,
        sectors: list[str] | None = None,
        min_amount: float | None = None,
        min_volume: float | None = None,
        min_change_pct: float | None = None,
        max_change_pct: float | None = None,
        history_days: int = 20,
        top_per_sector: int | None = None,
        include_stale: bool = False,
    ) -> dict[str, Any]:
        """Scan the local SQLite warehouse for a broad, non-LLM candidate shortlist.

        This method is intentionally read-only and does not call online providers.
        It is a fast discovery layer before the deeper multi-agent analysis.
        """

        safe_limit = max(1, min(int(limit or 30), 500))
        safe_history_days = max(2, min(int(history_days or 20), 250))
        normalized_sectors = _normalize_filter_values(sectors or [])
        criteria = {
            "limit": safe_limit,
            "as_of_date": as_of_date or "",
            "sectors": normalized_sectors,
            "min_amount": min_amount,
            "min_volume": min_volume,
            "min_change_pct": min_change_pct,
            "max_change_pct": max_change_pct,
            "history_days": safe_history_days,
            "top_per_sector": top_per_sector,
            "include_stale": bool(include_stale),
        }
        base_payload: dict[str, Any] = {
            "status": "missing_db" if not self.exists() else "empty",
            "source": "local_sqlite",
            "db_path": str(self.path),
            "criteria": criteria,
            "coverage": self.coverage_summary(stock_limit=min(safe_limit, 30), date_limit=min(safe_history_days, 60)),
            "latest_quote_date": "",
            "as_of_date": as_of_date or "",
            "candidate_pool_count": 0,
            "stale_count": 0,
            "count": 0,
            "candidates": [],
            "next_steps": [
                "先运行 datasource sync-local 补齐本地 SQLite 行情，再重新执行 active-scan。",
                "active-scan 只做本地广域发现；对候选股仍需运行 analyze 或 agent start 做深度多 Agent 分析。",
            ],
        }
        if not self.exists():
            return base_payload

        params: list[Any] = []
        where = ["1=1"]
        try:
            with self._connect(readonly=True) as conn:
                latest_row = conn.execute("SELECT MAX(date) FROM quotes").fetchone()
                latest_quote_date = str(latest_row[0] or "") if latest_row else ""
                reference_date = (as_of_date or latest_quote_date).strip()
                if not include_stale and reference_date:
                    where.append("q.date = ?")
                    params.append(reference_date)
                elif include_stale and as_of_date:
                    where.append("q.date <= ?")
                    params.append(as_of_date)
                if normalized_sectors:
                    placeholders = ",".join("?" for _ in normalized_sectors)
                    where.append(f"COALESCE(NULLIF(q.sector, ''), NULLIF(s.sector, ''), NULLIF(f.sector, ''), '') IN ({placeholders})")
                    params.extend(normalized_sectors)
                if min_amount is not None:
                    where.append("q.amount >= ?")
                    params.append(float(min_amount))
                if min_volume is not None:
                    where.append("q.volume >= ?")
                    params.append(float(min_volume))
                if min_change_pct is not None:
                    where.append("q.change_pct >= ?")
                    params.append(float(min_change_pct))
                if max_change_pct is not None:
                    where.append("q.change_pct <= ?")
                    params.append(float(max_change_pct))

                pool_limit = max(safe_limit * 8, 200)
                rows = conn.execute(
                    f"""
                    SELECT q.stock_code,
                           COALESCE(NULLIF(q.stock_name, ''), NULLIF(s.stock_name, ''), q.stock_code) AS stock_name,
                           COALESCE(NULLIF(q.sector, ''), NULLIF(s.sector, ''), NULLIF(f.sector, ''), '') AS sector,
                           q.date, q.price, q.change_pct, q.volume, q.amount,
                           f.pe_ttm, f.pb, f.roe, f.market_cap
                    FROM quotes q
                    LEFT JOIN stocks s ON s.stock_code = q.stock_code
                    LEFT JOIN financials f ON f.stock_code = q.stock_code
                    WHERE {' AND '.join(where)}
                    ORDER BY q.amount DESC, q.volume DESC, q.stock_code
                    LIMIT ?
                    """,
                    (*params, pool_limit),
                ).fetchall()
        except sqlite3.Error as exc:
            base_payload["status"] = "error"
            base_payload["error"] = str(exc)[:500]
            return base_payload

        if not rows:
            base_payload["latest_quote_date"] = reference_date if "reference_date" in locals() else ""
            base_payload["as_of_date"] = base_payload["latest_quote_date"]
            return base_payload

        max_amount = max(_safe_float(row[7]) for row in rows) or 1.0
        candidates: list[dict[str, Any]] = []
        for row in rows:
            stock_code = str(row[0])
            bars = self.get_history(stock_code, days=safe_history_days)
            return_5d = _window_return(bars, 5)
            return_20d = _window_return(bars, 20)
            latest_bar = bars[-1] if bars else None
            previous_bars = bars[:-1] or bars
            avg_volume = sum(item.volume for item in previous_bars) / len(previous_bars) if previous_bars else 0.0
            avg_amount = sum(item.amount for item in previous_bars) / len(previous_bars) if previous_bars else 0.0
            volume_ratio = (latest_bar.volume / avg_volume) if latest_bar and avg_volume else 0.0
            amount_ratio = (latest_bar.amount / avg_amount) if latest_bar and avg_amount else 0.0
            amount = _safe_float(row[7])
            change_pct = _safe_float(row[5])
            liquidity_score = _clamp(amount / max(max_amount, _safe_float(min_amount), 1.0))
            momentum_score = _clamp(0.5 + change_pct * 4.0 + return_5d * 2.0 + return_20d)
            expansion_score = _clamp((max(volume_ratio, amount_ratio) - 0.8) / 1.4)
            roe = _safe_float(row[10])
            quality_score = _clamp(roe / 0.18) if roe else 0.5
            score = liquidity_score * 0.35 + momentum_score * 0.25 + expansion_score * 0.25 + quality_score * 0.15
            reasons = _candidate_reasons(
                amount=amount,
                min_amount=_safe_float(min_amount),
                change_pct=change_pct,
                return_5d=return_5d,
                return_20d=return_20d,
                volume_ratio=volume_ratio,
                amount_ratio=amount_ratio,
                roe=roe,
                quote_date=str(row[3] or ""),
                latest_quote_date=latest_quote_date,
            )
            candidates.append(
                {
                    "stock_code": stock_code,
                    "stock_name": str(row[1] or stock_code),
                    "sector": str(row[2] or ""),
                    "date": str(row[3] or ""),
                    "price": round(_safe_float(row[4]), 4),
                    "change_pct": round(change_pct, 6),
                    "volume": round(_safe_float(row[6]), 4),
                    "amount": round(amount, 4),
                    "turnover": round(_safe_float(getattr(latest_bar, "turnover", 0.0)), 6),
                    "return_5d": round(return_5d, 6),
                    "return_20d": round(return_20d, 6),
                    "volume_ratio_20d": round(volume_ratio, 6),
                    "amount_ratio_20d": round(amount_ratio, 6),
                    "pe_ttm": round(_safe_float(row[8]), 4),
                    "pb": round(_safe_float(row[9]), 4),
                    "roe": round(roe, 6),
                    "market_cap": round(_safe_float(row[11]), 4),
                    "bar_count": len(bars),
                    "score": round(score, 6),
                    "reasons": reasons,
                    "next_steps": [
                        f"python -m astock_agent_system.cli analyze {stock_code} --days {safe_history_days}",
                        "检查最近 K 线、财务快照和公告/舆情风险后再交给模拟盘。",
                    ],
                }
            )

        candidates.sort(key=lambda item: (item["score"], item["amount"]), reverse=True)
        selected = _apply_sector_cap(candidates, safe_limit=safe_limit, top_per_sector=top_per_sector)
        return {
            **base_payload,
            "status": "ok" if selected else "empty",
            "latest_quote_date": latest_quote_date,
            "as_of_date": reference_date,
            "candidate_pool_count": len(candidates),
            "stale_count": sum(1 for item in candidates if latest_quote_date and item.get("date") != latest_quote_date),
            "count": len(selected),
            "candidates": selected,
            "next_steps": [
                "把 active-scan 输出当作广域短名单，不等同于买入建议。",
                "对候选股运行 analyze 或 agent start，查看完整技术/基本面/舆情/风控协作链。",
                "若覆盖率低或日期陈旧，先运行 datasource sync-local 增量补齐本地库。",
            ],
        }

    def _connect(self, readonly: bool = False) -> sqlite3.Connection:
        if readonly:
            uri = f"file:{self.path.as_posix()}?mode=ro"
            return sqlite3.connect(uri, uri=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path)


def _safe_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _normalize_filter_values(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        for item in str(value or "").split(","):
            text = item.strip()
            if text and text not in normalized:
                normalized.append(text)
    return normalized


def _window_return(bars: list[StockBar], window: int) -> float:
    if len(bars) < 2:
        return 0.0
    latest = bars[-1].close
    base_index = max(0, len(bars) - window - 1)
    base = bars[base_index].close
    return (latest / base - 1.0) if base else 0.0


def _candidate_reasons(
    *,
    amount: float,
    min_amount: float,
    change_pct: float,
    return_5d: float,
    return_20d: float,
    volume_ratio: float,
    amount_ratio: float,
    roe: float,
    quote_date: str,
    latest_quote_date: str,
) -> list[str]:
    reasons: list[str] = []
    if min_amount > 0 and amount >= min_amount:
        reasons.append(f"成交额达到阈值（{amount:,.0f} >= {min_amount:,.0f}）")
    elif amount > 0:
        reasons.append(f"成交额靠前（{amount:,.0f}）")
    if change_pct > 0:
        reasons.append(f"最新涨跌幅为正（{change_pct:.2%}）")
    if return_5d > 0:
        reasons.append(f"5日收益为正（{return_5d:.2%}）")
    if return_20d > 0:
        reasons.append(f"20日收益为正（{return_20d:.2%}）")
    if volume_ratio >= 1.2 or amount_ratio >= 1.2:
        reasons.append(f"近端量能放大（量比 {volume_ratio:.2f} / 额比 {amount_ratio:.2f}）")
    if roe >= 0.1:
        reasons.append(f"ROE 较高（{roe:.2%}）")
    if latest_quote_date and quote_date and quote_date != latest_quote_date:
        reasons.append(f"报价日期 {quote_date} 非全库最新 {latest_quote_date}，需复核时效")
    return reasons[:6] or ["本地库指标进入候选池，需进一步深度分析"]


def _apply_sector_cap(
    candidates: list[dict[str, Any]],
    *,
    safe_limit: int,
    top_per_sector: int | None,
) -> list[dict[str, Any]]:
    cap = int(top_per_sector or 0)
    if cap <= 0:
        return candidates[:safe_limit]
    selected: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for item in candidates:
        sector = str(item.get("sector") or "(未分类)")
        if counts.get(sector, 0) >= cap:
            continue
        selected.append(item)
        counts[sector] = counts.get(sector, 0) + 1
        if len(selected) >= safe_limit:
            break
    return selected
