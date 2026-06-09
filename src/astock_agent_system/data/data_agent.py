"""Data access layer with an offline-first fallback."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from astock_agent_system.config import PROJECT_ROOT, Settings, load_settings
from astock_agent_system.models import FinancialSnapshot, StockBar, StockIdentity, StockQuote

logger = logging.getLogger(__name__)


DEFAULT_PROVIDER_CHAIN = ["tushare", "baostock", "akshare"]

PROVIDER_ALIASES = {
    "alpha-vantage": "alpha_vantage",
    "alphavantage": "alpha_vantage",
    "aa_stock": "aastock",
    "aa-stock": "aastock",
    "bao_stock": "baostock",
    "bao-stock": "baostock",
    "joinquant": "jqdata",
    "ths": "ths_skill",
    "tonghuashun": "ths_skill",
    "同花顺": "ths_skill",
}

PROVIDER_CATALOG: dict[str, dict[str, Any]] = {
    "tushare": {
        "display_name": "Tushare Pro",
        "class_name": "TushareProvider",
        "capabilities": ["universe", "history", "financial", "quote"],
        "credential_fields": ["tushare_token"],
        "default_chain": True,
        "suitability": "A股主数据源，适合行情、历史K线、基础财务和估值。",
        "limitations": ["需要用户本地维护 TUSHARE_TOKEN。"],
    },
    "baostock": {
        "display_name": "Baostock",
        "class_name": "BaostockProvider",
        "capabilities": ["universe", "history", "quote"],
        "credential_fields": [],
        "default_chain": True,
        "suitability": "免费A股历史行情补充源，适合在 Tushare 不可用时补 K 线。",
        "limitations": ["不提供本系统所需的完整财务快照，财务数据会继续降级。"],
    },
    "akshare": {
        "display_name": "AkShare",
        "class_name": "AkShareProvider",
        "capabilities": ["universe", "history", "financial", "quote"],
        "credential_fields": [],
        "default_chain": True,
        "suitability": "免费A股综合数据源，适合兜底股票池、行情、估值和部分财务指标。",
        "limitations": ["公开网页源可能受限流或字段变化影响。"],
    },
    "adata": {
        "display_name": "AData",
        "class_name": "ADataProvider",
        "capabilities": ["universe", "history", "quote"],
        "credential_fields": [],
        "default_chain": False,
        "suitability": "A股本地量化数据工具，可作为轻量历史行情补充。",
        "limitations": ["第三方包 API 版本差异较大，默认不放入主链。"],
    },
    "openbb": {
        "display_name": "OpenBB",
        "class_name": "OpenBBProvider",
        "capabilities": ["history", "quote"],
        "credential_fields": [],
        "default_chain": False,
        "suitability": "适合全球市场、宏观或港美股参照，不作为A股主数据源。",
        "limitations": ["依赖较重，默认不安装、不放入主链。"],
    },
    "aastock": {
        "display_name": "AAStock",
        "class_name": "",
        "capabilities": ["hk_news_reference"],
        "credential_fields": [],
        "default_chain": False,
        "suitability": "更适合港股新闻和市场参考，不直接适配当前A股行情模型。",
        "limitations": ["未接入非官方网页抓取；如后续使用需先确认授权和稳定 API。"],
    },
    "yfinance": {
        "display_name": "yfinance",
        "class_name": "YFinanceProvider",
        "capabilities": ["history", "quote"],
        "credential_fields": [],
        "default_chain": False,
        "suitability": "适合海外市场、港股或A股 Yahoo 映射代码的参考行情。",
        "limitations": ["A股覆盖和实时性不稳定，默认不作为A股主链。"],
    },
    "alpha_vantage": {
        "display_name": "Alpha Vantage",
        "class_name": "AlphaVantageProvider",
        "capabilities": ["history", "quote"],
        "credential_fields": ["alpha_vantage_api_key"],
        "default_chain": False,
        "suitability": "适合海外市场、宏观参照和少量全球股票接口。",
        "limitations": ["需要 ALPHA_VANTAGE_API_KEY；免费额度和A股覆盖有限。"],
    },
    "jqdata": {
        "display_name": "JQData / 聚宽",
        "class_name": "JQDataProvider",
        "capabilities": ["universe", "history", "quote"],
        "credential_fields": ["jqdata_username", "jqdata_password"],
        "default_chain": False,
        "suitability": "适合有聚宽账号时补充A股研究数据。",
        "limitations": ["需要本地 JQDATA_USERNAME/JQDATA_PASSWORD；授权和额度由用户账号决定。"],
    },
    "ths_skill": {
        "display_name": "同花顺 Skill / 数据能力",
        "class_name": "",
        "capabilities": ["manual_research_skill"],
        "credential_fields": [],
        "default_chain": False,
        "suitability": "适合未来沉淀人工研究流程或合规插件，不直接进入行情 provider chain。",
        "limitations": ["当前不做未授权爬取，也不接入真实下单。"],
    },
}


def normalize_provider_name(source: str) -> str:
    """Normalize provider aliases from config/UI to registry keys."""
    key = source.strip().lower().replace(" ", "_")
    return PROVIDER_ALIASES.get(key, key)


def provider_supports(source: str, capability: str) -> bool:
    """Return whether a provider advertises one normalized capability."""
    name = normalize_provider_name(source)
    capabilities = PROVIDER_CATALOG.get(name, {}).get("capabilities", [])
    return capability in capabilities


def build_provider_catalog(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Return public provider metadata and credential presence flags."""
    settings = settings or load_settings()
    configured_chain = [normalize_provider_name(item) for item in getattr(settings.data, "provider_chain", [])]
    items: list[dict[str, Any]] = []
    for source, spec in PROVIDER_CATALOG.items():
        credential_fields = [str(item) for item in spec.get("credential_fields", [])]
        missing_credentials = [
            field_name
            for field_name in credential_fields
            if not str(getattr(settings.data, field_name, "") or "").strip()
        ]
        items.append(
            {
                "source": source,
                "display_name": spec.get("display_name", source),
                "capabilities": list(spec.get("capabilities", [])),
                "configured": source in configured_chain,
                "default_chain": bool(spec.get("default_chain", False)),
                "requires_credentials": bool(credential_fields),
                "has_credentials": not missing_credentials,
                "missing_credentials": missing_credentials,
                "adapter_available": bool(spec.get("class_name")),
                "suitability": spec.get("suitability", ""),
                "limitations": list(spec.get("limitations", [])),
            }
        )
    return items


