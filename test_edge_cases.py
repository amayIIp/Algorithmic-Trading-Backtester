import os
import unittest
from datetime import datetime, timedelta
from events import MarketEvent, OrderEvent, SignalEvent
from data_handler import DataHandler
from engine import BacktestEngine
from portfolio import Portfolio
from execution import ExecutionSimulator

class TestEdgeCases(unittest.TestCase):
    def test_no_data_empty_file(self):
        print("\n--- Edge Case: Empty Data File ---")
        empty_csv = "empty_test.csv"
        with open(empty_csv, "w") as f:
            f.write("")  # Completely empty file
            
        dh = DataHandler({"AAPL": empty_csv})
        engine = BacktestEngine(dh)
        
        # Verify that running on an empty file terminates gracefully without crash
        try:
            engine.run()
            print("Engine terminated gracefully on empty data file.")
        except Exception as e:
            self.fail(f"Engine crashed on empty data file with exception: {e}")
        finally:
            if os.path.exists(empty_csv):
                os.remove(empty_csv)

    def test_missing_timestamp_column(self):
        print("\n--- Edge Case: Missing Timestamp Column ---")
        bad_csv = "bad_test.csv"
        with open(bad_csv, "w") as f:
            f.write("open,high,low,close,volume\n")
            f.write("100.0,105.0,95.0,101.0,1000\n")
            
        dh = DataHandler({"AAPL": bad_csv})
        
        with self.assertRaises(ValueError) as context:
            list(dh.stream_data())
            
        self.assertIn("No timestamp column found", str(context.exception))
        print("DataHandler correctly caught missing timestamp column:", context.exception)
        
        if os.path.exists(bad_csv):
            os.remove(bad_csv)

    def test_zero_liquidity_volume(self):
        print("\n--- Edge Case: Zero Liquidity / Zero Volume ---")
        # In a zero volume situation, we check that the execution simulator handles it
        # without divide-by-zero crashes.
        exec_sim = ExecutionSimulator(volume_impact_coeff=0.5)
        
        t0 = datetime(2026, 6, 29, 10, 0, 0)
        m_event = MarketEvent(
            timestamp=t0,
            symbol="AAPL",
            # Note volume is 0.0
            data={'open': 100.0, 'high': 100.0, 'low': 100.0, 'close': 100.0, 'volume': 0.0}
        )
        exec_sim.handle_event(m_event)
        
        order = OrderEvent(
            timestamp=t0,
            symbol="AAPL",
            order_type="MKT",
            quantity=100,
            direction="BUY",
            price=100.0
        )
        
        try:
            fills = exec_sim.handle_event(order)
            self.assertIsNotNone(fills)
            self.assertEqual(fills[0].fill_price, 100.0) # Slippage calculation is bypassed when volume <= 0
            print("Zero volume execution handled gracefully with no division-by-zero.")
        except ZeroDivisionError:
            self.fail("ExecutionSimulator crashed with ZeroDivisionError on 0 volume bar.")

    def test_extreme_latency(self):
        print("\n--- Edge Case: Extreme Latency (Order Scheduled Beyond Backtest End) ---")
        # Generate 2 bars
        extreme_csv = "extreme_lat.csv"
        start_time = datetime(2026, 6, 29, 10, 0, 0)
        with open(extreme_csv, "w") as f:
            f.write("timestamp,open,high,low,close,volume\n")
            f.write("2026-06-29T10:00:00,100.0,101.0,99.0,100.0,1000\n")
            f.write("2026-06-29T10:01:00,101.0,102.0,100.0,101.0,1000\n")
            
        dh = DataHandler({"AAPL": extreme_csv})
        engine = BacktestEngine(dh)
        
        # Portfolio with 1-day latency (much larger than the 1-minute backtest)
        portfolio = Portfolio(initial_capital=100000.0, latency=timedelta(days=1))
        exec_sim = ExecutionSimulator()
        
        # Simple strategy to emit signal on first event
        class TriggerBuyStrategy:
            def handle_event(self, event):
                if isinstance(event, MarketEvent):
                    return MarketEvent(timestamp=event.timestamp, symbol=event.symbol, data=event.data) # no-op
                return None
                
        # Register a mock handler to manually inject a buy order
        class ManualOrderHandler:
            def __init__(self):
                self.order_sent = False
            def handle_event(self, event):
                if isinstance(event, MarketEvent) and not self.order_sent:
                    self.order_sent = True
                    # Initialize price in portfolio
                    portfolio.current_prices[event.symbol] = 100.0
                    # Generate order with 1-day latency
                    sig = SignalEvent(timestamp=event.timestamp, symbol=event.symbol, direction='BUY')
                    return portfolio._handle_signal(sig)
                return None
        
        # Inject the signal buyer manually
        manual_trader = ManualOrderHandler()
        engine.register_handler(manual_trader)
        engine.register_handler(portfolio)
        engine.register_handler(exec_sim)
        
        try:
            engine.run()
            # Order is scheduled at 2026-06-29T10:00:00 + 1 day = 2026-06-30T10:00:00
            # Backtest ended at 2026-06-29T10:01:00, so the order is never popped/processed
            # Final holdings should be empty, cash should be initial capital
            self.assertEqual(len(portfolio.positions), 0)
            self.assertEqual(portfolio.cash, 100000.0)
            print("Extreme latency handled gracefully: backtest ended before order reached exchange.")
        except Exception as e:
            self.fail(f"Extreme latency crashed the engine with exception: {e}")
        finally:
            if os.path.exists(extreme_csv):
                os.remove(extreme_csv)

if __name__ == "__main__":
    unittest.main()
