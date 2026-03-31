from collections import defaultdict
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from config import MERGED_PARQUET
from ingestion.trade_history import (
    fetch_all_trades,
    build_player_lookup,
    compute_trade_values,
    get_league_chain,
)
from ingestion.ktc_history import (
    batch_fetch_histories,
    build_pick_lookup,
)

# Grading mode definitions
MODES = {
    "Value Gained (Realized)": {
        "description": "Value at exit (or today if still held) minus value at trade time",
        "diff_key": "abs_diff_realized",
        "winner_key": "winner_realized",
        "loser_key": "loser_realized",
        "grade_key": "grade_realized",
    },
    "Hindsight (Today)": {
        "description": "Who has more value today",
        "diff_key": "abs_diff_now",
        "winner_key": "winner_now",
        "loser_key": "loser_now",
        "grade_key": "grade_now",
    },
    "At Trade Time": {
        "description": "Who got more value when the trade was made",
        "diff_key": "abs_diff",
        "winner_key": "winner",
        "loser_key": "loser",
        "grade_key": "grade",
    },
}


def render():
    st.header("Trade History")

    with st.expander("How it works", expanded=False):
        st.markdown("""
**Trade History** analyzes every trade in your dynasty league's history using
KeepTradeCut's historical superflex values. It automatically walks back through
every season via Sleeper's league history chain to find all completed trades.

---

**Grading Modes** — Toggle in the sidebar to change how trades are scored.
Everything updates: the leaderboard, fleece rankings, win/loss records, and charts.

- **Value Gained (Realized)** *(default)* — The most accurate way to grade trades.
  For each asset you received, we track its KTC value from the **trade date** to
  the **exit date** (when you traded it away) or **today** if you still hold it.
  This is true realized value — if you got a player and flipped him a month later,
  your gain is locked at the flip price. You don't get credit (or blame) for what
  happened after you no longer held the asset.

- **Hindsight (Today)** — Compares what each side of the trade is worth today,
  regardless of whether you still hold the assets. Useful for seeing how a trade
  looks on paper right now, but doesn't account for subsequent moves.

- **At Trade Time** — What each side was worth the day the trade was made. Shows
  who "won on paper" at the moment of the deal.

---

**Pick Resolution** — Traded draft picks are linked to the player who was eventually
selected in the rookie draft. A "2024 Round 1" becomes "2024 Round 1 -- became
Malik Nabers" with the drafted player's value used for grading. For picks where
the draft hasn't happened yet, KTC's pick tier values are used (e.g. "2026 Mid 1st").

**Historical Values** — Each player's KTC superflex value is scraped from their
individual KTC player page, which contains daily value snapshots going back years.
These are cached locally for 7 days to avoid re-fetching.

**Grading Scale** — Based on the KTC value gap between sides in the selected mode:
A+ (3000+) | A (2000+) | B (1000+) | C (500+) | Fair (<500)

**Win %** — Calculated from decided trades only (excludes "Fair" trades). A manager
with 20W-10L-5F has a 67% win rate (20/30).

**Leaderboard** — Sorted by net KTC value in the selected mode. The bar chart and
win % progress bar make it easy to see who's winning the trade game.

**Manager Timeline** — Select any manager to see their cumulative trade value over
time as a line chart, plus detailed trade cards showing every asset with its value
at acquisition and at exit/today.
""")

    if "league_id" not in st.session_state:
        st.info("Connect a Sleeper league to view trade history.")
        return

    if not MERGED_PARQUET.exists():
        st.info("No data loaded. Click **Refresh Data** in the sidebar to get started.")
        return

    league_id = st.session_state["league_id"]
    cache_key = f"trade_analysis_{league_id}"

    if cache_key not in st.session_state:
        _load_trade_data(league_id, cache_key)

    if cache_key not in st.session_state or not st.session_state[cache_key]:
        st.warning("No trades found for this league.")
        return

    trades = st.session_state[cache_key]

    if st.button("Refresh Trade Data"):
        if cache_key in st.session_state:
            del st.session_state[cache_key]
        st.rerun()

    tab1, tab2 = st.tabs(["League Trade History", "Manager Trade Timeline"])

    with tab1:
        _render_league_history(trades)

    with tab2:
        _render_manager_timeline(trades)


