# Algorithmic Trading Event-Driven Backtester

A high-performance, strictly time-ordered event-driven backtesting engine written in Python. This backtester is designed to model realistic market conditions by simulating network latency, fixed and volume-proportional slippage, and limit order books, avoiding any lookahead bias or future-leakage.

## Key Features
* **Memory-Efficient Generator Streaming**: Historical data (CSV/Parquet) is merged chronologically using a min-heap structure, reading row-by-row on demand without loading whole datasets into memory.
* **Strict Chronological Ordering**: A priority queue sorted by timestamp tracks all events, using unique sequence numbers as tie-breakers to avoid type comparisons and preserve FIFO ordering for same-timestamp events.
* **Network & Order Latency**: Configurable delays simulate the time it takes for orders to reach the exchange, causing them to execute on future bars/ticks (market-impact/price lag).
* **Realistic Slippage & Market Impact**: Includes fixed spread/slippage (BPS) and size-based market impact (volume-proportional slippage coefficients).
* **Limit Order Matching**: Queues limit orders in an exchange-side order book, executing them dynamically when subsequent market bars touch or cross the limit thresholds.
* **Zero Lookahead Bias Validation**: Includes validation metrics and lookahead bias detection tests.

---

## Architecture Diagram

```
           +-----------------------------------------+
           |               DataHandler               |
           |   (Streams multi-symbol chronological   |
           |      CSV/Parquet events lazily)         |
           +--------------------+--------------------+
                                |
                                | (MarketEvent)
                                v
           +--------------------+--------------------+
           |               EventQueue                |
           |   (Priority Queue sorted by Timestamp)  |
           +--------------------+--------------------+
                                |
          +---------------------+---------------------+
          |                                           | (Pops Next Event)
          |                                           v
          |                        +------------------+------------------+
          |                        |             BacktestEngine          |
          |                        |            (Main Event Loop)        |
          |                        +------------------+------------------+
          |                                           |
          | (SignalEvent)                             | (MarketEvent)
          v                                           v
+---------+----------+                     +----------+----------+
|      Portfolio     |                     |       Strategy      |
|  (Sizing, Capital, |                     | (SMA / Mean Revert) |
|   Risk Limits)     |                     +---------------------+
+---------+----------+
          |
          | (OrderEvent at T + Latency)
          v
+---------+----------+
| ExecutionSimulator |
| (Slippage, Impact, |
|    Limit Book)     |
+---------+----------+
          |
          | (FillEvent at T + Latency + Return Delay)
          +-------------------------------------------+
```

---

## Project Structure
```
├── events.py           # Core event dataclasses (Market, Signal, Order, Fill)
├── data_handler.py     # Lazy chronological stream generator (CSV & Parquet)
├── engine.py           # EventQueue and central BacktestEngine loop
├── strategy.py         # Abstract Strategy interface, SMA Crossover, and Mean Reversion
├── portfolio.py        # Position tracking, cash account, risk sizing rules
├── execution.py        # Simulated execution handlers (perfect fills vs realistic slippage/latency)
├── metrics.py          # Annualized Sharpe, Max Drawdown, Win Rate, and Turnover calculations
├── report.py           # Console reporting and Matplotlib equity curve rendering
├── config.yaml         # Configuration file for strategy parameters and execution constraints
├── runner.py           # Entry point to parse config, run backtests, and output reports
├── test_backtest.py    # Unit tests for core engine components
├── test_phase2.py      # Unit tests for strategy signals and portfolio accounting
├── test_phase3.py      # Unit tests for realistic execution (slippage vs perfect fills)
├── test_phase4.py      # Unit tests for metrics and lookahead bias validation
└── test_edge_cases.py  # Unit tests for empty files, 0 liquidity, and extreme latency
```

---

## Getting Started

### 1. Prerequisites
Ensure you have Python 3.8+ installed. Install dependencies using:
```bash
pip install pyyaml pandas numpy matplotlib
```
*(Optional) Install `pyarrow` if you wish to stream Parquet files.*

### 2. Running a Backtest
To run a backtest using the configuration defined in `config.yaml`, execute:
```bash
python runner.py
```
*Note: If no input data is found, the runner will automatically generate synthetic historical data for demonstration purposes.*

### 3. Modifying Config
You can customize parameters inside `config.yaml`:
```yaml
strategy:
  name: "SMACrossoverStrategy"
  parameters:
    short_window: 5
    long_window: 10

portfolio:
  initial_capital: 100000.0
  target_percent: 0.5
  latency_seconds: 120       # Delay before order reaches the market

execution:
  commission: 10.0            # Transaction fees
  slippage_bps: 50.0          # Spread penalty
  volume_impact_coeff: 0.5    # Price impact coefficient
```

### 4. Running the Tests
To verify all engine components, run:
```bash
python -m unittest discover
```
