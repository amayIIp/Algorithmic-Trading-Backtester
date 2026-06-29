import numpy as np
import pandas as pd
from typing import List, Dict, Any

def calculate_performance_metrics(
    equity_curve: List[Dict[str, Any]], 
    fills: List[Any], 
    risk_free_rate: float = 0.0
) -> Dict[str, Any]:
    """
    Computes key performance metrics from the equity curve and transaction fills:
    - Sharpe Ratio (annualized, assuming daily frequency)
    - Max Drawdown
    - Win Rate (from round-trip trades)
    - Turnover (total traded value / average portfolio equity)
    """
    if not equity_curve:
        return {}

    # Convert equity curve to DataFrame
    df = pd.DataFrame(equity_curve)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    
    # Resample to daily frequency to compute daily returns
    daily_df = df['equity'].resample('D').last().ffill()
    daily_returns = daily_df.pct_change().dropna()
    
    # 1. Sharpe Ratio (annualized, assuming 252 trading days/year)
    mean_return = daily_returns.mean()
    std_return = daily_returns.std()
    
    if std_return > 0:
        sharpe = np.sqrt(252) * (mean_return - (risk_free_rate / 252)) / std_return
    else:
        sharpe = 0.0

    # 2. Max Drawdown
    peaks = daily_df.cummax()
    drawdowns = (daily_df - peaks) / peaks
    max_drawdown = drawdowns.min()

    # 3. Win Rate
    # Track trades (FIFO matching)
    trades = []  # List of profits
    open_buys = []
    open_sells = []
    
    for fill in fills:
        qty = fill.quantity
        price = fill.fill_price
        direction = fill.direction
        
        if direction == 'BUY':
            # Match with open sells if any
            while qty > 0 and open_sells:
                sell_qty, sell_price = open_sells[0]
                match_qty = min(qty, sell_qty)
                
                # Profit = (sell_price - buy_price) * quantity
                profit = (sell_price - price) * match_qty
                trades.append(profit)
                
                qty -= match_qty
                if sell_qty == match_qty:
                    open_sells.pop(0)
                else:
                    open_sells[0] = (sell_qty - match_qty, sell_price)
            
            if qty > 0:
                open_buys.append((qty, price))
                
        elif direction == 'SELL':
            # Match with open buys if any
            while qty > 0 and open_buys:
                buy_qty, buy_price = open_buys[0]
                match_qty = min(qty, buy_qty)
                
                # Profit = (sell_price - buy_price) * quantity
                profit = (price - buy_price) * match_qty
                trades.append(profit)
                
                qty -= match_qty
                if buy_qty == match_qty:
                    open_buys.pop(0)
                else:
                    open_buys[0] = (buy_qty - match_qty, buy_price)
            
            if qty > 0:
                open_sells.append((qty, price))
                
    # Calculate win rate from matched trades
    total_trades = len(trades)
    winning_trades = sum(1 for p in trades if p > 0)
    win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

    # 4. Turnover
    # Traded Value = sum of (qty * price) for all fills
    total_traded_value = sum(f.quantity * f.fill_price for f in fills)
    avg_equity = df['equity'].mean()
    turnover = total_traded_value / avg_equity if avg_equity > 0 else 0.0

    return {
        "final_equity": df['equity'].iloc[-1],
        "sharpe_ratio": float(sharpe),
        "max_drawdown": float(max_drawdown),
        "win_rate": float(win_rate),
        "turnover": float(turnover),
        "total_trades": total_trades
    }
