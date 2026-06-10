"""Data access layer with an offline-first fallback."""

from __future__ import annotations

import hashlib
import json
import importlib.util
import logging
import os
import queue
import threading
from pathlib import Path
from typing import Any

from astock_agent_system.config import PROJECT_ROOT, Settings, load_settings
from astock_agent_system.data.cache import MarketDataCache
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
        "dependency_module": "tushare",
        "capabilities": ["universe", "history", "financial", "quote"],
        "credential_fields": ["tushare_token"],
        "default_chain": True,
        "suitability": "A股主数据源，适合行情、历史K线、基础财务和估值。",
        "limitations": ["需要用户本地维护 TUSHARE_TOKEN。"],
    },
    "baostock": {
        "display_name": "Baostock",
        "class_name": "BaostockProvider",
        "dependency_module": "baostock",
        "capabilities": ["universe", "history", "financial", "quote"],
        "credential_fields": [],
        "default_chain": True,
        "suitability": "免费A股历史行情补充源，适合在 Tushare 不可用时补 K 线和生成保守财务占位。",
        "limitations": ["不提供完整财务指标；financial 仅返回基于行情的保守占位，PE/PB/ROE 等为 0。"],
    },
    "akshare": {
        "display_name": "AkShare",
        "class_name": "AkShareProvider",
        "dependency_module": "akshare",
        "capabilities": ["universe", "history", "financial", "quote"],
        "credential_fields": [],
        "default_chain": True,
        "suitability": "免费A股综合数据源，适合兜底股票池、行情、估值和部分财务指标。",
        "limitations": ["公开网页源可能受限流或字段变化影响。"],
    },
    "adata": {
        "display_name": "AData",
        "class_name": "ADataProvider",
        "dependency_module": "adata",
        "capabilities": ["universe", "history", "quote"],
        "credential_fields": [],
        "default_chain": False,
        "suitability": "A股本地量化数据工具，可作为轻量历史行情补充。",
        "limitations": ["第三方包 API 版本差异较大，默认不放入主链。"],
    },
    "openbb": {
        "display_name": "OpenBB",
        "class_name": "OpenBBProvider",
        "dependency_module": "openbb",
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
        "dependency_module": "yfinance",
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
        "dependency_module": "jqdatasdk",
        "capabilities": ["universe", "history", "financial", "quote"],
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
        dependency_module = str(spec.get("dependency_module", ""))
        dependency_installed = True
        if dependency_module:
            dependency_installed = importlib.util.find_spec(dependency_module) is not None
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
                "dependency_module": dependency_module,
                "dependency_installed": dependency_installed,
                "suitability": spec.get("suitability", ""),
                "limitations": list(spec.get("limitations", [])),
            }
        )
    return items


def default_provider_chain() -> list[str]:
    """Return the online provider fallback chain used when config is empty."""
    return list(DEFAULT_PROVIDER_CHAIN)


def _provider_timeout_seconds() -> float:
    """Return the hard timeout for one external data-provider operation."""
    raw_value = os.getenv("DATA_PROVIDER_TIMEOUT_SECONDS", "15")
    try:
        return max(0.5, float(raw_value))
    except (TypeError, ValueError):
        return 15.0