def _load_trade_data(league_id: str, cache_key: str):
    """Fetch trades, scrape KTC history, compute values."""
    with st.status("Loading trade history...", expanded=True) as status:
        st.write("Traversing league history...")
        trades = fetch_all_trades(league_id)

        if not trades:
            st.session_state[cache_key] = []
            status.update(label="No trades found", state="complete")
            return

        st.write(f"Found {len(trades)} trades across all seasons")

        st.write("Building player lookup...")
        player_lookup = build_player_lookup()

        player_ktc_ids = set()
        for trade in trades:
            for side in trade["sides"]:
                for pid in side["players_received"]:
                    info = player_lookup.get(pid, {})
                    ktc_id = info.get("ktc_id")
                    ktc_slug = info.get("ktc_slug")
                    if ktc_id and ktc_slug:
                        player_ktc_ids.add((ktc_slug, ktc_id))

                for pick in side["picks_received"]:
                    if pick.get("is_resolved") and pick.get("resolved_player_id"):
                        info = player_lookup.get(pick["resolved_player_id"], {})
                        ktc_id = info.get("ktc_id")
                        ktc_slug = info.get("ktc_slug")
                        if ktc_id and ktc_slug:
                            player_ktc_ids.add((ktc_slug, ktc_id))

        st.write(f"Fetching KTC history for {len(player_ktc_ids)} players...")
        progress_bar = st.progress(0)

        def update_progress(current, total):
            progress_bar.progress(current / total if total > 0 else 1.0)

        histories = batch_fetch_histories(list(player_ktc_ids), update_progress)
        progress_bar.empty()

        st.write("Fetching draft pick values...")
        pick_lookup = build_pick_lookup()

        pick_ktc_ids = set()
        for trade in trades:
            for side in trade["sides"]:
                for pick in side["picks_received"]:
                    if not pick.get("is_resolved"):
                        from ingestion.trade_history import _match_pick_to_ktc
                        pick_name = _match_pick_to_ktc(pick, pick_lookup)
                        if pick_name and pick_name in pick_lookup:
                            slug, kid = pick_lookup[pick_name]
                            pick_ktc_ids.add((slug, kid))

        pick_histories = {}
        if pick_ktc_ids:
            st.write(f"Fetching KTC history for {len(pick_ktc_ids)} draft picks...")
            pick_histories = batch_fetch_histories(list(pick_ktc_ids))

        st.write("Computing trade values...")
        enriched = compute_trade_values(
            trades, player_lookup, histories, pick_lookup, pick_histories
        )

        st.session_state[cache_key] = enriched
        status.update(label=f"Loaded {len(enriched)} trades", state="complete")


