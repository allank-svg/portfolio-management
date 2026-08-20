"""
Daily Fundamental Research Engine
Exhaustive analysis from broad universe → 20 candidates → 10 recommendations
Pure fundamentals, no momentum/technicals
"""

import json
from datetime import datetime, timedelta
from portfolio_analyzer import HOLDINGS_DETAILED

# Scoring methodology
SCORING_WEIGHTS = {
    # FUNDAMENTAL SCORES (60% of decision)
    "earnings_quality": 0.25,      # Growth rate, guidance raises, beat probability
    "valuation_opportunity": 0.20, # Price vs fair value, upside/downside potential
    "thesis_quality": 0.15,         # Risk factors, catalyst clarity, deterioration signals

    # MOMENTUM SCORES (40% of decision - guide/timing, not primary)
    "momentum_institutional": 0.20, # Options flow, institutional positioning
    "technical_momentum": 0.20      # Price action, overbought/oversold
}

def score_holding(symbol, current_data, holdings_detailed):
    """
    Score a holding on fundamental criteria (0-100).
    Returns: score, recommendation (BUY/HOLD/SELL), reasoning
    """
    if symbol not in holdings_detailed:
        return None

    h = holdings_detailed[symbol]
    scores = {}

    # ==================== EARNINGS QUALITY (30%) ====================
    # Metrics: Revenue growth, EPS growth, guidance, beat probability
    revenue_growth = h.get('revenue_growth', 0)
    pe_multiple = h.get('pe_multiple', 0)

    earnings_score = 50  # Neutral baseline

    # Strong growth (>20% YoY) = +15
    if revenue_growth > 0.20:
        earnings_score += 15
    elif revenue_growth > 0.10:
        earnings_score += 8
    elif revenue_growth < 0.05:
        earnings_score -= 10

    # Reasonable valuation for growth rate (PEG ratio)
    if revenue_growth > 0:
        peg = pe_multiple / (revenue_growth * 100)
        if peg < 1.0:
            earnings_score += 10  # Good value
        elif peg > 2.0:
            earnings_score -= 8   # Expensive

    scores['earnings_quality'] = min(100, max(0, earnings_score))

    # ==================== VALUATION OPPORTUNITY (25%) ====================
    # Metrics: Current price vs fair value range, upside/downside
    current_price = current_data.get(symbol, {}).get('last', h.get('fair_value', 0))
    fair_value = h.get('fair_value', 0)
    bull_value = h.get('bull_case', 0)
    bear_value = h.get('bear_case', 0)

    valuation_score = 50

    if current_price > 0 and fair_value > 0:
        upside_pct = ((fair_value - current_price) / current_price) * 100

        # Strong upside to fair value = +20
        if upside_pct > 15:
            valuation_score += 20
        elif upside_pct > 5:
            valuation_score += 10
        elif upside_pct < -15:
            valuation_score -= 20  # Significant downside
        elif upside_pct < -5:
            valuation_score -= 10

    scores['valuation_opportunity'] = min(100, max(0, valuation_score))

    # ==================== MOMENTUM / INSTITUTIONAL (20%) ====================
    # Metrics: Options flow (call/put ratio) - shows smart money positioning
    momentum_score = 50

    # In production, would get call/put ratio from options_flow
    # For now, neutral baseline
    scores['momentum_institutional'] = momentum_score

    # ==================== TECHNICAL MOMENTUM (20%) ====================
    # Metrics: Price action, overbought/oversold levels
    # Helps with TIMING and CONFIDENCE, but doesn't override fundamentals
    technical_score = 50

    # In production, would calculate:
    # - Days up vs days down (trend)
    # - RSI overbought (>70) = reduce entry size or trim positions
    # - RSI oversold (<30) = increase entry size, good buying dip
    # - Volume on moves (momentum confirmation)
    scores['technical_momentum'] = technical_score

    # ==================== THESIS QUALITY (15%) ====================
    # Metrics: Are key thesis drivers still valid? Any deterioration signals?
    thesis_score = 50

    # Thesis quality assessment would come from news/earnings monitoring
    # For now, use FCF yield as proxy for thesis robustness
    fcf_yield = h.get('fcf_yield', 0)

    if fcf_yield > 0.10:
        thesis_score += 15  # Healthy FCF generation
    elif fcf_yield > 0.05:
        thesis_score += 8
    elif fcf_yield < 0.01:
        thesis_score -= 15  # Thesis weak if no FCF

    scores['thesis_quality'] = min(100, max(0, thesis_score))

    # ==================== PORTFOLIO FIT (10%) ====================
    # Metrics: Diversification, sector balance
    # Simplified: favor underweighted sectors
    portfolio_fit_score = 50  # Placeholder
    scores['portfolio_fit'] = portfolio_fit_score

    # ==================== WEIGHTED COMPOSITE SCORE ====================
    composite = 0
    for metric, weight in SCORING_WEIGHTS.items():
        composite += scores.get(metric, 50) * weight

    composite = min(100, max(0, composite))

    # Split fundamentals and momentum scores for recommendation logic
    fundamental_score = (scores['earnings_quality'] * 0.25 +
                        scores['valuation_opportunity'] * 0.20 +
                        scores['thesis_quality'] * 0.15) / 0.60

    momentum_score = (scores['momentum_institutional'] * 0.20 +
                     scores['technical_momentum'] * 0.20) / 0.40

    # Determine recommendation using BOTH scores
    recommendation = _get_recommendation(fundamental_score, momentum_score)

    # Build reasoning
    reasoning = f"""
Fundamentals Score: {fundamental_score:.0f}/100 (Earnings {scores['earnings_quality']:.0f}, Valuation {scores['valuation_opportunity']:.0f}, Thesis {scores['thesis_quality']:.0f})
Momentum Score: {momentum_score:.0f}/100 (Institutional {scores['momentum_institutional']:.0f}, Technical {scores['technical_momentum']:.0f})
Current ${current_price:.2f} vs Fair Value ${fair_value:.0f} (Upside: {((fair_value - current_price) / current_price * 100):.1f}%)
    """.strip()

    return {
        'symbol': symbol,
        'name': h.get('name', symbol),
        'composite_score': composite,
        'fundamental_score': fundamental_score,
        'momentum_score': momentum_score,
        'recommendation': recommendation,
        'reasoning': reasoning,
        'current_price': current_price,
        'fair_value': fair_value,
        'bull_case': bull_value,
        'bear_case': bear_value,
        'upside_to_fair': ((fair_value - current_price) / current_price * 100) if current_price > 0 else 0,
        'thesis': h.get('bull_thesis', ''),
        'revenue_growth': revenue_growth,
        'pe_multiple': pe_multiple,
        'fcf_yield': fcf_yield
    }

