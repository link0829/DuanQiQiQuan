#!/usr/bin/env python3
"""
Pin Bar 战法 — 完整交易系统
融合：形态识别 + 趋势背景 + 关键位共振 + 止损止盈
"""
import numpy as np

class PinBarStrategy:
    """
    Pin Bar 完整战法
    
    核心原则：
    - 趋势中的Pin Bar > 震荡中的Pin Bar
    - 关键位的Pin Bar > 随机位置的Pin Bar
    - 大时间框架的Pin Bar > 小时间框架的Pin Bar
    """
    
    # 精确量化阈值
    CONDITIONS = {
        "bullish": {"shadow_min": 2.0, "body_max": 0.3, "cpr_min": 0.7},
        "bearish": {"shadow_min": 2.0, "body_max": 0.3, "cpr_max": 0.3}
    }
    
    @staticmethod
    def detect(df, lookback=30):
        """
        检测Pin Bar并输出完整分析
        
        返回:
        [{
            "type": "bullish"/"bearish",
            "idx": timestamp,
            "price": close,
            "high": high,
            "low": low,
            "body": body_size,
            "shadow": shadow_length,
            "shadow_ratio": shadow/body,
            "volume": volume,
            "score": 0-5 综合评分,
            "strength": "weak"/"moderate"/"strong"
        }]
        """
        recent = df.tail(lookback)
        pins = []
        C = PinBarStrategy.CONDITIONS
        
        for i in range(len(recent)):
            r = recent.iloc[i]
            body = float(r['BodySize'])
            rng = float(r['Range'])
            if rng == 0: continue
            upper = float(r['UpperShadow'])
            lower = float(r['LowerShadow'])
            cpr = float(r['ClosePositionRatio'])
            
            # — 看涨Pin Bar —
            if lower >= C["bullish"]["shadow_min"] * body and \
               body <= C["bullish"]["body_max"] * rng and \
               cpr >= C["bullish"]["cpr_min"]:
                
                shadow_ratio = lower / body if body > 0 else 99
                pins.append(PinBarStrategy._grade(r, "bullish", body, lower, upper, shadow_ratio, cpr, rng))
            
            # — 看跌Pin Bar —
            if upper >= C["bearish"]["shadow_min"] * body and \
               body <= C["bearish"]["body_max"] * rng and \
               cpr <= C["bearish"]["cpr_max"]:
                
                shadow_ratio = upper / body if body > 0 else 99
                pins.append(PinBarStrategy._grade(r, "bearish", body, upper, lower, shadow_ratio, cpr, rng))
        
        return pins[-5:] if pins else []
    
    @staticmethod
    def _grade(r, ptype, body, shadow_main, shadow_opp, shadow_ratio, cpr, rng):
        """评分：0-5分"""
        score = 1  # 基础分
        
        # 影线越长越高分
        if shadow_ratio >= 5: score += 1  # 5倍以上影线
        if shadow_ratio >= 3: score += 1  # 3倍以上
        if body <= rng * 0.15: score += 1  # 超级小实体
        
        # 对侧影线极短加分
        if shadow_opp < body * 0.1: score += 1  # 几乎没有对侧影线
        
        # 收盘位置加分
        if ptype == "bullish" and cpr >= 0.85: score += 1
        if ptype == "bearish" and cpr <= 0.15: score += 1
        
        strength = "strong" if score >= 5 else ("moderate" if score >= 3 else "weak")
        vol = float(r['Volume'])
        
        return {
            "type": ptype,
            "idx": r.name,
            "price": round(float(r['Close']), 2),
            "high": round(float(r['High']), 2),
            "low": round(float(r['Low']), 2),
            "body": round(body, 2),
            "shadow_main": round(shadow_main, 2),
            "shadow_ratio": round(shadow_ratio, 1),
            "volume": int(vol),
            "score": score,
            "strength": strength
        }
    
    @staticmethod
    def validate_context(pin, trend_state, fib_levels, df):
        """
        验证Pin Bar的交易背景
        
        返回:
        {
            "valid": True/False,
            "confluences": [...],
            "reasons": [...]
        }
        """
        result = {"valid": False, "confluences": [], "blockers": []}
        price = pin['price']
        
        # 1. 趋势匹配
        if pin['type'] == 'bullish':
            if trend_state == 'BULLISH':
                result['confluences'].append("✅ 顺势Pin Bar (多头趋势中的看涨Pin)")
            elif trend_state == 'RANGE':
                result['confluences'].append("⚡ 震荡区Pin Bar (需额外确认)")
            else:
                result['blockers'].append("❌ 逆势Pin Bar (空头趋势不做多)")
        else:
            if trend_state == 'BEARISH':
                result['confluences'].append("✅ 顺势Pin Bar (空头趋势中的看跌Pin)")
            elif trend_state == 'RANGE':
                result['confluences'].append("⚡ 震荡区Pin Bar (需额外确认)")
            else:
                result['blockers'].append("❌ 逆势Pin Bar (多头趋势不做空)")
        
        # 2. 关键位共振
        if fib_levels and isinstance(fib_levels, dict):
            zone_low = fib_levels.get('zone_low', 0)
            zone_high = fib_levels.get('zone_high', 0)
            entry_618 = fib_levels.get('entry_618', 0)
            
            if zone_low and zone_high and zone_low <= price <= zone_high:
                result['confluences'].append(f"🎯 Fib OTE 共振 (${zone_low:.2f}~${zone_high:.2f})")
            elif entry_618 and abs(price - entry_618) / price < 0.005:
                result['confluences'].append(f"🎯 Fib 0.618 精确命中")
        
        # 3. 成交量验证
        if 'Volume' in df.columns and len(df) > 1:
            avg_vol = float(df['Volume'].tail(10).mean())
            if pin['volume'] > avg_vol * 1.5:
                result['confluences'].append(f"💥 放量确认 (x{int(pin['volume']/avg_vol)})")
        
        # 4. 评分过滤
        if pin['score'] >= 4:
            result['confluences'].append(f"⭐ 高质量Pin (评分{pin['score']}/5)")
        elif pin['score'] <= 2:
            result['blockers'].append(f"⚠️ 低质量Pin (评分{pin['score']}/5)")
        
        result['valid'] = len(result['confluences']) >= 2 and len(result['blockers']) == 0
        return result
    
    @staticmethod
    def trade_plan(pin, context, sl_buffer=0.05):
        """
        输出Pin Bar交易计划
        
        做多:
          - 入场: Pin Bar收盘价 或 下一根开盘
          - 止损: Pin Bar最低点下方 (buffer%)
          - 止盈: 前高 / 1:2 / 2×影线长度
        做空: 反向
        """
        price = pin['price']
        high = pin['high']
        low = pin['low']
        body = pin['body']
        shadow = pin['shadow_main']
        
        if pin['type'] == 'bullish':
            entry = price
            sl = low - (high - low) * sl_buffer  # 最低点下方留缓冲
            # 止盈目标1: 1倍影线长度
            tp1 = price + shadow * 2
            # 止盈目标2: 前高
            tp2 = price + shadow * 3
        else:
            entry = price
            sl = high + (high - low) * sl_buffer
            tp1 = price - shadow * 2
            tp2 = price - shadow * 3
        
        rr1 = abs(tp1 - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0
        
        return {
            "direction": "🟢 做多 (LONG)" if pin['type'] == 'bullish' else "🔴 做空 (SHORT)",
            "pin_score": f"{pin['score']}/5 ({pin['strength']})",
            "entry": round(entry, 2),
            "sl": round(sl, 2),
            "tp1": round(tp1, 2),
            "tp2": round(tp2, 2),
            "rr": round(rr1, 2),
            "confluences": context.get('confluences', []),
            "valid": context['valid']
        }
    
    @staticmethod
    def print_plan(plan):
        """格式化输出Pin Bar交易计划"""
        print(f"\n{'─'*50}")
        print(f"  📌 Pin Bar 战法 — 交易计划")
        print(f"{'─'*50}")
        print(f"  {plan['direction']} | 评分: {plan['pin_score']} | {'✅ 有效' if plan['valid'] else '❌ 无效'}")
        print(f"\n  ├ 入场: ${plan['entry']}")
        print(f"  ├ 止损: ${plan['sl']}")
        print(f"  ├ T1:   ${plan['tp1']}")
        print(f"  ├ T2:   ${plan['tp2']}")
        print(f"  └ RR:   {plan['rr']}:1 {'✅' if plan['rr'] >= 1.5 else '❌'}")
        if plan['confluences']:
            print(f"\n  共振:")
            for c in plan['confluences']:
                print(f"    {c}")
