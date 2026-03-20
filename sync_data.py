#!/usr/bin/env python3
"""
Sync all paper trader data into a single data.json for the dashboard.
Reads from ~/Desktop/claude-master/ trader directories.
Run manually or via cron: */5 * * * * cd ~/Desktop/trader-dashboard && python3 sync_data.py
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path.home() / "Desktop" / "claude-master"
OUT = Path(__file__).parent / "data.json"

TRADERS = {
    "meme": {
        "name": "Meme Scanner",
        "type": "meme",
        "trades_file": BASE / "meme-scanner" / "trades.json",
        "state_file": None,
        "pid_file": None,
        "process_pattern": "scanner.py",
        "equity_csv": None,
    },
    "forex": {
        "name": "Forex 5m",
        "type": "jsonl",
        "trades_file": BASE / "forex" / "output" / "paper_trade" / "trades.jsonl",
        "state_file": BASE / "forex" / "output" / "paper_trade" / "state.json",
        "pid_file": BASE / "forex" / "output" / "paper_trade" / "paper_trader.pid",
        "equity_csv": BASE / "forex" / "output" / "paper_trade" / "equity_curve.csv",
    },
    "stock": {
        "name": "Stock Trader",
        "type": "jsonl",
        "trades_file": BASE / "stock-trader" / "output" / "paper_trade" / "trades.jsonl",
        "state_file": BASE / "stock-trader" / "output" / "paper_trade" / "state.json",
        "pid_file": BASE / "stock-trader" / "output" / "paper_trade" / "paper_trader.pid",
        "equity_csv": BASE / "stock-trader" / "output" / "paper_trade" / "equity_curve.csv",
    },
    "crypto_5m": {
        "name": "Crypto 5m",
        "type": "jsonl",
        "trades_file": BASE / "crypto" / "output" / "paper_trade_5m" / "trades.jsonl",
        "state_file": BASE / "crypto" / "output" / "paper_trade_5m" / "state.json",
        "pid_file": BASE / "crypto" / "output" / "paper_trade_5m" / "paper_trader_5m.pid",
        "equity_csv": BASE / "crypto" / "output" / "paper_trade_5m" / "equity_curve.csv",
    },
    "crypto_15m": {
        "name": "Crypto 15m",
        "type": "jsonl",
        "trades_file": BASE / "crypto" / "output" / "paper_trade" / "trades.jsonl",
        "state_file": BASE / "crypto" / "output" / "paper_trade" / "state.json",
        "pid_file": BASE / "crypto" / "output" / "paper_trade" / "paper_trader.pid",
        "equity_csv": BASE / "crypto" / "output" / "paper_trade" / "equity_curve.csv",
    },
    "crypto_lev": {
        "name": "Crypto Leverage",
        "type": "jsonl_lev",
        "trades_file": BASE / "crypto" / "output" / "paper_trade_leverage" / "trades.jsonl",
        "state_file": BASE / "crypto" / "output" / "paper_trade_leverage" / "state.json",
        "pid_file": BASE / "crypto" / "output" / "paper_trade_leverage" / "paper_trader_leverage.pid",
        "equity_csv": BASE / "crypto" / "output" / "paper_trade_leverage" / "equity_curve.csv",
    },
}


def unix_to_iso(ts):
    """Convert unix timestamp to ISO string."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def check_status(cfg):
    """Check if a trader process is running."""
    # Check PID file first
    pid_file = cfg.get("pid_file")
    if pid_file and pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            return "running"
        except (ProcessLookupError, ValueError, PermissionError):
            pass

    # Check process pattern (for meme scanner)
    pattern = cfg.get("process_pattern")
    if pattern:
        try:
            r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                return "running"
        except Exception:
            pass

    # Fallback: check state file last_cycle
    state_file = cfg.get("state_file")
    if state_file and state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            lc = state.get("last_cycle")
            if lc:
                last = datetime.fromisoformat(lc)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - last).total_seconds() < 600:
                    return "running"
        except Exception:
            pass

    # Fallback for meme: check trades.json mtime
    tf = cfg.get("trades_file")
    if tf and tf.exists():
        mtime = os.path.getmtime(tf)
        if time.time() - mtime < 300:
            return "running"

    return "stopped"


