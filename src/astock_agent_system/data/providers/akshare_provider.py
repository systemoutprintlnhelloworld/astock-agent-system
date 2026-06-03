"""AkShare data provider as a free fallback for A-share data."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Callable

try:
    import pandas as pd
except ImportError:
    pd = None

from astock_agent_system.models import FinancialSnapshot, StockBar, StockIdentity, StockQuote

logger = logging.getLogger(__name__)


class AkShareProvider:
    """Fetch A-share data from AkShare (free, no token required)."""

    def __init__(self) -> None:
        self._ak: Any = None

    def _get_ak(self) -> Any:
        """Lazy load akshare module."""
        if self._ak is not None:
            return self._ak
        try:
            import akshare as ak
        except ImportError as exc:
            raise ImportError(
                "akshare is not installed. Run: pip install -e .[market]"
            ) from exc
        self._ak = ak
        logger.info("AkShare module loaded successfully")
        return self._ak

    def get_universe(self, limit: int | None = None) -> list[StockIdentity]:
        """Get stock universe from AkShare (东方财富网数据)."""
        ak = self._get_ak()
        
        try:
            df = _call_with_retries(ak.stock_zh_a_spot_em)
        except Exception as exc:
            logger.error(f"Failed to fetch stock universe from AkShare: {exc}")
            return []
        
        stocks = []
        for _, row in df.iterrows():
            stock_code = str(row['代码'])
            stocks.append(StockIdentity(
                stock_code=stock_code,
                stock_name=str(row['名称']),
                sector=str(row.get('行业', ''))
            ))
            if limit and len(stocks) >= limit:
                break
        
        logger.info(f"Fetched {len(stocks)} stocks from AkShare universe")
        return stocks

    def get_history(
        self, 
        stock_code: str, 
        days: int = 30, 
        freq: str = 'daily'
    ) -> list[StockBar]:
        """Get historical bars from AkShare.
        
        Args:
            stock_code: Stock code (e.g., '600519')
            days: Number of days to look back
            freq: Frequency ('daily', '1', '5', '15', '30', '60' for minutes)
        """
        ak = self._get_ak()
        
        try:
            if freq == 'daily':
                # Daily data
                df = _call_with_retries(
                    ak.stock_zh_a_hist,
                    symbol=stock_code,
                    period="daily",
                    start_date=(datetime.now() - timedelta(days=days)).strftime('%Y%m%d'),
                    end_date=datetime.now().strftime('%Y%m%d'),
                    adjust="qfq"  # 前复权
                )
            else:
                # Intraday minute data (1/5/15/30/60)
                df = _call_with_retries(
                    ak.stock_zh_a_hist_min_em,
                    symbol=stock_code,
                    period=freq,
                    adjust="qfq"
                )
                # Filter to last N days
                if pd is None:
                    raise ImportError("pandas is required for AkShare minute data")
                df['日期'] = pd.to_datetime(df['时间'])
                cutoff = datetime.now() - timedelta(days=days)
                df = df[df['日期'] >= cutoff]
        except Exception as exc:
            logger.warning(f"Failed to fetch history for {stock_code}: {exc}")
            return []
        
        if df is None or df.empty:
            return []
        
        bars = []
        for _, row in df.iterrows():
            bars.append(StockBar(
                stock_code=stock_code,
                date=str(row.get('日期', row.get('时间', ''))),
                open=_safe_float(row['开盘']),
                high=_safe_float(row['最高']),
                low=_safe_float(row['最低']),
                close=_safe_float(row['收盘']),
                volume=_safe_float(row['成交量']),
                amount=_safe_float(row['成交额']),
                turnover=_safe_float(row.get('涨跌幅', 0.0))
            ))
        
        bars.sort(key=lambda x: x.date)
        logger.info(f"Fetched {len(bars)} bars for {stock_code} from AkShare")
        return bars

    def get_financial(self, stock_code: str) -> FinancialSnapshot:
        """Get financial data from AkShare."""
        ak = self._get_ak()
        
        try:
            # Get basic stock info
            df_spot = _call_with_retries(ak.stock_zh_a_spot_em)
            stock_row = df_spot[df_spot['代码'] == stock_code]
            
            if stock_row.empty:
                raise ValueError(f"Stock {stock_code} not found")
            
            stock_row = stock_row.iloc[0]
            
            # Try to get financial indicators
            try:
                df_fina = _call_with_retries(ak.stock_financial_analysis_indicator, symbol=stock_code, attempts=2)
                fina = df_fina.iloc[0] if not df_fina.empty else {}
            except Exception:
                fina = {}
            
            return FinancialSnapshot(
                stock_code=stock_code,
                stock_name=str(stock_row['名称']),
                report_date=datetime.now().strftime('%Y%m%d'),
                pe_ttm=_safe_float(stock_row.get('市盈率-动态', 0.0)),
                pb=_safe_float(stock_row.get('市净率', 0.0)),
                roe=_safe_float(fina.get('净资产收益率', 0.0)) if fina else 0.0,
                debt_ratio=_safe_float(fina.get('资产负债率', 0.0)) if fina else 0.0,
                revenue_growth=_safe_float(fina.get('营业总收入同比增长', 0.0)) if fina else 0.0,
                profit_growth=_safe_float(fina.get('净利润同比增长', 0.0)) if fina else 0.0,
                market_cap=_safe_float(stock_row.get('总市值', 0.0)),
                sector=str(stock_row.get('行业', ''))
            )
        except Exception as exc:
            logger.warning(f"AkShare spot financial failed for {stock_code}: {exc}; trying individual info")
            return self._get_financial_from_individual_info(stock_code)

    def get_quote(self, stock_code: str) -> StockQuote:
        """Get real-time quote from AkShare."""
        ak = self._get_ak()
        
        try:
            df = _call_with_retries(ak.stock_zh_a_spot_em)
            stock_row = df[df['代码'] == stock_code]
            
            if stock_row.empty:
                raise ValueError(f"Stock {stock_code} not found")
            
            stock_row = stock_row.iloc[0]
            
            return StockQuote(
                stock_code=stock_code,
                stock_name=str(stock_row['名称']),
                date=datetime.now().strftime('%Y-%m-%d'),
                price=_safe_float(stock_row['最新价']),
                change_pct=_safe_float(stock_row['涨跌幅']) / 100.0,  # AkShare returns percentage
                volume=_safe_float(stock_row['成交量']),
                amount=_safe_float(stock_row['成交额']),
                sector=str(stock_row.get('行业', ''))
            )
        except Exception as exc:
            logger.warning(f"AkShare spot quote failed for {stock_code}: {exc}; trying daily history fallback")
            bars = self.get_history(stock_code, days=5, freq='daily')
            if not bars:
                raise
            latest = bars[-1]
            previous = bars[-2] if len(bars) > 1 else latest
            change_pct = (latest.close - previous.close) / previous.close if previous.close else 0.0
            return StockQuote(
                stock_code=stock_code,
                stock_name=stock_code,
                date=latest.date,
                price=latest.close,
                change_pct=change_pct,
                volume=latest.volume,
                amount=latest.amount,
                sector='',
            )

    def _get_financial_from_individual_info(self, stock_code: str) -> FinancialSnapshot:
        ak = self._get_ak()
        df_info = _call_with_retries(ak.stock_individual_info_em, symbol=stock_code, attempts=2)
        info: dict[str, Any] = {}
        if df_info is not None and not df_info.empty:
            for _, row in df_info.iterrows():
                key = str(row.get('item', row.get('项目', ''))).strip()
                if key:
                    info[key] = row.get('value', row.get('值', ''))
        return FinancialSnapshot(
            stock_code=stock_code,
            stock_name=str(info.get('股票简称') or info.get('名称') or stock_code),
            report_date=datetime.now().strftime('%Y%m%d'),
            pe_ttm=0.0,
            pb=0.0,
            roe=0.0,
            debt_ratio=0.0,
            revenue_growth=0.0,
            profit_growth=0.0,
            market_cap=_safe_float(info.get('总市值', 0.0)),
            sector=str(info.get('行业') or ''),
        )


def _call_with_retries(func: Callable[..., Any], *args: Any, attempts: int = 3, delay_seconds: float = 1.0, **kwargs: Any) -> Any:
    last_exc: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - network guard
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(delay_seconds * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("AkShare call failed without exception")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN guard
        return default
    return number
