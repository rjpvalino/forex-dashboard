from backtest.engine import BacktestEngine
e = BacktestEngine()
r = e.run_demo()
total_t = sum(x["total_trades"] for x in r)
total_w = sum(x["wins"] for x in r)
overall_wr = round(total_w / total_t * 100, 1) if total_t else 0
print("EMA Pullback Trend Rider Results")
print("Overall win rate:", overall_wr, "pct  (" + str(total_w) + "W / " + str(total_t - total_w) + "L)")
print()
for x in r:
    pf = x["profit_factor"]
    pf_str = str(pf) if pf < 999 else "inf"
    line = (x["instrument"] + " | trades:" + str(x["total_trades"]) +
            " | WR:" + str(x["win_rate"]) + "%" +
            " | PF:" + pf_str +
            " | return:" + str(x["total_return"]) + "%" +
            " | maxDD:" + str(x["max_drawdown"]) + "%" +
            " | exp:$" + str(x["expectancy"]))
    print(line)
