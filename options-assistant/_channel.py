#!/usr/bin/env python3
import yfinance as yf
d = yf.download('TSLA', period='1d', interval='5m', progress=False)
d.columns = [c[0] if isinstance(c,tuple) else c for c in d.columns]
p = float(d['Close'].iloc[-1])
dh = float(d['High'].max())
dl = float(d['Low'].min())

# 下跌波段
high = 432.35
low = dl
diff = high - low

print(f'TSLA ${p:.2f} | 日高${high} 日低${low:.2f}')
print(f'\n下跌通道: ${high} -> ${low:.2f} (${diff:.2f})\n')

print('Fib扩展:')
for lvl in [0.0, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.382, 1.5, 1.618]:
    pl = high - diff * lvl
    m = ' <--' if abs(p-pl)/p < 0.005 else ''
    print(f'  {lvl:<5}: ${pl:.2f}{m}')

print(f'\n=== $395 PUT 交易计划 ===')
entry = 398
print(f'进场: TSLA ${entry}')
print(f'当前: TSLA ${p:.2f}')
print(f'利润: ${entry-p:.2f} / 股')
# Fib扩展目标
t1 = high - diff * 1.272
t2 = high - diff * 1.618
t3 = high - diff * 2.0
print(f'\n止损: TSLA > ${entry} (进场位)')
print(f'\n止盈:')
print(f'  T1: ${t1:.2f} (Fib 1.272)')
print(f'  T2: ${t2:.2f} (Fib 1.618)')
print(f'  T3: ${t3:.2f} (Fib 2.0)')
print(f'\n策略:')
print(f'  T1到 → 平半仓，保本')
print(f'  T2到 → 再平一半')
print(f'  T3到 → 全清')
