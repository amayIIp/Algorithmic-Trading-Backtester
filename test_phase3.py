import os
import unittest
from datetime import datetime, timedelta
from events import MarketEvent, OrderEvent, FillEvent
from data_handler import DataHandler
from engine import BacktestEngine
from strategy import SMACrossoverStrategy
from portfolio import Portfolio
from execution import SimulatedExecutionHandler, ExecutionSimulator

class TestPhase3(unittest.TestCase):
    def setUp(self):
        self.aapl_csv = "test_aapl_p3.csv"
        
        # 40 bars of price data
        # Bars 1-20: price climbs from 100 to 119
        # Bars 21-30: price stays flat at 120
        # Bars 31-40: price drops from 118 to 100
        prices = list(range(100, 120)) + [120]*10 + list(range(118, 98, -2))
        
        start_time = datetime(2026, 6, 29, 10, 0, 0)
        with open(self.aapl_csv, "w") as f:
            f.write("timestamp,open,high,low,close,volume\n")
            for i, p in enumerate(prices):
                ts = (start_time + timedelta(minutes=i)).isoformat()
                # Volume is 10,000 per bar
                f.write(f"{ts},{float(p)},{float(p+1)},{float(p-1)},{float(p)},10000.0\n")
                
        self.file_paths = {"AAPL": self.aapl_csv}

    def tearDown(self):
        if os.path.exists(self.aapl_csv):
            os.remove(self.aapl_csv)

    def test_execution_simulator_off_vs_on(self):
        print("\n--- Testing Execution Simulator Off vs On (Milestone) ---")
        
        # ----------------------------------------------------
        # Scenario 1: SIMULATOR OFF (No latency, no slippage)
        # ----------------------------------------------------
        dh_off = DataHandler(self.file_paths)
        engine_off = BacktestEngine(dh_off)
        
        strategy_off = SMACrossoverStrategy(short_window=5, long_window=10)
        portfolio_off = Portfolio(initial_capital=100000.0, target_percent=0.5)
        execution_off = SimulatedExecutionHandler(commission=0.0)
        
        engine_off.register_handler(strategy_off)
        engine_off.register_handler(portfolio_off)
        engine_off.register_handler(execution_off)
        
        engine_off.run()
        final_equity_off = portfolio_off.equity_curve[-1]['equity']
        
        # ----------------------------------------------------
        # Scenario 2: SIMULATOR ON (With latency, slippage, and volume impact)
        # ----------------------------------------------------
        dh_on = DataHandler(self.file_paths)
        engine_on = BacktestEngine(dh_on)
        
        strategy_on = SMACrossoverStrategy(short_window=5, long_window=10)
        # Latency of 2 minutes (2 bars delay)
        portfolio_on = Portfolio(
            initial_capital=100000.0, 
            target_percent=0.5, 
            latency=timedelta(minutes=2)
        )
        # 50 bps slippage, 0.5 volume impact coefficient, 10s return latency
        execution_on = ExecutionSimulator(
            commission=10.0, 
            slippage_bps=50.0, 
            volume_impact_coeff=0.5,
            return_latency=timedelta(seconds=10)
        )
        
        engine_on.register_handler(strategy_on)
        engine_on.register_handler(portfolio_on)
        engine_on.register_handler(execution_on)
        
        engine_on.run()
        final_equity_on = portfolio_on.equity_curve[-1]['equity']
        
        # Display comparison
        print(f"Simulator OFF Final Equity: ${final_equity_off:,.2f}")
        print(f"Simulator ON Final Equity:  ${final_equity_on:,.2f}")
        
        # Check that Simulator On has lower returns than Simulator Off due to slippage and lag
        self.assertNotEqual(final_equity_off, final_equity_on)
        self.assertTrue(final_equity_on < final_equity_off)
        print("Milestone reached: Realistic execution simulation correctly penalizes returns!")

    def test_limit_orders(self):
        print("\n--- Testing Limit Order Fill Logic ---")
        # Initialize queue and simulator
        exec_sim = ExecutionSimulator(commission=0.0, slippage_bps=0.0)
        
        # Let's mock the latest market state inside the execution simulator
        t0 = datetime(2026, 6, 29, 10, 0, 0)
        m_event = MarketEvent(
            timestamp=t0,
            symbol="AAPL",
            data={'open': 100.0, 'high': 105.0, 'low': 95.0, 'close': 101.0, 'volume': 1000}
        )
        # Pass MarketEvent to simulator to populate current prices/bars
        exec_sim.handle_event(m_event)
        
        # 1. Test BUY Limit Order that should fill immediately (limit price = 96.0 >= low 95.0)
        buy_lmt = OrderEvent(
            timestamp=t0,
            symbol="AAPL",
            order_type="LMT",
            quantity=100,
            direction="BUY",
            price=96.0
        )
        fills = exec_sim.handle_event(buy_lmt)
        self.assertIsNotNone(fills)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].fill_price, 96.0)
        self.assertEqual(fills[0].quantity, 100)
        print("Immediate BUY limit order fill verified.")
        
        # 2. Test BUY Limit Order that should NOT fill immediately (limit price = 92.0 < low 95.0)
        buy_lmt_unfilled = OrderEvent(
            timestamp=t0,
            symbol="AAPL",
            order_type="LMT",
            quantity=100,
            direction="BUY",
            price=92.0
        )
        fills_unfilled = exec_sim.handle_event(buy_lmt_unfilled)
        self.assertIsNone(fills_unfilled)
        self.assertEqual(len(exec_sim.open_limit_orders), 1)
        print("Unfilled limit order correctly added to order book.")
        
        # 3. Trigger next bar where price drops to 90.0 (high=92.0, low=88.0)
        t1 = t0 + timedelta(minutes=1)
        m_event_drop = MarketEvent(
            timestamp=t1,
            symbol="AAPL",
            data={'open': 94.0, 'high': 96.0, 'low': 88.0, 'close': 90.0, 'volume': 1000}
        )
        fills_from_bar = exec_sim.handle_event(m_event_drop)
        self.assertIsNotNone(fills_from_bar)
        self.assertEqual(len(fills_from_bar), 1)
        self.assertEqual(fills_from_bar[0].fill_price, 92.0)
        self.assertEqual(len(exec_sim.open_limit_orders), 0)
        print("Delayed limit order fill on subsequent bar verified successfully.")

if __name__ == "__main__":
    unittest.main()
