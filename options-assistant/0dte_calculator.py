#!/usr/bin/env python3
"""0DTE 末日期权计算器 — 用正股价格算期权入场/止损/止盈"""
import math

def estimate_0dte_premium(stock_price, strike, option_type, iv=0.30, minutes_to_close=90):
    """
    近似计算0DTE期权权利金（简化BS模型）
    iv: 隐含波动率（默认30%）
    minutes_to_close: 距收盘分钟数
    """
    # 时间转为年
    t = minutes_to_close / (365 * 24 * 60)
    if t <= 0:
        t = 0.001
    
    # 简化的内在价值 + 时间价值
    intrinsic = 0
    if option_type == "CALL":
        intrinsic = max(stock_price - strike, 0)
    else:
        intrinsic = max(strike - stock_price, 0)
    
    # ATM附近的时间价值估算
    moneyness = abs(stock_price - strike) / stock_price
    atm_factor = max(0, 1 - moneyness * 5)  # 越ATM时间价值越高
    time_value = stock_price * iv * math.sqrt(t) * atm_factor * 0.4
    
    premium = intrinsic + time_value
    return max(premium, 0.01)

def calculate_0dte_plan(stock_price, direction, fib_levels, minutes_to_close=120):
    """
    输出0DTE完整交易计划
    
    参数:
      stock_price: 正股当前价
      direction: "LONG" 或 "SHORT"
      fib_levels: {0.0: x, 0.382: x, ...}
      minutes_to_close: 距收盘分钟数
    
    返回:
      {
        "entry_stock": 正股进场位,
        "entry_premium": 预估权利金,
        "strike": 建议行权价,
        "sl_stock": 正股止损位,
        "sl_premium_pct": 权利金止损比例,
        "tp1_stock": 第一目标,
        "tp1_premium_pct": 权利金目标涨幅,
        "tp2_stock": 第二目标,
        "total_risk_usd": 单张最大亏损,
        "rr": 盈亏比
      }
    """
    iv_estimate = 0.35  # TSLA 0DTE IV通常30-40%
    mins_left = max(minutes_to_close, 15)  # 至少15分钟
    
    if direction == "LONG":
        entry_stock = fib_levels.get(0.618, stock_price * 0.995)
        strike = round(entry_stock / 0.5) * 0.5  # 就近行权价
        # 进场成本
        premium = estimate_0dte_premium(stock_price, strike, "CALL", iv_estimate, mins_left)
        
        # 正股止损: Fib 0.786下方
        sl_stock = fib_levels.get(0.786, entry_stock * 0.995)
        # 到止损时期权大概值（重置为ATM衰减计算）
        sl_premium = estimate_0dte_premium(sl_stock, strike, "CALL", iv_estimate, max(mins_left - 5, 5))
        premium_loss = premium - sl_premium
        sl_pct = (premium_loss / premium * 100) if premium > 0 else 30
        
        # 止盈：Fib 0.0
        tp1_stock = fib_levels.get(0.0, entry_stock * 1.01)
        tp1_premium = estimate_0dte_premium(tp1_stock, strike, "CALL", iv_estimate, max(mins_left - 10, 5))
        tp1_pct = (tp1_premium - premium) / premium * 100 if premium > 0 else 0
        
        # T2：突破0.0后看延伸
        tp2_stock = tp1_stock + (tp1_stock - entry_stock) * 0.5
        
        rr = abs(tp1_premium - premium) / abs(premium - sl_premium) if abs(premium - sl_premium) > 0 else 0
        
    else:  # SHORT
        entry_stock = fib_levels.get(0.618, stock_price * 1.005)
        strike = round(entry_stock / 0.5) * 0.5
        premium = estimate_0dte_premium(stock_price, strike, "PUT", iv_estimate, mins_left)
        
        sl_stock = fib_levels.get(0.786, entry_stock * 1.005)
        sl_premium = estimate_0dte_premium(sl_stock, strike, "PUT", iv_estimate, max(mins_left - 5, 5))
        premium_loss = premium - sl_premium
        sl_pct = (premium_loss / premium * 100) if premium > 0 else 30
        
        tp1_stock = fib_levels.get(0.0, entry_stock * 0.99)
        tp1_premium = estimate_0dte_premium(tp1_stock, strike, "PUT", iv_estimate, max(mins_left - 10, 5))
        tp1_pct = (tp1_premium - premium) / premium * 100 if premium > 0 else 0
        
        tp2_stock = tp1_stock - (entry_stock - tp1_stock) * 0.5
        rr = abs(tp1_premium - premium) / abs(premium - sl_premium) if abs(premium - sl_premium) > 0 else 0
    
    premium = max(premium, 0.01)
    sl_pct = min(max(sl_pct, 10), 80)  # 止损 10-80%
    tp1_pct = max(tp1_pct, 5)
    
    return {
        "direction": "🟢做多(CALL)" if direction == "LONG" else "🔴做空(PUT)",
        "entry_stock": round(entry_stock, 2),
        "strike": round(strike, 1),
        "est_premium": round(premium, 2),
        "sl_stock": round(sl_stock, 2),
        "sl_premium_pct": round(sl_pct),
        "tp1_stock": round(tp1_stock, 2),
        "tp1_return": f"+{round(tp1_pct)}%",
        "tp2_stock": round(tp2_stock, 2),
        "single_risk": round(premium * (sl_pct / 100), 2),
        "rr": round(rr, 2)
    }

def print_plan(plan):
    """格式化输出交易计划"""
    print(f"\n{'─' * 55}")
    print(f"  📋 0DTE 末日期权交易计划")
    print(f"{'─' * 55}")
    print(f"  {plan['direction']}")
    print(f"  建议行权价: ${plan['strike']}")
    print(f"  预估权利金: ${plan['est_premium']}/张")
    print(f"\n  ├ 入场: 正股 ${plan['entry_stock']} (期权≈${plan['est_premium']})")
    print(f"  ├ 止损: 正股 ${plan['sl_stock']} (权利金亏损{plan['sl_premium_pct']}%)")
    print(f"  ├ T1:   ${plan['tp1_stock']} ({plan['tp1_return']})")
    print(f"  ├ T2:   ${plan['tp2_stock']}")
    print(f"  ├ 单张风险: ${plan['single_risk']}")
    print(f"  └ 盈亏比: {plan['rr']}:1 {'✅达标' if plan['rr'] >= 1.5 else '❌不达标'}")
    print(f"{'─' * 55}")
    print(f"  ⏰ 距收盘预估时间 | Theta加速衰减中")
    print(f"  ⚠️ 建议最晚 15:30 ET 前平仓")

if __name__ == "__main__":
    import sys
    price = float(sys.argv[1]) if len(sys.argv) > 1 else 419.02
    direction = sys.argv[2] if len(sys.argv) > 2 else "LONG"
    
    fib = {0.0: 419.65, 0.382: 418.26, 0.5: 417.82, 0.618: 417.39, 0.786: 416.78, 1.0: 416.00}
    
    plan = calculate_0dte_plan(price, direction, fib, minutes_to_close=90)
    print_plan(plan)
