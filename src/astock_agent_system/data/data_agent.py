"""Data access layer with an offline-first fallback."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from astock_agent_system.config import PROJECT_ROOT, Settings, load_settings
from astock_agent_system.models import FinancialSnapshot, StockBar, StockIdentity, StockQuote

logger = logging.getLogger(__name__)


class DataAgent:
    """Fetch market data, using checked-in sample data when providers are absent."""

    def __init__(self, settings: Settings | None = None, data_path: str | None = None) -> None:
        self.settings = settings or load_settings()
        self.data_path = self._resolve_path(data_path or self.settings.data.offline_data_path)
        self._offline_payload: dict[str, Any] | None = None
        self._tushare_provider: Any = None
        self._akshare_provider: Any = None

    def _get_tushare_provider(self) -> Any | None:
        """Lazy load Tushare provider if token is available."""
        if self._tushare_provider is not None:
            return self._tushare_provider
        
        token = self.settings.data.tushare_token if hasattr(self.settings.data, 'tushare_token') else None
        if not token:
            return None
        
        try:
            from astock_agent_system.data.providers import TushareProvider
            self._tushare_provider = TushareProvider(token=token)
            logger.info("Tushare provider initialized")
            return self._tushare_provider
        except Exception as exc:
            logger.warning(f"Failed to initialize Tushare provider: {exc}")
            return None

    def _get_akshare_provider(self) -> Any | None:
        """Lazy load AkShare provider as fallback."""
        if self._akshare_provider is not None:
            return self._akshare_provider
        
        try:
            from astock_agent_system.data.providers import AkShareProvider
            self._akshare_provider = AkShareProvider()
            logger.info("AkShare provider initialized")
            return self._akshare_provider
        except Exception as exc:
            logger.warning(f"Failed to initialize AkShare provider: {exc}")
            return None

    def get_universe(self) -> list[StockIdentity]:
        """Get stock universe from providers with fallback chain: Tushare -> AkShare -> Offline."""
        # Try Tushare first
        if self.settings.data.mode != 'offline':
            tushare = self._get_tushare_provider()
            if tushare:
                try:
                    limit = getattr(self.settings.data, 'dynamic_universe_limit', None)
                    stocks = tushare.get_universe(limit=limit)
                    if stocks:
                        logger.info(f"Fetched {len(stocks)} stocks from Tushare")
                        return stocks
                except Exception as exc:
                    logger.warning(f"Tushare universe fetch failed: {exc}, trying AkShare")
            
            # Fallback to AkShare
            akshare = self._get_akshare_provider()
            if akshare:
                try:
                    limit = getattr(self.settings.data, 'dynamic_universe_limit', None)
                    stocks = akshare.get_universe(limit=limit)
                    if stocks:
                        logger.info(f"Fetched {len(stocks)} stocks from AkShare")
                        return stocks
                except Exception as exc:
                    logger.warning(f"AkShare universe fetch failed: {exc}, using offline data")
        
        # Final fallback to offline data
        payload = self._load_offline_payload()
        return [
            StockIdentity(
                stock_code=str(item["code"]),
                stock_name=str(item.get("name", item["code"])),
                sector=str(item.get("sector", "")),
            )
            for item in payload.get("stocks", [])
        ]

    def get_history(self, stock_code: str, days: int | None = None) -> list[StockBar]:
        """Get historical bars with fallback chain: Tushare -> AkShare -> Offline."""
        days = days or 30
        
        # Try Tushare first
        if self.settings.data.mode != 'offline':
            tushare = self._get_tushare_provider()
            if tushare:
                try:
                    bars = tushare.get_history(stock_code, days=days, freq='D')
                    if bars:
                        logger.info(f"Fetched {len(bars)} bars for {stock_code} from Tushare")
                        return bars
                except Exception as exc:
                    logger.warning(f"Tushare history fetch failed for {stock_code}: {exc}")
            
            # Fallback to AkShare
            akshare = self._get_akshare_provider()
            if akshare:
                try:
                    bars = akshare.get_history(stock_code, days=days, freq='daily')
                    if bars:
                        logger.info(f"Fetched {len(bars)} bars for {stock_code} from AkShare")
                        return bars
                except Exception as exc:
                    logger.warning(f"AkShare history fetch failed for {stock_code}: {exc}")
        
        # Final fallback to offline data
        record = self._get_stock_record(stock_code)
        bars = [self._bar_from_raw(stock_code, raw) for raw in record.get("history", [])]
        bars.sort(key=lambda bar: bar.date)
        if days is not None and days > 0:
            return bars[-days:]
        return bars

    def get_financial(self, stock_code: str) -> FinancialSnapshot:
        """Get financial data with fallback chain: Tushare -> AkShare -> Offline."""
        # Try Tushare first
        if self.settings.data.mode != 'offline':
            tushare = self._get_tushare_provider()
            if tushare:
                try:
                    return tushare.get_financial(stock_code)
                except Exception as exc:
                    logger.warning(f"Tushare financial fetch failed for {stock_code}: {exc}")
            
            # Fallback to AkShare
            akshare = self._get_akshare_provider()
            if akshare:
                try:
                    return akshare.get_financial(stock_code)
                except Exception as exc:
                    logger.warning(f"AkShare financial fetch failed for {stock_code}: {exc}")
        
        # Final fallback to offline data
        record = self._get_stock_record(stock_code)
        raw = record.get("financial", {})
        return FinancialSnapshot(
            stock_code=str(record["code"]),
            stock_name=str(record.get("name", record["code"])),
            report_date=str(raw.get("report_date", self._load_offline_payload().get("as_of", ""))),
            pe_ttm=float(raw.get("pe_ttm", 0.0)),
            pb=float(raw.get("pb", 0.0)),
            roe=float(raw.get("roe", 0.0)),
            debt_ratio=float(raw.get("debt_ratio", 0.0)),
            revenue_growth=float(raw.get("revenue_growth", 0.0)),
            profit_growth=float(raw.get("profit_growth", 0.0)),
            market_cap=float(raw.get("market_cap", 0.0)),
            sector=str(record.get("sector", "")),
        )

    def get_quote(self, stock_code: str) -> StockQuote:
        """Get real-time quote with fallback chain: Tushare -> AkShare -> Offline."""
        # Try Tushare first
        if self.settings.data.mode != 'offline':
            tushare = self._get_tushare_provider()
            if tushare:
                try:
                    return tushare.get_quote(stock_code)
                except Exception as exc:
                    logger.warning(f"Tushare quote fetch failed for {stock_code}: {exc}")
            
            # Fallback to AkShare
            akshare = self._get_akshare_provider()
            if akshare:
                try:
                    return akshare.get_quote(stock_code)
                except Exception as exc:
                    logger.warning(f"AkShare quote fetch failed for {stock_code}: {exc}")
        
        # Final fallback to offline data
        record = self._get_stock_record(stock_code)
        quote = record.get("quote") or {}
        if not quote:
            bars = self.get_history(stock_code, days=2)
            if not bars:
                raise ValueError(f"No quote or history found for {stock_code}")
            latest = bars[-1]
            previous_close = bars[-2].close if len(bars) > 1 else latest.close
            change_pct = (latest.close - previous_close) / previous_close if previous_close else 0.0
            return StockQuote(
                stock_code=str(record["code"]),
                stock_name=str(record.get("name", record["code"])),
                date=latest.date,
                price=latest.close,
                change_pct=change_pct,
                volume=latest.volume,
                amount=latest.amount,
                sector=str(record.get("sector", "")),
            )
        return StockQuote(
            stock_code=str(record["code"]),
            stock_name=str(record.get("name", record["code"])),
            date=str(quote.get("date", self._load_offline_payload().get("as_of", ""))),
            price=float(quote.get("price", 0.0)),
            change_pct=float(quote.get("change_pct", 0.0)),
            volume=float(quote.get("volume", 0.0)),
            amount=float(quote.get("amount", 0.0)),
            sector=str(record.get("sector", "")),
        )

    def refresh_from_providers(self) -> bool:
        """Placeholder for future Tushare/AkShare adapters.

        The MVP deliberately remains offline-capable. Real provider integration
        will populate the same normalized model objects used by this class.
        """
        return False

    def _resolve_path(self, path: str) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return PROJECT_ROOT / candidate

    def _load_offline_payload(self) -> dict[str, Any]:
        if self._offline_payload is not None:
            return self._offline_payload
        if not self.data_path.exists():
            raise FileNotFoundError(f"Offline data file not found: {self.data_path}")
        with self.data_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, dict) or not isinstance(payload.get("stocks"), list):
            raise ValueError("Offline data must be a JSON object with a 'stocks' list")
        self._offline_payload = payload
        return payload

    def _get_stock_record(self, stock_code: str) -> dict[str, Any]:
        for item in self._load_offline_payload().get("stocks", []):
            if str(item.get("code")) == str(stock_code):
                return item
        raise KeyError(f"Stock code not found in offline data: {stock_code}")

    @staticmethod
    def _bar_from_raw(stock_code: str, raw: Any) -> StockBar:
        if isinstance(raw, dict):
            return StockBar(
                stock_code=stock_code,
                date=str(raw["date"]),
                open=float(raw["open"]),
                high=float(raw["high"]),
                low=float(raw["low"]),
                close=float(raw["close"]),
                volume=float(raw.get("volume", 0.0)),
                amount=float(raw.get("amount", 0.0)),
                turnover=float(raw.get("turnover", 0.0)),
            )
        if isinstance(raw, list) and len(raw) >= 7:
            turnover = float(raw[7]) if len(raw) > 7 else 0.0
            return StockBar(
                stock_code=stock_code,
                date=str(raw[0]),
                open=float(raw[1]),
                high=float(raw[2]),
                low=float(raw[3]),
                close=float(raw[4]),
                volume=float(raw[5]),
                amount=float(raw[6]),
                turnover=turnover,
            )
        raise ValueError(f"Invalid bar record for {stock_code}: {raw!r}")
