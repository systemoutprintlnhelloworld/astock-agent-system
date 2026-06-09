"""Tushare data provider for real-time and historical market data."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from astock_agent_system.models import FinancialSnapshot, StockBar, StockIdentity, StockQuote

logger = logging.getLogger(__name__)


class TushareProvider:
    """Fetch A-share data from Tushare Pro API."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token
        self._api: Any = None
        self._identity_cache: dict[str, StockIdentity] = {}

    def _get_api(self) -> Any:
        """Lazy load tushare API."""
        if self._api is not None:
            return self._api
        if not self.token:
            raise ValueError("Tushare token is required. Set TUSHARE_TOKEN environment variable.")
        try:
            import tushare as ts
        except ImportError as exc:
            raise ImportError(
                "tushare is not installed. Run: pip install -e .[market]"
            ) from exc
        
        ts.set_token(self.token)
        self._api = ts.pro_api()
        logger.info("Tushare API initialized successfully")
        return self._api

    def get_universe(self, market: str = "主板", limit: int | None = None) -> list[StockIdentity]:
        """Get stock universe from Tushare.
        
        Args:
            market: 主板/创业板/科创板/北交所
            limit: Maximum number of stocks to return
        """
        api = self._get_api()
        df = api.stock_basic(
            exchange='',
            list_status='L',
            fields='ts_code,name,industry'
        )
        
        stocks = []
        for _, row in df.iterrows():
            stock = StockIdentity(
                stock_code=self._normalize_code(row['ts_code']),
                stock_name=str(row['name']),
                sector=str(row.get('industry', ''))
            )
            self._identity_cache[stock.stock_code] = stock
            stocks.append(stock)
            if limit and len(stocks) >= limit:
                break
        
        logger.info(f"Fetched {len(stocks)} stocks from Tushare universe")
        return stocks

    def get_history(
        self, 
        stock_code: str, 
        days: int = 30, 
        freq: str = '1min'
    ) -> list[StockBar]:
        """Get historical bars from Tushare.
        
        Args:
            stock_code: Stock code (e.g., '600519')
            days: Number of days to look back
            freq: Frequency ('D' for daily, '1min' for 1-minute)
        """
        api = self._get_api()
        ts_code = self._to_ts_code(stock_code)
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
        
        # Tushare uses different APIs for different frequencies
        if freq == 'D':
            df = api.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )
        elif freq in ['1min', '5min', '15min', '30min', '60min']:
            df = api.pro_bar(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                freq=freq
            )
        else:
            raise ValueError(f"Unsupported frequency: {freq}")
        
        if df is None or df.empty:
            logger.warning(f"No data returned for {stock_code}")
            return []
        
        bars = []
        for _, row in df.iterrows():
            bars.append(StockBar(
                stock_code=stock_code,
                date=str(row['trade_date']),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=float(row['vol']) * 100,  # Tushare uses 手 (100 shares)
                amount=float(row['amount']) * 1000,  # Tushare uses 千元
                turnover=float(row.get('pct_chg', 0.0))
            ))
        
        bars.sort(key=lambda x: x.date)
        logger.info(f"Fetched {len(bars)} bars for {stock_code} (freq={freq})")
        return bars

    def get_financial(self, stock_code: str) -> FinancialSnapshot:
        """Get financial data from Tushare."""
        api = self._get_api()
        ts_code = self._to_ts_code(stock_code)
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=370)).strftime('%Y%m%d')
        
        # Get latest daily basic data (PE, PB, etc.)
        df_basic = api.daily_basic(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            fields='ts_code,trade_date,pe_ttm,pb,total_mv'
        )
        
        # Get latest financial indicators
        df_fina = api.fina_indicator(
            ts_code=ts_code,
            fields='ts_code,end_date,roe,debt_to_assets,q_profit_yoy,q_sales_yoy'
        )
        
        if df_basic.empty:
            raise ValueError(f"No financial data found for {stock_code}")
        
        basic = df_basic.iloc[0]
        fina = df_fina.iloc[0] if not df_fina.empty else {}
        
        identity = self._identity_cache.get(stock_code)
        stock_name = identity.stock_name if identity else stock_code
        sector = identity.sector if identity else ''
        fina_row = fina if isinstance(fina, dict) else fina.to_dict()
        
        return FinancialSnapshot(
            stock_code=stock_code,
            stock_name=str(stock_name),
            report_date=str(basic['trade_date']),
            pe_ttm=_safe_float(basic.get('pe_ttm', 0.0)),
            pb=_safe_float(basic.get('pb', 0.0)),
            roe=_safe_float(fina_row.get('roe', 0.0)),
            debt_ratio=_safe_float(fina_row.get('debt_to_assets', 0.0)),
            revenue_growth=_safe_float(fina_row.get('q_sales_yoy', 0.0)),
            profit_growth=_safe_float(fina_row.get('q_profit_yoy', 0.0)),
            market_cap=_safe_float(basic.get('total_mv', 0.0)) * 10000,  # Tushare uses 万元
            sector=str(sector)
        )

    def get_quote(self, stock_code: str) -> StockQuote:
        """Get real-time quote from Tushare (uses latest daily data as fallback)."""
        self._get_api()
        
        # Try to get latest bar
        bars = self.get_history(stock_code, days=2, freq='D')
        if not bars:
            raise ValueError(f"No quote data found for {stock_code}")
        
        latest = bars[-1]
        previous_close = bars[-2].close if len(bars) > 1 else latest.close
        change_pct = (latest.close - previous_close) / previous_close if previous_close else 0.0
        
        identity = self._identity_cache.get(stock_code)
        stock_name = identity.stock_name if identity else stock_code
        sector = identity.sector if identity else ''
        
        return StockQuote(
            stock_code=stock_code,
            stock_name=str(stock_name),
            date=latest.date,
            price=latest.close,
            change_pct=change_pct,
            volume=latest.volume,
            amount=latest.amount,
            sector=str(sector)
        )

    @staticmethod
    def _to_ts_code(stock_code: str) -> str:
        """Convert stock code to Tushare format (e.g., '600519' -> '600519.SH')."""
        if '.' in stock_code:
            return stock_code
        
        # Determine market suffix
        if stock_code.startswith('6'):
            return f"{stock_code}.SH"
        elif stock_code.startswith(('0', '3')):
            return f"{stock_code}.SZ"
        elif stock_code.startswith('8'):
            return f"{stock_code}.BJ"
        else:
            raise ValueError(f"Cannot determine market for stock code: {stock_code}")

    @staticmethod
    def _normalize_code(ts_code: str) -> str:
        """Convert Tushare code to normalized format (e.g., '600519.SH' -> '600519')."""
        return ts_code.split('.')[0] if '.' in ts_code else ts_code


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert Tushare/Pandas scalar values to float without ambiguous truth checks."""
    try:
        if value is None:
            return default
        # pandas.NA/nan compare oddly; use pandas when available but keep provider optional.
        try:
            import pandas as pd  # type: ignore

            if pd.isna(value):
                return default
        except Exception:
            pass
        return float(value)
    except (TypeError, ValueError):
        return default