def _render_league_history(trades: list[dict]):
    """Tab 1: League-wide trade history with leaderboard."""
    if not trades:
        st.info("No trades found.")
        return

    # Sidebar filters
    all_managers = sorted({
        side["manager"] for t in trades for side in t["sides"]
    })
    all_seasons = sorted({t["season"] for t in trades}, reverse=True)

    with st.sidebar:
        st.markdown("---")
        st.subheader("Trade Filters")
        mode = st.radio(
            "Grade by",
            list(MODES.keys()),
            index=0,
            key="trade_mode",
            help="Value Gained = today minus trade time. Hindsight = today's values. At Trade Time = value when traded.",
        )
        selected_seasons = st.multiselect("Season", all_seasons, default=all_seasons)
        selected_managers = st.multiselect("Manager", all_managers, default=[])
        min_diff = st.slider("Min Value Difference", 0, 5000, 0, step=100)
        exclude_startup_picks = st.checkbox(
            "Exclude startup pick trades", value=True,
            help="Hide pick-only trades from the startup season (earliest year) that skew leaderboards",
        )

    m = MODES[mode]
    diff_key = m["diff_key"]
    winner_key = m["winner_key"]
    loser_key = m["loser_key"]
    grade_key = m["grade_key"]

    # Apply filters
    filtered = trades

    # Exclude pick-only trades from the startup season
    if exclude_startup_picks and all_seasons:
        startup_season = min(all_seasons)
        filtered = [
            t for t in filtered
            if not (
                t["season"] == startup_season
                and all(
                    len(s["players_received"]) == 0
                    for s in t["sides"]
                )
            )
        ]

    if selected_seasons:
        filtered = [t for t in filtered if t["season"] in selected_seasons]
    if selected_managers:
        filtered = [
            t for t in filtered
            if any(s["manager"] in selected_managers for s in t["sides"])
        ]
    if min_diff > 0:
        filtered = [t for t in filtered if t.get(diff_key, 0) >= min_diff]

    # Summary metrics
    if filtered:
        # Compute stats
        mgr_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "fair": 0, "net": 0.0})
        for t in filtered:
            if len(t["sides"]) < 2:
                continue
            w = t.get(winner_key)
            l = t.get(loser_key)
            for side in t["sides"]:
                mgr = side["manager"]
                mgr_stats[mgr]["trades"] += 1
                if t.get(grade_key) == "Fair":
                    mgr_stats[mgr]["fair"] += 1
                elif mgr == w:
                    mgr_stats[mgr]["wins"] += 1
                    mgr_stats[mgr]["net"] += t.get(diff_key, 0)
                elif mgr == l:
                    mgr_stats[mgr]["losses"] += 1
                    mgr_stats[mgr]["net"] -= t.get(diff_key, 0)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Trades", len(filtered))

        # Best trader
        if mgr_stats:
            best_mgr = max(mgr_stats, key=lambda m: mgr_stats[m]["net"])
            s = mgr_stats[best_mgr]
            win_pct = round(s["wins"] / s["trades"] * 100) if s["trades"] > 0 else 0
            col2.metric("Best Trader", best_mgr, f"+{s['net']:,.0f} KTC | {win_pct}% win rate")

        # Biggest fleece
        valued = [t for t in filtered if t.get(diff_key, 0) > 0]
        if valued:
            biggest = max(valued, key=lambda t: t[diff_key])
            col3.metric(
                "Biggest Fleece",
                biggest.get(winner_key, "N/A"),
                f"+{biggest[diff_key]:,.0f} KTC",
            )

        # Most active
        if mgr_stats:
            most_active = max(mgr_stats, key=lambda m: mgr_stats[m]["trades"])
            col4.metric("Most Active", most_active, f"{mgr_stats[most_active]['trades']} trades")

    # All Trades table
    st.subheader("All Trades")
    rows = []
    for t in filtered:
        if len(t["sides"]) < 2:
            continue
        s0, s1 = t["sides"][0], t["sides"][1]
        w = t.get(winner_key, "") or ""
        winner_side = s0 if s0["manager"] == w else s1
        loser_side = s1 if s0["manager"] == w else s0

        rows.append({
            "Date": t["date"].strftime("%b %d, %Y") if t["date"] else "Unknown",
            "Season": t["season"],
            "Winner": w or "Fair",
            "Winner Got": _format_assets(winner_side.get("assets", [])),
            "Loser": t.get(loser_key, "") or "Fair",
            "Loser Got": _format_assets(loser_side.get("assets", [])),
            "Gap": t.get(diff_key, 0),
            "Grade": t.get(grade_key, ""),
        })

    if rows:
        df = pd.DataFrame(rows).sort_values("Gap", ascending=False)
        st.dataframe(df, use_container_width=True, hide_index=True)

        csv = df.to_csv(index=False)
        st.download_button(
            "Export All Trades as CSV",
            csv,
            file_name="league_trade_history.csv",
            mime="text/csv",
        )

    # Fleece leaderboard
    _render_fleece_leaderboard(filtered, winner_key, loser_key, diff_key, grade_key)

    # Manager leaderboard
    _render_leaderboard(filtered, winner_key, loser_key, diff_key, grade_key)


def _all_assets_valued(trade):
    """Check that every asset in the trade has a KTC value (no N/A)."""
    for side in trade["sides"]:
        for asset in side.get("assets", []):
            if asset.get("ktc_value") is None:
                return False
    return True


def _render_fleece_leaderboard(trades, winner_key, loser_key, diff_key, grade_key):
    """Top 10 most lopsided trades as cards — only fully valued trades."""
    valued = [t for t in trades if len(t["sides"]) >= 2 and t.get(diff_key, 0) > 0 and _all_assets_valued(t)]
    if not valued:
        return

    st.subheader("Top 10 Fleeces")
    top10 = sorted(valued, key=lambda t: t[diff_key], reverse=True)[:10]

    for rank, t in enumerate(top10, 1):
        s0, s1 = t["sides"][0], t["sides"][1]
        winner = t.get(winner_key, "")
        loser = t.get(loser_key, "")
        winner_side = s0 if s0["manager"] == winner else s1
        loser_side = s1 if s0["manager"] == winner else s0
        date_str = t["date"].strftime("%b %d, %Y") if t["date"] else "?"
        gap = t.get(diff_key, 0)
        grade = t.get(grade_key, "")

        with st.container(border=True):
            header_col, grade_col = st.columns([5, 1])
            with header_col:
                st.markdown(f"**#{rank}** — {date_str} (S{t['season']} W{t['week']})")
            with grade_col:
                st.markdown(f"### {grade}")

            col_w, col_gap, col_l = st.columns([5, 2, 5])

            with col_w:
                st.markdown(f"**{winner}** (Winner)")
                for asset in winner_side.get("assets", []):
                    _render_asset_line(asset)

            with col_gap:
                st.markdown(f"<div style='text-align:center; padding-top:20px;'>"
                           f"<span style='font-size:1.5em; font-weight:bold; color:#4daf4a;'>"
                           f"+{gap:,.0f}</span><br><span style='font-size:0.8em;'>KTC gap</span></div>",
                           unsafe_allow_html=True)

            with col_l:
                st.markdown(f"**{loser}** (Loser)")
                for asset in loser_side.get("assets", []):
                    _render_asset_line(asset)


