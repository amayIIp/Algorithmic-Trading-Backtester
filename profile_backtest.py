import os
import cProfile
import pstats
from datetime import datetime, timedelta
import numpy as np
from data_handler import DataHandler
from engine import BacktestEngine
from strategy import SMACrossoverStrategy
from portfolio import Portfolio
from execution import ExecutionSimulator

def generate_profiling_data(file_path: str, num_bars: int = 100000):
    """Generates a large synthetic CSV file for profiling."""
    print(f"Generating {num_bars} bars of profiling data...")
    start_time = datetime(2026, 1, 1, 9, 30, 0)
    
    # Generate prices using a random walk
    np.random.seed(42)
    returns = np.random.normal(0.00002, 0.001, num_bars)
    prices = 100.0 * np.exp(np.cumsum(returns))
    
    with open(file_path, "w") as f:
        f.write("timestamp,open,high,low,close,volume\n")
        for i in range(num_bars):
            ts = (start_time + timedelta(seconds=i)).isoformat()
            p = prices[i]
            vol = float(np.random.randint(100, 10000))
            # Open, High, Low, Close
            f.write(f"{ts},{p:.4f},{p+0.1:.4f},{p-0.1:.4f},{p:.4f},{vol:.1f}\n")
    print("Data generation complete.")

def run_backtest(file_path: str):
    dh = DataHandler({"SYM": file_path})
    engine = BacktestEngine(dh)
    
    strategy = SMACrossoverStrategy(short_window=20, long_window=50)
    portfolio = Portfolio(initial_capital=100000.0, latency=timedelta(seconds=1))
    execution = ExecutionSimulator(commission=1.0, slippage_bps=5.0)
    
    engine.register_handler(strategy)
    engine.register_handler(portfolio)
    engine.register_handler(execution)
    
    engine.run()
    
    print(f"Backtest finished. Final equity: {portfolio.equity_curve[-1]['equity']:.2f}")

def main():
    csv_file = "large_profile_data.csv"
    if not os.path.exists(csv_file):
        generate_profiling_data(csv_file, num_bars=100000)
    
    print("Starting profiling run...")
    profiler = cProfile.Profile()
    profiler.enable()
    
    run_backtest(csv_file)
    
    profiler.disable()
    stats = pstats.Stats(profiler).sort_stats(pstats.SortKey.TIME)
    stats.print_stats(30)
    
    # Clean up
    if os.path.exists(csv_file):
        os.remove(csv_file)

if __name__ == "__main__":
    main()
