
"""
Trade Executor
Executes trades based on fundamental research signals
Respects user's configuration limits (max buy/sell per day, approval thresholds)
Handles automatic acquisition of new stocks and portfolio rebalancing
All trades logged with fundamental reasoning
"""
 
import json
import os
import uuid
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
 
PENDING_FILE = "pending_approvals.json"
TRADE_HISTORY_FILE = "trade_history.jsonl"
 
# ==================== PERSISTENT PENDING APPROVALS ====================
# These are module-level (not tied to a TradeExecutor instance) because each
# Flask request creates a fresh TradeExecutor, so approvals must survive on disk.
 
def load_pending_approvals():
    """Load the current queue of trades awaiting your approval"""
    if os.path.exists(PENDING_FILE):
        try:
            with open(PENDING_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []
 
def _save_pending_approvals(pending_list):
    with open(PENDING_FILE, "w") as f:
        json.dump(pending_list, f, indent=2)
 
def add_pending_approvals(new_decisions):
    """
    Add newly generated pending trades to the persistent queue.
    Accepts a mix of TradeDecision objects and raw dicts (acquisition candidates
    still waiting on cash). Dedupes by symbol+action+date so re-running research
    hourly doesn't spam duplicate approval requests for the same signal.
    """
    existing = load_pending_approvals()
    existing_keys = {(p['symbol'], p['action'], p['timestamp'][:10]) for p in existing}
    added = 0
 
    for d in new_decisions:
        if hasattr(d, 'symbol'):
            symbol, action, amount = d.symbol, d.action, d.amount
            reason, score, timestamp = d.reason, d.research_score, d.timestamp
            approval_reason = d.approval_reason or "Awaiting approval"
        else:
            symbol = d.get('symbol')
            action = 'BUY'
            amount = d.get('amount', 0)
            reason = d.get('reason', '')
            score = d.get('score', 0)
            timestamp = datetime.now().isoformat()
            approval_reason = "Insufficient cash available"
 
        key = (symbol, action, timestamp[:10])
        if key in existing_keys:
            continue
 
        existing.append({
            'id': str(uuid.uuid4()),
            'symbol': symbol,
            'action': action,
            'amount': amount,
            'reason': reason,
            'research_score': score,
            'approval_reason': approval_reason,
            'timestamp': timestamp,
            'status': 'pending'
        })
        added += 1
 
    if added:
        _save_pending_approvals(existing)
    return existing
 
def remove_pending_approval(approval_id):
    existing = load_pending_approvals()
    existing = [p for p in existing if p['id'] != approval_id]
    _save_pending_approvals(existing)
 
def get_pending_approval(approval_id):
    for p in load_pending_approvals():
        if p['id'] == approval_id:
            return p
    return None
 
def approve_pending_trade(approval_id):
    """User approves a pending trade from the dashboard: execute + log + clear from queue"""
    approval = get_pending_approval(approval_id)
    if not approval:
        return None, "Approval not found (it may have already been actioned)"
 
    entry = {
        'timestamp': datetime.now().isoformat(),
        'symbol': approval['symbol'],
        'action': approval['action'],
        'amount': approval['amount'],
        'reason': approval['reason'] + " [Approved by user]",
        'research_score': approval['research_score']
    }
    log_trade_history(entry)
    remove_pending_approval(approval_id)
    return entry, None
 
def reject_pending_trade(approval_id, reason=""):
    """User rejects a pending trade: remove from queue, log the rejection for the record"""
    approval = get_pending_approval(approval_id)
    if not approval:
        return None, "Approval not found (it may have already been actioned)"
 
    entry = {
        'timestamp': datetime.now().isoformat(),
        'symbol': approval['symbol'],
        'action': f"REJECTED_{approval['action']}",
        'amount': approval['amount'],
        'reason': approval['reason'] + (f" [Rejected: {reason}]" if reason else " [Rejected by user]"),
        'research_score': approval['research_score']
    }
    log_trade_history(entry)
    remove_pending_approval(approval_id)
    return approval, None
 
# ==================== PERSISTENT TRADE HISTORY ====================
 
def log_trade_history(entry):
    """Append an executed (or rejected) trade to the permanent history log"""
    try:
        with open(TRADE_HISTORY_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except:
        pass
 
def load_trade_history(limit=200):
    """Load trade history, most recent first"""
    history = []
    if os.path.exists(TRADE_HISTORY_FILE):
        try:
            with open(TRADE_HISTORY_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        history.append(json.loads(line))
        except:
            pass
    return list(reversed(history))[:limit]
 
class TradeConfig:
    """User-settable trading parameters"""
    def __init__(self):
        self.max_buy_per_stock_per_day = 50000      # Max $ to buy single stock in one day
        self.max_sell_per_stock_per_day = 50000     # Max $ to sell single stock in one day
        self.approval_threshold_buy = 100000        # Require approval for buys > this
        self.approval_threshold_sell = 100000       # Require approval for sells > this
        self.max_portfolio_concentration = 0.20     # No single position > 20% of portfolio
        self.use_limit_orders = True                # Use limit orders, not market
        self.order_validity_days = 7                # Good-til-canceled for 7 days
 
        # Acquisition & Rebalancing settings
        self.auto_buy_new_acquisitions = True       # Auto-buy new stocks that meet criteria
        self.min_cash_buffer = 2000                 # Keep minimum cash buffer
        self.acquisition_min_fundamental_score = 60 # Min fundamentals score to auto-buy
        self.acquisition_min_upside = 0.15          # Min 15% upside to fair value
        self.auto_rebalance = True                  # Auto-sell weak positions for better opportunities
        self.rebalance_threshold = 45               # Sell if composite score < this
        self.email_on_acquisition = True            # Email notification on new buys
        self.email_address = "allan@kginvest.net"   # Where to send notifications
 
    def to_dict(self):
        return {
            'max_buy_per_stock_per_day': self.max_buy_per_stock_per_day,
            'max_sell_per_stock_per_day': self.max_sell_per_stock_per_day,
            'approval_threshold_buy': self.approval_threshold_buy,
            'approval_threshold_sell': self.approval_threshold_sell,
            'max_portfolio_concentration': self.max_portfolio_concentration,
            'use_limit_orders': self.use_limit_orders,
            'order_validity_days': self.order_validity_days,
            'auto_buy_new_acquisitions': self.auto_buy_new_acquisitions,
            'min_cash_buffer': self.min_cash_buffer,
            'acquisition_min_fundamental_score': self.acquisition_min_fundamental_score,
            'acquisition_min_upside': self.acquisition_min_upside,
            'auto_rebalance': self.auto_rebalance,
            'rebalance_threshold': self.rebalance_threshold,
            'email_on_acquisition': self.email_on_acquisition,
            'email_address': self.email_address
        }
 
    @staticmethod
    def load(config_file="trade_config.json"):
        """Load config from file, or create default"""
        try:
            with open(config_file, "r") as f:
                data = json.load(f)
                config = TradeConfig()
                for key, value in data.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
                return config
        except:
            return TradeConfig()
 
    def save(self, config_file="trade_config.json"):
        """Persist config to file"""
        with open(config_file, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
 
class TradeDecision:
    """Represents a single trade recommendation"""
    def __init__(self, symbol, action, amount, reason, research_score):
        self.symbol = symbol
        self.action = action  # BUY or SELL
        self.amount = amount  # Dollar amount
        self.reason = reason  # Fundamental reasoning
        self.research_score = research_score  # Research score (0-100)
        self.timestamp = datetime.now().isoformat()
        self.requires_approval = False
        self.approval_reason = ""
 
class TradeExecutor:
    """Executes trades based on research signals, respecting config guardrails"""
 
    def __init__(self, config=None):
        self.config = config or TradeConfig.load()
        self.trade_log = []
        self.pending_approvals = []
 
    def should_execute_buy(self, symbol, amount, current_position_value, total_portfolio_value):
        """
        Check if a buy is within guardrails
        Returns: (can_execute, requires_approval, reason)
        """
 
        # Check daily buy limit
        today_buy_amount = sum(t['amount'] for t in self.trade_log
                              if t['symbol'] == symbol and t['action'] == 'BUY'
                              and self._is_today(t['timestamp']))
 
        if today_buy_amount + amount > self.config.max_buy_per_stock_per_day:
            return False, False, f"Exceeds daily buy limit of ${self.config.max_buy_per_stock_per_day}"
 
        # Check portfolio concentration
        new_position_value = current_position_value + amount
        if total_portfolio_value > 0:
            new_concentration = new_position_value / total_portfolio_value
            if new_concentration > self.config.max_portfolio_concentration:
                return False, False, f"Would exceed max {self.config.max_portfolio_concentration*100:.0f}% concentration"
 
        # Check approval threshold
        requires_approval = amount > self.config.approval_threshold_buy
 
        return True, requires_approval, "Within guardrails"
 
    def should_execute_sell(self, symbol, amount, current_position_value):
        """
        Check if a sell is within guardrails
        Returns: (can_execute, requires_approval, reason)
        """
 
        # Check daily sell limit
        today_sell_amount = sum(t['amount'] for t in self.trade_log
                               if t['symbol'] == symbol and t['action'] == 'SELL'
                               and self._is_today(t['timestamp']))
 
        if today_sell_amount + amount > self.config.max_sell_per_stock_per_day:
            return False, False, f"Exceeds daily sell limit of ${self.config.max_sell_per_stock_per_day}"
 
        # Can't sell more than we hold
        if amount > current_position_value:
            return False, False, f"Insufficient holdings (have ${current_position_value:.0f}, trying to sell ${amount:.0f})"
 
        # Check approval threshold
        requires_approval = amount > self.config.approval_threshold_sell
 
        return True, requires_approval, "Within guardrails"
 
    def generate_trade_decisions(self, research_report, portfolio, current_quotes):
        """
        Based on daily research, generate trade recommendations
        Returns: list of TradeDecision objects
        """
        decisions = []
 
        # Map current holdings
        holdings_map = {p['symbol']: p for p in portfolio['positions']}
 
        # BUY signals: research recommends buying
        for rec in research_report['buy_signals']:
            symbol = rec['symbol']
            score = rec['composite_score']
 
            if symbol in holdings_map:
                # Already holding - recommend "buy more"
                current_val = holdings_map[symbol]['position_value']
                # Size: add 10-20% depending on score
                size_pct = 0.10 + (score - 70) / 300  # Scale from 10-13%
                buy_amount = current_val * size_pct
            else:
                # New position - size at 2% of portfolio for diversification
                portfolio_val = portfolio['kpis']['account_value']
                buy_amount = portfolio_val * 0.02
 
            decision = TradeDecision(
                symbol=symbol,
                action='BUY',
                amount=buy_amount,
                reason=rec['reasoning'],
                research_score=score
            )
            decisions.append(decision)
 
        # SELL signals: research recommends selling
        for rec in research_report['sell_signals']:
            symbol = rec['symbol']
            score = rec['composite_score']
 
            if symbol in holdings_map:
                # We're holding this
                current_val = holdings_map[symbol]['position_value']
 
                # Decide how much to sell based on score
                if score < 30:
                    # Critical sell - exit 50%
                    sell_amount = current_val * 0.50
                elif score < 45:
                    # Weak sell - exit 25%
                    sell_amount = current_val * 0.25
                else:
                    # Trim - exit 10%
                    sell_amount = current_val * 0.10
 
                decision = TradeDecision(
                    symbol=symbol,
                    action='SELL',
                    amount=sell_amount,
                    reason=rec['reasoning'],
                    research_score=score
                )
                decisions.append(decision)
 
        return decisions
 
    def execute_trades(self, decisions, portfolio, current_quotes):
        """
        Execute a list of trade decisions, respecting config guardrails
        Returns: (executed_trades, pending_approval_trades)
        """
        executed = []
        pending = []
 
        portfolio_val = portfolio['kpis']['account_value']
        holdings_map = {p['symbol']: p for p in portfolio['positions']}
 
        for decision in decisions:
            symbol = decision.symbol
 
            if decision.action == 'BUY':
                current_pos_val = holdings_map.get(symbol, {}).get('position_value', 0)
                can_execute, needs_approval, reason = self.should_execute_buy(
                    symbol, decision.amount, current_pos_val, portfolio_val
                )
 
                if not can_execute:
                    decision.requires_approval = True
                    decision.approval_reason = reason
                    pending.append(decision)
                elif needs_approval:
                    decision.requires_approval = True
                    decision.approval_reason = f"Exceeds approval threshold of ${self.config.approval_threshold_buy}"
                    pending.append(decision)
                else:
                    # Auto-execute
                    self._log_trade(decision)
                    executed.append(decision)
                    self._send_notification(
                        f"✅ AUTO-EXECUTED BUY: {symbol}",
                        f"${decision.amount:,.0f} — {decision.reason}"
                    )
 
            elif decision.action == 'SELL':
                current_pos_val = holdings_map.get(symbol, {}).get('position_value', 0)
                can_execute, needs_approval, reason = self.should_execute_sell(
                    symbol, decision.amount, current_pos_val
                )
 
                if not can_execute:
                    decision.requires_approval = True
                    decision.approval_reason = reason
                    pending.append(decision)
                elif needs_approval:
                    decision.requires_approval = True
                    decision.approval_reason = f"Exceeds approval threshold of ${self.config.approval_threshold_sell}"
                    pending.append(decision)
                else:
                    # Auto-execute
                    self._log_trade(decision)
                    executed.append(decision)
                    self._send_notification(
                        f"✅ AUTO-EXECUTED SELL: {symbol}",
                        f"${decision.amount:,.0f} — {decision.reason}"
                    )
 
        if pending:
            add_pending_approvals(pending)
 
        return executed, pending
 
    def _log_trade(self, decision):
        """Log executed trade (in-memory for this request + permanent history file)"""
        entry = {
            'timestamp': decision.timestamp,
            'symbol': decision.symbol,
            'action': decision.action,
            'amount': decision.amount,
            'reason': decision.reason,
            'research_score': decision.research_score
        }
        self.trade_log.append(entry)
        log_trade_history(entry)
 
    def _is_today(self, timestamp_str):
        """Check if timestamp is from today"""
        from datetime import date
        timestamp = datetime.fromisoformat(timestamp_str)
        return timestamp.date() == date.today()
 
    def get_pending_approvals(self):
        """Get the persistent queue of trades waiting for user approval (survives across requests)"""
        return load_pending_approvals()
 
    def evaluate_new_acquisitions(self, candidates, current_portfolio, portfolio_value):
        """
        Evaluate new acquisition candidates for automatic buying
        Returns: (buy_recommendations, cash_needed, rebalance_suggestions)
        """
        buy_recommendations = []
        cash_needed = 0
        rebalance_suggestions = []
 
        for candidate in candidates:
            symbol = candidate['symbol']
            upside = candidate.get('upside_pct', 0) / 100
 
            # Check criteria
            if upside < self.config.acquisition_min_upside:
                continue  # Doesn't meet upside requirement
 
            # Estimate score from upside and valuation
            score = min(80, 50 + (upside * 100))  # Rough score from upside
 
            if score < self.config.acquisition_min_fundamental_score:
                continue  # Doesn't meet fundamental requirement
 
            # Size: 2% of portfolio for new positions
            buy_amount = portfolio_value * 0.02
 
            buy_recommendations.append({
                'symbol': symbol,
                'amount': buy_amount,
                'score': score,
                'upside': upside * 100,
                'reason': f"New acquisition: {candidate.get('thesis', '')}",
                'fair_value': candidate.get('fair_value', 0),
                'current_price': candidate.get('price', 0)
            })
 
            cash_needed += buy_amount
 
        return buy_recommendations, cash_needed, rebalance_suggestions
 
    def get_rebalance_candidates(self, portfolio, research_scores):
        """
        Find weak positions to sell to make room for better opportunities
        Returns: list of positions to sell (lowest score first)
        """
        rebalance_candidates = []
 
        for position in portfolio['positions']:
            symbol = position['symbol']
 
            # Find research score for this position
            score = None
            for rec in research_scores.get('top_10_recommendations', []):
                if rec['symbol'] == symbol:
                    score = rec['composite_score']
                    break
 
            if not score:
                score = 50  # Default neutral score
 
            # If score below threshold, consider for selling
            if score < self.config.rebalance_threshold:
                rebalance_candidates.append({
                    'symbol': symbol,
                    'value': position['position_value'],
                    'score': score,
                    'reason': f"Weak fundamentals ({score:.0f}/100), consider rebalancing"
                })
 
        # Sort by score (lowest first)
        rebalance_candidates.sort(key=lambda x: x['score'])
        return rebalance_candidates
 
    def process_acquisitions_with_rebalancing(self, candidates, portfolio, research, current_quotes):
        """
        Main acquisition processor: evaluate new opportunities and auto-buy with rebalancing.
        All buys/sells are still routed through should_execute_buy()/should_execute_sell()
        so daily limits, approval thresholds, and concentration caps are always respected —
        acquisitions and rebalancing get NO special exemption from your guardrails.
        Returns: (executed_acquisitions, pending_acquisitions, alerts)
        """
        executed = []
        pending = []
        alerts = []
 
        portfolio_value = portfolio['kpis']['account_value']
        current_cash = portfolio['kpis']['cash']
        holdings_map = {p['symbol']: p for p in portfolio['positions']}
 
        # Evaluate new acquisition candidates
        buy_recs, cash_needed, rebalance = self.evaluate_new_acquisitions(
            research.get('acquisition_candidates', []),
            portfolio['positions'],
            portfolio_value
        )
 
        for rec in buy_recs:
            symbol = rec['symbol']
            amount = rec['amount']
 
            # Check if we have cash
            if current_cash - self.config.min_cash_buffer >= amount:
                # We have cash - still must pass guardrails before auto-executing
                current_pos_val = holdings_map.get(symbol, {}).get('position_value', 0)
                can_execute, needs_approval, reason = self.should_execute_buy(
                    symbol, amount, current_pos_val, portfolio_value
                )
 
                decision = TradeDecision(
                    symbol=symbol,
                    action='BUY',
                    amount=amount,
                    reason=rec['reason'],
                    research_score=rec['score']
                )
 
                if can_execute and not needs_approval:
                    self._log_trade(decision)
                    executed.append(decision)
                    current_cash -= amount
 
                    self._send_notification(
                        f"🎯 NEW ACQUISITION: {symbol}",
                        f"Bought ${amount:,.0f} at ${rec['current_price']:.2f}\n"
                        f"Fair Value: ${rec['fair_value']:.2f}\n"
                        f"Upside: {rec['upside']:.1f}%"
                    )
                else:
                    decision.requires_approval = True
                    decision.approval_reason = reason if not can_execute else f"Exceeds approval threshold of ${self.config.approval_threshold_buy}"
                    pending.append(decision)
 
                    self._send_notification(
                        f"⏳ ACQUISITION PENDING APPROVAL: {symbol}",
                        f"Proposed: ${amount:,.0f} at ${rec['current_price']:.2f}\n"
                        f"Reason held for approval: {decision.approval_reason}"
                    )
 
            else:
                # Not enough cash - suggest rebalancing
                rebalance_candidates = self.get_rebalance_candidates(portfolio, research)
 
                if rebalance_candidates and self.config.auto_rebalance:
                    # Auto-rebalance: sell weakest position, buy new opportunity
                    weakest = rebalance_candidates[0]
                    sell_amount = weakest['value']
                    weakest_pos_val = holdings_map.get(weakest['symbol'], {}).get('position_value', sell_amount)
 
                    can_sell, sell_needs_approval, sell_reason = self.should_execute_sell(
                        weakest['symbol'], sell_amount, weakest_pos_val
                    )
 
                    sell_decision = TradeDecision(
                        symbol=weakest['symbol'],
                        action='SELL',
                        amount=sell_amount,
                        reason=weakest['reason'],
                        research_score=weakest['score']
                    )
 
                    if not (can_sell and not sell_needs_approval):
                        sell_decision.requires_approval = True
                        sell_decision.approval_reason = sell_reason if not can_sell else f"Exceeds approval threshold of ${self.config.approval_threshold_sell}"
                        pending.append(sell_decision)
 
                        self._send_notification(
                            f"⏳ REBALANCE SELL PENDING APPROVAL: {weakest['symbol']}",
                            f"Proposed sell: ${sell_amount:,.0f} (score {weakest['score']:.0f}/100) to fund {symbol}\n"
                            f"Reason held for approval: {sell_decision.approval_reason}"
                        )
                        continue
 
                    # Sell cleared guardrails - execute it
                    self._log_trade(sell_decision)
                    executed.append(sell_decision)
 
                    # Now check the buy leg against guardrails too
                    buy_pos_val = holdings_map.get(symbol, {}).get('position_value', 0)
                    can_buy, buy_needs_approval, buy_reason = self.should_execute_buy(
                        symbol, amount, buy_pos_val, portfolio_value
                    )
 
                    buy_decision = TradeDecision(
                        symbol=symbol,
                        action='BUY',
                        amount=amount,
                        reason=f"Rebalance: Sold {weakest['symbol']}, bought {symbol}",
                        research_score=rec['score']
                    )
 
                    if can_buy and not buy_needs_approval:
                        self._log_trade(buy_decision)
                        executed.append(buy_decision)
 
                        self._send_notification(
                            f"⚖️ PORTFOLIO REBALANCE",
                            f"Sold: {weakest['symbol']} (${sell_amount:,.0f}, score {weakest['score']:.0f}/100)\n"
                            f"Bought: {symbol} (${amount:,.0f}, score {rec['score']:.0f}/100)\n"
                            f"Reason: Better opportunity identified"
                        )
                    else:
                        buy_decision.requires_approval = True
                        buy_decision.approval_reason = buy_reason if not can_buy else f"Exceeds approval threshold of ${self.config.approval_threshold_buy}"
                        pending.append(buy_decision)
 
                        self._send_notification(
                            f"⏳ REBALANCE BUY PENDING APPROVAL: {symbol}",
                            f"Sold {weakest['symbol']} (${sell_amount:,.0f}) but the buy leg into {symbol} needs approval: {buy_decision.approval_reason}"
                        )
 
                else:
                    # Not enough cash, can't rebalance - need user input
                    alerts.append({
                        'type': 'CASH_NEEDED',
                        'symbol': symbol,
                        'amount_needed': amount - current_cash,
                        'message': f"Need ${amount - current_cash:,.0f} more to acquire {symbol}"
                    })
 
                    # Send alert
                    self._send_notification(
                        f"💰 CASH NEEDED",
                        f"Opportunity identified: {symbol}\n"
                        f"Required: ${amount:,.0f}\n"
                        f"Available: ${current_cash:,.0f}\n"
                        f"Shortage: ${amount - current_cash:,.0f}\n\n"
                        f"Please add funds or approve rebalancing."
                    )
 
                    pending.append(rec)
 
        if pending:
            add_pending_approvals(pending)
 
        return executed, pending, alerts
 
    def _send_notification(self, subject, message):
        """Send email notification (placeholder - implement with your email service)"""
        # For now, just log to file
        try:
            with open("notifications.log", "a") as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}] {subject}\n{message}\n\n")
        except:
            pass
        # TODO: Integrate with email service (SendGrid, AWS SES, etc.)
        # or use Anthropic notification system
 
if __name__ == "__main__":
    config = TradeConfig()
    executor = TradeExecutor(config)
    print(json.dumps(config.to_dict(), indent=2))
 