def _render_asset_line(asset: dict):
    """Render a single asset line in a trade card."""
    name = asset.get("name", "Unknown")
    pos = asset.get("position", "")

    then_val = asset.get("ktc_value")
    realized_val = asset.get("ktc_value_realized")
    exit_date = asset.get("exit_date")

    if asset["type"] == "player" and pos:
        label = f"{name} ({pos})"
    else:
        label = name

    parts = []
    if then_val:
        parts.append(f"then: {then_val:,}")
    if realized_val:
        if exit_date:
            parts.append(f"exit: {realized_val:,} ({exit_date.strftime('%b %y')})")
        else:
            parts.append(f"now: {realized_val:,}")
    val_str = " | ".join(parts) if parts else "N/A"

    st.markdown(f"- {label}  \n  *{val_str}*")


def _render_leaderboard(trades, winner_key, loser_key, diff_key, grade_key):
    """Manager leaderboard with win %, sorted by net value."""
    st.subheader("Manager Leaderboard")

    stats = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "fair": 0, "net": 0.0})

    for t in trades:
        if len(t["sides"]) < 2:
            continue
        w = t.get(winner_key)
        l = t.get(loser_key)
        for side in t["sides"]:
            mgr = side["manager"]
            stats[mgr]["trades"] += 1
            if t.get(grade_key) == "Fair":
                stats[mgr]["fair"] += 1
            elif mgr == w:
                stats[mgr]["wins"] += 1
                stats[mgr]["net"] += t.get(diff_key, 0)
            elif mgr == l:
                stats[mgr]["losses"] += 1
                stats[mgr]["net"] -= t.get(diff_key, 0)

    rows = []
    for mgr, s in stats.items():
        decided = s["wins"] + s["losses"]
        win_pct = round(s["wins"] / decided * 100) if decided > 0 else 0
        rows.append({
            "Manager": mgr,
            "Trades": s["trades"],
            "W": s["wins"],
            "L": s["losses"],
            "Fair": s["fair"],
            "Win %": win_pct,
            "Net KTC": round(s["net"]),
        })

    if not rows:
        return

    df = pd.DataFrame(rows).sort_values("Net KTC", ascending=False)

    st.dataframe(df, use_container_width=True, hide_index=True, column_config={
        "Manager": st.column_config.TextColumn("Manager", width="medium"),
        "Trades": st.column_config.NumberColumn("Trades", format="%d", width="small"),
        "W": st.column_config.NumberColumn("W", format="%d", width="small"),
        "L": st.column_config.NumberColumn("L", format="%d", width="small"),
        "Fair": st.column_config.NumberColumn("Fair", format="%d", width="small"),
        "Win %": st.column_config.ProgressColumn("Win %", min_value=0, max_value=100, format="%d%%"),
        "Net KTC": st.column_config.NumberColumn("Net KTC", format="%d"),
    })

    # Bar chart
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X("Net KTC:Q", title="Net KTC Value"),
        y=alt.Y("Manager:N", sort="-x", title=""),
        color=alt.condition(
            alt.datum["Net KTC"] > 0,
            alt.value("#4daf4a"),
            alt.value("#e41a1c"),
        ),
        tooltip=["Manager", "Net KTC", "Win %", "Trades", "W", "L"],
    )
    st.altair_chart(chart, use_container_width=True)