def load_meme(cfg):
    """Load meme scanner data."""
    tf = cfg["trades_file"]
    if not tf.exists():
        return empty_trader(cfg)

    data = json.loads(tf.read_text())
    settings = data.get("settings", {})
    open_trades = data.get("open", [])
    closed_trades = data.get("closed", [])

    # Normalize closed trades
    trades = []
    for t in closed_trades:
        trades.append({
            "id": t.get("mint", "")[:8],
            "opened_at": unix_to_iso(t.get("entry_time")),
            "closed_at": unix_to_iso(t.get("exit_time")),
            "symbol": t.get("symbol", "???"),
            "direction": "long",
            "entry_price": t.get("entry_price", 0),
            "exit_price": t.get("exit_price", 0),
            "pnl": t.get("pnl_usd", 0),
            "pnl_pct": t.get("pnl_pct", 0),
            "outcome": "WIN" if t.get("pnl_usd", 0) > 0 else "LOSS",
            "exit_reason": t.get("exit_reason", ""),
            "bankroll_after": None,
            "extra": {
                "entry_score": t.get("entry_score"),
                "peak_multiple": t.get("peak_multiple"),
                "entry_mc": t.get("entry_mc"),
            },
        })

    # Normalize open positions
    open_pos = []
    for t in open_trades:
        hold_mins = t.get("hold_time_minutes", 0)
        open_pos.append({
            "symbol": t.get("symbol", "???"),
            "entry_price": t.get("entry_price", 0),
            "current_price": t.get("current_price", 0),
            "pnl": t.get("pnl_usd", 0),
            "pnl_pct": t.get("pnl_pct", 0),
            "opened_at": unix_to_iso(t.get("entry_time")),
            "hold_minutes": round(hold_mins, 1),
            "extra": {
                "entry_score": t.get("entry_score"),
                "partial_sold": t.get("partial_sold"),
            },
        })

    # Compute stats
    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    losses = len(trades) - wins
    total_pnl = sum(t["pnl"] for t in trades)
    unrealized = sum(t["pnl"] for t in open_pos)
    position_size = settings.get("position_size", 100)
    total_invested = (len(closed_trades) + len(open_trades)) * position_size
    starting = total_invested if total_invested > 0 else position_size

    # Compute equity curve from closed trades
    equity_curve = build_equity_from_trades(trades, starting)

    # Find last trade time
    last_trade = None
    if trades:
        last_trade = max(t["closed_at"] for t in trades if t["closed_at"])

    return {
        "name": cfg["name"],
        "status": check_status(cfg),
        "bankroll": round(starting + total_pnl + unrealized, 2),
        "starting_bankroll": round(starting, 2),
        "total_pnl": round(total_pnl + unrealized, 2),
        "total_pnl_pct": round((total_pnl + unrealized) / starting * 100, 2) if starting > 0 else 0,
        "total_trades": len(closed_trades),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(trades) * 100, 1) if trades else 0,
        "daily_pnl": 0,
        "open_positions": len(open_trades),
        "last_trade_at": last_trade,
        "trades": trades,
        "open": open_pos,
        "equity_curve": equity_curve,
    }


def load_jsonl_trader(cfg, trader_type="standard"):
    """Load a JSONL-based trader (forex, stock, crypto)."""
    state_file = cfg.get("state_file")
    trades_file = cfg.get("trades_file")

    # Load state
    state = {}
    if state_file and state_file.exists():
        state = json.loads(state_file.read_text())

    # Load trades
    raw_trades = []
    if trades_file and trades_file.exists():
        with open(trades_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        raw_trades.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    # Normalize trades based on type
    trades = []
    for t in raw_trades:
        trades.append(normalize_trade(t, cfg["type"]))

    # Compute stats
    closed = [t for t in trades if t["outcome"] in ("WIN", "LOSS")]
    wins = sum(1 for t in closed if t["outcome"] == "WIN")
    losses = len(closed) - wins

    bankroll = state.get("bankroll", 0)
    starting = state.get("starting_bankroll", bankroll)
    total_pnl = state.get("total_pnl", sum(t["pnl"] for t in closed))

    # Open positions
    open_pos = []
    state_open = state.get("open_positions", state.get("positions", []))
    if isinstance(state_open, dict):
        state_open = list(state_open.values())
    for p in state_open:
        open_pos.append(normalize_open_position(p, cfg["type"]))

    # Equity curve
    equity_curve = load_equity_csv(cfg.get("equity_csv"))
    if not equity_curve:
        equity_curve = build_equity_from_trades(trades, starting)

    # Last trade time
    last_trade = None
    if trades:
        closed_times = [t["closed_at"] for t in trades if t.get("closed_at")]
        if closed_times:
            last_trade = max(closed_times)

    return {
        "name": cfg["name"],
        "status": check_status(cfg),
        "bankroll": round(bankroll, 2),
        "starting_bankroll": round(starting, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl / starting * 100, 2) if starting > 0 else 0,
        "total_trades": len(closed),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(closed) * 100, 1) if closed else 0,
        "daily_pnl": round(state.get("daily_pnl", 0), 2),
        "open_positions": len(open_pos),
        "last_trade_at": last_trade,
        "trades": trades,
        "open": open_pos,
        "equity_curve": equity_curve,
        "extra_state": {
            k: state.get(k)
            for k in ["total_fees", "total_spread_cost", "total_funding", "liquidations",
                       "consec_losses", "peak_bankroll", "max_drawdown"]
            if state.get(k) is not None
        },
    }


