#!/usr/bin/env python3
"""
盘面分析标准工作流 (三步流线型)
当你收到 "分析XXX" → 严格按照此流程执行
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import sys
sys.path.insert(0, '/home/codespace/.openclaw/workspace/options-assistant')

from hss_fib_scanner import (
    extract_candle_features, add_indicators, calc_hss_ha,
    MarketStructureMachine, PriceAction,
    calc_swing, calc_fib, ema_diag,
    EMA_CONFIG, FIB_LEVELS
)

def analyze_pa_phase(ticker):
    """步骤一：裸K状态确定 (3分钟/5分钟) + Pin Bar战法"""
    print("=" * 65)
    print("📊 Step 1 — 裸K状态确定 (Phase)")
    print("=" * 65)
    
    results = {}
    
    # 导入Pin Bar战法
    import sys
    sys.path.insert(0, '/home/codespace/.openclaw/workspace/options-assistant')
    from pinbar_strategy import PinBarStrategy
    
    for tf_name, period, interval in [("3分钟", "3d", "5m"), ("5分钟", "5d", "5m")]:
        try:
            data = yf.download(ticker, period=period, interval=interval, progress=False)
            if data.empty:
                continue
            data.columns = [c[0] if isinstance(c, tuple) else c for c in data.columns]
            data = extract_candle_features(data)
            data = add_indicators(data)
            
            last = data.iloc[-1]
            price = float(last['Close'])
            
            # 市场结构
            msm = MarketStructureMachine(data)
            ms = msm.get_state()
            trend_state = ms["state"]
            
            trend_icons = {"BULLISH": "🟢 多头趋势 (BULLISH)", "BEARISH": "🔴 空头趋势 (BEARISH)", "RANGE": "🟡 震荡横盘 (RANGE)"}
            print(f"\n  [{tf_name}] {trend_icons.get(trend_state, '未知')}")
            
            if ms['swing_highs']:
                print(f"    波峰: {ms['swing_highs'][-3:]}")
            if ms['swing_lows']:
                print(f"    波谷: {ms['swing_lows'][-3:]}")
            if ms.get("bos"):
                print(f"    {ms['bos']}")
            if ms.get("choch"):
                print(f"    {ms['choch']}")
            
            # 裸K形态识别
            pinbars = PriceAction.detect_pinbars(data, 10)
            engulfing = PriceAction.detect_engulfing(data, 10)
            
            # ── Pin Bar 战法升级 ──
            from pinbar_strategy import PinBarStrategy
            pbs_detected = PinBarStrategy.detect(data, 20)
            best_pin = None
            for pb in pbs_detected:
                # 找最近评分最高的Pin Bar
                if pb['score'] >= 3:
                    if best_pin is None or pb['score'] > best_pin['score']:
                        best_pin = pb
            
            patterns_found = []
            for pb in pinbars['bullish'][-1:]:
                patterns_found.append(f"🟢 看涨PinBar @ ${pb['price']:.2f}")
            for pb in pinbars['bearish'][-1:]:
                patterns_found.append(f"🔴 看跌PinBar @ ${pb['price']:.2f}")
            for eg in engulfing['bullish'][-1:]:
                patterns_found.append(f"🟢 看涨吞没 @ ${eg['price']:.2f}")
            for eg in engulfing['bearish'][-1:]:
                patterns_found.append(f"🔴 看跌吞没 @ ${eg['price']:.2f}")
            
            # FVG
            nf, _ = PriceAction.detect_fvg(data, 15)
            if nf:
                dir_sym = "🟢" if nf['type'] == 'bullish' else '🔴'
                patterns_found.append(f"{dir_sym} FVG缺口: ${nf['bottom']:.2f}~${nf['top']:.2f}")
            
            # 动量
            momentum = PriceAction.detect_momentum_state(data)
            
            print(f"    当前价: ${price:.2f}")
            print(f"    动量: {momentum}")
            
            # ── Pin Bar 战法评分输出 ──
            if best_pin:
                print(f"    📌 Pin Bar 战法评分: {best_pin['score']}/5 ({best_pin['strength']})")
                print(f"       影线={best_pin['shadow_main']:.2f} (x{best_pin['shadow_ratio']}实体) | 成交量={best_pin['volume']:,}")
                trend_state_label = ms.get('state', 'RANGE')
                from hss_fib_scanner import calc_swing
                fib_swing = calc_swing(data.tail(24))
                import sys; import importlib
                hss = importlib.import_module('hss_fib_scanner')
                if fib_swing:
                    fake_fib = {'zone_low': 0, 'zone_high': 0, 'entry_618': 0}
                    ctx = PinBarStrategy.validate_context(best_pin, trend_state_label, fake_fib, data)
                else:
                    ctx = PinBarStrategy.validate_context(best_pin, trend_state_label, {}, data)
                
                if ctx['confluences']:
                    for c in ctx['confluences'][:2]:
                        print(f"       {c}")
                if ctx['blockers']:
                    for b in ctx['blockers'][:2]:
                        print(f"       {b}")
                
                if ctx['valid']:
                    plan = PinBarStrategy.trade_plan(best_pin, ctx)
                    PinBarStrategy.print_plan(plan)
            if patterns_found:
                print(f"    形态:")
                for p in patterns_found[-3:]:
                    print(f"      {p}")
            else:
                print(f"    形态: ➡️ 无显著裸K形态")
            
            results[tf_name] = {
                "state": trend_state,
                "price": price,
                "patterns": patterns_found,
                "momentum": momentum,
                "ms": ms
            }
            
        except Exception as e:
            print(f"  [{tf_name}] ❌ {e}")
    
    return results

def analyze_strategy_phase(ticker, pa_results):
    """步骤二：策略技能扫描 (共振验证)"""
    print(f"\n{'=' * 65}")
    print("📊 Step 2 — 策略共振验证 (Strategy)")
    print("=" * 65)
    
    try:
        # 用5分钟K线做基准
        data = yf.download(ticker, period="3d", interval="5m", progress=False)
        if data.empty:
            print("  ⚠️ 无数据")
            return None
        data.columns = [c[0] if isinstance(c, tuple) else c for c in data.columns]
        data = extract_candle_features(data)
        data = add_indicators(data)
        
        last = data.iloc[-1]
        price = float(last['Close'])
        
        # ─── 100EMA ───
        ema100 = float(last['EMA100']) if 'EMA100' in last else price
        near_ema100 = abs(price - ema100) / price < 0.003
        
        # ─── VWAP ───
        vwap = float(last['VWAP']) if 'VWAP' in data.columns else price
        near_vwap = abs(price - vwap) / price < 0.003
        
        # ─── 斐波那契 ───
        swing_df = data.tail(24)  # 24根5分K = 2小时波段
        sd, sp, ep = calc_swing(swing_df)
        fib = calc_fib(sd, sp, ep)
        in_zone = fib['zone_low'] <= price <= fib['zone_high']
        
        # 共振汇总
        confluences = []
        if near_ema100: confluences.append(f"100EMA @ ${ema100:.2f}")
        if near_vwap: confluences.append(f"VWAP @ ${vwap:.2f}")
        if in_zone: confluences.append(f"FIB 0.5-0.618 (${fib['zone_low']:.2f}~${fib['zone_high']:.2f})")
        
        dir_icon = "📈" if sd == "UP" else "📉"
        print(f"\n  波段: {dir_icon} ${sp:.2f} → ${ep:.2f}")
        for lvl in [0.0, 0.382, 0.5, 0.618, 0.786, 1.0]:
            m = " ◀" if abs(price - fib[lvl]) / price < 0.002 else (" ★ OTE" if lvl == 0.618 else "")
            print(f"  {lvl:<5}: ${fib[lvl]:.2f}{m}")
        
        print(f"\n  EMA100: ${ema100:.2f} {'✅' if near_ema100 else '❌'}")
        print(f"  VWAP:   ${vwap:.2f} {'✅' if near_vwap else '❌'}")
        print(f"  FIB:    {'✅ 命中 0.5-0.618' if in_zone else '❌ 未到'}")
        
        if confluences:
            print(f"\n  🎯 共振位: {' | '.join(confluences)}")
            print(f"  ✅ {len(confluences)}/3 共振 → 有效")
        else:
            print(f"\n  ⚠️ 无共振 → 价格未触及关键位")
        
        return {
            "price": price,
            "ema100": ema100,
            "vwap": vwap,
            "fib": fib,
            "confluences": confluences,
            "in_zone": in_zone
        }
        
    except Exception as e:
        print(f"  ❌ {e}")
        return None

def analyze_options_phase(ticker, pa_results, strategy_results):
    """步骤三：期权异动 + 交易计划"""
    print(f"\n{'=' * 65}")
    print("📊 Step 3 — 期权异动 + 交易计划")
    print("=" * 65)
    
    try:
        tk = yf.Ticker(ticker)
        exp = tk.options
        
        if not exp:
            print("  ⚠️ 无期权数据")
            return
        
        today = datetime.now().strftime('%Y-%m-%d')
        near_exp = [e for e in exp if e >= today][:2] if [e for e in exp if e >= today] else exp[:2]
        
        total_call_vol, total_put_vol = 0, 0
        all_unusual = []
        
        for e in near_exp:
            dte = (datetime.strptime(e, '%Y-%m-%d') - datetime.now()).days
            chain = tk.option_chain(e)
            calls, puts = chain.calls, chain.puts
            
            cv = calls['volume'].sum()
            pv = puts['volume'].sum()
            total_call_vol += cv
            total_put_vol += pv
            
            # 异动检测
            calls['v_oi'] = calls['volume'] / calls['openInterest'].replace(0, np.nan)
            puts['v_oi'] = puts['volume'] / puts['openInterest'].replace(0, np.nan)
            
            for _, r in calls[calls['v_oi'] > 0.5].nlargest(3, 'volume').iterrows():
                all_unusual.append(("CALL", e, r['strike'], r['volume'], r['openInterest'], r['impliedVolatility']))
            for _, r in puts[puts['v_oi'] > 0.5].nlargest(3, 'volume').iterrows():
                all_unusual.append(("PUT", e, r['strike'], r['volume'], r['openInterest'], r['impliedVolatility']))
        
        cp_ratio = total_call_vol / total_put_vol if total_put_vol > 0 else float('inf')
        cp_dir = "偏多📈" if cp_ratio > 1.3 else ("偏空📉" if cp_ratio < 0.7 else "中性➡️")
        
        print(f"\n  Call/Put Vol = {cp_ratio:.2f} ({cp_dir})")
        print(f"  Call总成交量: {total_call_vol:,.0f} | Put总成交量: {total_put_vol:,.0f}")
        
        if all_unusual:
            print(f"\n  ⚠️ 潜在异动:")
            for u in all_unusual[:5]:
                sym = "🟢" if u[0] == "CALL" else "🔴"
                print(f"    {sym} {u[0]} ${u[2]:.0f} exp={u[1]} vol={u[3]:,.0f} OI={u[4]:,.0f} IV={u[5]:.2f}")
        else:
            print(f"  ➡️ 无显著期权异动")
        
        # ─── 输出交易计划 ───
        print(f"\n{'─' * 65}")
        print("📋 交易参考计划")
        print(f"{'─' * 65}")
        
        if strategy_results:
            price = strategy_results['price']
            confluences = strategy_results['confluences']
            fib = strategy_results['fib']
            
            # 判断方向
            direction = "NONE"
            for tf, r in pa_results.items():
                if r['state'] == 'BULLISH':
                    direction = "LONG"
                elif r['state'] == 'BEARISH':
                    direction = "SHORT"
                break  # 取第一时间框架
            
            # 如果有共振+期权方向一致
            options_bullish = cp_ratio > 1.2
            options_bearish = cp_ratio < 0.8
            has_confluence = len(confluences) >= 2
            
            if direction == "LONG" and has_confluence and options_bullish:
                sl = min(fib.get(0.786, price * 0.99), fib.get(1.0, price * 0.98))
                tp1 = fib.get(0.0, price * 1.01)
                tp2 = fib.get(0.0, price * 1.015)
                rr = abs(tp1 - price) / abs(price - sl) if abs(price - sl) > 0 else 0
                
                print(f"\n  🟢🟢 参考方向: 做多 (LONG)")
                print(f"  共振: {' | '.join(confluences)} | 期权: {cp_dir}")
                print(f"  ├ 入场时机: 等待当前K线收盘确认，下一根开盘进场")
                print(f"  │ 或回踩 ${fib.get(0.618, 0):.2f}(Fib 0.618) + 吞没信号确认")
                print(f"  ├ 严格止损: ${sl:.2f} (设在Fib 0.786下方)")
                print(f"  ├ 第一目标: ${tp1:.2f}")
                print(f"  └ 第二目标: ${tp2:.2f}")
                print(f"  ⚖️ 盈亏比: {rr:.1f}:1 {'✅达标' if rr >= 1.5 else '❌不达标'}")
                
            elif direction == "SHORT" and has_confluence and options_bearish:
                sl = max(fib.get(0.786, price * 1.01), fib.get(1.0, price * 1.02))
                tp1 = fib.get(0.0, price * 0.99)
                tp2 = fib.get(0.0, price * 0.985)
                rr = abs(price - tp1) / abs(sl - price) if abs(sl - price) > 0 else 0
                
                print(f"\n  🔴🔴 参考方向: 做空 (SHORT)")
                print(f"  共振: {' | '.join(confluences)} | 期权: {cp_dir}")
                print(f"  ├ 入场时机: 等待当前K线收盘确认，下一根开盘进场")
                print(f"  │ 或反弹至 ${fib.get(0.618, 0):.2f}(Fib 0.618) + PinBar确认")
                print(f"  ├ 严格止损: ${sl:.2f} (设在Fib 0.786上方)")
                print(f"  ├ 第一目标: ${tp1:.2f}")
                print(f"  └ 第二目标: ${tp2:.2f}")
                print(f"  ⚖️ 盈亏比: {rr:.1f}:1 {'✅达标' if rr >= 1.5 else '❌不达标'}")
                
            elif direction == "NONE" or (direction == "LONG" and options_bearish) or (direction == "SHORT" and options_bullish):
                print(f"\n  ⚠️ 技术面与期权信号冲突 (方向不明确)")
                print(f"  趋势: {direction} | 期权CPR: {cp_ratio:.2f}")
                print(f"  ➡️ 建议观望，等待方向明朗")
            
            else:
                print(f"\n  ⏸️ 等待条件成熟")
                print(f"  趋势: {direction} | 共振: {len(confluences)}/3 | 期权CPR: {cp_ratio:.2f}")
                print(f"  ➡️ 建议观望")
        else:
            print(f"\n  ⏸️ 数据不足，无法输出交易计划")
        
        print(f"\n{'=' * 65}")
        print("⚠️ 以上为技术分析参考，不构成投资建议。")
        print("   最终决策和下单由您本人手动执行。")
        
    except Exception as e:
        print(f"  ❌ 期权分析错误: {e}")

def full_workflow(ticker):
    """三步流线型盘面分析"""
    ticker = ticker.upper().strip()
    now = datetime.now(timezone.utc)
    et = f"美东 {(now.hour-4)%24:02d}:{now.minute:02d}"
    
    print(f"\n{'#' * 65}")
    print(f"# {ticker} 盘面分析 @ {now.strftime('%H:%M')} UTC | {et}")
    print(f"{'#' * 65}")
    
    # Step 0 — 宏观偏见（趋势解构四步法）
    print(f"\n{'='*65}")
    print("📊 Step 0 — 趋势解构 (宏观过滤器)")
    print("=" * 65)
    from hss_fib_scanner import macro_bias_analysis, print_macro_bias
    macro = macro_bias_analysis(ticker)
    if macro:
        print_macro_bias(macro, ticker)
        macro_bias = macro.get('bias', 'WAIT')
        if macro_bias == 'WAIT':
            print(f"\n  🚦 宏观过滤: 战略观望 → 放弃本次交易信号")
    else:
        macro_bias = 'WAIT'
    
    # ─── 关键位 + ATR + 多周期对齐 ───
    print(f"\n{'='*65}")
    print("📊 关键位 & 日内状态")
    print("=" * 65)
    try:
        d = yf.download(ticker, period='5d', interval='1d', progress=False)
        if not d.empty:
            d.columns = [c[0] if isinstance(c,tuple) else c for c in d.columns]
            # 昨日收盘 / 今日开盘
            prev_close = float(d['Close'].iloc[-2])
            today_open = float(d['Open'].iloc[-1])
            prev_high = float(d['High'].iloc[-2])
            prev_low = float(d['Low'].iloc[-2])
            prev_range = prev_high - prev_low
            
            # ATR(14)
            tr = pd.concat([d['High']-d['Low'], abs(d['High']-d['Close'].shift(1)), abs(d['Low']-d['Close'].shift(1))], axis=1).max(axis=1)
            atr14 = round(float(tr.tail(14).mean()), 2)
            
            # 今日日内数据
            intra = yf.download(ticker, period='1d', interval='5m', progress=False)
            if not intra.empty:
                intra.columns = [c[0] if isinstance(c,tuple) else c for c in intra.columns]
                today_high = float(intra['High'].max())
                today_low = float(intra['Low'].min())
                current = float(intra['Close'].iloc[-1])
                today_range = today_high - today_low
                range_pct = round(today_range / atr14 * 100, 0) if atr14 > 0 else 0
                
                # 多周期方向
                t1 = yf.download(ticker, period='2d', interval='1m', progress=False)
                if not t1.empty:
                    t1.columns = [c[0] if isinstance(c,tuple) else c for c in t1.columns]
                    from hss_fib_scanner import MarketStructureMachine, extract_candle_features
                    
                    # 1min方向
                    d1 = extract_candle_features(t1.tail(60).copy())
                    m1 = MarketStructureMachine(d1).get_state()
                    d1_state = m1['state']
                    
                    # 5min方向 - 复用pa结果
                    d5_state = list(pa.values())[0]['state'] if pa else 'RANGE'
                    
                    # 15min方向
                    t15 = yf.download(ticker, period='3d', interval='15m', progress=False)
                    if not t15.empty:
                        t15.columns = [c[0] if isinstance(c,tuple) else c for c in t15.columns]
                        d15 = extract_candle_features(t15.tail(60).copy())
                        m15 = MarketStructureMachine(d15).get_state()
                        d15_state = m15['state']
                    else:
                        d15_state = 'RANGE'
            
            state_icons = {'BULLISH':'🟢多头','BEARISH':'🔴空头','RANGE':'🟡震荡'}
            
            print(f"  昨日收盘: ${prev_close:.2f} | 今日开盘: ${today_open:.2f}")
            print(f"  前高: ${prev_high:.2f} | 前低: ${prev_low:.2f}")
            print(f"  ATR(14): {atr14:.2f} | 今日已走: {today_range:.2f} ({range_pct:.0f}%ATR)")
            
            # 多周期对齐
            print(f"  \n  📐 多周期方向对齐:")
            periods = [('1min', d1_state), ('5min', d5_state), ('15min', d15_state)]
            state_list = [s for _, s in periods]
            all_bull = all(s == 'BULLISH' for s in state_list)
            all_bear = all(s == 'BEARISH' for s in state_list)
            all_range = all(s == 'RANGE' for s in state_list)
            
            for name, state in periods:
                icon = state_icons.get(state, '⚪')
                print(f"    {name}: {icon}")
            
            if all_bull:
                align_msg = "✅ 全周期多头一致 → 趋势强劲，回调做多"
            elif all_bear:
                align_msg = "✅ 全周期空头一致 → 趋势强劲，反弹做空"
            elif all_range:
                align_msg = "⛔ 全周期震荡 → 不宜交易"
            else:
                align_msg = "⚠️ 周期方向不一致 → 小周期服从大周期"
            print(f"    {align_msg}")
            
    except Exception as e:
        print(f"   ⚠️ 数据加载错误: {e}")
    
    # Step 1
    pa = analyze_pa_phase(ticker)
    
    # Step 2
    strat = analyze_strategy_phase(ticker, pa)
    
    # Step 3
    analyze_options_phase(ticker, pa, strat)
    
    # ─── 总结：7问7答 ───
    print(f"\n{'#' * 65}")
    print("# 📋 交易决策总结")
    print(f"{'#' * 65}")
    
    # 提取关键信息
    trend_summary = "无法判断"
    market_action = "数据不足"
    entry_verdict = "⏸️ 观望"
    entry_reason = ""
    entry_zone = "无"
    sl_tp = "无"
    tp_strategy = "无"
    
    # 从pa结果提取趋势
    for tf, r in pa.items():
        ms = r.get('ms', {})
        trend_summary = ms.get('trend', '未知')
        bos_info = ms.get('bos', '')
        position = ms.get('position', '')
        momentum = r.get('momentum', '')
        
        # 多周期对齐描述
        try:
            align_phrases = []
            if 'd1_state' in dir():
                pass
            align_msg = locals().get('align_msg', '')
        except:
            align_msg = ''
        
        # 判断市场在干什么
        parts = []
        parts.append(position)
        if bos_info: parts.append(bos_info)
        parts.append(momentum)
        if align_msg: parts.append(align_msg.replace('✅ ','').replace('⛔ ','').replace('⚠️ ',''))
        market_action = ' | '.join(parts)
        break
    
    # 从macro判断入场
    if macro:
        mb = macro.get('bias', 'WAIT')
        if mb == 'WAIT':
            entry_verdict = '⛔ 不适合入场'
            entry_reason = '宏观战略观望（均线粘合/方向不明确），80%垃圾行情过滤'
        elif mb == 'BULLISH':
            entry_verdict = '🟢 适合入场（顺势做多）'
            entry_reason = 'MA多头排列 + MACD零轴上 + RSI偏多'
        elif mb == 'BEARISH':
            entry_verdict = '🔴 适合入场（顺势做空）'
            entry_reason = 'MA空头排列 + MACD零轴下 + RSI偏空'
    
    # 从strat取Fib入场位
    if strat:
        fib = strat.get('fib', {})
        price = strat.get('price', 0)
        entry_618 = fib.get('entry_618', 0)
        sl_786 = fib.get('sl_786', 0)
        tp_382 = fib.get('tp_382', 0)
        zone_low = fib.get('zone_low', 0)
        zone_high = fib.get('zone_high', 0)
        
        if entry_618 > 0:
            if entry_verdict.startswith('🟢'):
                entry_zone = f"回踩 Fib 0.5-0.618 (${zone_low:.2f}~${zone_high:.2f})，优先进场 ${entry_618:.2f}"
                sl_tp = f"止损: ${sl_786:.2f} (Fib 0.786下方) | T1: ${tp_382:.2f} (Fib 0.382) | T2: 突破前高"
                tp_strategy = "第一目标平半仓保本 → 第二目标飘到前高 → 移动止盈"
            elif entry_verdict.startswith('🔴'):
                entry_zone = f"反弹到 Fib 0.5-0.618 (${zone_low:.2f}~${zone_high:.2f})，优先挂空 ${entry_618:.2f}"
                sl_tp = f"止损: ${sl_786:.2f} (Fib 0.786上方) | T1: ${tp_382:.2f} (Fib 0.382) | T2: 跌破前低"
                tp_strategy = "第一目标减半仓 → 第二目标持有到结构位 → 移动止损"
    
    # 输出7问
    print(f"""
  📌 1. 现在属于什么趋势？
     {trend_summary}
  
  📌 2. 市场正在干什么？
     {market_action}
  
  📌 3. 适不适合入场？
     {entry_verdict}
  
  📌 4. 为什么？
     {entry_reason}
  
  📌 5. 在哪里入场？
     {entry_zone}
  
  📌 6. 止损止盈在哪？
     {sl_tp}
  
  📌 7. 止盈策略是什么？
     {tp_strategy}