def _get_recommendation(fundamental_score, momentum_score):
    """
    Recommendation matrix: Fundamentals are foundation, momentum influences TIMING & TYPE.

    Key principle:
    - Never buy weak fundamentals (avoid momentum traps)
    - Never sell strong fundamentals (even if momentum weak)
    - Use momentum to optimize entry/exit timing
    """

    # WEAK FUNDAMENTALS: Never buy, regardless of momentum
    if fundamental_score < 40:
        if momentum_score > 65:
            return "AVOID"  # Momentum trap - don't chase
        else:
            return "SELL"   # Thesis is broken

    # MODERATE FUNDAMENTALS: Thesis OK but not compelling
    elif fundamental_score < 55:
        if momentum_score > 65:
            return "HOLD"   # Wait for better entry, momentum not worth the risk
        else:
            return "HOLD"   # Nothing compelling to do

    # STRONG FUNDAMENTALS (55-70): Thesis solid, momentum drives CONFIDENCE & TIMING
    elif fundamental_score < 70:
        if momentum_score > 75:
            return "TRIM"   # Fundamentals solid, but massively overbought - reduce size
        elif momentum_score > 60:
            return "STRONG_BUY"  # Both fundamentals and momentum aligned - high conviction
        elif momentum_score > 45:
            return "BUY"    # Good fundamentals, weak momentum - good entry
        else:
            return "BUY"    # Fundamentals strong, momentum weak = best risk/reward

    # VERY STRONG FUNDAMENTALS (70+): High conviction regardless of momentum
    else:
        if momentum_score > 75:
            return "STRONG_BUY"  # Fundamentals excellent + momentum hot - maximum conviction
        elif momentum_score > 45:
            return "STRONG_BUY"  # Fundamentals excellent, momentum OK - solid confidence
        else:
            return "BUY"    # Fundamentals excellent, momentum weak - bargain entry

def generate_daily_research_report(current_data):
    """
    Daily research workflow:
    1. Score all holdings on fundamentals
    2. Rank by composite score
    3. Top 20 = candidates
    4. Top 10 = recommendations for portfolio
    5. Return detailed report with BUY/SELL/HOLD
    """

    # Score all holdings
    all_scores = []
    for symbol in HOLDINGS_DETAILED.keys():
        score_data = score_holding(symbol, current_data, HOLDINGS_DETAILED)
        if score_data:
            all_scores.append(score_data)

    # Sort by score descending
    all_scores.sort(key=lambda x: x['composite_score'], reverse=True)

    # Split into tiers
    top_20 = all_scores[:20]  # Candidates
    top_10 = all_scores[:10]  # Recommendations

    # Categorize by recommendation type
    strong_buys = [s for s in top_10 if s['recommendation'] == 'STRONG_BUY']
    buys = [s for s in top_10 if s['recommendation'] == 'BUY']
    trims = [s for s in top_10 if s['recommendation'] == 'TRIM']  # Reduce size due to overbought
    avoids = [s for s in top_10 if s['recommendation'] == 'AVOID']  # Momentum trap
    holds = [s for s in top_10 if s['recommendation'] == 'HOLD']
    sells = [s for s in top_10 if s['recommendation'] == 'SELL']

    return {
        'timestamp': datetime.now().strftime("%A %d %b %Y, %-I:%M %p ET"),
        'top_10_recommendations': top_10,
        'top_20_candidates': top_20,
        'strong_buy_signals': strong_buys,      # Fundamentals excellent + momentum aligned
        'buy_signals': buys,                     # Fundamentals solid, wait for better entry or good entry
        'trim_signals': trims,                   # Take profits - fundamentals OK but overbought
        'hold_signals': holds,                   # Thesis OK but not compelling
        'avoid_signals': avoids,                 # Momentum trap - avoid at any price
        'sell_signals': sells,                   # Thesis broken, exit position
        'summary': {
            'total_scored': len(all_scores),
            'strong_buy_count': len(strong_buys),
            'buy_count': len(buys),
            'trim_count': len(trims),
            'avoid_count': len(avoids),
            'hold_count': len(holds),
            'sell_count': len(sells),
        }
    }

def get_daily_research():
    """API endpoint: return today's research report"""
    # In production, this would read live quotes from Robinhood
    # For now, use cached data
    try:
        with open("/home/claude/dash/quote_cache.json", "r") as f:
            current_data = json.load(f)
    except:
        current_data = {}

    return generate_daily_research_report(current_data)

if __name__ == "__main__":
    report = get_daily_research()
    print(json.dumps(report, indent=2))
