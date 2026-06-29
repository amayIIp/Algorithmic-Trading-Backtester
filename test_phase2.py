import os
import unittest
from datetime import datetime, timedelta
from events import MarketEvent, SignalEvent, OrderEvent, FillEvent
from data_handler import DataHandler
from engine import BacktestEngine
from strategy import SMACrossoverStrategy, MeanReversionStrategy
from portfolio import Portfolio
from execution import SimulatedExecutionHandler

class TestPhase2(unittest.TestCase):
    def setUp(self):
        self.aapl_csv = "test_aapl_p2.csv"
        
        # We will generate 17 bars.
        # Bars 1-10: flat close of 100.0
        # Bar 11: 105.0 (Crossover above -> BUY)
        # Bar 12: 106.0
        # Bar 13: 95.0
        # Bar 14-17: 90.0 (Crossover below -> SELL)
        prices = [100.0] * 10 + [105.0, 106.0, 95.0, 90.0, 90.0, 90.0, 90.0]
        
        start_time = datetime(2026, 6, 29, 10, 0, 0)
        with open(self.aapl_csv, "w") as f:
            f.write("timestamp,open,high,low,close,volume\n")
            for i, p in enumerate(prices):
                ts = (start_time + timedelta(minutes=i)).isoformat()
                f.write(f"{ts},{p},{p+2},{p-2},{p},1000\n")
                
        self.file_paths = {"AAPL": self.aapl_csv}

    def tearDown(self):
        if os.path.exists(self.aapl_csv):
            os.remove(self.aapl_csv)

    def test_sma_crossover_and_portfolio_accounting(self):
        print("\n--- Testing SMA Crossover and Portfolio Logic ---")
        dh = DataHandler(self.file_paths)
        engine = BacktestEngine(dh)
        
        # Short window = 5, Long window = 10
        strategy = SMACrossoverStrategy(short_window=5, long_window=10)
        portfolio = Portfolio(initial_capital=100000.0, target_percent=0.2)
        execution = SimulatedExecutionHandler(commission=10.0) # Fixed commission of $10 per trade
        
        engine.register_handler(strategy)
        engine.register_handler(portfolio)
        engine.register_handler(execution)
        
        engine.run()
        
        # Let's inspect the equity curve and transactions
        print("Final Cash:", portfolio.cash)
        print("Final Positions:", portfolio.positions)
        print("Equity Curve Length:", len(portfolio.equity_curve))
        for entry in portfolio.equity_curve:
            print(f"Time: {entry['timestamp']} | Cash: {entry['cash']:.2f} | Holdings: {entry['holdings_val']:.2f} | Equity: {entry['equity']:.2f}")

        # Assertions
        # 1. Total bars processed is 17
        self.assertEqual(len(portfolio.equity_curve), 17)
        
        # 2. Check BUY order on bar 11
        # At bar 11 (2026-06-29T10:10:00), price is 105.0. 
        # Target spend = 20% of 100k = $20,000. 
        # Shares = 20,000 // 105.0 = 190.
        # Cost = 190 * 105.0 + 10.0 commission = $19,960.0.
        # Remaining cash = 100,000 - 19,960 = $80,040.0.
        bar_11_entry = portfolio.equity_curve[10]
        self.assertAlmostEqual(bar_11_entry['cash'], 80040.0)
        self.assertAlmostEqual(bar_11_entry['holdings_val'], 190 * 105.0)
        self.assertAlmostEqual(bar_11_entry['equity'], 100000.0 - 10.0) # Commission subtracted
        
        # 3. Check SELL/Liquidation order on bar 17 (index 16)
        # Price is 90.0. 
        # Shares held = 190.
        # Revenue = 190 * 90.0 - 10.0 commission = $17,090.0.
        # New cash = 80,040 + 17,090 = $97,130.0.
        # Holdings val = 0.
        # Total equity = $97,130.0.
        bar_17_entry = portfolio.equity_curve[16]
        self.assertAlmostEqual(bar_17_entry['cash'], 97130.0)
        self.assertAlmostEqual(bar_17_entry['holdings_val'], 0.0)
        self.assertAlmostEqual(bar_17_entry['equity'], 97130.0)
        
        print("Crossover, order sizing, and equity curve updates verified successfully!")

    def test_mean_reversion_strategy(self):
        print("\n--- Testing Mean Reversion Strategy ---")
        # Let's generate data that triggers Mean Reversion
        # We want price to drop sharply, stay down to fill window, then revert
        prices = [100.0] * 20 + [50.0]  # Standard deviation becomes non-zero at bar 21, and 50.0 is way below mean
        
        mrev_csv = "test_mrev.csv"
        start_time = datetime(2026, 6, 29, 10, 0, 0)
        with open(mrev_csv, "w") as f:
            f.write("timestamp,open,high,low,close,volume\n")
            for i, p in enumerate(prices):
                ts = (start_time + timedelta(minutes=i)).isoformat()
                f.write(f"{ts},{p},{p+1},{p-1},{p},1000\n")
                
        dh = DataHandler({"AAPL": mrev_csv})
        engine = BacktestEngine(dh)
        
        strategy = MeanReversionStrategy(window=20, entry_threshold=2.0)
        portfolio = Portfolio(initial_capital=100000.0)
        execution = SimulatedExecutionHandler()
        
        engine.register_handler(strategy)
        engine.register_handler(portfolio)
        engine.register_handler(execution)
        
        engine.run()
        
        if os.path.exists(mrev_csv):
            os.remove(mrev_csv)

        # On the 21st bar (price=50), the mean is approx 97.6, std is approx 10.9
        # Z-score of 50.0 is (50 - 97.6)/10.9 = -4.36 < -2.0 -> Should trigger BUY.
        # Verify that we bought AAPL shares
        self.assertTrue("AAPL" in portfolio.positions or len(portfolio.equity_curve) > 20)
        # Check that we hold positive shares
        self.assertTrue(portfolio.positions.get("AAPL", 0) > 0)
        print(f"Mean Reversion BUY triggered successfully! Position size: {portfolio.positions.get('AAPL')} shares")

if __name__ == "__main__":
    unittest.main()
