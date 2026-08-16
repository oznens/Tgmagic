from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://contract.mexc.com/api/v1/contract"
ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "signals.json"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "mexc-ote-scanner/1.0"})


def api(path: str, params=None):
    response = SESSION.get(f"{BASE}{path}", params=params, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(f"MEXC error: {payload}")
    return payload["data"]


def contracts():
    details = api("/detail")
    tickers = api("/ticker")
    volume = {x["symbol"]: float(x.get("amount24") or x.get("volume24") or 0) for x in tickers}
    allowed = []
    for item in details:
        symbol = item.get("symbol", "")
        if not symbol.endswith("_USDT"):
            continue
        if item.get("state") not in (None, 0):
            continue
        allowed.append((symbol, volume.get(symbol, 0)))
    allowed.sort(key=lambda x: x[1], reverse=True)
    minimum = float(CONFIG["min_volume24"])
    return [s for s, v in allowed if v >= minimum][: int(CONFIG["max_symbols"])]


def candles(symbol: str, interval: str, limit=220):
    now = int(time.time())
    seconds = {
        "Min5": 300, "Min15": 900, "Min30": 1800, "Min60": 3600,
        "Hour4": 14400, "Hour8": 28800, "Day1": 86400,
    }[interval]
    raw = api(f"/kline/{symbol}", {"interval": interval, "start": now - seconds * limit, "end": now})
    rows = []
    for values in zip(raw["time"], raw["open"], raw["high"], raw["low"], raw["close"], raw["vol"]):
        rows.append({"t": int(values[0]), "o": float(values[1]), "h": float(values[2]),
                     "l": float(values[3]), "c": float(values[4]), "v": float(values[5])})
    return rows


def pivots(rows, left: int, right: int):
    highs, lows = [], []
    for i in range(left, len(rows) - right):
        window = rows[i-left:i+right+1]
        if rows[i]["h"] == max(x["h"] for x in window):
            highs.append(i)
        if rows[i]["l"] == min(x["l"] for x in window):
            lows.append(i)
    return highs, lows


def structure(rows):
    left, right = int(CONFIG["pivot_left"]), int(CONFIG["pivot_right"])
    highs, lows = pivots(rows, left, right)
    if len(highs) < 2 or len(lows) < 2:
        return None
    close = rows[-2]["c"]  # only completed candles
    last_high, previous_high = highs[-1], highs[-2]
    last_low, previous_low = lows[-1], lows[-2]

    bullish_structure = rows[last_high]["h"] > rows[previous_high]["h"] and rows[last_low]["l"] >= rows[previous_low]["l"]
    bearish_structure = rows[last_low]["l"] < rows[previous_low]["l"] and rows[last_high]["h"] <= rows[previous_high]["h"]

    if close > rows[last_high]["h"] or bullish_structure:
        direction = "LONG"
        low_candidates = [i for i in lows if i < last_high]
        if not low_candidates:
            return None
        lo_i, hi_i = low_candidates[-1], last_high
    elif close < rows[last_low]["l"] or bearish_structure:
        direction = "SHORT"
        high_candidates = [i for i in highs if i < last_low]
        if not high_candidates:
            return None
        hi_i, lo_i = high_candidates[-1], last_low
    else:
        return None

    high, low = rows[hi_i]["h"], rows[lo_i]["l"]
    if not high > low:
        return None
    return {"direction": direction, "high": high, "low": low, "close": close,
            "range_start": min(rows[hi_i]["t"], rows[lo_i]["t"])}


def bias(symbol, interval):
    result = structure(candles(symbol, interval, 180))
    return result["direction"] if result else "NEUTRAL"


def setup(symbol):
    interval = CONFIG["interval"]
    rows = candles(symbol, interval)
    main = structure(rows)
    if not main:
        return None

    votes = [main["direction"]]
    mtf = {}
    for tf in CONFIG["confirmation_intervals"]:
        try:
            mtf[tf] = bias(symbol, tf)
        except Exception:
            mtf[tf] = "ERROR"
        votes.append(mtf[tf])

    direction = main["direction"]
    aligned = sum(v == direction for v in votes)
    if aligned < 2:
        return None

    high, low = main["high"], main["low"]
    width = high - low
    if direction == "LONG":
        ote_a, ote_b = high - width * .70, high - width * .79
        entry = (ote_a + ote_b) / 2
        stop, target = low, high
        distance = max(0.0, main["close"] - max(ote_a, ote_b))
    else:
        ote_a, ote_b = low + width * .70, low + width * .79
        entry = (ote_a + ote_b) / 2
        stop, target = high, low
        distance = max(0.0, min(ote_a, ote_b) - main["close"])

    if distance / width > float(CONFIG["scan_near_ote_percent"]):
        return None

    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk <= 0 or not math.isfinite(reward / risk):
        return None

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "id": f"{symbol}:{interval}:{direction}:{main['range_start']}",
        "created_at": stamp,
        "symbol": symbol,
        "interval": interval,
        "direction": direction,
        "status": "PENDING",
        "entry": entry,
        "ote_low": min(ote_a, ote_b),
        "ote_high": max(ote_a, ote_b),
        "stop": stop,
        "target": target,
        "rr": round(reward / risk, 2),
        "last_price": main["close"],
        "bias": {interval: direction, **mtf},
    }


def telegram(signal):
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    arrow = "🟢 LONG" if signal["direction"] == "LONG" else "🔴 SHORT"
    text = (
        f"<b>MEXC OTE Sinyali</b>\n{arrow} · <b>{signal['symbol']}</b> · {signal['interval']}\n\n"
        f"Giriş bölgesi: <code>{signal['ote_low']:.10g} – {signal['ote_high']:.10g}</code>\n"
        f"Stop: <code>{signal['stop']:.10g}</code>\nHedef: <code>{signal['target']:.10g}</code>\n"
        f"Tahmini R/R: <b>{signal['rr']}R</b>\n\n"
        f"Yönler: <code>{json.dumps(signal['bias'], ensure_ascii=False)}</code>\n"
        "⚠️ Finansal tavsiye değildir."
    )
    response = SESSION.post(f"https://api.telegram.org/bot{token}/sendMessage",
                            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=20)
    response.raise_for_status()


def update_status(items):
    for item in items:
        if item["status"] != "PENDING":
            continue
        try:
            row = candles(item["symbol"], CONFIG["interval"], 8)[-2]
        except Exception:
            continue
        if item["direction"] == "LONG":
            if row["l"] <= item["stop"]:
                item["status"], item["result_r"] = "STOP", -1
            elif row["h"] >= item["target"]:
                item["status"], item["result_r"] = "TARGET", item["rr"]
        else:
            if row["h"] >= item["stop"]:
                item["status"], item["result_r"] = "STOP", -1
            elif row["l"] <= item["target"]:
                item["status"], item["result_r"] = "TARGET", item["rr"]


def main():
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    old = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else []
    update_status(old)
    known = {x["id"] for x in old}
    created = []
    for symbol in contracts():
        try:
            found = setup(symbol)
            if found and found["id"] not in known:
                created.append(found)
                known.add(found["id"])
                telegram(found)
        except Exception as exc:
            print(f"{symbol}: {exc}")
        time.sleep(.12)
    combined = (created + old)[: int(CONFIG["max_signals"])]
    DATA_FILE.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"New signals: {len(created)}; total: {len(combined)}")


if __name__ == "__main__":
    main()
