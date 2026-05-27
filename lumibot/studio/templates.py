"""Built-in beginner strategy templates for the Local Backtest Studio."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StudioTemplate:
    template_id: str
    name: str
    description: str
    class_name: str
    default_symbol: str
    default_parameters: dict
    code: str

    def to_dict(self) -> dict:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "class_name": self.class_name,
            "default_symbol": self.default_symbol,
            "default_parameters": self.default_parameters,
        }


BUY_AND_HOLD_CODE = '''from lumibot.strategies import Strategy


class StudioBuyAndHold(Strategy):
    parameters = {
        "symbol": "SPY",
    }

    def initialize(self):
        self.sleeptime = "1D"

    def on_trading_iteration(self):
        if not self.first_iteration:
            return
        symbol = self.parameters.get("symbol", "SPY")
        price = self.get_last_price(symbol)
        if price is None or price <= 0:
            self.log_message(f"No valid price for {symbol}; skipping entry")
            return
        quantity = int(self.portfolio_value // price)
        if quantity <= 0:
            self.log_message(f"Not enough cash to buy {symbol}")
            return
        order = self.create_order(symbol, quantity, "buy")
        self.submit_order(order)
'''


MOVING_AVERAGE_CODE = '''from lumibot.strategies import Strategy


class StudioMovingAverageCrossover(Strategy):
    parameters = {
        "symbol": "SPY",
        "fast_window": 20,
        "slow_window": 50,
    }

    def initialize(self):
        self.sleeptime = "1D"

    def on_trading_iteration(self):
        symbol = self.parameters.get("symbol", "SPY")
        fast_window = int(self.parameters.get("fast_window", 20))
        slow_window = int(self.parameters.get("slow_window", 50))
        bars = self.get_historical_prices(symbol, slow_window + 2, "day")
        if bars is None or bars.df is None or len(bars.df) < slow_window:
            return
        close = bars.df["close"]
        fast = close.tail(fast_window).mean()
        slow = close.tail(slow_window).mean()
        position = self.get_position(symbol)
        if fast > slow and position is None:
            price = self.get_last_price(symbol)
            quantity = int(self.portfolio_value // price)
            if quantity > 0:
                self.submit_order(self.create_order(symbol, quantity, "buy"))
        elif fast < slow and position is not None:
            self.submit_order(self.create_order(symbol, position.quantity, "sell"))
'''


PORTFOLIO_REBALANCE_CODE = '''from lumibot.strategies import Strategy


class StudioPortfolioRebalance(Strategy):
    parameters = {
        "symbols": "SPY,TLT",
        "rebalance_every_days": 21,
    }

    def initialize(self):
        self.sleeptime = "1D"
        self.vars.iterations = 0

    def on_trading_iteration(self):
        symbols = [
            symbol.strip().upper()
            for symbol in str(self.parameters.get("symbols", "SPY,TLT")).split(",")
            if symbol.strip()
        ]
        if not symbols:
            return
        rebalance_every_days = int(self.parameters.get("rebalance_every_days", 21))
        if not self.first_iteration and self.vars.iterations % rebalance_every_days != 0:
            self.vars.iterations += 1
            return

        target_value = self.portfolio_value / len(symbols)
        for symbol in symbols:
            price = self.get_last_price(symbol)
            if price is None or price <= 0:
                continue
            current_position = self.get_position(symbol)
            current_qty = float(current_position.quantity) if current_position else 0.0
            target_qty = int(target_value // price)
            delta = target_qty - int(current_qty)
            if delta > 0:
                self.submit_order(self.create_order(symbol, delta, "buy"))
            elif delta < 0:
                self.submit_order(self.create_order(symbol, abs(delta), "sell"))
        self.vars.iterations += 1
'''


CSV_SINGLE_SYMBOL_CODE = '''from lumibot.strategies import Strategy


class StudioCsvSingleSymbol(Strategy):
    parameters = {
        "symbol": "SPY",
        "target_cash_pct": 0.02,
    }

    def initialize(self):
        self.sleeptime = "1D"

    def on_trading_iteration(self):
        symbol = self.parameters.get("symbol", "SPY")
        target_cash_pct = float(self.parameters.get("target_cash_pct", 0.02))
        price = self.get_last_price(symbol)
        if price is None or price <= 0:
            return
        position = self.get_position(symbol)
        if position is not None:
            return
        investable = self.portfolio_value * max(0.0, min(1.0, 1.0 - target_cash_pct))
        quantity = int(investable // price)
        if quantity > 0:
            self.submit_order(self.create_order(symbol, quantity, "buy"))
'''


TEMPLATES = {
    "buy_and_hold": StudioTemplate(
        template_id="buy_and_hold",
        name="Buy and Hold",
        description="Buy one stock or ETF on the first trading day and hold it.",
        class_name="StudioBuyAndHold",
        default_symbol="SPY",
        default_parameters={"symbol": "SPY"},
        code=BUY_AND_HOLD_CODE,
    ),
    "moving_average_crossover": StudioTemplate(
        template_id="moving_average_crossover",
        name="Moving Average Crossover",
        description="Buy when a fast moving average is above a slow moving average.",
        class_name="StudioMovingAverageCrossover",
        default_symbol="SPY",
        default_parameters={"symbol": "SPY", "fast_window": 20, "slow_window": 50},
        code=MOVING_AVERAGE_CODE,
    ),
    "portfolio_rebalance": StudioTemplate(
        template_id="portfolio_rebalance",
        name="Portfolio Rebalance",
        description="Equal-weight a comma-separated basket on a fixed cadence.",
        class_name="StudioPortfolioRebalance",
        default_symbol="SPY",
        default_parameters={"symbols": "SPY,TLT", "rebalance_every_days": 21},
        code=PORTFOLIO_REBALANCE_CODE,
    ),
    "csv_single_symbol": StudioTemplate(
        template_id="csv_single_symbol",
        name="CSV Single Symbol",
        description="Use a local OHLCV CSV and buy the selected symbol once.",
        class_name="StudioCsvSingleSymbol",
        default_symbol="SPY",
        default_parameters={"symbol": "SPY", "target_cash_pct": 0.02},
        code=CSV_SINGLE_SYMBOL_CODE,
    ),
}


def list_templates() -> list[dict]:
    return [template.to_dict() for template in TEMPLATES.values()]


def get_template(template_id: str) -> StudioTemplate:
    try:
        return TEMPLATES[template_id]
    except KeyError as exc:
        raise ValueError(f"Unknown Studio template: {template_id}") from exc
