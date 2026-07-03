#!/usr/bin/env python3
"""
0DTE 风控管家 — $1000本金版
规则：单笔不超30%余额 · 日亏$150停手 · 连亏3次强制休息
"""
import json, os, sys
from datetime import datetime, timezone

PF = os.path.join(os.path.dirname(__file__), '..', 'trading-journal', 'positions.json')

def load():
    try:
        with open(PF) as f: return json.load(f)
    except:
        return {"account": {"balance": 1000, "daily_loss_limit": 150, "max_contracts_per_trade": 5, "max_daily_trades": 3, "max_consecutive_losses": 3},
                "session": {"date": "", "trades_today": 0, "pnl_today": 0, "consecutive_losses": 0},
                "positions": [], "history": []}

def save(d):
    with open(PF, 'w') as f: json.dump(d, f, indent=2, default=str)

def check_trade(ticker, direction, contracts, premium, acct_bal=None):
    d = load(); today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    a = d['account']; s = d['session']
    if s['date'] != today:
        s.update({"date":today, "trades_today":0, "pnl_today":0, "consecutive_losses":0})
    
    bal = acct_bal or a['balance']
    cost = contracts * premium * 100
    warnings = []
    blocked = False
    
    if bal <= 0: return False, ["余额为0, 无法交易"]
    if cost > bal: return False, [f"成本${cost:.0f} > 余额${bal:.0f}, 钱不够"]
    if cost > bal * 0.3:
        warnings.append(f"单笔${cost:.0f}超余额30%(${bal*0.3:.0f})")
        blocked = True
    if s['trades_today'] >= a['max_daily_trades']:
        return False, [f"今日已交易{s['trades_today']}次, 已满"]
    if s['pnl_today'] <= -a['daily_loss_limit']:
        return False, [f"今日亏损${abs(s['pnl_today']):.0f}已达限额${a['daily_loss_limit']}, 休息"]
    if s['consecutive_losses'] >= a['max_consecutive_losses']:
        return False, [f"连续亏损{s['consecutive_losses']}次, 强制休息"]
    
    return not blocked, warnings

def print_check(ticker, direction, contracts, premium, acct_bal=None):
    passed, warns = check_trade(ticker, direction, contracts, premium, acct_bal)
    bal = acct_bal or load()['account']['balance']
    cost = contracts * premium * 100
    
    print(f"\n{'='*50}")
    if passed:
        print(f"  PASS — 可交易")
    else:
        print(f"  BLOCKED — 不能做!")
    for w in warns: print(f"  ! {w}")
    print(f"  {ticker} {direction} x{contracts} @ ${premium} = ${cost:.0f}")
    if bal > 0 and cost > 0: print(f"  占余额: {cost/bal*100:.1f}%")
    return passed

def record_trade(ticker, direction, contracts, premium, entry_price, exit_price=None):
    d = load(); today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    s = d['session']
    if s['date'] != today:
        s.update({"date":today,"trades_today":0,"pnl_today":0,"consecutive_losses":0})
    
    trade = {"ticker":ticker,"direction":direction,"contracts":contracts,"premium":premium,
             "entry_price":entry_price,"entry_time":datetime.now(timezone.utc).isoformat(),"status":"OPEN"}
    
    if exit_price is not None:
        pnl = (exit_price - entry_price) * contracts * 100
        if direction == 'SHORT': pnl = -pnl
        trade.update({"exit_price":exit_price,"pnl":round(pnl,2),"status":"CLOSED"})
        s['trades_today'] += 1
        s['pnl_today'] = round(s['pnl_today'] + pnl, 2)
        s['consecutive_losses'] = s['consecutive_losses'] + 1 if pnl < 0 else 0
    
    d['positions'].append(trade)
    d['session'] = s
    save(d)
    return trade

def status():
    d = load(); a = d['account']; s = d['session']
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if s['date'] != today: s = {"trades_today":0,"pnl_today":0,"consecutive_losses":0}
    
    rem = a['daily_loss_limit'] + min(s['pnl_today'], 0)
    
    print(f"\n{'='*50}")
    print(f"  0DTE 风控仪表盘 — ${a['balance']:,}")
    print(f"{'='*50}")
    if s['trades_today'] > 0:
        print(f"  今日: {s['trades_today']}笔 | P&L ${s['pnl_today']:+.0f}")
        if s['consecutive_losses'] >= 2:
            print(f"  连亏 {s['consecutive_losses']}次 !!")
    else:
        print(f"  今日暂无交易")
    print(f"  日亏限额: ${a['daily_loss_limit']} | 剩余: ${rem:.0f}")
    if rem <= a['daily_loss_limit'] * 0.3:
        print(f"  !!! 额度快没了, 悠着点!")
    print(f"{'='*50}")

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0]=='status': status()
    elif a[0]=='check' and len(a)>=4:
        print_check(a[1].upper(),a[2].upper(),int(a[3]),float(a[4]),float(a[5]) if len(a)>=6 else None)
    elif a[0]=='record' and len(a)>=5:
        record_trade(a[1].upper(),a[2].upper(),int(a[3]),float(a[4]),float(a[5]),float(a[6]) if len(a)>=7 else None)
        print("Recorded")
