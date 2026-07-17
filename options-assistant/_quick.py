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

# ② 板块资金流向
print(f'\n[板块资金]')
sectors = {'XLK':'科技','XLF':'金融','XLE':'能源','XLV':'医疗','XLI':'工业',
           'XLP':'消费防御','XLY':'消费可选','XLU':'公用事业','XLB':'材料','XLRE':'房地产'}
try:
    flows = []
    for tk_s, nm in sectors.items():
        sd = yf.download(tk_s, period='1d', interval='5m', progress=False)
        if sd.empty: continue
        sd.columns = [c[0] if isinstance(c,tuple) else c for c in sd.columns]
        so = float(sd['Open'].iloc[0]); sc = float(sd['Close'].iloc[-1])
        sch = (sc/so-1)*100
        flows.append((sch, nm, sc))
    flows.sort(reverse=True)
    top3 = flows[:3]; bot3 = flows[-3:]
    print(f'  🟢流入: {" | ".join([f"{n}+{c:.1f}%" for c,n,p in top3])}')
    print(f'  🔴流出: {" | ".join([f"{n}{c:+.1f}%" for c,n,p in bot3])}')
    v = yf.download('^VIX', period='1d', interval='5m', progress=False)
    if not v.empty: v.columns=[c[0] if isinstance(c,tuple) else c for c in v.columns]; vix=float(v['Close'].iloc[-1])
    print(f'  VIX: {vix:.1f}{"😱" if vix>25 else "😰" if vix>18 else "😐" if vix>12 else "😊"}')
except: print('  计算中...')

# ③ 宏观
macro = macro_bias_analysis(tk)
if macro: print(f'\n[宏观] {macro.get("trend","?")}')

# ③ 数据准备（3分K为主 — 1分K重采样）
d1m = yf.download(tk, period='3d', interval='1m', progress=False)
d1m.columns = [c[0] if isinstance(c,tuple) else c for c in d1m.columns]
# 重采样为3分K
d = d1m.resample("3min").agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
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

# ⑥ 缩量横盘检测 (弹簧检测)
print(f'\n[⚡ 弹簧检测]')
try:
    recent_vol = d.tail(30)
    high_vol = float(recent_vol['Volume'].head(15).mean())
    low_vol = float(recent_vol['Volume'].tail(15).mean())
    vol_shrink = low_vol / high_vol if high_vol > 0 else 1
    
    # 箱体检测（最近12根K线高低点范围）
    box = d.tail(12)
    box_high = float(box['High'].max())
    box_low = float(box['Low'].min())
    box_range = box_high - box_low
    
    # 趋势方向（最近20根K线）
    trend20 = d.tail(20)
    up_vol = float(trend20[trend20['Close'] > trend20['Open']]['Volume'].sum())
    down_vol = float(trend20[trend20['Close'] < trend20['Open']]['Volume'].sum())
    total = up_vol + down_vol if up_vol + down_vol > 0 else 1
    bias = '🟢偏多' if up_vol/total > 0.55 else ('🔴偏空' if down_vol/total > 0.55 else '➡️中性')
    
    if vol_shrink < 0.6 and box_range < float(d['Range'].tail(30).mean()) * 0.8:
        flag = '⚡弹簧压紧中'
        if vol_shrink < 0.4: flag += '（极度缩量！）'
        print(f'  {flag}')
        print(f'  箱体: ${box_low:.2f}~${box_high:.2f}（{len(box)}根K线）')
        print(f'  量能: {low_vol:.0f}（活跃期{high_vol:.0f}的{vol_shrink*100:.0f}%）')
        print(f'  方向: {bias}')
    elif vol_shrink < 0.8:
        print(f'  轻度缩量（活跃期{high_vol:.0f}→{low_vol:.0f}, {vol_shrink*100:.0f}%）')
    else:
        print(f'  量能正常（{int(low_vol):,}），无弹簧状态')
except: print('  计算中...')

