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

    def _connect(self, readonly: bool = False) -> sqlite3.Connection:
        if readonly:
            uri = f"file:{self.path.as_posix()}?mode=ro"
            return sqlite3.connect(uri, uri=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path)
