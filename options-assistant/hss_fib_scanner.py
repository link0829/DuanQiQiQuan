#!/usr/bin/env python3
"""
HSS + Fib + Price Action v5
裸K价格行为核心 + 市场结构状态机 + 多策略融合
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from collections import Counter
import sys

TICKERS = ["SPY", "QQQ"]
STREAK_MIN = 2
EMA_CONFIG = [8, 21, 50, 55, 100, 144]
FIB_LEVELS = [0.0, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618, 2.0]

# ═══════════════════════════════════════════════════
# 模块 1：裸K基础特征提取
# ═══════════════════════════════════════════════════

def extract_candle_features(df):
    """每根K线的裸K特征"""
    df['Range'] = df['High'] - df['Low']
    df['BodySize'] = (df['Close'] - df['Open']).abs()
    df['UpperShadow'] = df['High'] - df[['Open', 'Close']].max(axis=1)
    df['LowerShadow'] = df[['Open', 'Close']].min(axis=1) - df['Low']
    range_safe = df['Range'].replace(0, np.nan)
    df['ClosePositionRatio'] = (df['Close'] - df['Low']) / range_safe
    df['ClosePositionRatio'] = df['ClosePositionRatio'].fillna(0.5)
    df['BodyRatio'] = df['BodySize'] / range_safe.replace(0, np.nan)
    df['BodyRatio'] = df['BodyRatio'].fillna(0)
    df['IsBull'] = df['Close'] > df['Open']
    df['IsBear'] = df['Close'] < df['Open']
    df['IsDoji'] = df['BodySize'] < df['Range'] * 0.15
    # 动量：K线涨幅变化率（衡量加速/减速）
    df['RangeMA5'] = df['Range'].rolling(5).mean()
    df['Momentum'] = df['Range'] / df['RangeMA5'].replace(0, np.nan)
    df['Momentum'] = df['Momentum'].fillna(1.0)
    # 强动量K线：Range > 前5根均值 * 1.5 且 无影线
    df['StrongBull'] = df['IsBull'] & (df['Momentum'] >= 1.5) & (df['UpperShadow'] < df['BodySize'] * 0.1)
    df['StrongBear'] = df['IsBear'] & (df['Momentum'] >= 1.5) & (df['LowerShadow'] < df['BodySize'] * 0.1)
    return df

# ═══════════════════════════════════════════════════
# 模块 2：市场结构状态机
# ═══════════════════════════════════════════════════

def detect_swing_points(df, lookback=50):
    """
    波峰/波谷检测：
    当前K线的High高于前后各3根 → Swing High
    当前K线的Low低于前后各3根 → Swing Low
    """
    df = df.copy()
    df['SwingHigh'] = False
    df['SwingLow'] = False
    
    for i in range(3, len(df)-3):
        # Swing High: 最高点
        if all(df.iloc[i]['High'] > df.iloc[i-j]['High'] for j in [1,2,3]) and \
           all(df.iloc[i]['High'] > df.iloc[i+j]['High'] for j in [1,2,3]):
            df.loc[df.index[i], 'SwingHigh'] = True
        # Swing Low: 最低点
        if all(df.iloc[i]['Low'] < df.iloc[i-j]['Low'] for j in [1,2,3]) and \
           all(df.iloc[i]['Low'] < df.iloc[i+j]['Low'] for j in [1,2,3]):
            df.loc[df.index[i], 'SwingLow'] = True
    
    return df

class MarketStructureMachine:
    """
    市场结构状态机
    
    状态:
      - BULLISH: 连续HH+HL → 只做多，屏蔽空信号
      - BEARISH: 连续LH+LL → 只做空，屏蔽多信号
      - RANGE:   不满足条件 → 强制观望，屏蔽所有信号
    """
    
    # 趋势阈值（连续几组HH/HL才算趋势）
    TREND_THRESHOLD = 2
    
    def __init__(self, df):
        self.df = df
        self.last_idx = df.index[-1]
    
    def get_state(self):
        """返回当前市场状态"""
        recent = self.df.tail(50).copy()
        recent = detect_swing_points(recent)
        
        # 提取最近的波峰波谷
        sh = recent[recent['SwingHigh']].tail(6)
        sl = recent[recent['SwingLow']].tail(6)
        
        h_prices = sh['High'].values.tolist() if len(sh) > 0 else []
        l_prices = sl['Low'].values.tolist() if len(sl) > 0 else []
        
        result = {
            "state": "RANGE",
            "swing_highs": [round(x,2) for x in h_prices[-4:]],
            "swing_lows": [round(x,2) for x in l_prices[-4:]],
            "trend": "🟡 震荡趋势 (RANGE) — 强制观望"
        }
        
        # 按时间顺序排列波峰波谷
        swing_events = []
        for idx, row in recent.iterrows():
            if row['SwingHigh']:
                swing_events.append(('H', row['High'], idx))
            if row['SwingLow']:
                swing_events.append(('L', row['Low'], idx))
        
        # 至少需要4个点才能判断趋势 (H,L,H,L 或 L,H,L,H)
        if len(swing_events) < 4:
            result["state"] = "RANGE"
            result["trend"] = "🟡 数据不足 (RANGE)"
            return result
        
        # 提取交替的高低点
        highs_in_order = [p for t, p, _ in swing_events[-6:] if t == 'H']
        lows_in_order = [p for t, p, _ in swing_events[-6:] if t == 'L']
        
        # 多头: 更高的高点 AND 更高的低点
        hh = all(highs_in_order[i] > highs_in_order[i-1] for i in range(1, len(highs_in_order))) if len(highs_in_order) >= 2 else False
        hl = all(lows_in_order[i] > lows_in_order[i-1] for i in range(1, len(lows_in_order))) if len(lows_in_order) >= 2 else False
        
        # 空头: 更低的高点 AND 更低的低点
        lh = all(highs_in_order[i] < highs_in_order[i-1] for i in range(1, len(highs_in_order))) if len(highs_in_order) >= 2 else False
        ll = all(lows_in_order[i] < lows_in_order[i-1] for i in range(1, len(lows_in_order))) if len(lows_in_order) >= 2 else False
        
        if hh and hl:
            result["state"] = "BULLISH"
            result["trend"] = f"🟢 上升趋势 (HH+HL)"
        elif lh and ll:
            result["state"] = "BEARISH"
            result["trend"] = f"🔴 下降趋势 (LH+LL)"
        else:
            # 部分满足的情况
            if hh and not hl:
                result["trend"] = f"🟡 疑似多头 (HH但无HL)"
            elif hl and not hh:
                result["trend"] = f"🟡 疑似多头 (HL但无HH)"
            elif lh and not ll:
                result["trend"] = f"🟡 疑似空头 (LH但无LL)"
            elif ll and not lh:
                result["trend"] = f"🟡 疑似空头 (LL但无LH)"
        
        # Break of Structure
        if len(highs_in_order) >= 3:
            if highs_in_order[-1] > max(highs_in_order[:-1]):
                result["bos"] = "✅ 突破前高 (BuOS)"
        if len(lows_in_order) >= 3:
            if lows_in_order[-1] < min(lows_in_order[:-1]):
                result["bos"] = "✅ 跌破前低 (BdOS)"
        
        return result

# ═══════════════════════════════════════════════════
# 模块 3：价格行为扩展
# ═══════════════════════════════════════════════════

class PriceAction:
    
    @staticmethod
    def detect_strong_support(df, lookback=30):
        """
        用法1：没影线的大阳线 = 强支撑
        回踩该价位容易反弹
        """
        recent = df.tail(lookback)
        supports = []
        resistances = []
        for i in range(len(recent)):
            r = recent.iloc[i]
            if float(r['StrongBull']):
                # 无影线大阳线 → 强支撑位
                supports.append({
                    "idx": r.name,
                    "level": float(r['Close']),
                    "low": float(r['Low']),
                    "text": f"🟢 强支撑 @ ${float(r['Close']):.2f} (大阳线无上影)"
                })
            if float(r['StrongBear']):
                resistances.append({
                    "idx": r.name,
                    "level": float(r['Close']),
                    "high": float(r['High']),
                    "text": f"🔴 强阻力 @ ${float(r['Close']):.2f} (大阴线无下影)"
                })
        return supports[-2:] if supports else [], resistances[-2:] if resistances else []
    
    @staticmethod
    def detect_momentum_state(df, lookback=20):
        """
        用法3：动量 = 价格涨跌速度
        Momentum > 1 = 加速 (动能强，趋势延续)
        Momentum < 1 = 减速 (可能反转)
        """
        recent = df.tail(lookback)
        avg_momentum = float(recent['Momentum'].mean())
        recent_momentum = float(recent['Momentum'].tail(5).mean())
        price_up = float(recent['Close'].iloc[-1]) > float(recent['Close'].iloc[-5])
        
        if price_up and recent_momentum >= 1.2:
            return "⚡ 多头加速 (动能强劲，趋势延续)"
        elif price_up and recent_momentum < 0.8:
            return "⚠️ 多头减速 (涨势放缓，可能反转)"
        elif not price_up and recent_momentum >= 1.2:
            return "⚡ 空头加速 (动能强劲，趋势延续)"
        elif not price_up and recent_momentum < 0.8:
            return "⚠️ 空头减速 (跌势放缓，可能反转)"
        elif recent_momentum >= 0.8 and recent_momentum < 1.2:
            return "➡️ 动量中性 (正常波动)"
        else:
            return f"➡️ 动量[{avg_momentum:.2f}] 正常"
    
    @staticmethod
    def check_fib_strength(price, fib):
        """
        用法4：斐波那契回调强度分析
        上涨回调: 在0.618上方=弱回调(多头稳) / 跌破0.382=强回调(可能反转)
        """
        result = {}
        if price > fib.get(0.618, 0):
            result["assessment"] = "🟢 弱回调 (在0.618上方，多头稳健)"
            result["strength"] = "BULLISH"
        elif price > fib.get(0.5, 0):
            result["assessment"] = "🟡 中等回调 (0.5-0.618，正常范围)"
            result["strength"] = "NEUTRAL"
        elif price > fib.get(0.382, 0):
            result["assessment"] = "🔴 强回调 (0.382-0.5，警惕转势)"
            result["strength"] = "WEAK"
        else:
            result["assessment"] = "🔴🔴 深度回调 (跌破0.382，可能横盘或反转)"
            result["strength"] = "REVERSAL"
        return result
    def detect_liquidity(df, lookback=30):
        recent = df.tail(lookback)
        highs = recent['High'].values; lows = recent['Low'].values; closes = recent['Close'].values
        up, down = False, False
        if len(highs) >= 15:
            h10 = max(highs[-10:-1]); l10 = min(lows[-10:-1])
            if closes[-1] < h10 and highs[-1] > h10 * 1.001: up = True
            if closes[-1] > l10 and lows[-1] < l10 * 0.999: down = True
        # 等高低点
        eqh = eql = False
        if len(highs) >= 20:
            hc = Counter([round(x, 1) for x in highs[-20:]])
            lc = Counter([round(x, 1) for x in lows[-20:]])
            for v,c in hc.items():
                if c >= 3 and v == round(max(highs[-20:]),1): eqh = True
            for v,c in lc.items():
                if c >= 3 and v == round(min(lows[-20:]),1): eql = True
        return {"bsl_sweep": up, "ssl_sweep": down, "eq_highs": eqh, "eq_lows": eql}
    
    @staticmethod
    def detect_fvg(df, lookback=30):
        recent = df.tail(lookback); fvgs = []
        for i in range(1, len(recent)-1):
            if recent.iloc[i]['Low'] > recent.iloc[i-1]['High']:
                fvgs.append({"type":"bullish","top":round(recent.iloc[i]['Low'],2),"bottom":round(recent.iloc[i-1]['High'],2)})
            if recent.iloc[i]['High'] < recent.iloc[i-1]['Low']:
                fvgs.append({"type":"bearish","top":round(recent.iloc[i-1]['Low'],2),"bottom":round(recent.iloc[i]['High'],2)})
        p = df['Close'].iloc[-1]
        near = None
        for f in fvgs[-5:]:
            if f['bottom'] <= p <= f['top']: near = f; break
        return near, fvgs[-3:]
    
    @staticmethod
    def detect_ob(df, lookback=40):
        recent = df.tail(lookback); bo = {"bullish":None,"bearish":None}
        for i in range(2, min(40,len(recent)-1)):
            pb = abs(recent.iloc[i-1]['Close']-recent.iloc[i-1]['Open'])
            cb = abs(recent.iloc[i]['Close']-recent.iloc[i]['Open'])
            pb_bull = recent.iloc[i-1]['Close'] > recent.iloc[i-1]['Open']
            if not pb_bull and cb > pb*2 and not bo["bullish"]:
                bo["bullish"] = {"low":round(recent.iloc[i-1]['Low'],2),"high":round(recent.iloc[i-1]['High'],2)}
            if pb_bull and cb > pb*2 and not bo["bearish"]:
                bo["bearish"] = {"low":round(recent.iloc[i-1]['Low'],2),"high":round(recent.iloc[i-1]['High'],2)}
        return bo
    
    @staticmethod
    def detect_wyckoff(df, lookback=30):
        r = df.tail(lookback); h = r['High'].max(); l = r['Low'].min(); p = df['Close'].iloc[-1]; ra = h-l
        if ra == 0: return "数据不足"
        if p <= l + ra*0.33: return "📥 吸筹区 (Accumulation)"
        elif p >= h - ra*0.33: return "📤 派发区 (Distribution)"
        else: return "📊 测试区 (Test/UTAD)"

    # ─── 裸K形态量化（模块2 精确定义）───

    @staticmethod
    def detect_pinbars(df, lookback=20):
        """
        看涨Pin Bar: LowerShadow >= 2*BodySize, BodySize <= 0.3*Range, ClosePositionRatio >= 0.7
        看跌Pin Bar: UpperShadow >= 2*BodySize, BodySize <= 0.3*Range, ClosePositionRatio <= 0.3
        """
        recent = df.tail(lookback)
        bullish, bearish = [], []
        for i in range(len(recent)):
            r = recent.iloc[i]
            body = float(r['BodySize'])
            rng = float(r['Range'])
            if rng == 0: continue
            us = float(r['UpperShadow'])
            ls = float(r['LowerShadow'])
            cpr = float(r['ClosePositionRatio'])
            
            # 看涨 Pin Bar：长下影 + 实体小 + 收盘在高位
            if ls >= 2 * body and body <= 0.3 * rng and cpr >= 0.7:
                bullish.append({
                    "idx": r.name, "price": float(r['Close']), "high": float(r['High']), "low": float(r['Low']),
                    "text": f"🟢 看涨PinBar @ ${float(r['Close']):.2f} (下影{ls:.2f} 实体{body:.2f})"
                })
            # 看跌 Pin Bar：长上影 + 实体小 + 收盘在低位
            if us >= 2 * body and body <= 0.3 * rng and cpr <= 0.3:
                bearish.append({
                    "idx": r.name, "price": float(r['Close']), "high": float(r['High']), "low": float(r['Low']),
                    "text": f"🔴 看跌PinBar @ ${float(r['Close']):.2f} (上影{us:.2f} 实体{body:.2f})"
                })
        return {"bullish": bullish[-2:] if bullish else [], "bearish": bearish[-2:] if bearish else []}

    @staticmethod
    def detect_engulfing(df, lookback=20):
        """
        看涨吞没 (i-1阴, i阳):
          Open_i <= Close_i-1 AND Close_i >= Open_i-1
          BodySize_i > BodySize_i-1 AND Volume_i > Volume_i-1
        看跌吞没 (i-1阳, i阴): 反向
        """
        recent = df.tail(lookback)
        bullish, bearish = [], []
        for i in range(1, len(recent)):
            prev = recent.iloc[i-1]; curr = recent.iloc[i]
            pb = float(prev['BodySize']); cb = float(curr['BodySize'])
            if pb == 0: continue
            prev_bear = float(prev['IsBear'])
            curr_bull = float(curr['IsBull'])
            
            # 看涨吞没
            if prev_bear and curr_bull:
                if float(curr['Open']) <= float(prev['Close']) and float(curr['Close']) >= float(prev['Open']):
                    if cb > pb and float(curr['Volume']) > float(prev['Volume']):
                        bullish.append({
                            "idx": curr.name, "price": float(curr['Close']),
                            "high": float(curr['High']), "low": float(curr['Low']),
                            "text": f"🟢 看涨吞没 @ ${float(curr['Close']):.2f} (量{float(curr['Volume']):.0f}>{float(prev['Volume']):.0f})"
                        })
            
            # 看跌吞没
            curr_bear = float(curr['IsBear'])
            prev_bull = float(prev['IsBull'])
            if prev_bull and curr_bear:
                if float(curr['Open']) >= float(prev['Close']) and float(curr['Close']) <= float(prev['Open']):
                    if cb > pb and float(curr['Volume']) > float(prev['Volume']):
                        bearish.append({
                            "idx": curr.name, "price": float(curr['Close']),
                            "high": float(curr['High']), "low": float(curr['Low']),
                            "text": f"🔴 看跌吞没 @ ${float(curr['Close']):.2f} (量{float(curr['Volume']):.0f}>{float(prev['Volume']):.0f})"
                        })
        return {"bullish": bullish[-2:] if bullish else [], "bearish": bearish[-2:] if bearish else []}

# ═══════════════════════════════════════════════════
# 模块 4：斐波那契
# ═══════════════════════════════════════════════════

def calc_swing(df):
    hi = df['High'].max(); lo = df['Low'].min()
    return ('UP', lo, hi) if df['Close'].iloc[-1] > (hi+lo)/2 else ('DOWN', hi, lo)

def calc_fib(dir, sp, ep):
    d = abs(ep-sp); levs = {}
    for l in FIB_LEVELS:
        levs[l] = (ep-d*l if dir=='UP' else sp-d*l)
    return {
        **levs,
        "zone_low": min(levs[0.5], levs[0.618]), "zone_high": max(levs[0.5], levs[0.618]),
        "entry_618": levs[0.618], "sl_786": levs[0.786], "tp_382": levs[0.382],
    }

# ═══════════════════════════════════════════════════
# 模块 5：EMA + HSS
# ═══════════════════════════════════════════════════

def add_indicators(df):
    for n in EMA_CONFIG: df[f'EMA{n}'] = df['Close'].ewm(span=n, adjust=False).mean()
    e12 = df['Close'].ewm(span=12,adjust=False).mean()
    e26 = df['Close'].ewm(span=26,adjust=False).mean()
    df['MACD'] = e12 - e26
    df['MACD_Signal'] = df['MACD'].ewm(span=9,adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    df['ATR14'] = df['Range'].rolling(14).mean()
    # VWAP
    typical = (df['High'] + df['Low'] + df['Close']) / 3
    cum_pv = (typical * df['Volume']).cumsum()
    cum_vol = df['Volume'].cumsum().replace(0, np.nan)
    df['VWAP'] = cum_pv / cum_vol
    return df

def calc_hss_ha(df):
    ha = df.copy()
    ha['HA_Close'] = (ha['Open']+ha['High']+ha['Low']+ha['Close'])/4
    ha['HA_Open'] = np.nan
    ha.iloc[0, ha.columns.get_loc('HA_Open')] = (ha.iloc[0]['Open']+ha.iloc[0]['Close'])/2
    for i in range(1,len(ha)):
        ha.iloc[i, ha.columns.get_loc('HA_Open')] = (ha.iloc[i-1]['HA_Open']+ha.iloc[i-1]['HA_Close'])/2
    ha['HA_High'] = ha[['High','HA_Open','HA_Close']].max(axis=1)
    ha['HA_Low'] = ha[['Low','HA_Open','HA_Close']].min(axis=1)
    ha['HA_Body'] = abs(ha['HA_Close']-ha['HA_Open'])
    ha['HA_Bull'] = ha['HA_Close'] > ha['HA_Open']
    ha['HA_UpperWick'] = ha['HA_High'] - ha[['HA_Open','HA_Close']].max(axis=1)
    ha['HA_LowerWick'] = ha[['HA_Open','HA_Close']].min(axis=1) - ha['HA_Low']
    ha['NoUpper'] = ha['HA_UpperWick'] < ha['HA_Body']*0.1
    ha['NoLower'] = ha['HA_LowerWick'] < ha['HA_Body']*0.1
    ha['BearPB'] = (~ha['HA_Bull']) & ha['NoUpper']
    ha['BullPB'] = ha['HA_Bull'] & ha['NoLower']
    ha['BearPBCnt'] = ha['BearPB'].astype(int).groupby((~ha['BearPB']).cumsum()).cumsum()
    ha['BullPBCnt'] = ha['BullPB'].astype(int).groupby((~ha['BullPB']).cumsum()).cumsum()
    ha['DojiBody'] = ha['HA_Body'] < ha['ATR14']*0.15
    ha['VolHigh'] = ha['Volume'] >= ha['Volume'].shift(1).rolling(3,min_periods=1).max()
    ha['DojiSig'] = ha['DojiBody'] & ha['VolHigh']
    ha['BullMkt'] = ha['Close'] > ha['EMA100']
    ha['LongHSS'] = ha['BullMkt'] & (ha['BearPBCnt'] >= STREAK_MIN) & ha['DojiSig']
    ha['ShortHSS'] = (~ha['BullMkt']) & (ha['BullPBCnt'] >= STREAK_MIN) & ha['DojiSig']
    return ha

def ema_diag(df):
    p = float(df['Close'].iloc[-1]); emas = {}
    for n in EMA_CONFIG: emas[n] = float(df[f'EMA{n}'].iloc[-1]) if f'EMA{n}' in df else p
    r = {"price":p,"emas":emas}
    for n in EMA_CONFIG: r[f'a{n}'] = p > emas.get(n,p)
    if all(k in emas for k in [8,21,55,144]):
        if emas[8]>emas[21]>emas[55]>emas[144]: r["align"]="🟢多头排列"
        elif emas[8]<emas[21]<emas[55]<emas[144]: r["align"]="🔴空头排列"
        else: r["align"]="🟡交叉粘合"
    r["strong"] = "⚡强势" if p>emas.get(8,p) else "📉弱势"
    return r

def get_killzone(et_h, et_m):
    t = et_h*100+et_m
    if 800 <= t < 900: return "🌅 伦敦开盘"
    if 930 <= t < 1100: return "🔥 纽约开盘 ← 高流动性"
    if 1100 <= t < 1200: return "⚡ 伦敦收盘 ← 流动性高峰"
    if 1400 <= t < 1530: return "📊 午盘"
    if 1530 <= t < 1600: return "💥 Power Hour"
    if t >= 1600 or t < 300: return "🔒 盘后"
    if 300 <= t < 800: return "🌙 亚盘"
    return "🌤️ 早盘"

# ═══════════════════════════════════════════════════
# 模块 6：趋势解构四步法（宏观过滤器）
# ═══════════════════════════════════════════════════

def macro_bias_analysis(ticker):
    """
    Step 1 — 建立战略偏见
    日线MA20/60/120排列 + MACD + 价格位置
    输出: BULLISH / BEARISH / WAIT
    """
    try:
        daily = yf.download(ticker, period='6mo', interval='1d', progress=False)
        if daily.empty: return None
        daily.columns = [c[0] if isinstance(c,tuple) else c for c in daily.columns]
        
        for n in [20,60,120]:
            daily[f'MA{n}'] = daily['Close'].rolling(n).mean()
        
        # RSI
        delta = daily['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        daily['RSI'] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
        
        # MACD日线
        e12 = daily['Close'].ewm(span=12,adjust=False).mean()
        e26 = daily['Close'].ewm(span=26,adjust=False).mean()
        daily['MACD'] = e12 - e26
        daily['MACD_Signal'] = daily['MACD'].ewm(span=9,adjust=False).mean()
        daily['MACD_Zero'] = daily['MACD'] > 0
        
        last = daily.iloc[-1]
        price = float(last['Close'])
        ma20 = float(last['MA20']); ma60 = float(last['MA60']); ma120 = float(last['MA120'])
        
        # MA排列
        bull_align = ma20 > ma60 > ma120 and price > ma20
        bear_align = ma20 < ma60 < ma120 and price < ma20
        mixed = not bull_align and not bear_align
        
        # MACD
        macd_bull = float(last['MACD']) > float(last['MACD_Signal']) and float(last['MACD']) > 0
        macd_bear = float(last['MACD']) < float(last['MACD_Signal']) and float(last['MACD']) < 0
        
        # RSI
        rsi_val = float(last['RSI']) if not pd.isna(last['RSI']) else 50
        rsi_bull = rsi_val > 50
        rsi_bear = rsi_val < 50
        
        # 综合偏见投票
        bull_score = 0; bear_score = 0
        if bull_align: bull_score += 2
        if macd_bull: bull_score += 1
        if rsi_bull: bull_score += 1
        if bear_align: bear_score += 2
        if macd_bear: bear_score += 1
        if rsi_bear: bear_score += 1
        
        if bull_score >= 3 and bull_score > bear_score:
            bias = 'BULLISH'; trend = '🟢 战略偏多'
        elif bear_score >= 3 and bear_score > bull_score:
            bias = 'BEARISH'; trend = '🔴 战略偏空'
        else:
            bias = 'WAIT'; trend = '🟡 战略观望 (方向不明确)'
        
        return {
            'bias': bias, 'trend': trend,
            'ma20': round(ma20,2), 'ma60': round(ma60,2), 'ma120': round(ma120,2),
            'bull_align': bull_align, 'bear_align': bear_align, 'mixed': mixed,
            'macd_bull': macd_bull, 'macd_bear': macd_bear,
            'rsi': round(rsi_val,1),
            'price': round(price,2),
            'bull_score': bull_score, 'bear_score': bear_score
        }
    except Exception as e:
        return {'bias': 'WAIT', 'trend': f'⚠️ 数据错误: {e}'}

def trend_phase_analysis(daily_df):
    """
    Step 2 — 识别趋势阶段
    启动/加速/衰竭/反转
    """
    try:
        if len(daily_df) < 30: return '⏳ 数据不足'
        
        close = daily_df['Close']
        vol = daily_df['Volume']
        high = daily_df['High']
        low = daily_df['Low']
        
        last10 = daily_df.tail(10)
        prev10 = daily_df.tail(20).head(10)
        
        # K线实体变化
        avg_body_last = (abs(last10['Close'] - last10['Open'])).mean()
        avg_body_prev = (abs(prev10['Close'] - prev10['Open'])).mean()
        
        # 成交量变化
        avg_vol_last = vol.tail(10).mean()
        avg_vol_prev = vol.tail(20).head(10).mean()
        
        # MACD柱变化
        if 'MACD_Hist' in daily_df.columns:
            hist_last = float(daily_df['MACD_Hist'].tail(5).mean())
            hist_prev = float(daily_df['MACD_Hist'].tail(10).head(5).mean())
        else:
            hist_last = 0; hist_prev = 0
        
        # 近期高低点
        recent_range = high.tail(20).max() - low.tail(20).min()
        prev_range = high.tail(40).head(20).max() - low.tail(40).head(20).min()
        
        # 判断
        body_growing = avg_body_last > avg_body_prev * 1.2
        body_shrinking = avg_body_last < avg_body_prev * 0.8
        vol_growing = avg_vol_last > avg_vol_prev * 1.2
        vol_shrinking = avg_vol_last < avg_vol_prev * 0.8
        hist_growing = abs(hist_last) > abs(hist_prev) * 1.1
        hist_shrinking = abs(hist_last) < abs(hist_prev) * 0.9
        range_expanding = recent_range > prev_range * 1.2
        
        # 趋势阶段投票
        start_score = 0
        accel_score = 0
        exhaust_score = 0
        
        if body_growing and vol_growing: start_score += 2
        if body_growing and vol_growing and range_expanding: accel_score += 3
        if hist_growing and body_growing: accel_score += 1
        if vol_shrinking and body_shrinking: exhaust_score += 2
        if hist_shrinking: exhaust_score += 1
        if vol_growing and body_shrinking: exhaust_score += 2
        
        if accel_score >= 3:
            return '⚡ 加速期 (动能强劲)'
        elif start_score >= 2:
            return '🚀 启动期 (趋势形成)'
        elif exhaust_score >= 2:
            return '⚠️ 衰竭期 (动能衰退)'
        else:
            return '➡️ 整理期 (方向待定)'
    except:
        return '⏳ 计算中'

def print_macro_bias(output, ticker):
    """格式化输出宏观偏见"""
    print(f"\n{'─'*55}")
    print(f"  🌐 【趋势解构四步法】— {ticker}")
    print(f"{'─'*55}")
    
    if not output:
        print(f"  ⚠️ 无数据")
        return
    
    # Step 1
    print(f"\n  Step 1 — 战略偏见")
    print(f"  {output.get('trend','N/A')}")
    print(f"  MA20={output.get('ma20','N/A')} | MA60={output.get('ma60','N/A')} | MA120={output.get('ma120','N/A')}")
    print(f"  RSI(14)={output.get('rsi','N/A')} | 多头投票={output.get('bull_score',0)} vs 空头投票={output.get('bear_score',0)}")
    
    # Step 3 — 能量验证
    if output.get('bull_align'):
        print(f"  ✅ MA多头排列 + RSI>{'50' if output.get('rsi',50)>50 else '50'} + 能量达标")
    elif output.get('bear_align'):
        print(f"  ✅ MA空头排列 + RSI<{'50' if output.get('rsi',50)<50 else '50'} + 能量达标")
    else:
        print(f"  ⚠️ 能量不足/均线粘合 → 放弃交易信号")

# ═══════════════════════════════════════════════════
# 主分析
# ═══════════════════════════════════════════════════

def analyze(tickers=None):
    if tickers is None: tickers = TICKERS
    now = datetime.now(timezone.utc)
    eh = (now.hour-4)%24; em = now.minute
    print(f"🕐 {now.strftime('%H:%M:%S')} UTC | 美东 {eh:02d}:{em:02d}")
    print(f"   {get_killzone(eh, em)}")
    print("="*72)
    total_sig = []
    
    for tk in tickers:
        print(f"\n📊 {tk}")
        print("="*72)
        try:
            d = yf.download(tk, period="5d", interval="1m", progress=False)
            if d.empty: print("⚠️ 无数据"); continue
            d.columns = [c[0] if isinstance(c,tuple) else c for c in d.columns]
            
            d = extract_candle_features(d)
            d = add_indicators(d)
            d = calc_hss_ha(d)
            
            last = d.iloc[-1]; p = float(last['Close'])
            
            # ─── 宏观偏见（趋势解构四步法） ───
            macro = macro_bias_analysis(tk)
            if macro:
                print_macro_bias(macro, tk)
                
                # 宏观偏见过滤
                macro_bias = macro.get('bias', 'WAIT')
                if macro_bias == 'WAIT':
                    print(f"\n  🚦 宏观过滤: 战略观望 → 放弃本次交易信号")
            else:
                macro_bias = 'WAIT'
            print(f"\n┌─ ① 裸K特征")
            print(f"│  Range={float(last['Range']):.2f} | Body={float(last['BodySize']):.2f} ({float(last['BodyRatio'])*100:.0f}%)")
            print(f"│  上影={float(last['UpperShadow']):.2f} | 下影={float(last['LowerShadow']):.2f}")
            print(f"│  收盘位置={float(last['ClosePositionRatio'])*100:.0f}% | 类型={'阳' if last['IsBull'] else '阴' if last['IsBear'] else '十字星'}")
            
            # ─── ② 市场结构 ───
            msm = MarketStructureMachine(d)
            ms = msm.get_state()
            print(f"\n┌─ ② 市场结构状态机")
            print(f"│  {ms['trend']}")
            if ms.get("bos"): print(f"│  {ms['bos']}")
            if ms['swing_highs']: print(f"│  波峰: {ms['swing_highs']}")
            if ms['swing_lows']: print(f"│  波谷: {ms['swing_lows']}")
            
            # 趋势过滤引擎
            trend_state = ms["state"]  # BULLISH / BEARISH / RANGE
            if trend_state == "RANGE":
                trend_filter = "⛔ 震荡 → 屏蔽所有信号，强制观望"
            elif trend_state == "BULLISH":
                trend_filter = "🟢 多头趋势 → 仅做多，屏蔽空信号"
            else:
                trend_filter = "🔴 空头趋势 → 仅做空，屏蔽多信号"
            print(f"│  🚦 趋势过滤: {trend_filter}")
            
            # ─── ③ 流动性 ───
            liq = PriceAction.detect_liquidity(d)
            print(f"\n┌─ ③ 流动性 (ICT)")
            if liq['bsl_sweep']: print(f"│  🔴 上方流动性被扫 (BSL Sweep)")
            if liq['ssl_sweep']: print(f"│  🟢 下方流动性被扫 (SSL Sweep) ← 潜在反转做多区")
            if liq['eq_highs']: print(f"│  ⚠️ 等高点EQH")
            if liq['eq_lows']: print(f"│  ⚠️ 等低点EQL")
            if not any([liq['bsl_sweep'],liq['ssl_sweep'],liq['eq_highs'],liq['eq_lows']]):
                print(f"│  ➡️ 无显著事件")
            
            # ─── ④ FVG ───
            nf, _ = PriceAction.detect_fvg(d)
            print(f"\n┌─ ④ Fair Value Gap")
            if nf: print(f"│  {'🟢' if nf['type']=='bullish' else '🔴'} FVG: ${nf['bottom']:.2f}~${nf['top']:.2f}")
            else: print(f"│  ➡️ 无FVG")
            
            # ─── ⑤ OB + Wyckoff ───
            ob = PriceAction.detect_ob(d)
            print(f"\n┌─ ⑤ 供需区 + Wyckoff")
            if ob['bullish']: print(f"│  🟢 需求区: ${ob['bullish']['low']:.2f}~${ob['bullish']['high']:.2f}")
            if ob['bearish']: print(f"│  🔴 供给区: ${ob['bearish']['low']:.2f}~${ob['bearish']['high']:.2f}")
            wk = PriceAction.detect_wyckoff(d)
            print(f"│  {wk}")
            
            # ─── ⑥ 斐波那契 ───
            sw_df = d.tail(60)
            sd, sp, ep = calc_swing(sw_df)
            fib = calc_fib(sd, sp, ep)
            in_zone = fib['zone_low'] <= p <= fib['zone_high']
            print(f"\n┌─ ⑥ 斐波那契 OTE")
            print(f"│  {'📈' if sd=='UP' else '📉'} 波段: ${sp:.2f}→${ep:.2f}")
            for l in [0.0,0.382,0.5,0.618,0.786,1.0]:
                m = ""
                if abs(p-fib[l])/p < 0.001: m = " ◀"
                elif l == 0.618: m = " ★ OTE"
                print(f"│  {l:<5}: ${fib[l]:.2f}{m}")
            print(f"│  0.5-0.618: {'✅' if in_zone else '❌'}")
            
            # ─── ⑦ 裸K形态（模块2） ───
            pinbars = PriceAction.detect_pinbars(d)
            engulfing = PriceAction.detect_engulfing(d)
            print(f"\n┌─ ⑦ 裸K形态")
            if pinbars['bullish']:
                for pb in pinbars['bullish'][-1:]:
                    print(f"│  {pb['text']}")
            if pinbars['bearish']:
                for pb in pinbars['bearish'][-1:]:
                    print(f"│  {pb['text']}")
            if engulfing['bullish']:
                for eg in engulfing['bullish'][-1:]:
                    print(f"│  {eg['text']}")
            if engulfing['bearish']:
                for eg in engulfing['bearish'][-1:]:
                    print(f"│  {eg['text']}")
            if not any([pinbars['bullish'], pinbars['bearish'], engulfing['bullish'], engulfing['bearish']]):
                print(f"│  ➡️ 无显著形态")
            
            # ─── ⑧ 共振区 ───
            vwap = float(d['VWAP'].iloc[-1])
            ema100 = float(last['EMA100'])
            near_vwap = abs(p - vwap) / p < 0.002
            near_ema100 = abs(p - ema100) / p < 0.002
            confluences = []
            if near_vwap: confluences.append("VWAP")
            if near_ema100: confluences.append("100EMA")
            if in_zone: confluences.append("FIB 0.5-0.618")
            print(f"\n┌─ ⑧ 共振区 (VWAP+EMA+FIB)")
            print(f"│  VWAP=${vwap:.2f} | EMA100=${ema100:.2f}")
            print(f"│  共鸣: {'✅ '.join(confluences) if confluences else '❌ 无共振'}")
            
            # ─── ⑨ HSS ───
            print(f"\n┌─ ⑨ HSS")
            print(f"│  方向: {'🟢多头' if last['BullMkt'] else '🔴空头'} | 回调空{int(last['BearPBCnt'])}多{int(last['BullPBCnt'])}")
            print(f"│  十字星: {'✅' if last['DojiSig'] else '❌'} | 高量: {'✅' if last['VolHigh'] else '❌'}")
            
            # ─── ⑩ 动量 + 支撑/阻力 ───
            supports, resistances = PriceAction.detect_strong_support(d)
            momentum_state = PriceAction.detect_momentum_state(d)
            fib_strength = PriceAction.check_fib_strength(p, fib)
            ema50 = float(last['EMA50']) if 'EMA50' in last else p
            dev_50ma = (p - ema50) / ema50 * 100
            print(f"\n┌─ ⑩ 动量 + 支撑/阻力")
            print(f"│  {momentum_state}")
            if supports:
                for s in supports[-1:]:
                    print(f"│  {s['text']}")
            if resistances:
                for r in resistances[-1:]:
                    print(f"│  {r['text']}")
            print(f"│  {fib_strength['assessment']}")
            print(f"│  50MA偏差: {dev_50ma:+.2f}% {'(大幅偏离,有修复需求)' if abs(dev_50ma) > 1 else ''}")
            print(f"│  Range/Momentum: 最近={float(last['Momentum']):.2f}x | 5均={float(last['RangeMA5']):.2f}")
            
            # ─── ⑪ 交叉验证计数器 ───
            hss_long_raw = bool(last['LongHSS'])
            hss_short_raw = bool(last['ShortHSS'])
            crosses = 0
            cross_details = []
            # 1. 趋势方向
            if trend_state in ("BULLISH",):
                crosses += 1; cross_details.append("趋势偏多")
            elif trend_state in ("BEARISH",):
                crosses += 1; cross_details.append("趋势偏空")
            # 2. 斐波那契强度
            if fib_strength['strength'] in ("BULLISH",):
                crosses += 1; cross_details.append("Fib多头")
            elif fib_strength['strength'] in ("WEAK","REVERSAL"):
                crosses += 1; cross_details.append("Fib转势")
            # 3. 动量
            if '加速' in momentum_state:
                crosses += 1; cross_details.append("动量强劲")
            # 4. 共振区
            if confluences:
                crosses += 1; cross_details.append("共振")
            # 5. HSS信号
            if hss_long_raw or hss_short_raw:
                crosses += 1; cross_details.append("HSS就绪")
            print(f"\n┌─ ⑪ 交叉验证（{crosses}/5个规则对齐）")
            if cross_details:
                print(f"│  {' | '.join(cross_details)}")
            if crosses >= 3:
                print(f"│  ✅ 多规则一致，信号有效")
            else:
                print(f"│  ⚠️ 信号偏少，等待更多确认")
            
            # ─── FINAL：趋势过滤 + 风控（模块2工作流） ───
            print(f"\n└─ ⑩ 综合决策 [{trend_state}]")
            
            # 趋势过滤
            can_long = trend_state in ("BULLISH",)
            can_short = trend_state in ("BEARISH",)
            can_trade = trend_state != "RANGE"
            
            # 形态检测（最近3根内）
            has_bull_pin = any(pinbars['bullish'])
            has_bear_pin = any(pinbars['bearish'])
            has_bull_eng = any(engulfing['bullish'])
            has_bear_eng = any(engulfing['bearish'])
            has_bull_pattern = has_bull_pin or has_bull_eng
            has_bear_pattern = has_bear_pin or has_bear_eng
            
            # 信号源（已在上文定义）
            
            # 共振过滤：价格必须在 VWAP / EMA100 / FIB 至少一个共振区
            confluence_ok = len(confluences) >= 1
            
            sigs = []
            
            if not can_trade:
                print(f"│  ⛔ 震荡市场 → 强制观望")
            elif not confluence_ok:
                print(f"│  ⛔ 无共振 → 价格未触及VWAP/EMA/FIB任何区域")
            else:
                # --- 做多路径 ---
                bull_ready = hss_long_raw or has_bull_pattern
                if bull_ready and can_long and can_trade:
                    # 止损: 信号K线最低点下方
                    sl_price = min(
                        float(last['Low']) if hss_long_raw else 9999,
                        min([p['low'] for p in pinbars['bullish']], default=9999),
                        min([e['low'] for e in engulfing['bullish']], default=9999)
                    )
                    # 止盈: 前方波峰
                    tp_price = fib['tp_382']
                    if ms.get('swing_highs'):
                        tp_price = max(tp_price, max(ms['swing_highs']))
                    # RR计算
                    rr = abs(tp_price - p) / abs(p - sl_price) if abs(p - sl_price) > 0 else 0
                    
                    if p > sl_price:
                        signals_text = []
                        if hss_long_raw: signals_text.append("HSS")
                        if has_bull_pin: signals_text.append("PinBar")
                        if has_bull_eng: signals_text.append("Engulfing")
                        
                        if rr >= 1.5:
                            sigs.append((
                                f"🟢🟢 {'+'.join(signals_text)} 做多 (RR={rr:.1f})✅",
                                f"进场${p:.2f} SL${sl_price:.2f} TP${tp_price:.2f} | {'+'.join(confluences)}"
                            ))
                        else:
                            print(f"│  ⛔ RR={rr:.1f} < 1.5 → 强制放弃")
                            print(f"│  💡 信号: {'+'.join(signals_text)} | 共振: {'+'.join(confluences)}")
                
                # --- 做空路径 ---
                bear_ready = hss_short_raw or has_bear_pattern
                if bear_ready and can_short and can_trade:
                    sl_price = max(
                        float(last['High']) if hss_short_raw else 0,
                        max([p['high'] for p in pinbars['bearish']], default=0),
                        max([e['high'] for e in engulfing['bearish']], default=0)
                    )
                    tp_price = fib['tp_382']
                    if ms.get('swing_lows'):
                        tp_price = min(tp_price, min(ms['swing_lows']))
                    rr = abs(p - tp_price) / abs(sl_price - p) if abs(sl_price - p) > 0 else 0
                    
                    if sl_price > p:
                        signals_text = []
                        if hss_short_raw: signals_text.append("HSS")
                        if has_bear_pin: signals_text.append("PinBar")
                        if has_bear_eng: signals_text.append("Engulfing")
                        
                        if rr >= 1.5:
                            sigs.append((
                                f"🔴🔴 {'+'.join(signals_text)} 做空 (RR={rr:.1f})✅",
                                f"进场${p:.2f} SL${sl_price:.2f} TP${tp_price:.2f} | {'+'.join(confluences)}"
                            ))
                        else:
                            print(f"│  ⛔ RR={rr:.1f} < 1.5 → 强制放弃")
                            print(f"│  💡 信号: {'+'.join(signals_text)} | 共振: {'+'.join(confluences)}")
                
                # ICT流动性
                if liq['ssl_sweep'] and in_zone and can_long and not sigs:
                    sigs.append(("🟢 ICT SSL+FIB", "流动性扫荡+OTE到位 准备做多"))
                if liq['bsl_sweep'] and in_zone and can_short and not sigs:
                    sigs.append(("🔴 ICT BSL+FIB", "流动性扫荡+OTE到位 准备做空"))
                
                if sigs:
                    for s in sigs:
                        print(f"│  {s[0]}: {s[1]}")
                        total_sig.append((tk, s[0], p))
                else:
                    reasons = []
                    # 诊断
                    if hss_long_raw or has_bull_pattern:
                        if not can_long: reasons.append("趋势过滤阻挡做多")
                        elif not confluence_ok: reasons.append("无共振")
                    if hss_short_raw or has_bear_pattern:
                        if not can_short: reasons.append("趋势过滤阻挡做空")
                        elif not confluence_ok: reasons.append("无共振")
                    if not (hss_long_raw or hss_short_raw or has_bull_pattern or has_bear_pattern):
                        if can_trade and confluence_ok:
                            reasons.append("等待信号K线确认")
                    if not reasons:
                        reasons.append("无显著信号")
                    print(f"│  ⏸️ {' | '.join(reasons)}")
            
            # 最近3根
            print(f"\n   最近3根K线:")
            for i in range(max(0,len(d)-3), len(d)):
                r = d.iloc[i]; t = r.name
                ma = ""
                if r['LongHSS']: ma = "🟢"
                elif r['ShortHSS']: ma = "🔴"
                elif r['DojiSig']: ma = "◇"
                print(f"   {t.strftime('%H:%M'):>10} {r['Open']:>7.2f} {r['High']:>7.2f} {r['Low']:>7.2f} {r['Close']:>7.2f} {float(r['Volume']):>10,.0f} {ma}")
                
        except Exception as e:
            print(f"   ❌ {e}")
    
    print(f"\n{'='*72}")
    if not total_sig: print("⏸️ 无信号")
    else:
        print(f"🎯 {len(total_sig)} 信号:")
        for s in total_sig: print(f"   {s[0]} {s[1]} ${s[2]:.2f}")

if __name__ == "__main__":
    analyze(sys.argv[1:] if len(sys.argv) > 1 else None)