def _render_manager_timeline(trades: list[dict]):
    """Tab 2: Per-manager trade timeline with cumulative chart."""
    all_managers = sorted({
        side["manager"] for t in trades for side in t["sides"]
    })

    if not all_managers:
        st.info("No trades found.")
        return

    user_name = st.session_state.get("sleeper_display_name", "")
    default_idx = 0
    for i, m in enumerate(all_managers):
        if m.lower() == user_name.lower():
            default_idx = i
            break

    selected = st.selectbox("Select Manager", all_managers, index=default_idx)

    # Get current mode from sidebar
    mode = st.session_state.get("trade_mode", "Value Gained (Realized)")
    m = MODES[mode]
    winner_key = m["winner_key"]
    loser_key = m["loser_key"]
    diff_key = m["diff_key"]
    grade_key = m["grade_key"]

    manager_trades = [
        t for t in trades
        if any(s["manager"] == selected for s in t["sides"])
    ]

    if not manager_trades:
        st.info(f"No trades found for {selected}.")
        return

    # Stats
    wins = sum(1 for t in manager_trades if t.get(winner_key) == selected)
    losses = sum(1 for t in manager_trades if t.get(loser_key) == selected)
    fair = len(manager_trades) - wins - losses
    decided = wins + losses
    win_pct = round(wins / decided * 100) if decided > 0 else 0

    total_net = 0
    for t in manager_trades:
        if len(t["sides"]) < 2:
            continue
        if t.get(winner_key) == selected:
            total_net += t.get(diff_key, 0)
        elif t.get(loser_key) == selected:
            total_net -= t.get(diff_key, 0)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Trades", len(manager_trades))
    col2.metric("Record", f"{wins}W - {losses}L - {fair}F")
    col3.metric("Win %", f"{win_pct}%")
    net_sign = "+" if total_net >= 0 else ""
    col4.metric("Net KTC", f"{net_sign}{total_net:,.0f}")

    # Best and worst trades
    _render_best_worst(manager_trades, selected, winner_key, loser_key, diff_key, grade_key)

    # Cumulative chart
    st.subheader("Cumulative Trade Value")
    chart_data = []
    running = 0

    for t in sorted(manager_trades, key=lambda x: x["timestamp"]):
        if len(t["sides"]) < 2:
            continue
        for i, side in enumerate(t["sides"]):
            if side["manager"] == selected:
                other = t["sides"][1 - i]
                if t.get(winner_key) == selected:
                    running += t.get(diff_key, 0)
                elif t.get(loser_key) == selected:
                    running -= t.get(diff_key, 0)
                chart_data.append({
                    "Date": t["date"],
                    "Net Value": running,
                    "Trade": f"vs {other['manager']}",
                })
                break

    if chart_data:
        chart_df = pd.DataFrame(chart_data)
        line = alt.Chart(chart_df).mark_line(point=True).encode(
            x=alt.X("Date:T", title=""),
            y=alt.Y("Net Value:Q", title="Cumulative Net KTC"),
            tooltip=["Date:T", "Net Value:Q", "Trade:N"],
        )
        zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
            strokeDash=[5, 5], color="gray"
        ).encode(y="y:Q")
        st.altair_chart(line + zero, use_container_width=True)

    # Trade cards
    st.subheader("Trade Details")
    for t in manager_trades:
        if len(t["sides"]) < 2:
            continue

        my_side = None
        other_side = None
        for i, side in enumerate(t["sides"]):
            if side["manager"] == selected:
                my_side = side
                other_side = t["sides"][1 - i]
                break

        if not my_side or not other_side:
            continue

        is_winner = t.get(winner_key) == selected
        is_loser = t.get(loser_key) == selected
        gap = t.get(diff_key, 0)
        grade = t.get(grade_key, "")

        if is_winner:
            net_str = f"+{gap:,.0f}"
            result = "W"
        elif is_loser:
            net_str = f"-{gap:,.0f}"
            result = "L"
        else:
            net_str = "0"
            result = "F"

        with st.expander(
            f"{result} | S{t['season']} W{t['week']} vs {other_side['manager']} | "
            f"{net_str} KTC ({grade})"
        ):
            col_sent, col_recv = st.columns(2)

            with col_sent:
                st.markdown("**Sent**")
                for asset in other_side.get("assets", []):
                    _render_asset_line(asset)
                st.markdown(
                    f"**Then: {other_side['total_value']:,} | "
                    f"Now: {other_side.get('total_value_now', 0):,}**"
                )

            with col_recv:
                st.markdown("**Received**")
                for asset in my_side.get("assets", []):
                    _render_asset_line(asset)
                st.markdown(
                    f"**Then: {my_side['total_value']:,} | "
                    f"Now: {my_side.get('total_value_now', 0):,}**"
                )

    # Export
    _render_export(manager_trades, selected, winner_key, loser_key, diff_key, grade_key)


