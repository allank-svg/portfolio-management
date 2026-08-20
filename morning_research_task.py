"""
Morning Research Task
Runs at market open (9:30 AM ET) on trading days
Executes: Daily research → Auto-acquisitions → Rebalancing → Notifications
"""

import json
from datetime import datetime, time
import requests
from config import HOLDINGS, CASH
from research_engine import get_daily_research
from portfolio_analyzer import get_acquisition_candidates
from portfolio_manager import get_portfolio_performance
from trade_executor import TradeExecutor, TradeConfig

def is_trading_day():
    """Check if today is a trading day (Monday-Friday)"""
    from datetime import datetime
    today = datetime.now().weekday()
    return today < 5  # Monday=0, Friday=4

def get_portfolio_from_cache():
    """Load current portfolio from quote cache"""
    try:
        with open("quote_cache.json", "r") as f:
            quotes = json.load(f)
    except:
        quotes = {}

    # Build portfolio
    positions = []
    total_invested = sum(h['invested'] for h in HOLDINGS)
    total_value = 0

    for holding in HOLDINGS:
        sym = holding["symbol"]
        qty = holding["qty"]
        invested = holding["invested"]

        if sym in quotes:
            last = quotes[sym].get("last", holding["avg_cost"])
        else:
            last = holding["avg_cost"]

        val = qty * last
        total_value += val

        positions.append({
            'symbol': sym,
            'position_value': val,
            'qty': qty,
            'current_price': last
        })

    return {
        'positions': positions,
        'kpis': {
            'account_value': total_value + CASH,
            'equity_value': total_value,
            'cash': CASH,
            'invested': total_invested
        }
    }

def run_morning_research():
    """Execute full morning research workflow"""
    print(f"[{datetime.now()}] Starting morning research workflow...")

    if not is_trading_day():
        print("Not a trading day, skipping...")
        return

    # Step 1: Run research
    print("Step 1: Running daily research...")
    research = get_daily_research()
    print(f"  - Scored {research['summary']['total_scored']} holdings")
    print(f"  - Found {research['summary'].get('acquisition_candidates_count', 0)} new opportunities")

    # Step 2: Get current portfolio
    print("Step 2: Loading current portfolio...")
    portfolio = get_portfolio_from_cache()
    print(f"  - Account value: ${portfolio['kpis']['account_value']:,.2f}")
    print(f"  - Cash available: ${portfolio['kpis']['cash']:,.2f}")
    print(f"  - Positions: {len(portfolio['positions'])}")

    # Step 3: Process acquisitions & rebalancing
    print("Step 3: Evaluating new acquisitions...")
    config = TradeConfig.load()
    executor = TradeExecutor(config)

    executed_acq, pending_acq, alerts = executor.process_acquisitions_with_rebalancing(
        research.get('acquisition_candidates', []),
        portfolio,
        research,
        {}
    )

    print(f"  - Executed acquisitions: {len(executed_acq)}")
    print(f"  - Pending acquisitions: {len(pending_acq)}")
    print(f"  - Cash alerts: {len(alerts)}")

    # Step 4: Process existing holdings trades
    print("Step 4: Processing holdings recommendations...")
    decisions = executor.generate_trade_decisions(research, portfolio, {})
    executed_trades, pending_trades = executor.execute_trades(decisions, portfolio, {})

    print(f"  - Executed trades: {len(executed_trades)}")
    print(f"  - Pending approval: {len(pending_trades)}")

    # Step 5: Save results
    results = {
        'timestamp': research['timestamp'],
        'trading_day': True,
        'research_summary': research['summary'],
        'acquisitions_executed': len(executed_acq),
        'acquisitions_pending': len(pending_acq),
        'trades_executed': len(executed_trades),
        'trades_pending': len(pending_trades),
        'cash_alerts': len(alerts),
        'portfolio_snapshot': {
            'account_value': portfolio['kpis']['account_value'],
            'cash': portfolio['kpis']['cash'],
            'positions': len(portfolio['positions'])
        }
    }

    # Log results
    try:
        with open("morning_research_log.jsonl", "a") as f:
            f.write(json.dumps(results) + "\n")
    except:
        pass

    print(f"[{datetime.now()}] Morning research complete!")
    print(json.dumps(results, indent=2))

    return results

if __name__ == "__main__":
    run_morning_research()
