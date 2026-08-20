
import json
from flask import Flask, render_template, jsonify, request, session, redirect
from datetime import datetime, timedelta
import os
from portfolio_analyzer import get_earnings_calendar, get_fair_value_models, get_options_flow, get_acquisition_candidates
from research_engine import get_daily_research
from portfolio_manager import get_portfolio_dashboard, get_yesterday_research, save_research_archive
from trade_executor import TradeExecutor, TradeConfig
from config import HOLDINGS, CASH, SPY_ENTRY
from robinhood_quotes import fetch_robinhood_quotes_live, load_quote_cache, get_quotes_with_metadata
 
app = Flask(__name__)
app.secret_key = "your-secret-key-change-this"  # Change this to something random
 
# Simple login credentials (change these)
VALID_USERNAME = "allan"
VALID_PASSWORD = "portfolio2026"
 
# Import Robinhood MCP tools
def get_quotes(symbols):
    """Fetch live quotes from Robinhood API"""
    try:
        # This is a placeholder - in production, call the Robinhood API
        # For now, return cached data from the last refresh
        cache_file = "quote_cache.json"
        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                return json.load(f)
    except:
        pass
    return {}
 
def get_portfolio_data():
    """Build portfolio data with live quotes"""
    # Get quotes (would call Robinhood API in production)
    quotes = get_quotes([h["symbol"] for h in HOLDINGS])
 
    rows = []
    tot_cost = tot_val = tot_day = 0
 
    for holding in HOLDINGS:
        sym = holding["symbol"]
        qty = holding["qty"]
        avg = holding["avg_cost"]
        cost = holding["invested"]
 
        # Get live price (fallback to avg_cost if not available)
        if sym in quotes:
            last = quotes[sym].get("last", avg)
            prevclose = quotes[sym].get("prevclose", avg)
        else:
            last = avg
            prevclose = avg
 
        val = qty * last
        pl = val - cost
        plp = 100 * pl / cost if cost else 0
        day = qty * (last - prevclose)
        dayp = 100 * (last - prevclose) / prevclose if prevclose else 0
 
        tot_cost += cost
        tot_val += val
        tot_day += day
 
        rows.append({
            "symbol": sym,
            "qty": qty,
            "avg": avg,
            "last": last,
            "val": val,
            "pl": pl,
            "plp": plp,
            "day": day,
            "dayp": dayp,
            "prevclose": prevclose,
            "thesis": holding["thesis"],
            "earnings": holding["earnings"],
        })
 
    tot_pl = tot_val - tot_cost
    acct = tot_val + CASH
    port_ret = 100 * tot_pl / tot_cost if tot_cost else 0
    spy_ret = 0  # Would calculate if SPY quote available
 
    # Generate alerts
    alerts = []
    for r in rows:
        if r["plp"] <= -8:
            alerts.append({
                "level": "red",
                "title": f"{r['symbol']} down {r['plp']:.1f}% from cost",
                "detail": "Approaching your −10% loss gate. Monitor will flag fundamental/macro breaks only."
            })
 
    return {
        "positions": sorted(rows, key=lambda x: x["dayp"], reverse=True),
        "kpis": {
            "account_value": acct,
            "equity_value": tot_val,
            "cash": CASH,
            "invested": tot_cost,
            "unrealized_pl": tot_pl,
            "unrealized_pl_pct": port_ret,
            "today_pl": tot_day,
            "vs_spy": port_ret - spy_ret,
        },
        "alerts": alerts,
        "timestamp": datetime.now().strftime("%A %d %b %Y, %-I:%M %p ET"),
    }
 