""")
    
    # ── ⑧ 仓位建议 ──
    confidence = 0
    position_size = "不建议开仓"
    reasoning = ""
    
    if entry_verdict.startswith('⛔'):
        confidence = 1
        position_size = "⛔ 不建议开仓"
        reasoning = "宏观过滤未通过，不入场"
    elif entry_verdict.startswith('🟢'):
        # 计算信心分
        if macro: confidence += 1
        if strat and strat.get('confluences'): confidence += len(strat['confluences'])
        if pa:
            for r in pa.values():
                if r.get('state') == 'BULLISH': confidence += 1
                break
        if strat and strat.get('in_zone'): confidence += 1
        
        if confidence >= 4:
            position_size = "🟢🟢 正常仓位 (2%)"
            reasoning = "多信号共振 + 趋势一致，正常仓位进场"
        elif confidence >= 2:
            position_size = "🟡 轻仓试探 (0.5-1%)"
            reasoning = "有信号但共振不足，轻仓试探为主"
        else:
            position_size = "⛔ 观望"
            reasoning = "信号偏弱"
    elif entry_verdict.startswith('🔴'):
        if macro: confidence += 1
        if strat and strat.get('confluences'): confidence += len(strat['confluences'])
        if pa:
            for r in pa.values():
                if r.get('state') == 'BEARISH': confidence += 1
                break
        if strat and strat.get('in_zone'): confidence += 1
        
        if confidence >= 4:
            position_size = "🔴🔴 正常仓位 (2%)"
            reasoning = "空头信号共振，正常仓位进场"
        elif confidence >= 2:
            position_size = "🟡 轻仓试探 (0.5-1%)"
            reasoning = "有信号但共振不足"
        else:
            position_size = "⛔ 观望"
            reasoning = "信号偏弱"
    
    print(f"""
  📌 8. 仓位建议
     {position_size}
     信心指数: {'⭐' * min(confidence, 5)} ({confidence}/5)
     理由: {reasoning}