def normalize_trade(t, trader_type):
    """Normalize a trade record to common schema."""
    if trader_type in ("jsonl",):
        # Forex / Stock — check which fields exist
        if "pair" in t:
            # Forex
            return {
                "id": t.get("id"),
                "opened_at": t.get("opened_at"),
                "closed_at": t.get("closed_at"),
                "symbol": t.get("pair", ""),
                "direction": t.get("direction", ""),
                "entry_price": t.get("entry_price", 0),
                "exit_price": t.get("exit_price", 0),
                "pnl": t.get("pnl", 0),
                "pnl_pct": round(t.get("pnl", 0) / t.get("risk_amount", 1) * 100, 2) if t.get("risk_amount") else 0,
                "outcome": t.get("outcome", ""),
                "exit_reason": t.get("reason", ""),
                "bankroll_after": t.get("bankroll_after"),
                "extra": {
                    "pnl_pips": t.get("pnl_pips"),
                    "spread_cost": t.get("spread_cost"),
                    "signal_score": t.get("signal_score"),
                    "confidence": t.get("confidence"),
                    "duration": t.get("duration"),
                },
            }
        elif "symbol" in t:
            # Stock
            return {
                "id": t.get("id"),
                "opened_at": t.get("opened_at"),
                "closed_at": t.get("closed_at"),
                "symbol": t.get("symbol", ""),
                "direction": t.get("direction", ""),
                "entry_price": t.get("entry_price", 0),
                "exit_price": t.get("exit_price", 0),
                "pnl": t.get("pnl", 0),
                "pnl_pct": t.get("pnl_pct", 0),
                "outcome": t.get("outcome", ""),
                "exit_reason": t.get("exit_reason", ""),
                "bankroll_after": t.get("bankroll_after"),
                "extra": {
                    "shares": t.get("shares"),
                    "score": t.get("score"),
                    "strategy": t.get("strategy"),
                    "hold_minutes": t.get("hold_minutes"),
                },
            }
        else:
            # Crypto 5m / 15m (has 'coin' + 'side')
            return {
                "id": t.get("id"),
                "opened_at": t.get("timestamp"),
                "closed_at": t.get("resolved_at"),
                "symbol": t.get("coin", ""),
                "direction": t.get("side", ""),
                "entry_price": t.get("market_price", 0),
                "exit_price": None,
                "pnl": t.get("pnl", 0),
                "pnl_pct": round(t.get("pnl", 0) / t.get("bet_size", 1) * 100, 2) if t.get("bet_size") else 0,
                "outcome": t.get("outcome", ""),
                "exit_reason": "resolved",
                "bankroll_after": t.get("bankroll_after"),
                "extra": {
                    "ml_prob": t.get("ml_prob"),
                    "edge_pct": t.get("edge_pct"),
                    "bet_size": t.get("bet_size"),
                    "confidence": t.get("confidence"),
                    "market_regime": t.get("market_regime"),
                    "fee": t.get("fee"),
                },
            }

    elif trader_type == "jsonl_lev":
        # Crypto Leverage
        return {
            "id": t.get("id"),
            "opened_at": t.get("opened_at"),
            "closed_at": t.get("closed_at"),
            "symbol": t.get("coin", ""),
            "direction": t.get("direction", ""),
            "entry_price": t.get("entry_price", 0),
            "exit_price": t.get("exit_price", 0),
            "pnl": t.get("pnl", 0),
            "pnl_pct": round(t.get("pnl", 0) / t.get("margin", 1) * 100, 2) if t.get("margin") else 0,
            "outcome": t.get("outcome", ""),
            "exit_reason": t.get("exit_reason", ""),
            "bankroll_after": t.get("bankroll_after"),
            "extra": {
                "leverage": t.get("leverage"),
                "margin": t.get("margin"),
                "funding_paid": t.get("funding_paid"),
            },
        }

    return {}


