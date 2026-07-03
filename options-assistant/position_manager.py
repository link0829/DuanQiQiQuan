#!/usr/bin/env python3
"""仓位管理系统 — 持仓追踪 + 风险计算 + 仓位建议"""
import json, os
from datetime import datetime, timezone

PF = os.path.join(os.path.dirname(__file__), '..', 'trading-journal', 'positions.json')

def load():
    try:
        with open(PF) as f: return json.load(f)
    except: return {"account": {"balance": 25000, "risk_per_trade": 0.02}, "positions": [], "history": []}

def save(data):
    with open(PF, 'w') as f: json.dump(data, f, indent=2, default=str)

def position_sizing(ticker, direction, entry, sl, tp=None, balance=25000, risk_pct=0.02):
    if tp is None: tp = entry + abs(entry - sl) * 1.5
    rr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0
    max_loss = balance * risk_pct
    risk_per_share = abs(entry - sl)
    shares = max(1, int(max_loss / risk_per_share))
    total_risk = shares * risk_per_share
    
    print(f"\n{'='*50}")
    print(f"  D5 仓位管理 — {ticker}")
    print(f"{'='*50}")
    print(f"  账户: ${balance:,} | 单笔风险: ${max_loss:,.0f} ({risk_pct*100:.0f}%)")
    print(f"  {'BUY' if direction=='LONG' else 'SELL'} {ticker} @ ${entry:.2f}")
    print(f"  SL: ${sl:.2f} | TP: ${tp:.2f} | RR: {rr:.1f}")
    print(f"  建议: {shares} 股 / 合约")
    print(f"  占用: ${shares*entry:,.0f} | 最大亏损: ${total_risk:,.0f} ({total_risk/balance*100:.1f}%)")
    if rr >= 1.5: print(f"  收益预期: ${shares*abs(tp-entry):,.0f} {'✅' if rr>=1.5 else '❌'}")
    print(f"{'='*50}")
    
    data = load()
    data['positions'].append({
        "ticker": ticker, "direction": direction,
        "entry": entry, "sl": sl, "tp": tp, "rr": round(rr, 2),
        "shares": shares, "entry_time": datetime.now(timezone.utc).isoformat(), "status": "OPEN"
    })
    data['account']['balance'] = balance
    save(data)

def show_positions():
    data = load(); ops = [p for p in data['positions'] if p['status'] == 'OPEN']
    if not ops: print("\nD5 当前无持仓"); return
    print(f"\nD5 持仓 ({len(ops)})")
    for p in ops:
        print(f"  {'L' if p['direction']=='LONG' else 'S'} {p['ticker']} @ ${p['entry']} SL${p['sl']} TP${p['tp']} RR{p['rr']}")

def close_position(ticker):
    data = load()
    for p in data['positions']:
        if p['ticker'] == ticker and p['status'] == 'OPEN':
            p['status'] = 'CLOSED'; p['exit_time'] = datetime.now(timezone.utc).isoformat()
            save(data); print(f"  {ticker} closed"); return
    print(f"  {ticker} not found")

if __name__ == "__main__":
    import sys; a = sys.argv[1:]
    if not a or a[0]=='show': show_positions()
    elif a[0]=='close' and len(a)>=2: close_position(a[1])
    elif len(a)>=4: position_sizing(a[0].upper(), a[1].upper(), float(a[2]), float(a[3]),
                     float(a[4]) if len(a)>=5 else None, float(a[5]) if len(a)>=6 else 25000)