def default_provider_chain() -> list[str]:
    """Return the online provider fallback chain used when config is empty."""
    return list(DEFAULT_PROVIDER_CHAIN)


class DataAgent:
    """Fetch market data, using checked-in sample data when providers are absent."""

    def __init__(self, settings: Settings | None = None, data_path: str | None = None) -> None:
        self.settings = settings or load_settings()
        self.data_path = self._resolve_path(data_path or self.settings.data.offline_data_path)
        self._offline_payload: dict[str, Any] | None = None
        self._provider_cache: dict[str, Any] = {}
        self._provider_attempts: list[dict[str, str]] = []

    def _get_tushare_provider(self) -> Any | None:
        """Lazy load Tushare provider if token is available."""
        return self._get_provider("tushare")

    def _get_akshare_provider(self) -> Any | None:
        """Lazy load AkShare provider as fallback."""
        return self._get_provider("akshare")

    def provider_catalog(self) -> list[dict[str, Any]]:
        """Return data-source metadata without exposing local credentials."""
        return build_provider_catalog(self.settings)

    def provider_diagnostics(self) -> dict[str, Any]:
        """Return provider-chain diagnostics for GUI/TUI/debug views."""
        return {
            "mode": self.settings.data.mode,
            "provider_chain": self._configured_provider_chain(),
            "catalog": self.provider_catalog(),
            "attempts": list(self._provider_attempts[-50:]),
            "offline_data_path": str(self.data_path),
        }

    def get_universe(self) -> list[StockIdentity]:
        """Get stock universe from online providers, then offline samples."""
        if self.settings.data.mode != "offline":
            for source, provider in self._iter_online_providers("universe"):
                try:
                    limit = getattr(self.settings.data, "dynamic_universe_limit", None)
                    stocks = provider.get_universe(limit=limit)
                    if stocks:
                        self._record_provider_attempt(source, "universe", "ok", f"{len(stocks)} stocks")
                        logger.info("Fetched %s stocks from %s", len(stocks), source)
                        return stocks
                    self._record_provider_attempt(source, "universe", "empty", "no stocks returned")
                except Exception as exc:
                    self._record_provider_attempt(source, "universe", "error", str(exc))
                    logger.warning("%s universe fetch failed: %s", source, exc)
        
        # Final fallback to offline data
        payload = self._load_offline_payload()
        self._record_provider_attempt("offline", "universe", "ok", "sample data")
        return [
            StockIdentity(
                stock_code=str(item["code"]),
                stock_name=str(item.get("name", item["code"])),
                sector=str(item.get("sector", "")),
            )
            for item in payload.get("stocks", [])
        ]

    def get_history(self, stock_code: str, days: int | None = None) -> list[StockBar]:
        """Get historical bars from provider chain, then offline samples."""
        days = days or 30
        
        if self.settings.data.mode != "offline":
            for source, provider in self._iter_online_providers("history"):
                try:
                    kwargs = self._history_kwargs_for_provider(source)
                    bars = provider.get_history(stock_code, days=days, **kwargs)
                    if bars:
                        self._record_provider_attempt(source, "history", "ok", f"{stock_code}: {len(bars)} bars")
                        logger.info("Fetched %s bars for %s from %s", len(bars), stock_code, source)
                        return bars
                    self._record_provider_attempt(source, "history", "empty", stock_code)
                except Exception as exc:
                    self._record_provider_attempt(source, "history", "error", f"{stock_code}: {exc}")
                    logger.warning("%s history fetch failed for %s: %s", source, stock_code, exc)
        
        # Final fallback to offline data
        record = self._get_stock_record(stock_code, strict=False)
        bars = [self._bar_from_raw(stock_code, raw) for raw in record.get("history", [])]
        bars.sort(key=lambda bar: bar.date)
        status = "ok" if bars else "empty"
        detail = stock_code if bars else f"{stock_code}: no offline sample"
        self._record_provider_attempt("offline", "history", status, detail)
        if days is not None and days > 0:
            return bars[-days:]
        return bars

    def get_financial(self, stock_code: str) -> FinancialSnapshot:
        """Get financial data from provider chain, then offline samples."""
        if self.settings.data.mode != "offline":
            for source, provider in self._iter_online_providers("financial"):
                try:
                    snapshot = provider.get_financial(stock_code)
                    self._record_provider_attempt(source, "financial", "ok", stock_code)
                    return snapshot
                except Exception as exc:
                    self._record_provider_attempt(source, "financial", "error", f"{stock_code}: {exc}")
                    logger.warning("%s financial fetch failed for %s: %s", source, stock_code, exc)
        
        # Final fallback to offline data
        record = self._get_stock_record(stock_code, strict=False)
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
        """Get latest quote from provider chain, then offline samples."""
        if self.settings.data.mode != "offline":
            for source, provider in self._iter_online_providers("quote"):
                try:
                    quote = provider.get_quote(stock_code)
                    self._record_provider_attempt(source, "quote", "ok", stock_code)
                    return quote
                except Exception as exc:
                    self._record_provider_attempt(source, "quote", "error", f"{stock_code}: {exc}")
                    logger.warning("%s quote fetch failed for %s: %s", source, stock_code, exc)
        
        # Final fallback to offline data
        record = self._get_stock_record(stock_code, strict=False)
        quote = record.get("quote") or {}
        if not quote:
            bars = self.get_history(stock_code, days=2)
            if not bars:
                self._record_provider_attempt("offline", "quote", "empty", f"{stock_code}: no quote or history")
                return StockQuote(
                    stock_code=str(record["code"]),
                    stock_name=str(record.get("name", record["code"])),
                    date=str(self._load_offline_payload().get("as_of", "")),
                    price=0.0,
                    change_pct=0.0,
                    volume=0.0,
                    amount=0.0,
                    sector=str(record.get("sector", "")),
                )
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
        """Return whether at least one configured online provider can initialize.

        The project remains offline-capable; provider refresh never blocks the
        fallback sample data path.
        """
        if self.settings.data.mode == "offline":
            return False
        return any(provider is not None for _, provider in self._iter_online_providers())

    def _configured_provider_chain(self) -> list[str]:
        raw_chain = getattr(self.settings.data, "provider_chain", None) or DEFAULT_PROVIDER_CHAIN
        chain: list[str] = []
        for item in raw_chain:
            name = normalize_provider_name(str(item))
            if name and name in PROVIDER_CATALOG and name not in chain:
                chain.append(name)
        return chain or list(DEFAULT_PROVIDER_CHAIN)

    def _iter_online_providers(self, capability: str | None = None):
        for source in self._configured_provider_chain():
            if capability and not provider_supports(source, capability):
                self._record_provider_attempt(source, capability, "skipped", "capability not supported")
                continue
            provider = self._get_provider(source)
            if provider is not None:
                yield source, provider

    def _get_provider(self, source: str) -> Any | None:
        name = normalize_provider_name(source)
        if not name:
            return None
        if name in self._provider_cache:
            return self._provider_cache[name]

        spec = PROVIDER_CATALOG.get(name)
        if not spec:
            self._record_provider_attempt(name, "init", "skipped", "unknown provider")
            return None
        class_name = str(spec.get("class_name", ""))
        if not class_name:
            self._record_provider_attempt(name, "init", "skipped", "no provider adapter")
            return None
        missing = self._missing_credentials(name)
        if missing:
            self._record_provider_attempt(name, "init", "skipped", f"missing credentials: {', '.join(missing)}")
            return None

        try:
            import astock_agent_system.data.providers as provider_module

            provider_class = getattr(provider_module, class_name)
            provider = self._instantiate_provider(name, provider_class)
            self._provider_cache[name] = provider
            self._record_provider_attempt(name, "init", "ok", class_name)
            logger.info("%s provider initialized", name)
            return provider
        except Exception as exc:
            self._record_provider_attempt(name, "init", "error", str(exc))
            logger.warning("Failed to initialize %s provider: %s", name, exc)
            return None

    def _instantiate_provider(self, source: str, provider_class: Any) -> Any:
        if source == "tushare":
            return provider_class(token=self.settings.data.tushare_token)
        if source == "alpha_vantage":
            return provider_class(api_key=self.settings.data.alpha_vantage_api_key)
        if source == "jqdata":
            return provider_class(
                username=self.settings.data.jqdata_username,
                password=self.settings.data.jqdata_password,
            )
        return provider_class()

    def _missing_credentials(self, source: str) -> list[str]:
        missing: list[str] = []
        for field_name in PROVIDER_CATALOG.get(source, {}).get("credential_fields", []):
            if not str(getattr(self.settings.data, str(field_name), "") or "").strip():
                missing.append(str(field_name))
        return missing

    @staticmethod
    def _history_kwargs_for_provider(source: str) -> dict[str, Any]:
        if source == "tushare":
            return {"freq": "D"}
        if source == "akshare":
            return {"freq": "daily"}
        return {}

    def _record_provider_attempt(self, source: str, operation: str, status: str, detail: str = "") -> None:
        self._provider_attempts.append(
            {
                "source": source,
                "operation": operation,
                "status": status,
                "detail": detail[:300],
            }
        )
        self._provider_attempts = self._provider_attempts[-100:]

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

    def _get_stock_record(self, stock_code: str, *, strict: bool = True) -> dict[str, Any]:
        for item in self._load_offline_payload().get("stocks", []):
            if str(item.get("code")) == str(stock_code):
                return item
        if strict:
            raise KeyError(f"Stock code not found in offline data: {stock_code}")
        self._record_provider_attempt("offline", "fallback", "missing", f"{stock_code}: generated conservative placeholder")
        return {
            "code": str(stock_code),
            "name": str(stock_code),
            "sector": "",
            "history": [],
            "quote": {},
            "financial": {
                "report_date": self._load_offline_payload().get("as_of", ""),
                "pe_ttm": 0.0,
                "pb": 0.0,
                "roe": 0.0,
                "debt_ratio": 0.0,
                "revenue_growth": 0.0,
                "profit_growth": 0.0,
                "market_cap": 0.0,
            },
        }

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
