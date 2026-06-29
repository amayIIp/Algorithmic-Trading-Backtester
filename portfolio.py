from datetime import timedelta
from typing import Dict, Any, List, Optional
from events import Event, MarketEvent, SignalEvent, OrderEvent, FillEvent

class Portfolio:
    """
    Tracks cash, positions, and total equity value.
    Converts incoming Signals into sized Orders based on risk rules and capital.
    Updates cash and positions when fills are received.
    """
    def __init__(
        self, 
        initial_capital: float = 100000.0, 
        target_percent: float = 0.2, 
        max_position_pct: float = 0.5,
        latency: timedelta = timedelta(seconds=0)
    ):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, int] = {}          # symbol -> shares (int)
        self.current_prices: Dict[str, float] = {}   # symbol -> last seen price (float)
        self.target_percent = target_percent          # % of equity to allocate per trade
        self.max_position_pct = max_position_pct      # max % of equity allowed per position
        self.latency = latency                        # network latency to reach exchange
        self.equity_curve: List[Dict[str, Any]] = []  # historical track of equity/cash

    def handle_event(self, event: Event) -> Optional[OrderEvent]:
        if isinstance(event, MarketEvent):
            self._handle_market(event)
        elif isinstance(event, SignalEvent):
            return self._handle_signal(event)
        elif isinstance(event, FillEvent):
            self._handle_fill(event)
        return None

    def _handle_market(self, event: MarketEvent):
        # Update latest close price for the symbol
        close = event.data.get('close') or event.data.get('price')
        if close is not None:
            self.current_prices[event.symbol] = close

        # Fast path: skip valuation loop if we hold no positions
        if not self.positions:
            holdings_val = 0.0
        else:
            holdings_val = sum(qty * self.current_prices[sym] for sym, qty in self.positions.items())
            
        equity = self.cash + holdings_val

        entry = {
            'timestamp': event.timestamp,
            'cash': self.cash,
            'holdings_val': holdings_val,
            'equity': equity
        }

        # Overwrite or append based on timestamp to avoid duplicate records at the same timestamp
        if self.equity_curve and self.equity_curve[-1]['timestamp'] == event.timestamp:
            self.equity_curve[-1] = entry
        else:
            self.equity_curve.append(entry)

    def _handle_signal(self, event: SignalEvent) -> Optional[OrderEvent]:
        symbol = event.symbol
        direction = event.direction
        price = self.current_prices.get(symbol)

        if not price:
            return None

        # Risk Rule: Ensure we have enough cash for a minimal trade
        if self.cash < 100.0:
            return None

        current_qty = self.positions.get(symbol, 0)

        # Calculate current total equity
        holdings_val = sum(qty * self.current_prices.get(sym, 0.0) for sym, qty in self.positions.items())
        total_equity = self.cash + holdings_val

        if direction == 'BUY':
            # Simple rule: Only buy if we do not already hold this symbol (long-only flat-to-long)
            if current_qty > 0:
                return None

            # Calculate target spend based on target_percent and max_position_pct constraints
            target_spend = min(total_equity * self.target_percent, total_equity * self.max_position_pct)
            
            # Sizing logic: Cap target spend by available cash
            spend_amount = min(target_spend, self.cash)
            qty = int(spend_amount // price)

            if qty > 0:
                return OrderEvent(
                    timestamp=event.timestamp + self.latency,
                    symbol=symbol,
                    order_type='MKT',
                    quantity=qty,
                    direction='BUY',
                    price=price
                )

        elif direction == 'SELL':
            # Sizing logic: Liquidate entire holding
            if current_qty > 0:
                return OrderEvent(
                    timestamp=event.timestamp + self.latency,
                    symbol=symbol,
                    order_type='MKT',
                    quantity=current_qty,
                    direction='SELL',
                    price=price
                )

        return None

    def _handle_fill(self, event: FillEvent):
        symbol = event.symbol
        qty = event.quantity
        direction = event.direction
        fill_price = event.fill_price
        commission = event.commission

        current_qty = self.positions.get(symbol, 0)

        if direction == 'BUY':
            self.positions[symbol] = current_qty + qty
            cost = (qty * fill_price) + commission
            self.cash -= cost
        elif direction == 'SELL':
            self.positions[symbol] = current_qty - qty
            revenue = (qty * fill_price) - commission
            self.cash += revenue

        # Clean up positions dictionary
        if self.positions[symbol] == 0:
            del self.positions[symbol]

        # Immediately update the equity curve entry for this timestamp to reflect the fill
        if self.equity_curve and self.equity_curve[-1]['timestamp'] == event.timestamp:
            if not self.positions:
                holdings_val = 0.0
            else:
                holdings_val = sum(qty * self.current_prices[sym] for sym, qty in self.positions.items())
                
            equity = self.cash + holdings_val
            self.equity_curve[-1] = {
                'timestamp': event.timestamp,
                'cash': self.cash,
                'holdings_val': holdings_val,
                'equity': equity
            }