""")
    
    # ── ⑨ 人话解读 ──
    narrative = "数据不足，无法解读"
    
    # 检测经典剧本
    try:
        intra_today = yf.download(ticker, period='1d', interval='5m', progress=False)
        if not intra_today.empty:
            intra_today.columns = [c[0] if isinstance(c,tuple) else c for c in intra_today.columns]
            cur = float(intra_today['Close'].iloc[-1])
            day_high = float(intra_today['High'].max())
            day_low = float(intra_today['Low'].min())
            
            # 检测尾盘/盘中剧本
            now_et = (datetime.now(timezone.utc).hour - 4) % 24
            
            if strat and strat.get('fib', {}).get(0.0, 0) and cur > strat['fib'][0.0] * 0.995:
                narrative = "价格接近Fib 0.0前高阻力位，" 
                narrative += "如果在阻力位附近出现长上影/放量滞涨 → 可能是流动性扫荡后的派发"
                narrative += "如果在阻力位附近突破放量站稳 → 趋势延续"
            elif strat and strat.get('in_zone'):
                narrative = "价格在Fib OTE回调区间，"
                narrative += "关注是否出现Pin Bar/吞没形态确认支撑/阻力"
            elif '震荡' in trend_summary or 'RANGE' in trend_summary:
                narrative = "市场处于震荡格局，当前在区间内运行，"
                narrative += "上下沿分别是$%.2f和$%.2f，突破前高抛低吸或等待方向" % (day_high, day_low)
            elif '多头' in trend_summary:
                narrative = f"多头趋势中，当前价格在${cur:.2f}，"
                narrative += "关注回踩关键支撑位（EMA100/FIB OTE）的做多机会，"
                narrative += "避免逆势做空"
            elif '空头' in trend_summary:
                narrative = f"空头趋势中，当前价格在${cur:.2f}，"
                narrative += "关注反弹关键阻力位的做空机会，避免抄底"
            
            # 0DTE特别提醒
            if now_et >= 14:
                narrative += "\n   ⏰ 已过14:00 ET，Theta加速衰减，0DTE注意时间损耗"
            if now_et >= 15:
                narrative += "\n   🔔 进入Power Hour，Gamma爆炸，尾盘波动剧烈"
    except:
        pass
    
    print(f"  📌 9. 场内解读（人话版）")
    print(f"     {narrative}")
