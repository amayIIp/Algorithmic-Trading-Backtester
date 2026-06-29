import yaml
import sys
import os
from datetime import timedelta
from data_handler import DataHandler
from engine import BacktestEngine
from strategy import SMACrossoverStrategy, MeanReversionStrategy
from portfolio import Portfolio
from execution import ExecutionSimulator
from report import generate_report

def run_backtest_from_config(config_path: str):
    """Loads configuration from YAML and runs the backtester."""
    if not os.path.exists(config_path):
        print(f"Error: Config file not found at {config_path}")
        sys.exit(1)

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # 1. Parse Data Config
    file_paths = config['data']['file_paths']
    
    # Check that data files exist
    for sym, path in file_paths.items():
        if not os.path.exists(path):
            # Create a simple synthetic dataset if configured file doesn't exist
            # This makes the project instantly runnable out-of-the-box
            print(f"Data file for {sym} not found at {path}. Generating synthetic data for demonstration...")
            from test_phase3 import TestPhase3
            test_setup = TestPhase3()
            test_setup.setUp()
            # Rename/copy file to the target path if needed
            if path != test_setup.aapl_csv:
                os.rename(test_setup.aapl_csv, path)
            print(f"Synthetic data generated at {path}")

    dh = DataHandler(file_paths)
    engine = BacktestEngine(dh)

    # 2. Parse Strategy Config
    strat_config = config['strategy']
    strat_name = strat_config['name']
    strat_params = strat_config.get('parameters', {})
    
    if strat_name == "SMACrossoverStrategy":
        strategy = SMACrossoverStrategy(**strat_params)
    elif strat_name == "MeanReversionStrategy":
        strategy = MeanReversionStrategy(**strat_params)
    else:
        raise ValueError(f"Unknown strategy class: {strat_name}")

    # 3. Parse Portfolio Config
    port_config = config['portfolio']
    portfolio = Portfolio(
        initial_capital=float(port_config.get('initial_capital', 100000.0)),
        target_percent=float(port_config.get('target_percent', 0.2)),
        max_position_pct=float(port_config.get('max_position_pct', 0.5)),
        latency=timedelta(seconds=port_config.get('latency_seconds', 0))
    )

    # 4. Parse Execution Config
    exec_config = config['execution']
    execution = ExecutionSimulator(
        commission=float(exec_config.get('commission', 0.0)),
        slippage_bps=float(exec_config.get('slippage_bps', 0.0)),
        volume_impact_coeff=float(exec_config.get('volume_impact_coeff', 0.0)),
        return_latency=timedelta(seconds=exec_config.get('return_latency_seconds', 0))
    )

    # 5. Register Handlers and Run
    engine.register_handler(strategy)
    engine.register_handler(portfolio)
    engine.register_handler(execution)

    print(f"Starting backtest using strategy: {strat_name}...")
    engine.run()
    print("Backtest run complete.")

    # 6. Generate Report
    generate_report(portfolio.equity_curve, execution.all_fills)

if __name__ == "__main__":
    config_file = "config.yaml"
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    run_backtest_from_config(config_file)
