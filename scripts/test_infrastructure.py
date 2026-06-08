"""Test script for real-time data providers and storage layer."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from astock_agent_system.config import load_settings
from astock_agent_system.data.data_agent import DataAgent


def test_data_providers():
    """Test configured market providers with fallback to offline."""
    print("=" * 60)
    print("Testing Data Providers (provider chain -> Offline)")
    print("=" * 60)
    
    settings = load_settings()
    print(f"Data mode: {settings.data.mode}")
    print(f"Provider chain: {', '.join(settings.data.provider_chain)}")
    
    data_agent = DataAgent(settings=settings)
    diagnostics = data_agent.provider_diagnostics()
    print("Configured providers:")
    for item in diagnostics.get("catalog", []):
        if item.get("configured"):
            print(f"  - {item.get('source')}: capabilities={','.join(item.get('capabilities', []))}")
    
    # Test 1: Get universe
    print("\n1. Testing get_universe()...")
    try:
        stocks = data_agent.get_universe()
        print(f"✓ Fetched {len(stocks)} stocks")
        if stocks:
            print(f"  Sample: {stocks[0].stock_code} {stocks[0].stock_name}")
    except Exception as exc:
        print(f"✗ Failed: {exc}")
    
    # Test 2: Get history
    print("\n2. Testing get_history(600519)...")
    try:
        bars = data_agent.get_history("600519", days=5)
        print(f"✓ Fetched {len(bars)} bars")
        if bars:
            latest = bars[-1]
            print(f"  Latest: {latest.date} Close={latest.close}")
    except Exception as exc:
        print(f"✗ Failed: {exc}")
    
    # Test 3: Get financial
    print("\n3. Testing get_financial(600519)...")
    try:
        financial = data_agent.get_financial("600519")
        print(f"✓ PE={financial.pe_ttm:.2f}, PB={financial.pb:.2f}, ROE={financial.roe:.2f}%")
    except Exception as exc:
        print(f"✗ Failed: {exc}")
    
    # Test 4: Get quote
    print("\n4. Testing get_quote(600519)...")
    try:
        quote = data_agent.get_quote("600519")
        print(f"✓ Price={quote.price:.2f}, Change={quote.change_pct*100:.2f}%")
    except Exception as exc:
        print(f"✗ Failed: {exc}")
    
    print("\n" + "=" * 60)
    print("Data Provider Tests Complete")
    print("=" * 60)


def test_storage_layer():
    """Test MongoDB and Redis storage."""
    print("\n" + "=" * 60)
    print("Testing Storage Layer (MongoDB + Redis)")
    print("=" * 60)
    
    # Test MongoDB
    print("\n[MongoDB Tests]")
    try:
        from astock_agent_system.storage import MongoClient
        
        mongo = MongoClient()
        
        # Test save trade
        print("\n1. Testing save_trade()...")
        trade_id = mongo.save_trade({
            "agent_id": "test-agent",
            "stock_code": "600519",
            "action": "BUY",
            "price": 1700.0,
            "shares": 100,
            "amount": 170000.0,
            "reason": "Test trade"
        })
        print(f"✓ Saved trade: {trade_id}")
        
        # Test get trades
        print("\n2. Testing get_trades()...")
        trades = mongo.get_trades(agent_id="test-agent", limit=5)
        print(f"✓ Retrieved {len(trades)} trades")
        
        # Test save position
        print("\n3. Testing save_position_snapshot()...")
        snapshot_id = mongo.save_position_snapshot({
            "agent_id": "test-agent",
            "equity": 1000000.0,
            "cash": 830000.0,
            "positions": [
                {
                    "stock_code": "600519",
                    "shares": 100,
                    "cost_basis": 1700.0,
                    "market_value": 170000.0,
                    "unrealized_pnl": 0.0
                }
            ],
            "daily_pnl": 0.0,
            "total_pnl": 0.0
        })
        print(f"✓ Saved position snapshot: {snapshot_id}")
        
        mongo.close()
        print("\n✓ MongoDB tests passed")
        
    except ImportError:
        print("✗ MongoDB not available (pymongo not installed)")
    except Exception as exc:
        print(f"✗ MongoDB tests failed: {exc}")
    
    # Test Redis
    print("\n[Redis Tests]")
    try:
        from astock_agent_system.storage import RedisClient
        
        redis = RedisClient()
        
        # Test cache market data
        print("\n1. Testing cache_market_data()...")
        success = redis.cache_market_data(
            "600519",
            "quote",
            {"price": 1700.0, "change_pct": 0.02},
            ttl=60
        )
        print(f"✓ Cached market data: {success}")
        
        # Test get market data
        print("\n2. Testing get_market_data()...")
        data = redis.get_market_data("600519", "quote")
        print(f"✓ Retrieved cached data: {data}")
        
        # Test LLM cache
        print("\n3. Testing cache_llm_response()...")
        success = redis.cache_llm_response(
            prompt="Test prompt",
            model="gpt-4",
            response={"content": "Test response"},
            ttl=3600
        )
        print(f"✓ Cached LLM response: {success}")
        
        # Test stats
        print("\n4. Testing get_stats()...")
        stats = redis.get_stats()
        if stats:
            print(f"✓ Hit rate: {stats.get('hit_rate', 0)*100:.1f}%")
        
        redis.close()
        print("\n✓ Redis tests passed")
        
    except ImportError:
        print("✗ Redis not available (redis not installed)")
    except Exception as exc:
        print(f"✗ Redis tests failed: {exc}")
    
    print("\n" + "=" * 60)
    print("Storage Layer Tests Complete")
    print("=" * 60)


if __name__ == "__main__":
    print("\n🚀 A股 LLM 投资系统 - 基础设施测试\n")
    
    test_data_providers()
    test_storage_layer()
    
    print("\n✅ All tests complete!")
    print("\nNext steps:")
    print("  1. Set TUSHARE_TOKEN in .env to enable real-time data")
    print("  2. Run docker-compose up -d to start MongoDB and Redis")
    print("  3. Install optional dependencies: pip install -e .[all]")
