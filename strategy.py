import math
from abc import ABC, abstractmethod
from collections import deque
from events import Event, MarketEvent, SignalEvent, OrderEvent, FillEvent

class Strategy(ABC):
    """
    Abstract Base Class for trading strategies.
    Processes MarketEvents and returns SignalEvents.
    """
    def handle_event(self, event: Event) -> SignalEvent | None:
        if isinstance(event, MarketEvent):
            return self.on_market_event(event)
        return None

    @abstractmethod
    def on_market_event(self, event: MarketEvent) -> SignalEvent | None:
        """
        Calculates signals based on the incoming MarketEvent.
        """
        pass


class SMACrossoverStrategy(Strategy):
    """
    Simple Moving Average (SMA) Crossover strategy.
    Emits BUY when short MA crosses above long MA.
    Emits SELL when short MA crosses below long MA.
    """
    def __init__(self, short_window: int = 5, long_window: int = 20):
        self.short_window = short_window
        self.long_window = long_window
        self.prices = {}       # symbol -> deque of prices
        self.last_signals = {}  # symbol -> last emitted direction

    def on_market_event(self, event: MarketEvent) -> SignalEvent | None:
        symbol = event.symbol
        close = event.data.get('close') or event.data.get('price')
        if close is None:
            return None

        if symbol not in self.prices:
            self.prices[symbol] = deque(maxlen=self.long_window)
            self.last_signals[symbol] = None

        self.prices[symbol].append(close)

        if len(self.prices[symbol]) < self.long_window:
            return None

        prices_list = list(self.prices[symbol])
        
        # Optimize MA calculation by using Python's sum() on list slices
        # This is W and W_short iterations in pure C, much faster than NumPy overhead
        short_ma = sum(prices_list[-self.short_window:]) / self.short_window
        long_ma = sum(prices_list) / self.long_window

        if short_ma > long_ma and self.last_signals[symbol] != 'BUY':
            self.last_signals[symbol] = 'BUY'
            return SignalEvent(timestamp=event.timestamp, symbol=symbol, direction='BUY')
        elif short_ma < long_ma and self.last_signals[symbol] != 'SELL':
            self.last_signals[symbol] = 'SELL'
            return SignalEvent(timestamp=event.timestamp, symbol=symbol, direction='SELL')

        return None


class MeanReversionStrategy(Strategy):
    """
    Mean Reversion strategy based on rolling Z-score.
    Emits BUY when price drops below entry_threshold standard deviations.
    Emits SELL when price exceeds entry_threshold standard deviations.
    """
    def __init__(self, window: int = 20, entry_threshold: float = 2.0):
        self.window = window
        self.entry_threshold = entry_threshold
        self.prices = {}       # symbol -> deque of prices
        self.last_signals = {}  # symbol -> last emitted direction

    def on_market_event(self, event: MarketEvent) -> SignalEvent | None:
        symbol = event.symbol
        close = event.data.get('close') or event.data.get('price')
        if close is None:
            return None

        if symbol not in self.prices:
            self.prices[symbol] = deque(maxlen=self.window)
            self.last_signals[symbol] = None

        self.prices[symbol].append(close)

        n = len(self.prices[symbol])
        if n < self.window:
            return None

        # Optimize Mean and Std calculation using single-pass pure Python loop
        prices_list = list(self.prices[symbol])
        s = 0.0
        sq = 0.0
        for x in prices_list:
            s += x
            sq += x * x
        
        mean = s / n
        var = (sq / n) - (mean * mean)
        # Avoid float precision issues yielding negative variance
        std = math.sqrt(var) if var > 0.0 else 0.0

        if std == 0:
            return None

        z_score = (close - mean) / std

        if z_score < -self.entry_threshold and self.last_signals[symbol] != 'BUY':
            self.last_signals[symbol] = 'BUY'
            return SignalEvent(timestamp=event.timestamp, symbol=symbol, direction='BUY')
        elif z_score > self.entry_threshold and self.last_signals[symbol] != 'SELL':
            self.last_signals[symbol] = 'SELL'
            return SignalEvent(timestamp=event.timestamp, symbol=symbol, direction='SELL')

        return None

