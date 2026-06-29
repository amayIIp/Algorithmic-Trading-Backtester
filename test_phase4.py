import os
import unittest
from datetime import datetime, timedelta
from events import MarketEvent, SignalEvent, OrderEvent, FillEvent
from data_handler import DataHandler
from engine import BacktestEngine
from portfolio import Portfolio
from execution import SimulatedExecutionHandler
from metrics import calculate_performance_metrics

class LookaheadStrategy:
    """
    A strategy that has access to future prices (lookahead bias).
    It looks at the next bar's price to decide whether to BUY or SELL on the current bar.
    """
    def __init__(self, future_prices: list):
        self.future_prices = future_prices
        self.current_idx = 0

    def handle_event(self, event):
        if not isinstance(event, MarketEvent):
            return None
        
        symbol = event.symbol
        current_close = event.data.get('close')
        
        # Look ahead to the next bar
        if self.current_idx < len(self.future_prices) - 1:
            next_close = self.future_prices[self.current_idx + 1]
            self.current_idx += 1
            
            # If price will go up, BUY. If down, SELL.
            if next_close > current_close:
                return SignalEvent(timestamp=event.timestamp, symbol=symbol, direction='BUY')
            elif next_close < current_close:
                return SignalEvent(timestamp=event.timestamp, symbol=symbol, direction='SELL')
                
        return None


class TestPhase4(unittest.TestCase):
    def setUp(self):
        self.test_csv = "test_lookahead.csv"
        
        # Price path: oscillates up and down
        # 100 -> 105 -> 100 -> 105 -> 100 -> 105 ...
        self.prices = [100.0, 105.0, 100.0, 105.0, 100.0, 105.0, 100.0, 105.0, 100.0, 105.0]
        
        start_time = datetime(2026, 6, 29, 10, 0, 0)
        with open(self.test_csv, "w") as f:
            f.write("timestamp,open,high,low,close,volume\n")
            for i, p in enumerate(self.prices):
                ts = (start_time + timedelta(minutes=i)).isoformat()
                f.write(f"{ts},{p},{p+1},{p-1},{p},1000\n")
                
        self.file_paths = {"AAPL": self.test_csv}

    def tearDown(self):
        if os.path.exists(self.test_csv):
            os.remove(self.test_csv)

    def test_performance_metrics_calculation(self):
        print("\n--- Testing Performance Metrics Calculation ---")
        # Generate dummy equity curve
        t0 = datetime(2026, 6, 29, 12, 0, 0)
        equity_curve = [
            {'timestamp': t0, 'cash': 100000.0, 'holdings_val': 0.0, 'equity': 100000.0},
            {'timestamp': t0 + timedelta(days=1), 'cash': 80000.0, 'holdings_val': 22000.0, 'equity': 102000.0},
            {'timestamp': t0 + timedelta(days=2), 'cash': 105000.0, 'holdings_val': 0.0, 'equity': 105000.0},
        ]
        
        # Mock some matched fills
        # Buy 100 shares at 200, Sell 100 shares at 250 (Profit = +$5000, Winning trade)
        class MockFill:
            def __init__(self, symbol, quantity, fill_price, direction):
                self.symbol = symbol
                self.quantity = quantity
                self.fill_price = fill_price
                self.direction = direction

        fills = [
            MockFill("AAPL", 100, 200.0, "BUY"),
            MockFill("AAPL", 100, 250.0, "SELL")
        ]
        
        metrics = calculate_performance_metrics(equity_curve, fills)
        print("Calculated Metrics:", metrics)
        
        self.assertAlmostEqual(metrics['final_equity'], 105000.0)
        self.assertEqual(metrics['total_trades'], 1)
        self.assertEqual(metrics['win_rate'], 1.0)
        # Traded value = 100*200 + 100*250 = 45000. Avg equity = 102333.33. Turnover = 45000/102333.33 = ~0.44
        self.assertAlmostEqual(metrics['turnover'], 45000.0 / ((100000.0 + 102000.0 + 105000.0) / 3.0), places=4)
        self.assertTrue(metrics['sharpe_ratio'] > 0)
        print("Performance metrics calculations validated successfully!")

    def test_lookahead_bias_degradation(self):
        print("\n--- Testing Lookahead Bias Degradation ---")
        
        # ----------------------------------------------------
        # Scenario 1: Lookahead bias ACTIVE (Perfect Execution)
        # ----------------------------------------------------
        dh_bias = DataHandler(self.file_paths)
        engine_bias = BacktestEngine(dh_bias)
        
        strategy_bias = LookaheadStrategy(self.prices)
        portfolio_bias = Portfolio(initial_capital=100000.0, target_percent=0.8, latency=timedelta(seconds=0))
        execution_bias = SimulatedExecutionHandler(commission=0.0)
        
        engine_bias.register_handler(strategy_bias)
        engine_bias.register_handler(portfolio_bias)
        engine_bias.register_handler(execution_bias)
        
        engine_bias.run()
        
        equity_bias = portfolio_bias.equity_curve[-1]['equity']
        
        # ----------------------------------------------------
        # Scenario 2: Lookahead bias DEGRADED (1 bar execution delay)
        # ----------------------------------------------------
        dh_degraded = DataHandler(self.file_paths)
        engine_degraded = BacktestEngine(dh_degraded)
        
        strategy_degraded = LookaheadStrategy(self.prices)
        # We introduce a 1-minute delay (1 bar delay) in order execution
        portfolio_degraded = Portfolio(initial_capital=100000.0, target_percent=0.8, latency=timedelta(minutes=1))
        execution_degraded = SimulatedExecutionHandler(commission=0.0)
        
        engine_degraded.register_handler(strategy_degraded)
        engine_degraded.register_handler(portfolio_degraded)
        engine_degraded.register_handler(execution_degraded)
        
        engine_degraded.run()
        
        equity_degraded = portfolio_degraded.equity_curve[-1]['equity']
        
        print(f"Biased Equity (Instant Fills):   ${equity_bias:,.2f}")
        print(f"Degraded Equity (1 Bar Delayed): ${equity_degraded:,.2f}")
        
        # Biased equity should be much higher because it trades on future info immediately.
        # Degraded equity should lose money or make much less because the oscillations work against it when delayed.
        self.assertTrue(equity_bias > equity_degraded)
        print("Lookahead-bias validation test passed: shifting signals by one bar degrades performance as expected.")

if __name__ == "__main__":
    unittest.main()
