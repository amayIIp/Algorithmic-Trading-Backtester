from datetime import timedelta
from typing import Dict, List, Optional, Any
from events import Event, MarketEvent, OrderEvent, FillEvent

class SimulatedExecutionHandler:
    """
    Simulates perfect order execution: fills orders instantly at the order's price
    with zero slippage and a configurable fixed commission.
    """
    def __init__(self, commission: float = 0.0):
        self.commission = commission

    def handle_event(self, event: Event) -> Optional[FillEvent]:
        if isinstance(event, OrderEvent):
            return FillEvent(
                timestamp=event.timestamp,
                symbol=event.symbol,
                exchange='SIM',
                quantity=event.quantity,
                direction=event.direction,
                fill_price=event.price,
                commission=self.commission
            )
        return None


class ExecutionSimulator:
    """
    A realistic execution simulator supporting:
    - Fixed and volume-proportional slippage.
    - Market and Limit order fill logic.
    - Configurable return network latency.
    - Active limit order book tracking across historical bars.
    """
    def __init__(
        self, 
        commission: float = 0.0, 
        slippage_bps: float = 0.0, 
        volume_impact_coeff: float = 0.0,
        return_latency: timedelta = timedelta(seconds=0)
    ):
        self.commission = commission
        self.slippage_bps = slippage_bps
        self.volume_impact_coeff = volume_impact_coeff
        self.return_latency = return_latency
        
        self.current_prices: Dict[str, float] = {}
        self.latest_bars: Dict[str, Dict[str, Any]] = {}
        self.open_limit_orders: List[OrderEvent] = []
        self.all_fills: List[FillEvent] = []

    def handle_event(self, event: Event) -> Optional[List[FillEvent]]:
        fills = []
        if isinstance(event, MarketEvent):
            self._handle_market(event, fills)
        elif isinstance(event, OrderEvent):
            self._handle_order(event, fills)
        
        if fills:
            self.all_fills.extend(fills)
            return fills
        return None

    def _handle_market(self, event: MarketEvent, fills: List[FillEvent]):
        symbol = event.symbol
        close = event.data.get('close') or event.data.get('price')
        if close is not None:
            self.current_prices[symbol] = close
        self.latest_bars[symbol] = event.data

        # Process limit orders with the new market data (high, low, volume)
        remaining_limit_orders = []
        high = event.data.get('high', close)
        low = event.data.get('low', close)
        volume = event.data.get('volume', 1.0)
        
        for order in self.open_limit_orders:
            if order.symbol != symbol:
                remaining_limit_orders.append(order)
                continue
                
            is_filled = False
            fill_price = order.price
            
            if order.direction == 'BUY':
                # BUY limit order fills if price drops below limit
                if low <= order.price:
                    is_filled = True
            elif order.direction == 'SELL':
                # SELL limit order fills if price rises above limit
                if high >= order.price:
                    is_filled = True
            
            if is_filled:
                # Apply slippage & volume impact
                actual_fill_price = self._calculate_slippage(order.direction, fill_price, order.quantity, volume)
                
                # Slipped limit orders cannot fill outside of the high-low bounds of the bar
                if order.direction == 'BUY':
                    actual_fill_price = min(actual_fill_price, high)
                else:
                    actual_fill_price = max(actual_fill_price, low)
                
                fill = FillEvent(
                    timestamp=event.timestamp + self.return_latency,
                    symbol=order.symbol,
                    exchange='SIM',
                    quantity=order.quantity,
                    direction=order.direction,
                    fill_price=actual_fill_price,
                    commission=self.commission
                )
                fills.append(fill)
            else:
                remaining_limit_orders.append(order)
                
        self.open_limit_orders = remaining_limit_orders

    def _handle_order(self, event: OrderEvent, fills: List[FillEvent]):
        symbol = event.symbol
        
        if event.order_type == 'MKT':
            market_price = self.current_prices.get(symbol)
            if market_price is None:
                # Can't fill if we don't have current pricing
                return
            
            bar_data = self.latest_bars.get(symbol, {})
            volume = bar_data.get('volume', 1.0)
            
            fill_price = self._calculate_slippage(event.direction, market_price, event.quantity, volume)
            
            fill = FillEvent(
                timestamp=event.timestamp + self.return_latency,
                symbol=symbol,
                exchange='SIM',
                quantity=event.quantity,
                direction=event.direction,
                fill_price=fill_price,
                commission=self.commission
            )
            fills.append(fill)
            
        elif event.order_type == 'LMT':
            # Check if we can fill immediately upon arrival based on the current bar
            bar_data = self.latest_bars.get(symbol, {})
            close = self.current_prices.get(symbol, event.price)
            high = bar_data.get('high', close)
            low = bar_data.get('low', close)
            volume = bar_data.get('volume', 1.0)
            
            is_filled = False
            if event.direction == 'BUY' and low <= event.price:
                is_filled = True
            elif event.direction == 'SELL' and high >= event.price:
                is_filled = True
                
            if is_filled:
                actual_fill_price = self._calculate_slippage(event.direction, event.price, event.quantity, volume)
                if event.direction == 'BUY':
                    actual_fill_price = min(actual_fill_price, high)
                else:
                    actual_fill_price = max(actual_fill_price, low)
                
                fill = FillEvent(
                    timestamp=event.timestamp + self.return_latency,
                    symbol=symbol,
                    exchange='SIM',
                    quantity=event.quantity,
                    direction=event.direction,
                    fill_price=actual_fill_price,
                    commission=self.commission
                )
                fills.append(fill)
            else:
                self.open_limit_orders.append(event)

    def _calculate_slippage(self, direction: str, base_price: float, quantity: int, volume: float) -> float:
        # 1. Apply fixed bps slippage
        bps_factor = 1.0 + (self.slippage_bps / 10000.0) if direction == 'BUY' else 1.0 - (self.slippage_bps / 10000.0)
        price = base_price * bps_factor
        
        # 2. Apply volume-proportional market impact slippage
        if self.volume_impact_coeff > 0 and volume > 0:
            impact_ratio = quantity / volume
            impact_factor = 1.0 + (self.volume_impact_coeff * impact_ratio) if direction == 'BUY' else 1.0 - (self.volume_impact_coeff * impact_ratio)
            price = price * impact_factor
            
        return price