@app.route("/", methods=["GET", "POST"])
def login():
    """Login page"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
 
        if username == VALID_USERNAME and password == VALID_PASSWORD:
            session["logged_in"] = True
            session.permanent = True
            app.permanent_session_lifetime = timedelta(days=30)
            return redirect("/dashboard")
        else:
            return render_template("login.html", error="Invalid username or password")
 
    # If already logged in, redirect to dashboard
    if session.get("logged_in"):
        return redirect("/dashboard")
 
    return render_template("login.html")
 
@app.route("/dashboard")
def dashboard():
    """Serve the portfolio dashboard (primary interface - daily research & execution)"""
    if not session.get("logged_in"):
        return redirect("/")
    return render_template("portfolio_dashboard.html")
 
@app.route("/dashboard-analytics")
def dashboard_analytics():
    """Serve the detailed analytics dashboard (secondary)"""
    if not session.get("logged_in"):
        return redirect("/")
    return render_template("dashboard_v2.html")
 
@app.route("/dashboard_v2")
def dashboard_v2():
    """Redirect to unified dashboard"""
    if not session.get("logged_in"):
        return redirect("/")
    return redirect("/dashboard")
 
@app.route("/research")
def research():
    """Serve the Institutional Equity Review"""
    if not session.get("logged_in"):
        return redirect("/")
    try:
        # Try local path first, then Render path
        paths = [
            "Institutional_Equity_Review_2026-08-17.html",
            "/home/claude/Institutional_Equity_Review_2026-08-17.html",
        ]
        for path in paths:
            try:
                with open(path, "r") as f:
                    return f.read()
            except:
                continue
        return "<div style='color: #e6edf3; padding: 20px;'>Research page unavailable. Check back soon.</div>"
    except:
        return "<div style='color: #e6edf3; padding: 20px;'>Research page unavailable. Check back soon.</div>"
 
@app.route("/api/data")
def api_data():
    """API endpoint for live portfolio data"""
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_portfolio_data())
 
@app.route("/api/earnings-calendar")
def api_earnings_calendar():
    """API endpoint for earnings calendar"""
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_earnings_calendar())
 
@app.route("/api/fair-value")
def api_fair_value():
    """API endpoint for fair value models"""
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_fair_value_models())
 
@app.route("/api/options-flow")
def api_options_flow():
    """API endpoint for options flow data"""
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_options_flow())
 
@app.route("/api/acquisition-scan")
def api_acquisition_scan():
    """API endpoint for acquisition candidates"""
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({
        "candidates": get_acquisition_candidates(),
        "timestamp": datetime.now().strftime("%A %d %b %Y, %-I:%M %p ET"),
        "scan_criteria": {
            "earnings_growth": ">20% YoY",
            "thesis_clarity": "Required",
            "fair_value_gap": ">15% above current price",
            "diversification": "Low correlation to existing holdings"
        }
    })
 
@app.route("/api/research")
def api_research():
    """API endpoint: Daily exhaustive research report (broad → 20 → 10)"""
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    research = get_daily_research()
    # Save to archive for tracking history
    save_research_archive(research)
    return jsonify(research)
 
@app.route("/api/portfolio-today")
def api_portfolio_today():
    """API endpoint: Portfolio dashboard (today's performance + recommendation changes)"""
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
 
    # Load quotes
    try:
        with open("quote_cache.json", "r") as f:
            quotes = json.load(f)
    except:
        quotes = {}
 
    # Get today and yesterday research
    today_research = get_daily_research()
    yesterday_research = get_yesterday_research()
 
    # Build dashboard
    dashboard = get_portfolio_dashboard(quotes, today_research, yesterday_research)
    return jsonify(dashboard)
 
@app.route("/api/trade-config", methods=["GET", "POST"])
def api_trade_config():
    """API endpoint: Get/set trading configuration"""
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
 
    if request.method == "GET":
        config = TradeConfig.load()
        return jsonify(config.to_dict())
 
    elif request.method == "POST":
        data = request.json
        config = TradeConfig.load()
 
        # Update from request
        for key in data:
            if hasattr(config, key):
                setattr(config, key, data[key])
 
        config.save()
        return jsonify({"status": "saved", "config": config.to_dict()})
 
@app.route("/api/trade-decisions")
def api_trade_decisions():
    """API endpoint: Generate trade decisions based on today's research"""
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
 
    # Load data
    try:
        with open("quote_cache.json", "r") as f:
            quotes = json.load(f)
    except:
        quotes = {}
 
    # Get research and portfolio
    today_research = get_daily_research()
    portfolio = get_portfolio_data()
 
    # Generate trade decisions
    config = TradeConfig.load()
    executor = TradeExecutor(config)
    decisions = executor.generate_trade_decisions(today_research, portfolio, quotes)
 
    # Check which can auto-execute vs need approval
    executed, pending = executor.execute_trades(decisions, portfolio, quotes)
 
    return jsonify({
        "auto_executed": [
            {
                "symbol": d.symbol,
                "action": d.action,
                "amount": d.amount,
                "reason": d.reason,
                "score": d.research_score
            } for d in executed
        ],
        "pending_approval": [
            {
                "symbol": d.symbol,
                "action": d.action,
                "amount": d.amount,
                "reason": d.reason,
                "score": d.research_score,
                "approval_reason": d.approval_reason
            } for d in pending
        ],
        "summary": {
            "auto_executed_count": len(executed),
            "pending_approval_count": len(pending)
        }
    })
 
@app.route("/api/morning-research", methods=["GET"])
def api_morning_research():
    """API endpoint: Daily morning research workflow with auto-acquisitions & rebalancing"""
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
 
    # Load quotes
    try:
        with open("quote_cache.json", "r") as f:
            quotes = json.load(f)
    except:
        quotes = {}
 
    # Get current portfolio
    portfolio = get_portfolio_data()
 
    # Run research
    research = get_daily_research()
 
    # Process acquisitions with auto-rebalancing
    config = TradeConfig.load()
    executor = TradeExecutor(config)
 
    executed_acquisitions, pending_acquisitions, cash_alerts = executor.process_acquisitions_with_rebalancing(
        research.get('acquisition_candidates', []),
        portfolio,
        research,
        quotes
    )
 
    # Get existing trade recommendations
    decisions = executor.generate_trade_decisions(research, portfolio, quotes)
    executed_trades, pending_trades = executor.execute_trades(decisions, portfolio, quotes)
 
    return jsonify({
        'timestamp': research['timestamp'],
        'research_summary': research['summary'],
        'acquisitions_executed': [
            {
                'symbol': d.symbol,
                'action': d.action,
                'amount': d.amount,
                'reason': d.reason,
                'score': d.research_score
            } for d in executed_acquisitions
        ],
        'acquisitions_pending': [
            {
                'symbol': d['symbol'],
                'amount': d['amount'],
                'score': d['score'],
                'upside': d['upside'],
                'reason': d['reason']
            } for d in pending_acquisitions
        ],
        'trades_executed': [
            {
                'symbol': d.symbol,
                'action': d.action,
                'amount': d.amount,
                'reason': d.reason,
                'score': d.research_score
            } for d in executed_trades
        ],
        'trades_pending_approval': [
            {
                'symbol': d.symbol,
                'action': d.action,
                'amount': d.amount,
                'reason': d.reason,
                'approval_reason': d.approval_reason
            } for d in pending_trades
        ],
        'cash_alerts': cash_alerts,
        'portfolio_updated': {
            'account_value': portfolio['kpis']['account_value'],
            'equity_value': portfolio['kpis']['equity_value'],
            'cash': portfolio['kpis']['cash'],
            'positions': len(portfolio['positions'])
        }
    })
 
@app.route("/api/quotes-refresh", methods=["POST"])
def api_quotes_refresh():
    """API endpoint: Refresh quotes from Robinhood (or cache)"""
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
 
    # Fetch fresh quotes
    quotes = fetch_robinhood_quotes_live()
    quotes_data, metadata = get_quotes_with_metadata()
 
    return jsonify({
        "status": "refreshed",
        "quote_count": len(quotes),
        "timestamp": metadata['timestamp'],
        "source": metadata['source'],
        "message": "Quotes updated. Live Robinhood API integration coming soon — currently using cached quotes."
    })
 
@app.route("/api/quotes-status")
def api_quotes_status():
    """API endpoint: Get quote data freshness"""
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
 
    quotes, metadata = get_quotes_with_metadata()
    return jsonify({
        "quote_count": len(quotes),
        "timestamp": metadata['timestamp'],
        "source": metadata['source'],
        "note": "To enable live Robinhood quotes: (1) Set ROBINHOOD_API_KEY env var, (2) Uncomment API integration in robinhood_quotes.py"
    })
 
@app.route("/logout")
def logout():
    """Logout"""
    session.clear()
    return redirect("/")
 
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
 
