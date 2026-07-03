#!/usr/bin/env python3
"""实时画斐波那契 + 裸K状态"""
import yfinance as yf, sys
sys.path.insert(0, '/home/codespace/.openclaw/workspace/options-assistant')
from hss_fib_scanner import *

ticker = sys.argv[1] if len(sys.argv) > 1 else "TSLA"
data = yf.download(ticker, period="1d", interval="5m", progress=False)
data.columns = [c[0] if isinstance(c,tuple) else c for c in data.columns]
data = extract_candle_features(data)
data = add_indicators(data)

# 最新Fib（24根5分K=2小时）
swing = data.tail(24)
sd, sp, ep = calc_swing(swing)
fib = calc_fib(sd, sp, ep)
price = float(data['Close'].iloc[-1])

print(f"📊 {ticker} 实时斐波那契 @ {pd.Timestamp.now().strftime('%H:%M')}")
print(f"  窗口: 最近24根5分K (2小时)")
print(f"  波段: {'📈' if sd=='UP' else '📉'} ${sp:.2f} → ${ep:.2f}")
print(f"  当前: ${price:.2f}")
print()
for l in [0.0, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618]:
    if l in fib:
        m = ""
        if abs(price-fib[l])/price < 0.003: m = " ◀ 当前"
        elif l == 0.618: m = " ★ OTE"
        print(f"  {l:<5}: ${fib[l]:.2f}{m}")

# HSS
data = calc_hss_ha(data)
last = data.iloc[-1]
print(f"\n  EMA100: ${float(last['EMA100']):.2f}")
print(f"  VWAP:   ${float(last['VWAP']):.2f}")

# 当前波段内的位置
print(f"\n  波段内位置:")
if price > fib[1.0]:
    print(f"  价格 ${price} > Fib 1.0(${fib[1.0]}) — 已突破波段，需重新画线")
elif price < fib[0.0]:
    print(f"  价格 ${price} < Fib 0.0(${fib[0.0]}) — 已跌破波段，需重新画线")
elif price >= fib[0.618]:
    print(f"  在0.618上方 → 弱回调，多头稳健")
elif price >= fib[0.5]:
    print(f"  在0.5-0.618区间 → 正常回调范围")
elif price >= fib[0.382]:
    print(f"  在0.382-0.5 → 强回调，注意转势")
else:
    print(f"  跌破0.382 → 深度回调，可能反转")
