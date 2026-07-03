#!/usr/bin/env python3
"""
HSS 期权剥头皮分析工具
盘中实时扫描 1min K线，检测 HSS 策略信号
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import sys

# ─── 配置 ───────────────────────────────────────
TICKERS = ["SPY", "QQQ"]  # 默认扫描标的
STREAK_MIN = 2            # 最少回调K线数
EMA_LEN = 100             # 100 EMA

def calc_heikin_ashi(df):
    """计算 Heikin Ashi K线"""
    ha = df.copy()
    ha['HA_Close'] = (ha['Open'] + ha['High'] + ha['Low'] + ha['Close']) / 4
    ha['HA_Open'] = np.nan
    ha.iloc[0, ha.columns.get_loc('HA_Open')] = (ha.iloc[0]['Open'] + ha.iloc[0]['Close']) / 2
    for i in range(1, len(ha)):
        ha.iloc[i, ha.columns.get_loc('HA_Open')] = (ha.iloc[i-1]['HA_Open'] + ha.iloc[i-1]['HA_Close']) / 2
    ha['HA_High'] = ha[['High', 'HA_Open', 'HA_Close']].max(axis=1)
    ha['HA_Low']  = ha[['Low',  'HA_Open', 'HA_Close']].min(axis=1)
    ha['HA_Body'] = abs(ha['HA_Close'] - ha['HA_Open'])
    ha['HA_Bull'] = ha['HA_Close'] > ha['HA_Open']
    ha['HA_UpperWick'] = ha['HA_High'] - ha[['HA_Open', 'HA_Close']].max(axis=1)
    ha['HA_LowerWick'] = ha[['HA_Open', 'HA_Close']].min(axis=1) - ha['HA_Low']
    return ha

def scan_hss_signals(ticker, data):
    """在数据上扫描 HSS 信号"""
    df = calc_heikin_ashi(data)
    df['EMA100'] = df['Close'].ewm(span=EMA_LEN, adjust=False).mean()
    
    # 无影线判断
    df['NoUpperWick'] = df['HA_UpperWick'] < df['HA_Body'] * 0.1
    df['NoLowerWick'] = df['HA_LowerWick'] < df['HA_Body'] * 0.1
    
    # 回调K线
    df['BearPullback'] = (~df['HA_Bull']) & df['NoUpperWick']  # 阴线 + 上端无影线
    df['BullPullback'] = df['HA_Bull'] & df['NoLowerWick']      # 阳线 + 下端无影线
    
    # 连续计数
    df['BearPB_Count'] = df['BearPullback'].astype(int).groupby((~df['BearPullback']).cumsum()).cumsum()
    df['BullPB_Count'] = df['BullPullback'].astype(int).groupby((~df['BullPullback']).cumsum()).cumsum()
    
    # 十字星 + 高成交量
    atr = df['HA_Body'].rolling(14).mean()
    df['DojiBody'] = df['HA_Body'] < atr * 0.15
    df['VolHigh']  = df['Volume'] >= df['Volume'].shift(1).rolling(3, min_periods=1).max()
    df['DojiSignal'] = df['DojiBody'] & df['VolHigh']
    
    # 多空方向
    df['BullMkt'] = df['Close'] > df['EMA100']
    
    # 信号
    df['LongSignal']  = df['BullMkt'] & (df['BearPB_Count'] >= STREAK_MIN) & df['DojiSignal']
    df['ShortSignal'] = (~df['BullMkt']) & (df['BullPB_Count'] >= STREAK_MIN) & df['DojiSignal']
    
    return df

def analyze(tickers=None):
    """主分析函数"""
    if tickers is None:
        tickers = TICKERS
    
    now = datetime.now(timezone.utc)
    print(f"🕐 {now.strftime('%H:%M:%S')} UTC | 美东 {(now.hour-4)%24}:{now.strftime('%M:%S')}")
    print("="*60)
    
    signals_found = []
    
    for ticker in tickers:
        print(f"\n📊 {ticker} 扫描中...")
        try:
            # 拉当天所有1分钟数据
            data = yf.download(ticker, period="1d", interval="1m", progress=False)
            if data.empty:
                print(f"   ⚠️ 无数据（可能休市）")
                continue
            
            # Flatten columns
            data.columns = [c[0] if isinstance(c, tuple) else c for c in data.columns]
            
            df = scan_hss_signals(ticker, data)
            last = df.iloc[-1]
            
            # 当前状态
            ema = last['EMA100']
            price = last['Close']
            direction = "🟢 多头" if last['BullMkt'] else "🔴 空头"
            
            print(f"   价格: ${price:.2f} | 100 EMA: ${ema:.2f} | 方向: {direction}")
            print(f"   回调计数: 空头回调={int(last['BearPB_Count'])} | 多头回调={int(last['BullPB_Count'])}")
            print(f"   十字星: {'✅' if last['DojiSignal'] else '❌'} | 高量: {'✅' if last['VolHigh'] else '❌'}")
            
            # 最新信号
            if last['LongSignal']:
                sl = last['Low']  # 止损: 十字星最低
                tp1 = price + (price - sl) * 1.0
                tp2 = price + (price - sl) * 1.5
                print(f"\n   🟢🟢🟢 做多信号! 🟢🟢🟢")
                print(f"   进场: ${price:.2f}")
                print(f"   止损: ${sl:.2f} ({(price-sl)/price*100:.2f}%)")
                print(f"   止盈1:1: ${tp1:.2f} | 1:1.5: ${tp2:.2f}")
                signals_found.append((ticker, "LONG", price, sl, tp2))
                
            elif last['ShortSignal']:
                sl = last['High']  # 止损: 十字星最高
                tp1 = price - (sl - price) * 1.0
                tp2 = price - (sl - price) * 1.5
                print(f"\n   🔴🔴🔴 做空信号! 🔴🔴🔴")
                print(f"   进场: ${price:.2f}")
                print(f"   止损: ${sl:.2f} ({(sl-price)/price*100:.2f}%)")
                print(f"   止盈1:1: ${tp1:.2f} | 1:1.5: ${tp2:.2f}")
                signals_found.append((ticker, "SHORT", price, sl, tp2))
            else:
                print(f"   ⏸️ 等待信号...")
                
            # 最近5根K线速览
            print(f"\n   最近5根 1min K线:")
            print(f"   {'时间':>12} {'开':>7} {'高':>7} {'低':>7} {'收':>7} {'量':>8}")
            for i in range(max(0, len(df)-5), len(df)):
                r = df.iloc[i]
                t = r.name
                is_doji = "◇" if r['DojiSignal'] else " "
                is_sig = "⬆" if r['LongSignal'] else ("⬇" if r['ShortSignal'] else " ")
                print(f"   {t.strftime('%H:%M'):>12} {r['Open']:>7.2f} {r['High']:>7.2f} {r['Low']:>7.2f} {r['Close']:>7.2f} {int(r['Volume']):>8,}{is_doji}{is_sig}")
                
        except Exception as e:
            print(f"   ❌ 错误: {e}")
    
    print("\n" + "="*60)
    if not signals_found:
        print("⏸️ 当前无信号")
    else:
        print(f"🎯 发现 {len(signals_found)} 个信号!")
    
    return signals_found

if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else None
    analyze(tickers)
