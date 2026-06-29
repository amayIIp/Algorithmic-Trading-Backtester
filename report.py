import pandas as pd
import matplotlib.pyplot as plt
from typing import List, Dict, Any
from metrics import calculate_performance_metrics

def generate_report(
    equity_curve: List[Dict[str, Any]], 
    fills: List[Any], 
    output_image_path: str = "equity_curve.png"
):
    """
    Computes final backtest statistics, prints a clean ASCII summary table,
    and plots the equity curve to a PNG file.
    """
    # 1. Compute metrics
    metrics = calculate_performance_metrics(equity_curve, fills)
    if not metrics:
        print("No metrics computed. Empty backtest run.")
        return

    # 2. Print summary table to console
    print("\n" + "="*45)
    print("           BACKTEST PERFORMANCE REPORT       ")
    print("="*45)
    print(f"  Final Portfolio Equity : ${metrics['final_equity']:,.2f}")
    print(f"  Annualized Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
    print(f"  Max Drawdown           : {metrics['max_drawdown']*100:.2f}%")
    print(f"  Win Rate (FIFO Trades) : {metrics['win_rate']*100:.1f}%")
    print(f"  Total Closed Trades    : {metrics['total_trades']}")
    print(f"  Portfolio Turnover     : {metrics['turnover']:.2f}x")
    print("="*45 + "\n")

    # 3. Plot the equity curve
    df = pd.DataFrame(equity_curve)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    
    plt.figure(figsize=(10, 6))
    plt.plot(df.index, df['equity'], label='Total Equity (Cash + Holdings)', color='#1f77b4', linewidth=2)
    plt.plot(df.index, df['cash'], label='Cash Balance', color='#2ca02c', linestyle='--', alpha=0.7)
    
    plt.title('Equity Curve & Cash Balance Over Time', fontsize=14, fontweight='bold', pad=15)
    plt.xlabel('Date / Time', fontsize=11)
    plt.ylabel('Value ($)', fontsize=11)
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.legend(loc='upper left', frameon=True, shadow=False)
    plt.tight_layout()
    
    plt.savefig(output_image_path, dpi=150)
    plt.close()
    print(f"Saved equity curve plot to: {output_image_path}")