def _render_best_worst(
    manager_trades: list[dict],
    manager: str,
    winner_key: str,
    loser_key: str,
    diff_key: str,
    grade_key: str,
):
    """Show the 5 best and 5 worst trades for a manager."""
    scored = []
    for t in manager_trades:
        if len(t["sides"]) < 2:
            continue
        if t.get(winner_key) == manager:
            scored.append((t.get(diff_key, 0), t))
        elif t.get(loser_key) == manager:
            scored.append((-t.get(diff_key, 0), t))
        else:
            scored.append((0, t))

    if not scored:
        return

    scored.sort(key=lambda x: x[0], reverse=True)

    col_best, col_worst = st.columns(2)

    with col_best:
        st.subheader("5 Best Trades")
        for net, t in scored[:5]:
            _render_mini_trade_card(t, manager, net, winner_key, loser_key, diff_key, grade_key)

    with col_worst:
        st.subheader("5 Worst Trades")
        for net, t in scored[-5:]:
            _render_mini_trade_card(t, manager, net, winner_key, loser_key, diff_key, grade_key)


def _render_mini_trade_card(t, manager, net, winner_key, loser_key, diff_key, grade_key):
    """Compact trade card for best/worst lists."""
    my_side = None
    other_side = None
    for i, side in enumerate(t["sides"]):
        if side["manager"] == manager:
            my_side = side
            other_side = t["sides"][1 - i]
            break
    if not my_side or not other_side:
        return

    date_str = t["date"].strftime("%b '%y") if t["date"] else "?"
    grade = t.get(grade_key, "")
    net_sign = "+" if net >= 0 else ""
    color = "#4daf4a" if net >= 0 else "#e41a1c"

    with st.container(border=True):
        st.markdown(
            f"**{date_str}** vs {other_side['manager']} | "
            f"<span style='color:{color};font-weight:bold;'>{net_sign}{net:,.0f} KTC</span> ({grade})",
            unsafe_allow_html=True,
        )
        st.caption(
            f"Sent: {_format_assets(other_side.get('assets', []))}  \n"
            f"Got: {_format_assets(my_side.get('assets', []))}"
        )


def _render_export(
    manager_trades: list[dict],
    manager: str,
    winner_key: str,
    loser_key: str,
    diff_key: str,
    grade_key: str,
):
    """CSV export button for manager's trades."""
    rows = []
    for t in manager_trades:
        if len(t["sides"]) < 2:
            continue

        my_side = None
        other_side = None
        for i, side in enumerate(t["sides"]):
            if side["manager"] == manager:
                my_side = side
                other_side = t["sides"][1 - i]
                break
        if not my_side or not other_side:
            continue

        is_winner = t.get(winner_key) == manager
        is_loser = t.get(loser_key) == manager
        gap = t.get(diff_key, 0)

        rows.append({
            "Date": t["date"].isoformat() if t["date"] else "",
            "Season": t["season"],
            "Week": t["week"],
            "Opponent": other_side["manager"],
            "Received": _format_assets(my_side.get("assets", [])),
            "Received Value (Then)": my_side["total_value"],
            "Received Value (Realized)": my_side.get("total_value_realized", 0),
            "Received Value (Now)": my_side.get("total_value_now", 0),
            "Sent": _format_assets(other_side.get("assets", [])),
            "Sent Value (Then)": other_side["total_value"],
            "Sent Value (Realized)": other_side.get("total_value_realized", 0),
            "Sent Value (Now)": other_side.get("total_value_now", 0),
            "Net": gap if is_winner else -gap if is_loser else 0,
            "Result": "W" if is_winner else "L" if is_loser else "Fair",
            "Grade": t.get(grade_key, ""),
        })

    if rows:
        df = pd.DataFrame(rows)
        csv = df.to_csv(index=False)
        st.download_button(
            "Export as CSV",
            csv,
            file_name=f"trade_history_{manager}.csv",
            mime="text/csv",
        )


def _format_assets(assets: list[dict]) -> str:
    """Format a list of assets into a comma-separated string."""
    parts = []
    for a in assets:
        name = a.get("name", "Unknown")
        if a["type"] == "player":
            pos = a.get("position", "")
            parts.append(f"{name} ({pos})" if pos else name)
        else:
            parts.append(name)
    return ", ".join(parts) if parts else "N/A"
