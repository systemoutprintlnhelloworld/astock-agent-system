"""Market data providers for A-share."""

from astock_agent_system.data.providers.tushare_provider import TushareProvider
from astock_agent_system.data.providers.akshare_provider import AkShareProvider

__all__ = ["TushareProvider", "AkShareProvider"]