# ⑦ 筹码峰成交量 (Volume Profile)
print(f'\n[⛰️ 筹码峰成交量]')
try:
    vp = d.tail(78)
    if len(vp) > 10:
        pmn = float(vp['Low'].min())
        pmx = float(vp['High'].max())
        rng = pmx - pmn
        step = max(round(rng / 15, 0), 0.5) if rng > 0 else 1
        
        # 每个价格档位的成交量
        pvols = {}
        for s in [pmn + i*step for i in range(16)]:
            if s > pmx: break
            e = s + step
            v = float(vp[(vp['High']>=s)&(vp['Low']<=e)]['Volume'].sum())
            if v > 0:
                pvols[round(s,1)] = {'vol': v, 'end': round(e,1)}
        
        if pvols:
            max_v = max(p['vol'] for p in pvols.values())
            sorted_v = sorted([p['vol'] for p in pvols.values()], reverse=True)
            top3_threshold = sorted_v[2] if len(sorted_v) > 2 else max_v * 0.8
            median_v = sorted_v[len(sorted_v)//2] if sorted_v else max_v
            
            print(f'  量峰（█=峰值 ▓=密集 ░=稀疏）:')
            for lvl, info in sorted(pvols.items()):
                v = info['vol']
                bar_len = max(1, int(v / max_v * 20))
                if v >= top3_threshold:
                    bar = '█' * bar_len
                    tag = f' ⛰️ 峰值{v:,.0f}'
                elif v >= median_v:
                    bar = '▓' * bar_len
                    tag = f' {v:,.0f}'
                else:
                    bar = '░' * bar_len
                    tag = ''
                marker = ' ◀当前' if lvl <= price <= info['end'] else ''
                print(f'  ${lvl:.0f}-${info["end"]:.0f} {bar:<20}{tag}{marker}')
            
            # 峰值信号
            print(f'  ⛰️ 峰值区: ${sorted(pvols.keys())[:3]} — 机构主战场')
except: print('  计算中...')

# ⑧ ICT流动性
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

# RSI + MACD
print(f'\n[动量]')
try:
    rsi1 = round(100 * float(d['ClosePositionRatio'].iloc[-1]), 1)
    rs = '多头动能' if rsi1 >= 60 else ('空头动能' if rsi1 <= 40 else '中性')
    print(f'  RSI(1)={rsi1:.0f} ({rs})')
    if 'MACD' in d.columns:
        mv = float(d['MACD'].iloc[-1]); ms = float(d['MACD_Signal'].iloc[-1])
        mh = float(d['MACD_Hist'].iloc[-1])
        md = '多头' if mv > ms else '空头'
        hd = '放大' if mh > float(d['MACD_Hist'].iloc[-2]) else '缩小' if len(d) > 2 else ''
        print(f'  MACD: {md} | 柱{hd}')
    # 3分VWAP突破检测
    if len(d) >= 3:
        vwap = float(d['VWAP'].iloc[-1])
        c1, c2 = float(d['Close'].iloc[-2]), float(d['Close'].iloc[-1])
        o1, o2 = float(d['Open'].iloc[-2]), float(d['Open'].iloc[-1])
        if c2 > vwap and c1 < vwap:
            print(f'  VWAP突破: ⬆️ 冲破VWAP')
            if c2 > o2 and c2 > c1:
                print(f'    第二根继续向前 ✅ 进场信号')
            else:
                print(f'    第二根力度不足 ⏳')
        elif c2 < vwap and c1 > vwap:
            print(f'  VWAP突破: ⬇️ 跌破VWAP')
            if c2 < o2 and c2 < c1:
                print(f'    第二根继续向下 ✅ 进场信号')
            else:
                print(f'    第二根力度不足 ⏳')
        else:
            if abs(c2 - vwap) / vwap < 0.002:
                print(f'  VWAP: 价格在VWAP附近')
except: pass

# 自动画图
import matplotlib
if True:
    try:
        import matplotlib.font_manager
        try:
            matplotlib.font_manager.fontManager.addfont('/tmp/NotoSansCJK.ttf')
            matplotlib.rcParams['font.family'] = 'Noto Sans CJK JP'
        except: pass
        import matplotlib.pyplot as plt, subprocess, shutil
        from hss_fib_scanner import calc_swing, calc_fib
        fig,ax=plt.subplots(figsize=(20,12)); fig.patch.set_facecolor('#0d1117');ax.set_facecolor('#0d1117')
        for i in range(len(d)):
            cc='#3fb950' if d['Close'].iloc[i]>d['Open'].iloc[i] else '#f85149'
            ax.plot([i,i],[d['Low'].iloc[i],d['High'].iloc[i]],cc,linewidth=0.3)
            ax.plot([i,i],[d['Open'].iloc[i],d['Close'].iloc[i]],cc,linewidth=2.5)
        # VWAP
        typ=(d['High']+d['Low']+d['Close'])/3
        if 'VWAP' not in d:
            d['VWAP']=(typ*d['Volume']).cumsum()/d['Volume'].cumsum()
        ax.plot(range(len(d)),d['VWAP'],'#58a6ff',linewidth=1.5,linestyle='--',alpha=0.7,label='VWAP')
        # Fib
        sw=d.tail(24);sd,sp,ep=calc_swing(sw);fib=calc_fib(sd,sp,ep)
        for lv,nm,cl,ex in[(0.0,'0.0 顶','#8b949e',''),(0.382,'0.382','#8b949e',''),(0.5,'0.5 中','#d29922',''),(0.618,'0.618 OTE','#f0883e','进场'),(0.786,'0.786','#8b949e',''),(1.0,'1.0 底','#8b949e','止损')]:
            pr=fib[lv];ax.axhline(y=pr,color=cl,linewidth=1,linestyle='--',alpha=0.5)
            t=f'  {nm} ${pr:.0f}'+(f' ~ {ex}' if ex else '');ax.text(len(d)-2,pr,t,fontsize=10,color=cl,fontweight='bold' if ex else 'normal')
        # FVG
        try:
            fvg_drawn=False
            for i in range(1,len(d)-1):
                if float(d['Low'].iloc[i])>float(d['High'].iloc[i-1]):
                    lo_fvg=float(d['High'].iloc[i-1]);hi_fvg=float(d['Low'].iloc[i])
                    ax.axhspan(lo_fvg,hi_fvg,alpha=0.12,color='#3fb950')
                    ax.text(len(d)-30,(lo_fvg+hi_fvg)/2,'FVG 看涨缺口',fontsize=11,color='#3fb950',fontweight='bold',bbox=dict(boxstyle='round',fc='#0d1117',ec='#3fb950'));fvg_drawn=True;break
                if float(d['Low'].iloc[i-1])>float(d['High'].iloc[i]):
                    lo_fvg=float(d['High'].iloc[i]);hi_fvg=float(d['Low'].iloc[i-1])
                    ax.axhspan(lo_fvg,hi_fvg,alpha=0.12,color='#f85149')
                    ax.text(len(d)-30,(lo_fvg+hi_fvg)/2,'FVG 看跌缺口',fontsize=11,color='#f85149',fontweight='bold',bbox=dict(boxstyle='round',fc='#0d1117',ec='#f85149'));fvg_drawn=True;break
            if not fvg_drawn:
                ax.text(0.02,0.92,'FVG: 无缺口',transform=ax.transAxes,fontsize=10,color='#8b949e',fontfamily='monospace')
        except: pass
        # T1 T2
        fib_range=fib[0.0]-fib[1.0]
        tp1=fib[0.0]+fib_range*0.2; tp2=fib[0.0]+fib_range*0.5
        ax.axhline(y=tp1,color='#58a6ff',linewidth=1.5,linestyle='-.');ax.annotate(f'T1 ${tp1:.0f}',xy=(len(d)-8,tp1+2),fontsize=12,color='#58a6ff',fontweight='bold',bbox=dict(boxstyle='round',fc='#0d1117',ec='#58a6ff'))
        ax.axhline(y=tp2,color='#58a6ff',linewidth=1.5,linestyle=':');ax.annotate(f'T2 ${tp2:.0f}',xy=(len(d)-12,tp2+2),fontsize=12,color='#58a6ff',fontweight='bold',bbox=dict(boxstyle='round',fc='#0d1117',ec='#58a6ff'))
        # 当前价
        ax.axhline(y=p,color='#ffd700',linewidth=2);ax.annotate(f'当前 ${p:.2f}',xy=(len(d)-1,p),fontsize=14,color='#ffd700',fontweight='bold')
        # 策略面板
        dir='做多' if p>float(d['VWAP'].iloc[-1]) else '做空'
        try:
            rsi_v=round(100*float(d['ClosePositionRatio'].iloc[-1]),1)
        except: rsi_v=50
        tx=f'交易计划\n{"="*16}\n方向: {dir}\n进场: Fib 0.618\n止损: Fib 1.0\nT1: Fib 0.0\nT2: 突破延伸\nRR: 2:1\n{"="*16}\nRSI(1)={rsi_v:.0f}'
        ax.text(0.75,0.35,tx,transform=ax.transAxes,fontsize=12,color='#f0f6fc',fontfamily='monospace',va='top',bbox=dict(boxstyle='round,pad=1',facecolor='#161b22',edgecolor='#30363d',lw=2))
        ax.set_title(f'{tk}',fontsize=16,color='#f0f6fc',fontweight='bold')
        ax.tick_params(colors='#8b949e');ax.grid(alpha=0.05);ax.legend(loc='upper left',facecolor='#0d1117',labelcolor='#f0f6fc')
        plt.tight_layout();plt.savefig('/tmp/ch.png',dpi=150,facecolor='#0d1117')
        shutil.copy('/tmp/ch.png','/home/codespace/.openclaw/workspace/ch.png')
        subprocess.run(['git','add','ch.png'],cwd='/home/codespace/.openclaw/workspace',capture_output=True)
        subprocess.run(['git','commit','-m','ch'],cwd='/home/codespace/.openclaw/workspace',capture_output=True)
        subprocess.run(['git','push'],cwd='/home/codespace/.openclaw/workspace',capture_output=True)
    except: pass

from risk_manager import print_check
print(f'\n[风控]')
print_check(tk, 'PUT', 2, 1.50, 1000)
