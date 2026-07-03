#!/usr/bin/env python3
"""全技能分析 v4 — ICT-0DTE终极版"""
import yfinance as yf, sys
sys.path.insert(0, '/home/codespace/.openclaw/workspace/options-assistant')
from hss_fib_scanner import *
from pinbar_strategy import PinBarStrategy

tk = sys.argv[1] if len(sys.argv) > 1 else 'SPY'

print('='*55)
print(f'  {tk} ICT-0DTE分析')
print('='*55)

# ① 大盘
print(f'\n[大盘]')
for idx in ['SPY','QQQ','DIA','IWM']:
    d = yf.download(idx, period='1d', interval='5m', progress=False)
    if d.empty: continue
    d.columns = [c[0] if isinstance(c,tuple) else c for c in d.columns]
    o=float(d['Open'].iloc[0]); h=float(d['High'].max()); l=float(d['Low'].min()); c=float(d['Close'].iloc[-1])
    print(f'  {idx}: ${c:.0f} ({(c/o-1)*100:+.1f}%) 峰谷${h-l:.0f}')

# ② 宏观
macro = macro_bias_analysis(tk)
if macro: print(f'\n[宏观] {macro.get("trend","?")}')

# ③ 数据准备
d = yf.download(tk, period='5d', interval='5m', progress=False)
d.columns = [c[0] if isinstance(c,tuple) else c for c in d.columns]
d = extract_candle_features(d); d = add_indicators(d); d = calc_hss_ha(d)
last = d.iloc[-1]; price = float(last['Close'])

msm = MarketStructureMachine(d); ms = msm.get_state()
print(f'\n[结构] {ms.get("trend","?")}')
if ms.get('bos'): print(f'  {ms["bos"]}')

swing = d.tail(24); sd, sp, ep = calc_swing(swing); fib = calc_fib(sd, sp, ep)
print(f'\n[Fib] ${sp:.2f}->${ep:.2f}')
for l in [0.0,0.382,0.5,0.618,0.786,1.0]:
    m=''
    if abs(price-fib[l])/price<0.003: m=' <--'
    elif l==0.618: m=' OTE'
    print(f'  {l:<5}: ${fib[l]:.2f}{m}')

# ④ OB结构带
print(f'\n[🔵 OB结构带]')
try:
    recent = d.tail(40)
    for i in range(2, len(recent)-1):
        pb = abs(float(recent.iloc[i-1]['Close'])-float(recent.iloc[i-1]['Open']))
        cb = abs(float(recent.iloc[i]['Close'])-float(recent.iloc[i]['Open']))
        pr = float(recent.iloc[i-1]['Close']) < float(recent.iloc[i-1]['Open'])
        if pr and cb > pb*2:
            print(f'  需求区(黄色支撑): ${recent.iloc[i-1]["Low"]:.2f}~${recent.iloc[i-1]["High"]:.2f}')
            break
    for i in range(2, len(recent)-1):
        pb = abs(float(recent.iloc[i-1]['Close'])-float(recent.iloc[i-1]['Open']))
        cb = abs(float(recent.iloc[i]['Close'])-float(recent.iloc[i]['Open']))
        pb_bull = float(recent.iloc[i-1]['Close']) > float(recent.iloc[i-1]['Open'])
        if pb_bull and cb > pb*2:
            print(f'  供给区(头顶压力): ${recent.iloc[i-1]["Low"]:.2f}~${recent.iloc[i-1]["High"]:.2f}')
            break
except: print('  计算中...')

# ⑤ FVG几何+CE锚定
print(f'\n[🟢 FVG几何+CE锚定]')
try:
    r5 = d.tail(50)
    found = False
    for i in range(1, len(r5)-1):
        k1l = float(r5.iloc[i]['Low']); k3h = float(r5.iloc[i+1]['High'])
        k1h = float(r5.iloc[i]['High']); k3l = float(r5.iloc[i+1]['Low'])
        # Bearish: K1_Low > K3_High
        if k1l > k3h:
            lo = round(k3h,2); hi = round(k1l,2); ce = round((hi+lo)/2,2)
            ins = '🔵在FVG内🎯CE' if lo<=price<=hi and abs(price-ce)/price<0.002 else ('🔵在FVG内' if lo<=price<=hi else '')
            print(f'  看跌FVG: ${lo}~${hi} CE={ce} {ins}'); found=True; break
        # Bullish: K3_Low > K1_High
        if k3l > k1h:
            lo = round(k1h,2); hi = round(k3l,2); ce = round((hi+lo)/2,2)
            ins = '🔵在FVG内🎯CE' if lo<=price<=hi and abs(price-ce)/price<0.002 else ('🔵在FVG内' if lo<=price<=hi else '')
            print(f'  看涨FVG: ${lo}~${hi} CE={ce} {ins}'); found=True; break
    if not found: print('  无FVG缺口（动能中性）')
except: print('  计算中...')

# ⑥ ICT流动性
liq = PriceAction.detect_liquidity(d)
print(f'\n[🔴 ICT流动性]')
if liq.get('bsl_sweep'): print(f'  BSL扫荡(上方) — 警惕假突破反手做空')
if liq.get('ssl_sweep'): print(f'  SSL扫荡(下方) — 警惕假跌破反手做多')
if liq.get('eq_highs'): print(f'  等高点EQH — 突破后易反转')
if liq.get('eq_lows'): print(f'  等低点EQL — 跌破后易反转')
if not any([liq.get('bsl_sweep'),liq.get('ssl_sweep'),liq.get('eq_highs'),liq.get('eq_lows')]):
    print(f'  无显著流动性事件')

# ⑦ 日内
d1 = yf.download(tk, period='1d', interval='5m', progress=False)
if not d1.empty:
    d1.columns = [c[0] if isinstance(c,tuple) else c for c in d1.columns]
    dh=float(d1['High'].max()); dl=float(d1['Low'].min())
    yd = yf.download(tk, period="3d", interval="1d", progress=False)
    if not yd.empty: yd.columns = [c[0] if isinstance(c,tuple) else c for c in yd.columns]
    yc = float(yd.iloc[-2]["Close"]) if not yd.empty and len(yd)>1 else dh
    print(f'\n[日内] 高${dh:.2f} 低${dl:.2f} 幅${dh-dl:.2f}')
    print(f'  昨收${yc:.0f}→${price:.2f} ({price-yc:+.0f}) | 位置{(price-dl)/(dh-dl)*100:.0f}%')

pins = PinBarStrategy.detect(d, 20)
if pins:
    best = max(pins, key=lambda x: x['score'])
    print(f'\n[PinBar] {best["type"]} {best["score"]}/5 @ ${best["price"]}')

from risk_manager import print_check
print(f'\n[风控]')
print_check(tk, 'PUT', 2, 1.50, 1000)
