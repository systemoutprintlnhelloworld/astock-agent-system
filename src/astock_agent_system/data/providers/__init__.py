"""Market data providers for A-share."""

from astock_agent_system.data.providers.akshare_provider import AkShareProvider
from astock_agent_system.data.providers.adata_provider import ADataProvider
from astock_agent_system.data.providers.alpha_vantage_provider import AlphaVantageProvider
from astock_agent_system.data.providers.baostock_provider import BaostockProvider
from astock_agent_system.data.providers.ifind_provider import IfindProvider
from astock_agent_system.data.providers.jqdata_provider import JQDataProvider
from astock_agent_system.data.providers.openbb_provider import OpenBBProvider
from astock_agent_system.data.providers.tushare_provider import TushareProvider
from astock_agent_system.data.providers.yfinance_provider import YFinanceProvider

__all__ = [
    "ADataProvider",
    "AkShareProvider",
    "AlphaVantageProvider",
    "BaostockProvider",
    "IfindProvider",
    "JQDataProvider",
    "OpenBBProvider",
    "TushareProvider",
    "YFinanceProvider",
]
