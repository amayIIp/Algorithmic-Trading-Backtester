import os
import unittest
from datetime import datetime
from events import Event, MarketEvent, SignalEvent, OrderEvent, FillEvent
from data_handler import DataHandler
from engine import BacktestEngine, EventQueue

class NoOpStrategy:
    """
    A Strategy that listens to MarketEvents and does nothing (no trades).
    Prints events to confirm chronological order.
    """
    def __init__(self, log_events: list = None):
        self.log_events = log_events if log_events is not None else []

    def handle_event(self, event: Event):
        if isinstance(event, MarketEvent):
            self.log_events.append(event)
        return None

class MockTradingSystem:
    """
    A mock strategy/portfolio/execution handler that generates subsequent
    events with the exact same timestamp to test the full event cycle.
    """
    def __init__(self, log_events: list = None):
        self.log_events = log_events if log_events is not None else []

    def handle_event(self, event: Event):
        self.log_events.append(event)
        
        if isinstance(event, MarketEvent):
            close = event.data.get('close', 0.0)
            if close > 100.0:
                return SignalEvent(
                    timestamp=event.timestamp,
                    symbol=event.symbol,
                    direction='BUY',
                    strength=1.0
                )
        
        elif isinstance(event, SignalEvent):
            return OrderEvent(
                timestamp=event.timestamp,
                symbol=event.symbol,
                order_type='MKT',
                quantity=100,
                direction=event.direction,
                price=0.0
            )
            
        elif isinstance(event, OrderEvent):
            return FillEvent(
                timestamp=event.timestamp,
                symbol=event.symbol,
                exchange='MOCK',
                quantity=event.quantity,
                direction=event.direction,
                fill_price=105.0 if event.direction == 'BUY' else 95.0,
                commission=1.0
            )
            
        return None

class TestBacktestEngine(unittest.TestCase):
    def setUp(self):
        # Create dummy CSV files
        self.aapl_csv = "test_aapl.csv"
        self.msft_csv = "test_msft.csv"

        with open(self.aapl_csv, "w") as f:
            f.write("timestamp,open,high,low,close,volume\n")
            f.write("2026-06-29T10:00:00,100.0,102.0,99.0,101.0,1000\n")
            f.write("2026-06-29T10:02:00,101.0,103.0,100.0,102.0,1500\n")

        with open(self.msft_csv, "w") as f:
            f.write("timestamp,open,high,low,close,volume\n")
            f.write("2026-06-29T10:01:00,200.0,201.0,199.0,200.0,800\n")
            f.write("2026-06-29T10:03:00,200.0,202.0,198.0,201.0,1200\n")

        self.file_paths = {
            "AAPL": self.aapl_csv,
            "MSFT": self.msft_csv
        }

    def tearDown(self):
        # Clean up files
        for f in [self.aapl_csv, self.msft_csv]:
            if os.path.exists(f):
                os.remove(f)

    def test_no_op_strategy_chronological_order(self):
        print("\n--- Testing No-Op Strategy Chronological Order ---")
        dh = DataHandler(self.file_paths)
        engine = BacktestEngine(dh)
        
        logged_events = []
        strategy = NoOpStrategy(logged_events)
        engine.register_handler(strategy)
        
        # Run loop
        engine.run()
        
        # We expect exactly 4 MarketEvents, ordered strictly:
        # AAPL (10:00) -> MSFT (10:01) -> AAPL (10:02) -> MSFT (10:03)
        self.assertEqual(len(logged_events), 4)
        
        expected_sequence = [
            (datetime.fromisoformat("2026-06-29T10:00:00"), "AAPL"),
            (datetime.fromisoformat("2026-06-29T10:01:00"), "MSFT"),
            (datetime.fromisoformat("2026-06-29T10:02:00"), "AAPL"),
            (datetime.fromisoformat("2026-06-29T10:03:00"), "MSFT")
        ]
        
        for i, (ts, symbol) in enumerate(expected_sequence):
            event = logged_events[i]
            print(f"Processed: {event}")
            self.assertEqual(event.timestamp, ts)
            self.assertEqual(event.symbol, symbol)
            
        print("Chronological order for multi-symbol stream verified successfully!")

    def test_mock_trading_system_lifecycle(self):
        print("\n--- Testing Mock Trading System (Full Event Cycle) ---")
        dh = DataHandler(self.file_paths)
        engine = BacktestEngine(dh)
        
        logged_events = []
        trading_system = MockTradingSystem(logged_events)
        engine.register_handler(trading_system)
        
        # Run loop
        engine.run()
        
        # For each of the 4 MarketEvents, the MockTradingSystem triggers:
        # MarketEvent -> SignalEvent -> OrderEvent -> FillEvent.
        # This makes 4 events per bar, so 16 events total.
        self.assertEqual(len(logged_events), 16)
        
        # Check that events are processed in strict non-decreasing chronological order
        prev_time = None
        for event in logged_events:
            print(f"Time: {event.timestamp} | Event: {type(event).__name__} for {event.symbol}")
            if prev_time is not None:
                self.assertTrue(event.timestamp >= prev_time, f"Order violation: {event.timestamp} < {prev_time}")
            prev_time = event.timestamp
            
        # Verify event ordering at the same timestamp (e.g. AAPL 10:00:00)
        # Should be Market -> Signal -> Order -> Fill
        aapl_10_00_events = [ev for ev in logged_events if ev.timestamp == datetime.fromisoformat("2026-06-29T10:00:00")]
        self.assertEqual(len(aapl_10_00_events), 4)
        self.assertIsInstance(aapl_10_00_events[0], MarketEvent)
        self.assertIsInstance(aapl_10_00_events[1], SignalEvent)
        self.assertIsInstance(aapl_10_00_events[2], OrderEvent)
        self.assertIsInstance(aapl_10_00_events[3], FillEvent)
        
        print("Lifecycle event sequence and stability verified successfully!")

    def test_time_travel_prevention(self):
        print("\n--- Testing Time-Travel Prevention ---")
        q = EventQueue()
        
        # First event
        t1 = datetime.fromisoformat("2026-06-29T10:00:00")
        ev1 = MarketEvent(timestamp=t1, symbol="AAPL", data={})
        q.put(ev1)
        
        # Pop first event, setting current_time to t1
        q.get()
        
        # Try to push an event with an earlier timestamp
        t_early = datetime.fromisoformat("2026-06-29T09:59:59")
        ev_early = MarketEvent(timestamp=t_early, symbol="AAPL", data={})
        
        with self.assertRaises(ValueError) as context:
            q.put(ev_early)
            
        self.assertIn("Time-travel detected!", str(context.exception))
        print("Time-travel exception correctly raised:", context.exception)

if __name__ == "__main__":
    unittest.main()
