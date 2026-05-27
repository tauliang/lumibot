# Lumibot

Lumibot is a Python framework for building algorithmic trading strategies that can be backtested, paper traded, and run live through supported brokers. It supports classic rule-based strategies, multi-asset backtests, broker integrations, and AI agent strategies that can reason with tools inside the trading loop.

Evaluated against `Lumiwealth/lumibot` on `dev` at commit `1f91fa6c` (`v4.5.32`, 2026-05-23).

> Trading software can lose money quickly. Start with backtests, then paper trading, then small live sizes. Never commit real API keys, broker tokens, or `.env` files.

## Contents

- [Choose Your Use Case](#choose-your-use-case)
- [Requirements](#requirements)
- [Install Lumibot](#install-lumibot)
- [Configuration Basics](#configuration-basics)
- [Use Case 1: Run a No-Key Daily Stock Backtest](#use-case-1-run-a-no-key-daily-stock-backtest)
- [Use Case 2: Run a Backtest with a Specific Data Provider](#use-case-2-run-a-backtest-with-a-specific-data-provider)
- [Use Case 3: Run a Strategy from This Repository](#use-case-3-run-a-strategy-from-this-repository)
- [Use Case 4: Run with Your Own CSV or Pandas Data](#use-case-4-run-with-your-own-csv-or-pandas-data)
- [Use Case 5: Run Crypto Backtests or Crypto Live Trading](#use-case-5-run-crypto-backtests-or-crypto-live-trading)
- [Use Case 6: Run Futures Backtests or Futures Live Trading](#use-case-6-run-futures-backtests-or-futures-live-trading)
- [Use Case 7: Paper Trade with a Broker](#use-case-7-paper-trade-with-a-broker)
- [Use Case 8: Run Live Trading](#use-case-8-run-live-trading)
- [Use Case 9: Run AI Agent Strategies](#use-case-9-run-ai-agent-strategies)
- [Use Case 10: Develop, Test, and Contribute](#use-case-10-develop-test-and-contribute)
- [Backtest Outputs](#backtest-outputs)
- [Broker and Data Source Reference](#broker-and-data-source-reference)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)
- [License and Disclaimer](#license-and-disclaimer)

## Choose Your Use Case

| Goal | Best starting point | Requires credentials? |
| --- | --- | --- |
| Try Lumibot quickly with daily stock or ETF data | Yahoo backtesting | No |
| Backtest stocks or ETFs with better control over data | ThetaData, Polygon, Alpaca, Pandas | Usually |
| Backtest options | ThetaData, Polygon, Tradier, Schwab, Pandas | Usually |
| Backtest futures | DataBento, IBKR REST, ThetaData routing, Pandas | Usually |
| Backtest crypto | CCXT backtesting, Alpaca crypto, Pandas | Sometimes |
| Paper trade stocks/options/crypto | Alpaca, Tradier, Schwab, IBKR, selected CCXT paths | Yes |
| Live trade futures | Tradovate, TopstepX via ProjectX, Bitunix perpetuals | Yes |
| Run an AI trading agent | Any supported backtest or broker path plus model API key | Yes |
| Contribute to the library | Editable source install and pytest | No for unit tests |

## Requirements

- Python `>=3.10`
- `pip`
- A virtual environment is strongly recommended
- Git, if installing from source

The package metadata advertises Python 3.10, 3.11, and 3.12 support. The GitHub workflows in this repo currently run CI and release jobs on Python 3.10.

## Install Lumibot

### Option A: Use Lumibot from PyPI

Use this when you want to write strategies in your own project.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install lumibot
```

Upgrade an existing install:

```bash
pip install --upgrade lumibot
```

### Option B: Develop Lumibot from Source

Use this when you want to modify this repository, run tests, or use the bundled examples.

```bash
git clone https://github.com/Lumiwealth/lumibot.git
cd lumibot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements_dev.txt
pip install -e .
```

ThetaData support has an optional extra:

```bash
pip install -e ".[thetadata]"
```

## Configuration Basics

Lumibot loads configuration from environment variables. For local work, create a `.env` file next to your strategy file or in your project root.

```bash
# Backtesting mode and dates
IS_BACKTESTING=True
BACKTESTING_START=2024-01-01
BACKTESTING_END=2024-12-31
BACKTESTING_DATA_SOURCE=yahoo

# Optional output controls
SHOW_PLOT=True
SHOW_INDICATORS=True
SHOW_TEARSHEET=True
BACKTESTING_QUIET_LOGS=true
BACKTESTING_SHOW_PROGRESS_BAR=true
```

Rules of thumb:

- Keep real secrets out of Git.
- `.env.local` is loaded after `.env` when present, so it can override local machine settings.
- Set `LUMIBOT_DISABLE_DOTENV=1` in production if secrets are injected by the runtime.
- Set `LUMIBOT_DISABLE_DOTENV_LOCAL=1` when `.env.local` should not be loaded.
- `BACKTESTING_DATA_SOURCE` can override the data source passed in code. Set it to `none` if you want code to control the data source.

Useful backtesting values:

```bash
BACKTESTING_DATA_SOURCE=yahoo
BACKTESTING_DATA_SOURCE=thetadata
BACKTESTING_DATA_SOURCE=polygon
BACKTESTING_DATA_SOURCE=alpaca
BACKTESTING_DATA_SOURCE=databento
BACKTESTING_DATA_SOURCE=ccxt
BACKTESTING_DATA_SOURCE=ibkr
BACKTESTING_DATA_SOURCE=router
BACKTESTING_DATA_SOURCE=none
```

Multi-provider routing is also supported:

```bash
BACKTESTING_DATA_SOURCE='{"default":"thetadata","stock":"thetadata","option":"thetadata","index":"thetadata","future":"ibkr","crypto":"ibkr","crypto_future":"ibkr"}'
```

## Use Case 1: Run a No-Key Daily Stock Backtest

This is the fastest way to prove the framework is working. Yahoo backtesting is free and works for daily stock or ETF backtests. It is not intended for intraday, options, futures, or high-fidelity execution modeling.

Create `my_strategy.py`:

```python
from datetime import datetime

from lumibot.backtesting import YahooDataBacktesting
from lumibot.strategies import Strategy


class BuyAndHold(Strategy):
    parameters = {
        "symbol": "SPY",
    }

    def initialize(self):
        self.sleeptime = "1D"

    def on_trading_iteration(self):
        if self.first_iteration:
            symbol = self.parameters["symbol"]
            price = self.get_last_price(symbol)
            quantity = int(self.portfolio_value // price)
            order = self.create_order(symbol, quantity, "buy")
            self.submit_order(order)


if __name__ == "__main__":
    BuyAndHold.backtest(
        YahooDataBacktesting,
        datetime(2024, 1, 1),
        datetime(2024, 12, 31),
        benchmark_asset="SPY",
    )
```

Run it:

```bash
python my_strategy.py
```

Expected result: Lumibot runs the simulation and writes logs, trades, stats, plots, and tearsheet artifacts under a local `logs/` directory.

## Use Case 2: Run a Backtest with a Specific Data Provider

Use provider-specific backtesting when Yahoo is too coarse or does not support your asset class.

### ThetaData

Best for U.S. equities, options, indexes, and deeper historical coverage. Some workflows require a ThetaData account. Lumibot can cache data locally.

```bash
THETADATA_USERNAME=your_username
THETADATA_PASSWORD=your_password
BACKTESTING_DATA_SOURCE=thetadata
```

```python
from datetime import datetime

from lumibot.backtesting import ThetaDataBacktesting

results = MyStrategy.backtest(
    ThetaDataBacktesting,
    datetime(2024, 1, 1),
    datetime(2024, 6, 1),
    benchmark_asset="SPY",
)
```

### Polygon

Useful for stocks, options, forex, and crypto when you already have Polygon access.

```bash
POLYGON_API_KEY=your_polygon_key
BACKTESTING_DATA_SOURCE=polygon
```

```python
from datetime import datetime

from lumibot.backtesting import PolygonDataBacktesting

results = MyStrategy.backtest(
    PolygonDataBacktesting,
    datetime(2024, 1, 1),
    datetime(2024, 6, 1),
    polygon_api_key="your_polygon_key",
    benchmark_asset="SPY",
)
```

### Alpaca Backtesting

Useful when you want Alpaca market data in a backtest.

```bash
ALPACA_API_KEY=your_key
ALPACA_API_SECRET=your_secret
ALPACA_IS_PAPER=true
BACKTESTING_DATA_SOURCE=alpaca
```

```python
from datetime import datetime

from lumibot.backtesting import AlpacaBacktesting
from lumibot.credentials import ALPACA_CONFIG

results = MyStrategy.backtest(
    AlpacaBacktesting,
    datetime(2024, 1, 1),
    datetime(2024, 6, 1),
    config=ALPACA_CONFIG,
    benchmark_asset="SPY",
)
```

### DataBento

Useful for futures and high-quality market data.

```bash
DATABENTO_API_KEY=your_databento_key
BACKTESTING_DATA_SOURCE=databento
```

```python
from lumibot.backtesting import DataBentoDataBacktesting
from lumibot.entities import Asset

results = MyStrategy.backtest(
    DataBentoDataBacktesting,
    benchmark_asset=Asset("SPY", Asset.AssetType.STOCK),
)
```

### Environment-Driven Backtests

If you want run configuration outside your code:

```bash
export IS_BACKTESTING=True
export BACKTESTING_START=2024-01-01
export BACKTESTING_END=2024-12-31
export BACKTESTING_DATA_SOURCE=yahoo
python my_strategy.py
```

Then let Lumibot select the data source:

```python
if __name__ == "__main__":
    MyStrategy.backtest(
        None,
        benchmark_asset="SPY",
    )
```

## Use Case 3: Run a Strategy from This Repository

The example strategies live in `lumibot/example_strategies/`.

From a source checkout:

```bash
cd lumibot
source .venv/bin/activate
python -m lumibot.example_strategies.stock_momentum
```

Explore examples:

```bash
ls lumibot/example_strategies
```

Representative examples:

| File | Use case |
| --- | --- |
| `stock_buy_and_hold.py` | Simple stock backtest / live skeleton; requires Alpaca test config in its current form |
| `stock_momentum.py` | Stock momentum strategy |
| `stock_bracket.py` | Bracket orders |
| `stock_oco.py` | One-cancels-other orders |
| `stock_limit_and_trailing_stops.py` | Limit and trailing stop behavior |
| `classic_60_40.py` | Allocation and rebalancing |
| `crypto_50_50.py` | Crypto allocation backtest |
| `ccxt_backtesting_example.py` | CCXT crypto backtesting |
| `options_hold_to_expiry.py` | Options lifecycle example |
| `futures_hold_to_expiry.py` | Futures lifecycle example |
| `bitunix_futures_example.py` | Bitunix perpetual futures |
| `agent_discretionary.py` | Single AI agent strategy |
| `ai_investment_committee.py` | Multi-agent investment committee |

Some examples require broker or data credentials. Read the top of the file before running.

## Use Case 4: Run with Your Own CSV or Pandas Data

Use Pandas backtesting when you have your own bars from CSV, parquet, a database, or another vendor. Your dataframe must have a datetime index and OHLCV columns: `open`, `high`, `low`, `close`, `volume`.

```python
from datetime import datetime

import pandas as pd

from lumibot.backtesting import PandasDataBacktesting
from lumibot.entities import Asset, Data
from lumibot.strategies import Strategy


class CsvStrategy(Strategy):
    def initialize(self):
        self.sleeptime = "1D"

    def on_trading_iteration(self):
        if self.first_iteration:
            order = self.create_order("AAPL", 10, "buy")
            self.submit_order(order)


if __name__ == "__main__":
    df = pd.read_csv("AAPL.csv", parse_dates=["datetime"])
    df = df.set_index("datetime")

    asset = Asset("AAPL", asset_type=Asset.AssetType.STOCK)
    pandas_data = {
        asset: Data(asset, df, timestep="day"),
    }

    CsvStrategy.backtest(
        PandasDataBacktesting,
        datetime(2024, 1, 1),
        datetime(2024, 12, 31),
        pandas_data=pandas_data,
        benchmark_asset="SPY",
    )
```

Use `timestep="minute"` for minute bars and `timestep="day"` for daily bars.

## Use Case 5: Run Crypto Backtests or Crypto Live Trading

Lumibot uses CCXT for selected crypto paths. It does not claim blanket support for every CCXT exchange.

Documented status:

- Auto-detected credential paths: Coinbase, Kraken, WEEX
- Exchange-specific live handling exists for selected Coinbase/Coinbase Pro, Kraken, KuCoin, and Binance paths
- Documented backtesting examples: Kraken, Binance, KuCoin, BitMEX, Bybit, OKX

For crypto strategies, set a 24/7 market:

```python
def initialize(self):
    self.sleeptime = "1H"
    self.set_market("24/7")
```

### CCXT Crypto Backtesting

```bash
BACKTESTING_DATA_SOURCE=kraken
python my_crypto_strategy.py
```

Or use a CCXT backtesting class directly:

```python
from lumibot.backtesting import CcxtBacktesting

MyCryptoStrategy.backtest(
    CcxtBacktesting,
    backtesting_start,
    backtesting_end,
    exchange_id="kraken",
)
```

### Kraken Live Trading

```bash
KRAKEN_API_KEY=your_key
KRAKEN_API_SECRET=your_secret
TRADING_BROKER=kraken
```

### Coinbase Live Trading

Coinbase CDP keys use an API key name and a private key.

```bash
COINBASE_API_KEY_NAME=organizations/<org-id>/apiKeys/<key-id>
COINBASE_PRIVATE_KEY="-----BEGIN EC PRIVATE KEY-----\n...\n-----END EC PRIVATE KEY-----\n"
TRADING_BROKER=coinbase
```

### WEEX Live Trading

```bash
WEEX_API_KEY=your_key
WEEX_API_SECRET=your_secret
WEEX_API_PASSPHRASE=your_passphrase
TRADING_BROKER=weex
```

WEEX has no public API sandbox and has jurisdiction restrictions. Validate with tiny sizes.

## Use Case 6: Run Futures Backtests or Futures Live Trading

Use `Asset.AssetType.CONT_FUTURE` for continuous futures when possible. Lumibot can handle contract rollover in supported data paths.

```python
from lumibot.entities import Asset

mes = Asset("MES", asset_type=Asset.AssetType.CONT_FUTURE)
```

Common futures symbols:

| Symbol | Description |
| --- | --- |
| `MES` | Micro E-mini S&P 500 |
| `ES` | E-mini S&P 500 |
| `MNQ` / `NQ` | Micro / standard Nasdaq futures |
| `M2K` / `RTY` | Micro / standard Russell futures |
| `CL` | Crude oil |
| `GC` | Gold |
| `ZN` | 10-Year Treasury Note |

### DataBento Futures Backtesting

```bash
DATABENTO_API_KEY=your_databento_key
BACKTESTING_DATA_SOURCE=databento
```

```python
from lumibot.backtesting import DataBentoDataBacktesting
from lumibot.entities import Asset
from lumibot.strategies import Strategy


class FuturesStrategy(Strategy):
    def initialize(self):
        self.sleeptime = "1M"
        self.asset = Asset("MES", asset_type=Asset.AssetType.CONT_FUTURE)

    def on_trading_iteration(self):
        price = self.get_last_price(self.asset)
        self.log_message(f"MES price: {price}")


FuturesStrategy.backtest(
    DataBentoDataBacktesting,
    benchmark_asset=Asset("SPY", Asset.AssetType.STOCK),
)
```

### Tradovate Live Futures Trading

Tradovate is a futures broker but does not provide market data. Configure a separate data source such as DataBento, ProjectX, or IBKR.

```bash
TRADING_BROKER=tradovate
TRADOVATE_USERNAME=your_username
TRADOVATE_DEDICATED_PASSWORD=your_api_password
TRADOVATE_CID=your_client_id
TRADOVATE_SECRET=your_secret
TRADOVATE_IS_PAPER=true

DATA_SOURCE=databento
DATABENTO_API_KEY=your_databento_key
```

### TopstepX via ProjectX

```bash
TRADING_BROKER=projectx
PROJECTX_TOPSTEPX_API_KEY=your_api_key
PROJECTX_TOPSTEPX_USERNAME=your_username
PROJECTX_TOPSTEPX_PREFERRED_ACCOUNT_NAME=your_account_name
```

### Bitunix Perpetual Futures

Bitunix support is for crypto perpetual futures, not spot trading.

```bash
TRADING_BROKER=bitunix
BITUNIX_API_KEY=your_key
BITUNIX_API_SECRET=your_secret
BITUNIX_TRADING_MODE=FUTURES
```

For accurate available-cash calculations, keep funds in the Bitunix futures wallet, preferably as USDT.

## Use Case 7: Paper Trade with a Broker

Paper trading is the recommended bridge between backtests and live trading.

### Alpaca Paper Trading

```bash
ALPACA_API_KEY=your_key
ALPACA_API_SECRET=your_secret
ALPACA_IS_PAPER=true
TRADING_BROKER=alpaca
```

```python
from lumibot.brokers import Alpaca
from lumibot.credentials import ALPACA_CONFIG
from lumibot.strategies import Strategy
from lumibot.traders import Trader


class PaperStrategy(Strategy):
    def initialize(self):
        self.sleeptime = "1D"

    def on_trading_iteration(self):
        if self.first_iteration:
            order = self.create_order("SPY", 1, "buy")
            self.submit_order(order)


if __name__ == "__main__":
    broker = Alpaca(ALPACA_CONFIG)
    strategy = PaperStrategy(broker=broker)
    trader = Trader()
    trader.add_strategy(strategy)
    trader.run_all()
```

Run it:

```bash
python paper_strategy.py
```

### Tradier Paper Trading

```bash
TRADIER_ACCESS_TOKEN=your_access_token
TRADIER_ACCOUNT_NUMBER=your_account_number
TRADIER_IS_PAPER=true
TRADING_BROKER=tradier
```

```python
from lumibot.brokers import Tradier
from lumibot.credentials import TRADIER_CONFIG

broker = Tradier(config=TRADIER_CONFIG)
```

### Schwab Sandbox or Approved Account

Schwab uses OAuth. First run may open a browser or print a one-time authorization URL.

```bash
TRADING_BROKER=schwab
SCHWAB_ACCOUNT_NUMBER=your_account_number
SCHWAB_APP_KEY=your_app_key
SCHWAB_APP_SECRET=your_app_secret
SCHWAB_BACKEND_CALLBACK_URL=https://127.0.0.1:8182
```

Keep `token.json` out of version control.

## Use Case 8: Run Live Trading

Live trading uses the same strategy class as paper trading. Change the broker configuration from paper or sandbox to live.

Examples:

```bash
# Alpaca live
ALPACA_IS_PAPER=false
TRADING_BROKER=alpaca
```

```bash
# Tradier live
TRADIER_IS_PAPER=false
TRADING_BROKER=tradier
```

```bash
# Tradovate live
TRADOVATE_IS_PAPER=false
TRADING_BROKER=tradovate
DATA_SOURCE=databento
```

Operational checklist before live trading:

- Run the strategy as a backtest over the intended period.
- Inspect trades, equity curve, drawdown, and logs.
- Run paper trading long enough to confirm order types, asset symbols, timezones, and broker behavior.
- Use small live sizes first.
- Add broker-side risk limits where available.
- Monitor logs, positions, open orders, buying power, and failed order events.
- Keep secrets and token files out of Git.

## Use Case 9: Run AI Agent Strategies

Lumibot includes an AI agent runtime inside the normal `Strategy` lifecycle. Agents can inspect account state, market data, orders, memory, indicators, docs, SEC data, FRED macro data, and custom tools. Trading permissions are controlled per agent.

### Single-Agent Backtest

```bash
export AGENT_MODEL="openai/gpt-5.4"
export OPENAI_API_KEY="your_openai_key"
export FRED_API_KEY="your_fred_key"
export BACKTESTING_START=2024-01-01
export BACKTESTING_END=2024-02-01
python -m lumibot.example_strategies.agent_discretionary
```

Other provider examples in the repo:

```bash
python -m lumibot.example_strategies.agent_m2_liquidity
python -m lumibot.example_strategies.agent_m2_liquidity_openai
python -m lumibot.example_strategies.agent_m2_liquidity_anthropic
python -m lumibot.example_strategies.agent_m2_liquidity_grok
```

### Multi-Agent Investment Committee

```bash
export COMMITTEE_RESEARCH_MODEL="openai/gpt-5.4-mini"
export COMMITTEE_BULL_MODEL="openai/gpt-5.5"
export COMMITTEE_BEAR_MODEL="openai/gpt-5.5"
export COMMITTEE_TRADER_MODEL="openai/gpt-5.5"
export OPENAI_API_KEY="your_openai_key"
export FRED_API_KEY="your_fred_key"
python -m lumibot.example_strategies.ai_investment_committee
```

Agent safety pattern:

```python
self.agents.create(
    name="researcher",
    model="openai/gpt-5.4-mini",
    allow_trading=False,
)

self.agents.create(
    name="portfolio_manager",
    model="openai/gpt-5.5",
    allow_trading=True,
)
```

Use `allow_trading=False` for research agents that should not submit, cancel, or modify orders.

Custom tools can be exposed with `@agent_tool`:

```python
from lumibot.components.agents import agent_tool
from lumibot.strategies import Strategy


class MyAgentStrategy(Strategy):
    @agent_tool(
        name="get_internal_signal",
        description="Fetch an internal signal for a ticker.",
    )
    def get_internal_signal(self, symbol: str) -> dict:
        return {"symbol": symbol, "score": 0.72}

    def initialize(self):
        self.agents.create(
            name="analyst",
            default_model="openai/gpt-5.4-mini",
            tools=[self.get_internal_signal],
            allow_trading=False,
        )
```

Backtest agent runs produce trace artifacts such as `agent_run_summaries.jsonl` and `agent_traces.zip`.

## Use Case 10: Develop, Test, and Contribute

Install development dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements_dev.txt
pip install -e .
```

Run the normal unit suite:

```bash
python -m pytest -m "not apitest and not downloader" --tb=short -q --durations=30
```

Run all tests:

```bash
pytest
```

Run one test file:

```bash
pytest tests/test_asset.py
```

Run coverage:

```bash
coverage run
coverage report
```

Run targeted lint checks:

```bash
ruff check .
isort --check-only .
```

Build docs locally:

```bash
pip install sphinx furo sphinx-llms-txt
cd docsrc
make html
```

Test markers:

| Marker | Meaning |
| --- | --- |
| `apitest` | Requires live external APIs or broker credentials |
| `downloader` | Requires the shared Theta downloader service |
| `acceptance_backtest` | Full strategy-library acceptance backtests |
| `smartlimit_matrix` | Larger live smart-limit matrix tests |

## Backtest Outputs

Lumibot writes backtest artifacts under `logs/` by default. Depending on configuration and strategy behavior, outputs can include:

- strategy logs
- trade records
- trade event records
- stats files
- indicator files
- tearsheet HTML
- plot files
- parquet versions of machine-readable artifacts
- AI agent summaries and traces

Useful output flags:

```bash
SHOW_PLOT=True
SHOW_INDICATORS=True
SHOW_TEARSHEET=True
BACKTESTING_QUIET_LOGS=true
BACKTESTING_SHOW_PROGRESS_BAR=true
LOG_BACKTEST_PROGRESS_TO_FILE=true
```

For production-style artifact strictness:

```bash
LUMIBOT_BACKTEST_PARQUET_MODE=required
```

For profiling:

```bash
BACKTESTING_PROFILE=yappi
```

## Broker and Data Source Reference

### Live Brokers

| Broker | Main asset focus | Key environment variables |
| --- | --- | --- |
| Alpaca | Stocks, ETFs, options, crypto | `ALPACA_API_KEY`, `ALPACA_API_SECRET`, `ALPACA_IS_PAPER` |
| Tradier | Stocks, ETFs, options | `TRADIER_ACCESS_TOKEN`, `TRADIER_ACCOUNT_NUMBER`, `TRADIER_IS_PAPER` |
| Schwab | Stocks, ETFs, options | `SCHWAB_ACCOUNT_NUMBER`, `SCHWAB_APP_KEY`, `SCHWAB_APP_SECRET`, `SCHWAB_BACKEND_CALLBACK_URL` |
| Interactive Brokers | Multi-asset | `IB_USERNAME`, `IB_PASSWORD`, `IB_ACCOUNT_ID`, or TWS socket settings |
| Tradovate | Futures | `TRADOVATE_USERNAME`, `TRADOVATE_DEDICATED_PASSWORD`, `TRADOVATE_CID`, `TRADOVATE_SECRET` |
| ProjectX / TopstepX | Futures | `PROJECTX_TOPSTEPX_API_KEY`, `PROJECTX_TOPSTEPX_USERNAME` |
| Bitunix | Crypto perpetual futures | `BITUNIX_API_KEY`, `BITUNIX_API_SECRET`, `BITUNIX_TRADING_MODE` |
| CCXT selected paths | Crypto | Exchange-specific vars such as `KRAKEN_API_KEY`, `COINBASE_API_KEY_NAME`, `WEEX_API_KEY` |

### Backtesting Data Sources

| Data source | Best for | Notes |
| --- | --- | --- |
| Yahoo | Daily stocks and ETFs | No API key, daily only |
| ThetaData | Stocks, options, indexes, richer history | Caches locally, account may be required |
| Polygon | Stocks, options, forex, crypto | Requires `POLYGON_API_KEY` |
| Alpaca | Alpaca market data | Requires Alpaca credentials |
| DataBento | Futures and high-quality historical data | Requires `DATABENTO_API_KEY` |
| IBKR REST | IBKR-backed historical data | Requires IBKR setup or downloader path |
| CCXT | Crypto backtesting examples | Exchange support varies |
| Pandas | Custom CSV/dataframe data | Most flexible, most manual |
| Routed backtesting | Different provider per asset type | Use JSON `BACKTESTING_DATA_SOURCE` |

## Troubleshooting

### `No .env file found`

This is not fatal if you are using shell environment variables or a secrets manager. Create a `.env` file only if you want local file-based configuration.

### My code passes one data source but Lumibot uses another

Check `BACKTESTING_DATA_SOURCE`. If it is set, it can override the class passed in code. Use:

```bash
BACKTESTING_DATA_SOURCE=none
```

### Yahoo backtesting does not have intraday bars

Yahoo is for daily stock and ETF backtests. Use ThetaData, Polygon, Alpaca, DataBento, IBKR, CCXT, or Pandas for other assets or intraday work.

### Tradovate connects but prices are missing

Tradovate does not provide market data. Set a separate `DATA_SOURCE`, for example:

```bash
DATA_SOURCE=databento
DATABENTO_API_KEY=your_key
```

### Schwab asks for login again

Schwab refresh tokens expire if the service is offline too long. Repeat the OAuth flow and keep `token.json` secure and out of Git.

### CCXT exchange does not work

Lumibot supports selected CCXT paths, not every CCXT exchange. Start with the documented exchanges, use tiny sizes, and validate balances, positions, order submission, fills, and cancellation before increasing size.

### Tests try to call real services

Use the normal local test command:

```bash
python -m pytest -m "not apitest and not downloader" --tb=short -q --durations=30
```

## Documentation

- Full docs: https://lumibot.lumiwealth.com/
- Source repository: https://github.com/Lumiwealth/lumibot
- PyPI: https://pypi.org/project/lumibot/
- Internal docs index: `docs/README.md`
- Environment variables: `docs/ENV_VARS.md` and `docsrc/environment_variables.rst`
- Backtesting architecture: `docs/BACKTESTING_ARCHITECTURE.md`
- AI trading agents: `docs/AI_TRADING_AGENTS.md`
- Deployment notes: `docs/DEPLOYMENT.md`
- Migration from Backtrader: `docs/MIGRATING_FROM_BACKTRADER.md`

## License and Disclaimer

Lumibot is released under the MIT License. See `LICENSE`.

This software is provided for educational and informational purposes only. It is not financial advice and does not constitute a recommendation to buy or sell any security. Algorithmic trading involves substantial risk of loss, including the possibility of losses greater than your initial investment. Past backtest performance does not guarantee future results. You are responsible for your own trading decisions, broker configuration, regulatory compliance, and risk controls.