class DataAgent:
    """Fetch market data, using checked-in sample data when providers are absent."""

    def __init__(self, settings: Settings | None = None, data_path: str | None = None) -> None:
        self.settings = settings or load_settings()
        self.data_path = self._resolve_path(data_path or self.settings.data.offline_data_path)
        self._offline_payload: dict[str, Any] | None = None
        self._provider_cache: dict[str, Any] = {}
        self._provider_attempts: list[dict[str, str]] = []
        self._provider_cooldowns: dict[tuple[str, str], str] = {}
        self._provider_global_cooldowns: dict[str, str] = {}
        self._universe_cache: list[StockIdentity] | None = None
        self._history_cache: dict[tuple[str, int], list[StockBar]] = {}
        self._financial_cache: dict[str, FinancialSnapshot] = {}
        self._quote_cache: dict[str, StockQuote] = {}
        self._market_cache = MarketDataCache(root=self._market_cache_root())

    def _market_cache_root(self) -> Path:
        """Scope persistent cache by data mode and provider chain."""
        chain = ",".join(self._configured_provider_chain())
        raw_key = f"mode={self.settings.data.mode};chain={chain}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:12]
        return PROJECT_ROOT / "data" / "market_cache" / digest

    def _persistent_cache_enabled(self) -> bool:
        """Return whether file-based provider cache should be used."""
        return self.settings.data.mode != "offline" and not os.getenv("PYTEST_CURRENT_TEST")

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
            "cooldowns": [
                {"source": source, "operation": operation, "reason": reason}
                for (source, operation), reason in self._provider_cooldowns.items()
            ],
            "global_cooldowns": [
                {"source": source, "reason": reason}
                for source, reason in self._provider_global_cooldowns.items()
            ],
            "offline_data_path": str(self.data_path),
        }

    def get_universe(self) -> list[StockIdentity]:
        """Get stock universe from online providers, then offline samples."""
        if self._universe_cache is not None:
            self._record_provider_attempt("cache", "universe", "ok", f"{len(self._universe_cache)} stocks")
            return list(self._universe_cache)
        if self.settings.data.mode != "offline":
            for source, provider in self._iter_online_providers("universe"):
                try:
                    limit = getattr(self.settings.data, "dynamic_universe_limit", None)
                    stocks = self._run_provider_call(
                        source,
                        "universe",
                        lambda: provider.get_universe(limit=limit),
                    )
                    if stocks:
                        self._record_provider_attempt(source, "universe", "ok", f"{len(stocks)} stocks")
                        logger.info("Fetched %s stocks from %s", len(stocks), source)
                        self._universe_cache = list(stocks)
                        return stocks
                    self._record_provider_attempt(source, "universe", "empty", "no stocks returned")
                except Exception as exc:
                    self._record_provider_attempt(source, "universe", "error", str(exc))
                    self._cooldown_provider(source, "universe", exc)
                    logger.warning("%s universe fetch failed: %s", source, exc)
        
        # Final fallback to offline data
        payload = self._load_offline_payload()
        self._record_provider_attempt("offline", "universe", "ok", "sample data")
        stocks = [
            StockIdentity(
                stock_code=str(item["code"]),
                stock_name=str(item.get("name", item["code"])),
                sector=str(item.get("sector", "")),
            )
            for item in payload.get("stocks", [])
        ]
        self._universe_cache = list(stocks)
        return stocks

    def get_history(self, stock_code: str, days: int | None = None) -> list[StockBar]:
        """Get historical bars from provider chain, then offline samples."""
        days = days or 30
        cache_key = (str(stock_code), int(days))
        if cache_key in self._history_cache:
            bars = self._history_cache[cache_key]
            self._record_provider_attempt("cache", "history", "ok", f"{stock_code}: {len(bars)} bars")
            return list(bars)
        cached_bars = self._market_cache.get_history(str(stock_code), int(days)) if self._persistent_cache_enabled() else None
        if cached_bars:
            self._record_provider_attempt("file_cache", "history", "ok", f"{stock_code}: {len(cached_bars)} bars")
            self._history_cache[cache_key] = list(cached_bars)
            return list(cached_bars)
        
        if self.settings.data.mode != "offline":
            for source, provider in self._iter_online_providers("history"):
                try:
                    kwargs = self._history_kwargs_for_provider(source)
                    bars = self._run_provider_call(
                        source,
                        "history",
                        lambda: provider.get_history(stock_code, days=days, **kwargs),
                    )
                    if bars:
                        self._record_provider_attempt(source, "history", "ok", f"{stock_code}: {len(bars)} bars")
                        logger.info("Fetched %s bars for %s from %s", len(bars), stock_code, source)
                        self._history_cache[cache_key] = list(bars)
                        if self._persistent_cache_enabled():
                            self._market_cache.set_history(str(stock_code), int(days), list(bars))
                        return bars
                    self._record_provider_attempt(source, "history", "empty", stock_code)
                except Exception as exc:
                    self._record_provider_attempt(source, "history", "error", f"{stock_code}: {exc}")
                    self._cooldown_provider(source, "history", exc)
                    logger.warning("%s history fetch failed for %s: %s", source, stock_code, exc)
        
        # Final fallback to offline data
        record = self._get_stock_record(stock_code, strict=False)
        bars = [self._bar_from_raw(stock_code, raw) for raw in record.get("history", [])]
        bars.sort(key=lambda bar: bar.date)
        status = "ok" if bars else "empty"
        detail = stock_code if bars else f"{stock_code}: no offline sample"
        self._record_provider_attempt("offline", "history", status, detail)
        if days is not None and days > 0:
            bars = bars[-days:]
        self._history_cache[cache_key] = list(bars)
        return bars

    def get_financial(self, stock_code: str) -> FinancialSnapshot:
        """Get financial data from provider chain, then offline samples."""
        stock_key = str(stock_code)
        if stock_key in self._financial_cache:
            self._record_provider_attempt("cache", "financial", "ok", stock_key)
            return self._financial_cache[stock_key]
        cached_snapshot = self._market_cache.get_financial(stock_key) if self._persistent_cache_enabled() else None
        if cached_snapshot is not None:
            self._record_provider_attempt("file_cache", "financial", "ok", stock_key)
            self._financial_cache[stock_key] = cached_snapshot
            return cached_snapshot
        if self.settings.data.mode != "offline":
            for source, provider in self._iter_online_providers("financial"):
                try:
                    snapshot = self._run_provider_call(
                        source,
                        "financial",
                        lambda: provider.get_financial(stock_code),
                    )
                    self._record_provider_attempt(source, "financial", "ok", stock_code)
                    self._financial_cache[stock_key] = snapshot
                    if self._persistent_cache_enabled():
                        self._market_cache.set_financial(stock_key, snapshot)
                    return snapshot
                except Exception as exc:
                    self._record_provider_attempt(source, "financial", "error", f"{stock_code}: {exc}")
                    self._cooldown_provider(source, "financial", exc)
                    logger.warning("%s financial fetch failed for %s: %s", source, stock_code, exc)
        
        # Final fallback to offline data
        record = self._get_stock_record(stock_code, strict=False)
        raw = record.get("financial", {})
        snapshot = FinancialSnapshot(
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
        self._financial_cache[stock_key] = snapshot
        return snapshot

    def get_quote(self, stock_code: str) -> StockQuote:
        """Get latest quote from provider chain, then offline samples."""
        stock_key = str(stock_code)
        if stock_key in self._quote_cache:
            self._record_provider_attempt("cache", "quote", "ok", stock_key)
            return self._quote_cache[stock_key]
        cached_quote = self._market_cache.get_quote(stock_key) if self._persistent_cache_enabled() else None
        if cached_quote is not None:
            self._record_provider_attempt("file_cache", "quote", "ok", stock_key)
            self._quote_cache[stock_key] = cached_quote
            return cached_quote
        if self.settings.data.mode != "offline":
            for source, provider in self._iter_online_providers("quote"):
                try:
                    quote = self._run_provider_call(
                        source,
                        "quote",
                        lambda: provider.get_quote(stock_code),
                    )
                    self._record_provider_attempt(source, "quote", "ok", stock_code)
                    self._quote_cache[stock_key] = quote
                    if self._persistent_cache_enabled():
                        self._market_cache.set_quote(stock_key, quote)
                    return quote
                except Exception as exc:
                    self._record_provider_attempt(source, "quote", "error", f"{stock_code}: {exc}")
                    self._cooldown_provider(source, "quote", exc)
                    logger.warning("%s quote fetch failed for %s: %s", source, stock_code, exc)
        
        # Final fallback to offline data
        record = self._get_stock_record(stock_code, strict=False)
        quote = record.get("quote") or {}
        if not quote:
            bars = self.get_history(stock_code, days=2)
            if not bars:
                self._record_provider_attempt("offline", "quote", "empty", f"{stock_code}: no quote or history")
                quote_obj = StockQuote(
                    stock_code=str(record["code"]),
                    stock_name=str(record.get("name", record["code"])),
                    date=str(self._load_offline_payload().get("as_of", "")),
                    price=0.0,
                    change_pct=0.0,
                    volume=0.0,
                    amount=0.0,
                    sector=str(record.get("sector", "")),
                )
                self._quote_cache[stock_key] = quote_obj
                return quote_obj
            latest = bars[-1]
            previous_close = bars[-2].close if len(bars) > 1 else latest.close
            change_pct = (latest.close - previous_close) / previous_close if previous_close else 0.0
            quote_obj = StockQuote(
                stock_code=str(record["code"]),
                stock_name=str(record.get("name", record["code"])),
                date=latest.date,
                price=latest.close,
                change_pct=change_pct,
                volume=latest.volume,
                amount=latest.amount,
                sector=str(record.get("sector", "")),
            )
            self._quote_cache[stock_key] = quote_obj
            return quote_obj
        quote_obj = StockQuote(
            stock_code=str(record["code"]),
            stock_name=str(record.get("name", record["code"])),
            date=str(quote.get("date", self._load_offline_payload().get("as_of", ""))),
            price=float(quote.get("price", 0.0)),
            change_pct=float(quote.get("change_pct", 0.0)),
            volume=float(quote.get("volume", 0.0)),
            amount=float(quote.get("amount", 0.0)),
            sector=str(record.get("sector", "")),
        )
        self._quote_cache[stock_key] = quote_obj
        return quote_obj

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
            if source in self._provider_global_cooldowns:
                self._record_provider_attempt(source, capability or "init", "skipped", self._provider_global_cooldowns[source])
                continue
            if capability and not provider_supports(source, capability):
                self._record_provider_attempt(source, capability, "skipped", "capability not supported")
                continue
            if capability and (source, capability) in self._provider_cooldowns:
                self._record_provider_attempt(source, capability, "skipped", self._provider_cooldowns[(source, capability)])
                continue
            provider = self._get_provider(source)
            if provider is not None:
                yield source, provider

    def _run_provider_call(self, source: str, operation: str, func: Any) -> Any:
        """Run an external provider call with a hard timeout.

        Free web sources such as AkShare and Baostock can occasionally hang in
        third-party network code. Online CLI runs must remain bounded and fall
        through the provider chain instead of turning into a long-running wait.
        """
        timeout_seconds = _provider_timeout_seconds()
        result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

        def _target() -> None:
            try:
                result_queue.put(("ok", func()))
            except Exception as exc:  # pragma: no cover - depends on external providers
                result_queue.put(("error", exc))

        worker = threading.Thread(target=_target, daemon=True, name=f"data-provider-{source}-{operation}")
        worker.start()
        worker.join(timeout_seconds)
        if worker.is_alive():
            raise TimeoutError(f"{source} {operation} exceeded {timeout_seconds:.1f}s")
        status, value = result_queue.get_nowait()
        if status == "error":
            raise value
        return value

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
        dependency_module = str(spec.get("dependency_module", ""))
        if dependency_module and importlib.util.find_spec(dependency_module) is None:
            self._record_provider_attempt(name, "init", "skipped", f"dependency not installed: {dependency_module}")
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

    def _cooldown_provider(self, source: str, operation: str, exc: Exception) -> None:
        """Skip repeated calls to a provider operation after likely run-wide failures."""
        text = str(exc)
        lower = text.lower()
        transient_markers = [
            "频率超限",
            "rate limit",
            "remote end closed connection",
            "connection aborted",
            "timeout",
            "timed out",
            "exceeded",
            "not installed",
        ]
        if any(marker in lower or marker in text for marker in transient_markers):
            self._provider_cooldowns[(source, operation)] = f"cooldown after previous error: {text[:220]}"
        sourcewide_markers = [
            "频率超限",
            "rate limit",
            "quota",
            "remote end closed connection",
            "connection aborted",
            "timeout",
            "timed out",
            "exceeded",
            "not installed",
        ]
        if any(marker in lower or marker in text for marker in sourcewide_markers):
            self._provider_global_cooldowns[source] = f"source cooldown after previous error: {text[:220]}"

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
