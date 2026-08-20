# Fundamental Portfolio Management System

**A daily exhaustive research engine driving automated trading with fundamental guardrails**

## Overview

This system provides a three-phase portfolio management workflow:
1. **Daily Research Engine** - Score all holdings on fundamentals (60%) + momentum (40%)
2. **Portfolio Today** - Executive brief showing current performance + recommendation changes
3. **Automated Trade Executor** - Execute trades with user-configured guardrails

## Architecture

### Core Modules

**config.py**
- Portfolio definitions (12 holdings)
- Cash allocation ($6,800)
- Shared constants

**app.py**
- Flask backend with session-based authentication
- 12 API endpoints for dashboard data
- Routes: /dashboard (primary), /api/research, /api/portfolio-today, /api/trade-decisions, etc.

**research_engine.py**
- Scores all holdings on 5 dimensions:
  - Earnings quality (25%)
  - Valuation opportunity (20%)
  - Thesis quality (15%)
  - Momentum institutional (20%)
  - Technical momentum (20%)
- Returns: top 20 candidates → top 10 recommendations
- Recommendation types: STRONG_BUY, BUY, TRIM, HOLD, AVOID, SELL

**portfolio_manager.py**
- Tracks current portfolio performance
- Calculates KPIs (account value, unrealized P&L, today's performance)
- Compares today's research vs yesterday's to flag recommendation changes
- Persists research archive for historical tracking

**trade_executor.py**
- Generates trade decisions from research signals
- Respects user configuration guardrails:
  - Max buy/sell per stock per day
  - Approval thresholds
  - Max portfolio concentration
- Returns: auto-executed trades + trades requiring approval

**portfolio_analyzer.py**
- Holdings data with detailed metrics
- Earnings calendar, fair value models, options flow
- Acquisition candidate scanner

**monitor.py**
- Scheduled hourly task runner (market hours)
- Updates quote cache from Robinhood API
- Refreshes market data for dashboard

## Dashboard

**Portfolio Today Tab**
- Key metrics (account value, unrealized P&L, today's performance)
- Action items from research (BUY/SELL/TRIM/HOLD recommendations)
- Recommendation changes from yesterday
- Current holdings table with performance

**Daily Research Tab**
- Research summary (counts by recommendation type)
- Top 10 recommendations (composite score, fundamentals, momentum, fair value)
- Top 20 candidates for consideration

**Market Overview Tab**
- Market indices (S&P 500, NASDAQ, Russell 2000)
- Market breadth percentage
- Sector rotation vs portfolio weighting
- Economic indicators (10Y yield, Fed funds, VIX, GDP)
- Institutional research iframe

**Configuration Tab**
- User guardrails:
  - Max buy/sell per stock per day
  - Approval thresholds
  - Max portfolio concentration
- Save button to persist settings

**Trade History Tab**
- Audit trail of executed trades
- Date, symbol, action, amount, research score, fundamental reason

## Scoring Methodology

### Fundamentals (60% of decision)
- **Earnings Quality** (25%)
  - Revenue growth rate (>20% YoY = +15 points)
  - PEG ratio (<1.0 = +10, >2.0 = -8)
  - Baseline score: 50/100

- **Valuation Opportunity** (20%)
  - Upside to fair value (>15% = +20, <-15% = -20)
  - Baseline score: 50/100

- **Thesis Quality** (15%)
  - FCF yield (>10% = +15, <1% = -15)
  - Risk factor assessment
  - Catalyst clarity
  - Baseline score: 50/100

### Momentum (40% of decision) — GUIDE/TIMING ONLY
- **Institutional Positioning** (20%)
  - Options flow (call/put ratio)
  - Baseline score: 50/100

- **Technical Momentum** (20%)
  - Price action, trend analysis
  - RSI overbought (>70) = reduce size
  - RSI oversold (<30) = increase size
  - Baseline score: 50/100

### Recommendation Matrix

| Fundamentals | Momentum | Recommendation | Rationale |
|---|---|---|---|
| <40 (Weak) | >65 | AVOID | Don't chase momentum traps |
| <40 | ≤65 | SELL | Thesis broken, exit |
| 40-55 (Moderate) | Any | HOLD | Thesis OK but not compelling |
| 55-70 (Strong) | >75 | TRIM | Fundamentals solid but overbought |
| 55-70 | 60-75 | STRONG_BUY | Both aligned, high conviction |
| 55-70 | 45-60 | BUY | Good fundamentals, weak momentum = good entry |
| 55-70 | <45 | BUY | Fundamentals strong, momentum weak = best risk/reward |
| 70+ (Very Strong) | >75 | STRONG_BUY | Maximum conviction |
| 70+ | 45-75 | STRONG_BUY | Fundamentals excellent |
| 70+ | <45 | BUY | Fundamentals excellent, momentum weak = bargain |

## API Endpoints

- `GET /api/data` - Current portfolio positions with P&L
- `GET /api/research` - Daily exhaustive research report
- `GET /api/portfolio-today` - Portfolio dashboard (performance + changes)
- `GET /api/trade-decisions` - Trade decisions with auto-execute vs approval split
- `GET /api/trade-config` - Current user configuration
- `POST /api/trade-config` - Update user configuration
- `GET /api/earnings-calendar` - Upcoming earnings dates
- `GET /api/fair-value` - Fair value models for all holdings
- `GET /api/options-flow` - Institutional positioning signals
- `GET /api/acquisition-scan` - New opportunities matching criteria

## Deployment

### Local Development
```bash
pip install -r requirements.txt
python app.py
# Visit http://localhost:5000
# Login with: allan / portfolio2026
```

### Render Deployment
1. Connect GitHub repository to Render
2. Deploy service pointing to Procfile
3. Set environment variables (if needed):
   - Change SECRET_KEY in app.py
   - Configure Robinhood API credentials (when implemented)
4. Service will auto-start with `gunicorn app:app`

### Monitoring
- Scheduled tasks run hourly during market hours (9:30 AM - 4:30 PM ET, weekdays)
- Quote cache updates automatically via monitor.py
- Research archive persists daily recommendations for historical tracking

## Key Features

✅ **Fundamental-First Approach**
- 60% fundamentals weight ensures thesis-driven decisions
- Momentum used only for timing and position sizing
- Never buy weak fundamentals on momentum (AVOID trap rule)

✅ **User-Configured Guardrails**
- Control daily buy/sell limits per position
- Set approval thresholds for large trades
- Limit portfolio concentration

✅ **Daily Exhaustive Research**
- 12 holdings scored across 5 dimensions
- Top 20 candidates identified, top 10 recommended
- Recommendation changes tracked vs previous day

✅ **Automated Trading with Approval**
- Trades below approval threshold auto-execute
- Larger trades held for user review
- All trades logged with fundamental reasoning

✅ **Market Context**
- Daily economic indicators
- Sector rotation vs portfolio weighting
- Institutional research integration

## File Structure

```
/home/claude/
├── app.py                      # Flask backend
├── config.py                   # Portfolio configuration
├── research_engine.py          # Daily research scorer
├── portfolio_manager.py        # Performance tracking
├── trade_executor.py           # Automated trading
├── portfolio_analyzer.py       # Holdings data
├── monitor.py                  # Scheduled tasks
├── requirements.txt            # Dependencies
├── Procfile                    # Render deployment config
└── templates/
    └── portfolio_dashboard.html # Primary UI (5 tabs)
```

## Next Steps

1. **Robinhood API Integration**
   - Implement live quote fetching in monitor.py
   - Implement actual trade execution in trade_executor.py
   - Add order status tracking

2. **Notification System**
   - Email alerts for approval-threshold trades
   - Morning briefing digest
   - Daily research summary

3. **Advanced Features**
   - Technical analysis scoring (RSI, trend, volume)
   - Robinhood insights monitoring
   - Historical performance attribution
   - Backtesting framework

## Support

For questions or issues, review:
- research_engine.py - for scoring logic
- portfolio_analyzer.py - for holdings data
- trade_executor.py - for guardrails configuration
- dashboard tabs - for real-time system status
