"""
Trade Executor
Executes trades based on fundamental research signals
Respects user's configuration limits (max buy/sell per day, approval thresholds)
All trades logged with fundamental reasoning
"""

import json
from datetime import datetime

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

    def to_dict(self):
        return {
            'max_buy_per_stock_per_day': self.max_buy_per_stock_per_day,
            'max_sell_per_stock_per_day': self.max_sell_per_stock_per_day,
            'approval_threshold_buy': self.approval_threshold_buy,
            'approval_threshold_sell': self.approval_threshold_sell,
            'max_portfolio_concentration': self.max_portfolio_concentration,
            'use_limit_orders': self.use_limit_orders,
            'order_validity_days': self.order_validity_days
        }

    @staticmethod
    def load(config_file="/home/claude/trade_config.json"):
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

    def save(self, config_file="/home/claude/trade_config.json"):
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

        return executed, pending

    def _log_trade(self, decision):
        """Log executed trade"""
        self.trade_log.append({
            'timestamp': decision.timestamp,
            'symbol': decision.symbol,
            'action': decision.action,
            'amount': decision.amount,
            'reason': decision.reason,
            'research_score': decision.research_score
        })

    def _is_today(self, timestamp_str):
        """Check if timestamp is from today"""
        from datetime import date
        timestamp = datetime.fromisoformat(timestamp_str)
        return timestamp.date() == date.today()

    def get_pending_approvals(self):
        """Get list of trades waiting for user approval"""
        return self.pending_approvals

    def approve_trade(self, symbol, action):
        """User approves a pending trade"""
        # Remove from pending, log as executed
        # Send confirmation email/notification
        pass

    def reject_trade(self, symbol, action, reason=""):
        """User rejects a pending trade"""
        # Remove from pending, log as rejected
        pass

if __name__ == "__main__":
    config = TradeConfig()
    executor = TradeExecutor(config)
    print(json.dumps(config.to_dict(), indent=2))