def normalize_open_position(p, trader_type):
    """Normalize an open position from state.json."""
    if isinstance(p, dict):
        # Try to extract common fields
        symbol = p.get("pair") or p.get("symbol") or p.get("coin") or "???"
        return {
            "symbol": symbol,
            "entry_price": p.get("entry_price", 0),
            "current_price": p.get("current_price", p.get("entry_price", 0)),
            "pnl": p.get("pnl", 0),
            "pnl_pct": p.get("pnl_pct", 0),
            "opened_at": p.get("opened_at"),
            "hold_minutes": 0,
            "extra": {
                "direction": p.get("direction"),
                "leverage": p.get("leverage"),
                "stop_loss": p.get("stop_loss"),
                "take_profit": p.get("take_profit"),
            },
        }
    return {}


def load_equity_csv(csv_path):
    """Load equity curve from CSV file."""
    if not csv_path or not csv_path.exists():
        return []

    curve = []
    with open(csv_path) as f:
        for i, line in enumerate(f):
            if i == 0:
                continue  # skip header
            parts = line.strip().split(",")
            if len(parts) >= 2:
                try:
                    curve.append({"date": parts[0], "value": float(parts[1])})
                except ValueError:
                    continue
    return curve


def build_equity_from_trades(trades, starting_bankroll):
    """Build equity curve from trade history."""
    if not trades:
        return [{"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "value": starting_bankroll}]

    # Sort by closed_at
    sorted_trades = sorted(
        [t for t in trades if t.get("closed_at")],
        key=lambda t: t["closed_at"]
    )

    if not sorted_trades:
        return [{"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "value": starting_bankroll}]

    # If bankroll_after is available, use it directly
    if sorted_trades[0].get("bankroll_after") is not None:
        curve = []
        seen_dates = set()
        for t in sorted_trades:
            dt = t["closed_at"][:10]
            val = t["bankroll_after"]
            if dt in seen_dates:
                # Update last entry for this date
                curve = [c for c in curve if c["date"] != dt]
            seen_dates.add(dt)
            curve.append({"date": dt, "value": round(val, 2)})
        return curve

    # Otherwise compute cumulative P&L
    equity = starting_bankroll
    curve = []
    seen_dates = set()
    for t in sorted_trades:
        equity += t.get("pnl", 0)
        dt = t["closed_at"][:10]
        if dt in seen_dates:
            curve = [c for c in curve if c["date"] != dt]
        seen_dates.add(dt)
        curve.append({"date": dt, "value": round(equity, 2)})

    return curve


def empty_trader(cfg):
    """Return empty trader data when files don't exist."""
    return {
        "name": cfg["name"],
        "status": "stopped",
        "bankroll": 0,
        "starting_bankroll": 0,
        "total_pnl": 0,
        "total_pnl_pct": 0,
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0,
        "daily_pnl": 0,
        "open_positions": 0,
        "last_trade_at": None,
        "trades": [],
        "open": [],
        "equity_curve": [],
    }


def sync():
    """Main sync: read all traders, write data.json."""
    result = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "traders": {},
    }

    for tid, cfg in TRADERS.items():
        try:
            if cfg["type"] == "meme":
                result["traders"][tid] = load_meme(cfg)
            else:
                result["traders"][tid] = load_jsonl_trader(cfg)
        except Exception as e:
            print(f"Error loading {tid}: {e}")
            result["traders"][tid] = empty_trader(cfg)
            result["traders"][tid]["error"] = str(e)

    # Write data.json
    OUT.write_text(json.dumps(result, indent=2, default=str))
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Synced {len(result['traders'])} traders → {OUT}")
    return result


def git_push():
    """Commit and push data.json if it changed."""
    repo = Path(__file__).parent
    try:
        # Check if data.json has changes
        r = subprocess.run(
            ["git", "diff", "--quiet", "data.json"],
            cwd=repo, capture_output=True
        )
        if r.returncode == 0:
            # Also check if untracked
            r2 = subprocess.run(
                ["git", "ls-files", "--error-unmatch", "data.json"],
                cwd=repo, capture_output=True
            )
            if r2.returncode == 0:
                print("No changes to push.")
                return

        subprocess.run(["git", "add", "data.json"], cwd=repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"sync: {datetime.now().strftime('%Y-%m-%d %H:%M')}"],
            cwd=repo, check=True, capture_output=True
        )
        subprocess.run(["git", "push"], cwd=repo, check=True, capture_output=True)
        print("Pushed to GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"Git push failed: {e}")


if __name__ == "__main__":
    import sys
    sync()
    if "--push" in sys.argv:
        git_push()
