import random

import numpy as np
import pandas as pd
import streamlit as st

from config import MERGED_PARQUET, POSITIONS, BLEND_WEIGHTS_DEFAULT

RANK_SOURCES = {
    "Blended (avg)": "blended_rank",
    "ADP": "adp_rank",
    "NFL Draft": "draft_skill_rank",
    "LateRound": "lr_rank",
    "FantasyCalc": "fc_rookie_rank",
    "KeepTradeCut": "ktc_rookie_rank",
}

SOURCE_RANK_COLS = {
    "lr": "lr_rank", "fc": "fc_rookie_rank", "ktc": "ktc_rookie_rank",
    "draft": "draft_skill_rank", "adp": "adp_rank",
}
SOURCE_LABELS = {"lr": "LR", "fc": "FC", "ktc": "KTC", "draft": "Draft", "adp": "ADP"}


def _get_rookies(rank_col: str, blend_weights: dict | None = None) -> pd.DataFrame:
    from ingestion.lateround import load_lateround, merge_lateround
    from ingestion.nfl_draft import load_nfl_draft, merge_nfl_draft
    from ingestion.adp import load_adp, merge_adp
    from ingestion.blend import blend_rank, rank_spread

    if blend_weights is None:
        blend_weights = dict(BLEND_WEIGHTS_DEFAULT)

    df = pd.read_parquet(MERGED_PARQUET)
    rookies = df[df["is_rookie"] == True].copy()  # noqa: E712

    # LateRound (rank, not tier)
    lr = load_lateround()
    if not lr.empty:
        rookies = merge_lateround(rookies, lr)
    for c in ("lr_rank", "lr_pos_rank", "lr_tier"):
        if c not in rookies.columns:
            rookies[c] = None

    # NFL draft capital + ADP
    rookies = merge_nfl_draft(rookies, load_nfl_draft())
    rookies = merge_adp(rookies, load_adp())

    # Rookie-only FC/KTC ranks (comparable to LR/Draft/ADP ranks)
    for src, col in [("fc", "fc_rank"), ("ktc", "ktc_rank")]:
        rookie_col = f"{src}_rookie_rank"
        subset = rookies[rookies[col].notna()].sort_values(col)
        rookies[rookie_col] = None
        rookies.loc[subset.index, rookie_col] = range(1, len(subset) + 1)

    # Equal-weight blend + disagreement spread
    def _row(r):
        sr = {}
        for k, c in SOURCE_RANK_COLS.items():
            v = r.get(c)
            sr[k] = float(v) if pd.notna(v) else None
        b = blend_rank(sr, blend_weights)
        sp, hi, lo = rank_spread(sr)
        return pd.Series({
            "blended_rank": b,
            "rank_spread": sp,
            "source_high": SOURCE_LABELS.get(hi),
            "source_low": SOURCE_LABELS.get(lo),
        })

    rookies[["blended_rank", "rank_spread", "source_high", "source_low"]] = \
        rookies.apply(_row, axis=1)

    # Snapshot the TRUE (unfilled) per-source ranks so the Draft Recap can blend on
    # real source coverage (None when a source doesn't rank a player), not the
    # sort-sentinel written by the fill loop below.
    for col in ["lr_rank", "fc_rookie_rank", "ktc_rookie_rank",
                "draft_skill_rank", "adp_rank"]:
        if col in rookies.columns:
            rookies[f"{col}__raw"] = pd.to_numeric(rookies[col], errors="coerce")

    # Fill unranked (None/NaN) per-source ranks with (max + 1) so they sort to the
    # BOTTOM of a column-sorted table — Streamlit sorts nulls to the top otherwise.
    # Done AFTER the blend/spread above so those reflect true source coverage.
    for col in ["lr_rank", "fc_rookie_rank", "ktc_rookie_rank", "draft_skill_rank", "adp_rank"]:
        if col in rookies.columns:
            nums = pd.to_numeric(rookies[col], errors="coerce")
            if nums.notna().any():
                rookies[col] = nums.fillna(int(nums.max()) + 1)

    # Keep every rookie; sort by the chosen source with unranked players last so
    # ranking by a sparse source (e.g. LateRound) never hides available players.
    rookies = rookies.sort_values(rank_col, na_position="last").reset_index(drop=True)
    return rookies


def _available_after_live_picks(rookies: pd.DataFrame, draft_id: str) -> pd.DataFrame:
    """Remove rookies already taken in the live Sleeper draft (by sleeper_id then name)."""
    from ingestion.sleeper import get_draft_picks
    from ingestion.match_util import normalize_name
    try:
        picks = get_draft_picks(draft_id)
    except Exception:
        return rookies
    taken_ids, taken_names = set(), set()
    for pk in picks or []:
        if pk.get("player_id"):
            taken_ids.add(str(pk["player_id"]))
        md = pk.get("metadata") or {}
        nm = f"{md.get('first_name','')} {md.get('last_name','')}".strip()
        if nm:
            taken_names.add(normalize_name(nm))
    if "sleeper_id" in rookies.columns:
        mask_id = rookies["sleeper_id"].astype(str).isin(taken_ids)
    else:
        mask_id = pd.Series(False, index=rookies.index)
    mask_name = rookies["name"].apply(lambda n: normalize_name(n) in taken_names)
    return rookies[~(mask_id | mask_name)].copy()


def _build_draft_order_from_sleeper(draft: dict, user_id: str | None,
                                     league_users: dict[str, str],
                                     traded_picks: list[dict] | None = None) -> list[dict]:
    """Build draft order from Sleeper draft metadata, accounting for traded picks."""
    settings = draft.get("settings", {})
    num_teams = settings.get("teams", 12)
    num_rounds = settings.get("rounds", 5)
    draft_type = draft.get("type", "linear")  # "linear" or "snake"
    reversal_round = settings.get("reversal_round", 0)
    season = draft.get("season", "2026")

    # slot_to_roster_id: {"1": 2, "2": 10, ...} — draft slot → roster_id
    slot_to_roster = {int(k): v for k, v in draft.get("slot_to_roster_id", {}).items()}
    roster_to_slot = {v: k for k, v in slot_to_roster.items()}

    # draft_order: {user_id: pick_slot} — who picks at which slot
    draft_order_map = draft.get("draft_order", {})

    # Build roster_id → display_name and slot → display_name
    roster_to_name = {}
    slot_to_name = {}
    for uid, slot in draft_order_map.items():
        roster_id = slot_to_roster.get(slot, slot)
        name = league_users.get(uid, f"Team {roster_id}")
        roster_to_name[roster_id] = name
        slot_to_name[slot] = name

    # Build traded picks map: (round, original_roster_id) → new_owner_roster_id
    trade_map = {}
    if traded_picks:
        for tp in traded_picks:
            if str(tp.get("season")) == str(season):
                trade_map[(tp["round"], tp["roster_id"])] = tp["owner_id"]

    # Find user's roster_id — try user_id first, then match by display name
    user_roster_id = None
    user_slot = None
    if user_id:
        if user_id in draft_order_map:
            user_slot = draft_order_map[user_id]
            user_roster_id = slot_to_roster.get(user_slot)
        else:
            # user_id not in draft_order — match by display name via league_users
            user_display = league_users.get(user_id)
            if user_display:
                for uid, slot in draft_order_map.items():
                    if league_users.get(uid) == user_display:
                        user_slot = slot
                        user_roster_id = slot_to_roster.get(user_slot)
                        break

    order = []
    for rd in range(1, num_rounds + 1):
        # Snake: reverse order on even rounds (or after reversal_round)
        is_reversed = False
        if draft_type == "snake":
            is_reversed = rd % 2 == 0
        elif reversal_round and rd >= reversal_round:
            is_reversed = rd % 2 == 0

        slots = list(range(1, num_teams + 1))
        if is_reversed:
            slots = list(reversed(slots))

        for i, slot in enumerate(slots):
            original_roster = slot_to_roster.get(slot, slot)
            # Check if this pick was traded
            actual_owner_roster = trade_map.get((rd, original_roster), original_roster)
            actual_owner_name = roster_to_name.get(actual_owner_roster, f"Team {actual_owner_roster}")

            is_user = actual_owner_roster == user_roster_id
            original_name = slot_to_name.get(slot, f"Slot {slot}")

            pick_num = (rd - 1) * num_teams + i + 1
            order.append({
                "pick": pick_num,
                "round": rd,
                "round_pick": i + 1,
                "slot": slot,
                "original_owner": original_name,
                "owner": actual_owner_name,
                "is_traded": actual_owner_roster != original_roster,
                "is_user": is_user,
            })

    return order, num_teams, num_rounds, user_slot


def _build_draft_order_manual(num_teams: int, num_rounds: int,
                               user_slot: int) -> list[dict]:
    """Build a simple linear draft order without Sleeper data."""
    order = []
    for rd in range(1, num_rounds + 1):
        for slot in range(1, num_teams + 1):
            pick_num = (rd - 1) * num_teams + slot
            order.append({
                "pick": pick_num,
                "round": rd,
                "round_pick": slot,
                "slot": slot,
                "owner": "You" if slot == user_slot else f"Team {slot}",
                "is_user": slot == user_slot,
            })
    return order


def _get_roster_strength(ownership_map: dict, merged_df: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Get positional strength per owner. Returns {owner: {pos: total_value}}."""
    if "owner" not in merged_df.columns:
        return {}
    strength = {}
    for owner in merged_df["owner"].dropna().unique():
        if owner in ("Free Agent", "Incoming Rookie", "Unknown"):
            continue
        team = merged_df[merged_df["owner"] == owner]
        pos_vals = {}
        for pos in POSITIONS:
            pos_team = team[team["position"] == pos]
            pos_vals[pos] = pos_team["blended_value"].sum() if "blended_value" in pos_team.columns else 0
        strength[owner] = pos_vals
    return strength


def _smart_auto_pick(available: pd.DataFrame, owner_name: str, rank_col: str,
                      roster_strength: dict, drafted_this_mock: dict,
                      draft_rules: list[dict] | None = None,
                      current_round: int = 1,
                      current_round_pick: int = 0) -> pd.Series:
    """Pick a player accounting for positional need, rules, and randomness."""
    if available.empty:
        return None

    # Check for forced pick rules first ("will draft player at pick")
    if draft_rules:
        for rule in draft_rules:
            if rule["manager"] not in ("All", owner_name):
                continue
            if (rule["type"] == "will draft player at pick"
                    and rule.get("round") == current_round
                    and rule.get("pick") == current_round_pick
                    and rule.get("player")):
                forced = available[available["name"] == rule["player"]]
                if not forced.empty:
                    return forced.iloc[0]

    # Apply manager rules to filter out ineligible players
    eligible = available
    if draft_rules:
        for rule in draft_rules:
            if rule["manager"] not in ("All", owner_name):
                continue
            r_type = rule["type"]
            r_pos = rule.get("position")
            r_round = rule.get("round")
            r_player = rule.get("player")

            r_pick = rule.get("pick")

            def _before_pick(cur_rd, cur_pk, rule_rd, rule_pk):
                """True if current pick is before the rule's round.pick."""
                return (cur_rd, cur_pk) < (rule_rd, rule_pk)

            if r_type == "won't draft position" and r_pos:
                eligible = eligible[eligible["position"] != r_pos]
            elif r_type == "won't draft position in round" and r_pos and r_round:
                if current_round == r_round:
                    eligible = eligible[eligible["position"] != r_pos]
            elif r_type == "won't draft position before round" and r_pos and r_round:
                if current_round < r_round:
                    eligible = eligible[eligible["position"] != r_pos]
            elif r_type == "won't draft position before pick" and r_pos and r_round and r_pick:
                if _before_pick(current_round, current_round_pick, r_round, r_pick):
                    eligible = eligible[eligible["position"] != r_pos]
            elif r_type == "won't draft player" and r_player:
                eligible = eligible[eligible["name"] != r_player]
            elif r_type == "won't draft player before pick" and r_player and r_round and r_pick:
                if _before_pick(current_round, current_round_pick, r_round, r_pick):
                    eligible = eligible[eligible["name"] != r_player]

        # If rules eliminated everyone, fall back to full available
        if eligible.empty:
            eligible = available

    scores = []
    # Existing roster strength for this owner
    owner_strength = roster_strength.get(owner_name, {})
    # Also count what they've drafted in this mock
    mock_pos_counts = drafted_this_mock.get(owner_name, {})

    # Determine positional need: gentle nudge, not an override.
    # Capped to [0.85, 1.20] so need can break a tie but can't make a team
    # reach 30+ ranks for positional fill.
    if owner_strength:
        total_vals = list(owner_strength.values())
        avg_val = np.mean(total_vals) if total_vals else 1
        pos_need = {}
        for pos in POSITIONS:
            val = owner_strength.get(pos, 0)
            mock_count = mock_pos_counts.get(pos, 0)
            if avg_val > 0:
                relative = val / avg_val
                # Weak position gets a small boost, strong position a small penalty
                need = max(0.85, min(1.20, 1.1 - relative * 0.1))
            else:
                need = 1.0
            # Small penalty if they already drafted this position
            need *= max(0.85, 1.0 - mock_count * 0.1)
            pos_need[pos] = need
    else:
        pos_need = {pos: 1.0 for pos in POSITIONS}

    # Score eligible players
    base_scores = []
    for _, player in eligible.iterrows():
        if "blended_value" in player.index and pd.notna(player["blended_value"]):
            base_score = player["blended_value"]
        else:
            rank = player[rank_col]
            base_score = 100.0 / max(rank, 1)

        need = pos_need.get(player["position"], 1.0)
        base_scores.append(base_score * need)

    # Add small noise that can only shuffle players within ~15% of each other.
    # This means a player scored at 80 can swap with one at ~70 but not one at 40.
    base_scores = np.array(base_scores)
    noise = np.random.uniform(0.92, 1.08, size=len(base_scores))
    final_scores = base_scores * noise

    best_idx = np.argmax(final_scores)
    return eligible.iloc[best_idx]


def _init_draft_state(draft_order: list[dict]):
    st.session_state["draft_picks"] = []
    st.session_state["draft_order"] = draft_order
    st.session_state["draft_current_pick"] = 0
    st.session_state["draft_active"] = True


def render():
    st.header("Rookie Draft Wizard")
    with st.expander("How it works"):
        st.markdown("""
**Draft Board** shows rookie rankings from three sources side by side — LateRound, FantasyCalc, and KeepTradeCut — so you can compare where they agree and disagree before your draft.

**Mock Draft Simulator** runs a full mock of your rookie draft. If you're connected to a Sleeper league, it auto-detects your draft settings (teams, rounds, pick order) and accounts for traded picks. Otherwise you can configure manually or paste a Sleeper draft ID.

When other teams pick, the simulator uses a **smart auto-pick** that considers:
- **Blended rankings** (50% LateRound, 25% FC, 25% KTC) as the base player value
- **Roster need** — teams weak at a position get a small nudge toward that position, but not enough to reach for a low-ranked player over a high-ranked one
- **Light randomness** — picks can shuffle within ~8% of each other so each mock plays out differently, but top-tier talent won't fall unrealistically

When it's **your turn**, you see the best available players, filter by position, and make your pick. Run it multiple times to explore different draft scenarios.

Use the **Rank by** setting in the sidebar to change which source drives the sort order and the auto-pick logic.
""")

    if not MERGED_PARQUET.exists():
        st.info("No data loaded. Click **Refresh Data** in the sidebar to get started.")
        return

    # --- Settings ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("Draft Settings")

    source_label = st.sidebar.radio(
        "Rank by", list(RANK_SOURCES.keys()), key="dw_source"
    )
    rank_col = RANK_SOURCES[source_label]

    st.sidebar.markdown("**Blend Weights**")
    w_lr = st.sidebar.slider("LateRound %", 0, 100, 20, 5, key="dw_w_lr")
    w_fc = st.sidebar.slider("FantasyCalc %", 0, 100, 20, 5, key="dw_w_fc")
    w_ktc = st.sidebar.slider("KeepTradeCut %", 0, 100, 20, 5, key="dw_w_ktc")
    w_draft = st.sidebar.slider("NFL Draft %", 0, 100, 20, 5, key="dw_w_draft")
    w_adp = st.sidebar.slider("ADP %", 0, 100, 20, 5, key="dw_w_adp")
    total_w = w_lr + w_fc + w_ktc + w_draft + w_adp
    if total_w == 0:
        total_w = 1
    blend_weights = {
        "lr": w_lr / total_w, "fc": w_fc / total_w, "ktc": w_ktc / total_w,
        "draft": w_draft / total_w, "adp": w_adp / total_w,
    }
    st.sidebar.caption(
        f"Effective: LR {blend_weights['lr']:.0%} / FC {blend_weights['fc']:.0%} / "
        f"KTC {blend_weights['ktc']:.0%} / Draft {blend_weights['draft']:.0%} / "
        f"ADP {blend_weights['adp']:.0%}"
    )

    # --- Manager rules ---
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Manager Rules**")

    if "draft_rules" not in st.session_state:
        st.session_state["draft_rules"] = []

    # Add new rule
    with st.sidebar.expander("Add rule"):
        # Get manager names from draft order if available
        manager_names = ["All"]
        if "ownership_map" in st.session_state:
            from ingestion.sleeper import get_league_users
            league_users = get_league_users(st.session_state.get("league_id", ""))
            manager_names += sorted(set(league_users.values()))

        rule_manager = st.selectbox("Manager", manager_names, key="dw_rule_mgr")
        rule_type = st.selectbox("Rule", [
            "won't draft position",
            "won't draft position in round",
            "won't draft position before round",
            "won't draft position before pick",
            "won't draft player",
            "won't draft player before pick",
            "will draft player at pick",
        ], key="dw_rule_type")

        rule_pos = None
        rule_round = None
        rule_pick = None
        rule_player = None

        if "position" in rule_type and "player" not in rule_type:
            rule_pos = st.selectbox("Position", POSITIONS, key="dw_rule_pos")
        if rule_type in ("won't draft position in round", "won't draft position before round"):
            rule_round = st.number_input("Round", 1, 10, 2, key="dw_rule_rd")
        if "before pick" in rule_type or "at pick" in rule_type:
            rule_round = st.number_input("Round", 1, 10, 1, key="dw_rule_rd2")
            rule_pick = st.number_input("Pick in round", 1, 16, 1, key="dw_rule_pick")
        if "player" in rule_type:
            rule_player = st.text_input("Player name", key="dw_rule_player")

        if st.button("Add Rule", key="dw_add_rule"):
            st.session_state["draft_rules"].append({
                "manager": rule_manager,
                "type": rule_type,
                "position": rule_pos,
                "round": rule_round,
                "pick": rule_pick,
                "player": rule_player,
            })
            st.rerun()

    # Display current rules
    rules = st.session_state["draft_rules"]
    if rules:
        for i, rule in enumerate(rules):
            label = f"{rule['manager']}: {rule['type']}"
            if rule.get("position"):
                label += f" {rule['position']}"
            if rule.get("round") and rule.get("pick"):
                label += f" Rd{rule['round']}.{rule['pick']}"
            elif rule.get("round"):
                label += f" Rd{rule['round']}"
            if rule.get("player"):
                label += f" {rule['player']}"
            col_rule, col_del = st.sidebar.columns([4, 1])
            col_rule.caption(label)
            if col_del.button("x", key=f"dw_del_rule_{i}"):
                st.session_state["draft_rules"].pop(i)
                st.rerun()
    else:
        st.sidebar.caption("No rules set")

    # --- Draft source: auto-detect from league, fallback to manual entry ---
    draft_order = None
    num_teams = 12
    num_rounds = 5
    user_slot = 1
    draft = None

    if "league_id" in st.session_state:
        from ingestion.sleeper import get_league_drafts, get_draft, get_league_users, get_traded_picks

        league_id = st.session_state["league_id"]
        league_drafts = get_league_drafts(league_id)

        # Find upcoming rookie drafts (player_type=1, not yet completed)
        rookie_drafts = [
            d for d in league_drafts
            if d.get("settings", {}).get("player_type") == 1
            and d.get("status") in ("pre_draft", "drafting")
        ]

        # If none upcoming, fall back to all rookie drafts
        if not rookie_drafts:
            rookie_drafts = [
                d for d in league_drafts
                if d.get("settings", {}).get("player_type") == 1
            ]

        if rookie_drafts:
            if len(rookie_drafts) == 1:
                selected_draft_id = rookie_drafts[0]["draft_id"]
            else:
                draft_options = {
                    f"{d.get('season')} — {d.get('status', 'unknown')} ({d['draft_id']})": d["draft_id"]
                    for d in rookie_drafts
                }
                selected = st.sidebar.selectbox("Rookie Draft", list(draft_options.keys()), key="dw_draft_select")
                selected_draft_id = draft_options[selected]
            # Fetch full draft details (league/drafts endpoint is missing slot_to_roster_id)
            draft = get_draft(selected_draft_id)

    # Fallback: manual draft ID input
    if draft is None:
        draft_id = st.sidebar.text_input("Sleeper Draft ID", key="dw_draft_id",
                                          help="Paste the draft ID from your Sleeper draft URL")
        if draft_id:
            from ingestion.sleeper import get_draft, get_league_users, get_traded_picks
            draft = get_draft(draft_id.strip())
            if draft is None:
                st.sidebar.error("Draft not found. Check the ID.")

    # Build draft order from Sleeper draft
    if draft:
        draft_league_id = draft.get("league_id", st.session_state.get("league_id", ""))
        if "get_league_users" not in dir():
            from ingestion.sleeper import get_league_users, get_traded_picks
        league_users = get_league_users(draft_league_id) if draft_league_id else {}
        traded_picks = get_traded_picks(draft_league_id) if draft_league_id else []
        current_user_id = st.session_state.get("user_id")

        draft_order, num_teams, num_rounds, detected_slot = (
            _build_draft_order_from_sleeper(
                draft, current_user_id, league_users, traded_picks
            )
        )

        st.sidebar.caption(
            f"Draft: {draft.get('draft_id')}  \n"
            f"Season: {draft.get('season')} | Status: {draft.get('status')}"
        )

        if detected_slot:
            user_slot = detected_slot
            st.sidebar.success(f"You pick at slot {user_slot}")
        else:
            st.sidebar.warning("Couldn't detect your slot")
            user_slot = st.sidebar.number_input(
                "Your pick slot", 1, num_teams, 1, key="dw_slot_override"
            )
            for pick in draft_order:
                pick["is_user"] = pick["slot"] == user_slot

        st.sidebar.caption(
            f"{num_teams} teams, {num_rounds} rounds, "
            f"{draft.get('type', 'linear')} draft"
        )

    if draft_order is None:
        # Full manual mode
        num_teams = st.sidebar.number_input("Teams", 4, 16, 12, key="dw_teams")
        num_rounds = st.sidebar.number_input("Rounds", 1, 10, 5, key="dw_rounds")
        user_slot = st.sidebar.number_input("Your pick slot", 1, num_teams, 1, key="dw_slot")
        draft_order = _build_draft_order_manual(num_teams, num_rounds, user_slot)

    rookies = _get_rookies(rank_col, blend_weights)

    # Live availability for the first-page cards/board
    available = rookies
    if draft and draft.get("draft_id"):
        available = _available_after_live_picks(rookies, draft["draft_id"])

    tab_board, tab_mock, tab_recap = st.tabs(
        ["Draft Board", "Mock Draft Simulator", "Draft Recap"])

    with tab_board:
        _render_draft_board(rookies, available, rank_col, source_label, draft)

    with tab_mock:
        _render_mock_draft(rookies, draft_order, rank_col, num_teams,
                           num_rounds, user_slot, rules)

    with tab_recap:
        from views.draft_value import render_draft_value_recap
        render_draft_value_recap(rookies, draft, st.session_state.get("league_id", ""))


def _render_draft_board(rookies, available, rank_col, source_label, draft):
    from views.draft_board import (render_best_available_cards,
                                   render_sortable_board, render_disagreements)

    # Mobile-first controls in the main pane (not the sidebar drawer)
    c1, c2 = st.columns([2, 1])
    with c1:
        top_n = st.radio("Cards per position", [2, 3], horizontal=True,
                         index=0, key="dw_top_n")
    with c2:
        if draft and draft.get("draft_id"):
            if st.button("↻ Refresh picks", use_container_width=True):
                from ingestion.sleeper import get_draft_picks
                get_draft_picks.clear()
                st.rerun()

    n_taken = len(rookies) - len(available)
    if draft and draft.get("draft_id"):
        st.caption(f"Live: {n_taken} drafted · {len(available)} available · sorted by {source_label}")
    else:
        st.caption(f"No live draft connected — showing overall best available · sorted by {source_label}")

    render_best_available_cards(available, rank_col, top_n=top_n)

    st.markdown("---")
    pos_filter = st.radio("Position", ["All"] + POSITIONS, horizontal=True, key="dw_board_pos")
    board = available if pos_filter == "All" else available[available["position"] == pos_filter]
    render_sortable_board(board)

    st.markdown("---")
    render_disagreements(available)


def _render_mock_draft(rookies, draft_order, rank_col, num_teams, num_rounds, user_slot, rules):
    st.subheader("Mock Draft Simulator")

    user_picks_in_draft = [p for p in draft_order if p["is_user"]]
    pick_parts = []
    for p in user_picks_in_draft:
        label = f"Rd{p['round']}.{p['round_pick']}"
        if p.get("is_traded"):
            label += f" (via {p.get('original_owner', '?')})"
        pick_parts.append(label)
    pick_summary = ", ".join(pick_parts) if pick_parts else "none"
    st.caption(f"{num_teams} teams, {num_rounds} rounds — your picks: {pick_summary}")

    col_start, col_step = st.columns([1, 1])
    with col_start:
        if st.button("Start New Mock Draft", type="primary"):
            _init_draft_state(draft_order)
            st.rerun()
    with col_step:
        auto_advance = st.checkbox("Auto-advance picks", value=True, key="dw_auto")

    if not st.session_state.get("draft_active"):
        # Show empty draft board grid
        _render_draft_board_grid(draft_order, [], num_teams, num_rounds)
        st.info("Click **Start New Mock Draft** to begin.")
        return

    picks = st.session_state["draft_picks"]
    current_idx = st.session_state["draft_current_pick"]
    total_picks = len(draft_order)

    drafted_names = {p["player"] for p in picks}
    available = rookies[~rookies["name"].isin(drafted_names)].copy()

    if current_idx >= total_picks or available.empty:
        st.session_state["draft_active"] = False
        _render_draft_board_grid(draft_order, picks, num_teams, num_rounds)
        st.success("Draft complete!")
        _render_your_haul(picks)
        return

    current_pick = draft_order[current_idx]

    # Auto-pick: advance one pick at a time (or batch until user's turn)
    if not current_pick["is_user"]:
        roster_strength = {}
        if "ownership_map" in st.session_state:
            full_df = pd.read_parquet(MERGED_PARQUET)
            from ingestion.ownership import annotate_ownership
            full_df = annotate_ownership(full_df, st.session_state["ownership_map"])
            roster_strength = _get_roster_strength(
                st.session_state["ownership_map"], full_df
            )

        drafted_this_mock: dict[str, dict[str, int]] = {}
        for p in picks:
            owner = p["owner"]
            pos = p.get("player_pos", "")
            drafted_this_mock.setdefault(owner, {})
            drafted_this_mock[owner][pos] = drafted_this_mock[owner].get(pos, 0) + 1

        if auto_advance:
            # Make one pick at a time, then rerun to animate
            pick_info = draft_order[current_idx]
            if not available.empty:
                best = _smart_auto_pick(
                    available, pick_info["owner"], rank_col,
                    roster_strength, drafted_this_mock,
                    draft_rules=rules,
                    current_round=pick_info["round"],
                    current_round_pick=pick_info["round_pick"],
                )
                picks.append({
                    **pick_info,
                    "player": best["name"],
                    "player_pos": best["position"],
                    "player_rank": best[rank_col],
                })
                st.session_state["draft_picks"] = picks
                st.session_state["draft_current_pick"] = current_idx + 1

                # Show board with this pick, then auto-rerun after a moment
                _render_draft_board_grid(draft_order, picks, num_teams, num_rounds)

                import time
                time.sleep(0.4)
                st.rerun()
        else:
            # Batch all picks until user's turn
            while current_idx < total_picks and not draft_order[current_idx]["is_user"]:
                pick_info = draft_order[current_idx]
                if available.empty:
                    break
                best = _smart_auto_pick(
                    available, pick_info["owner"], rank_col,
                    roster_strength, drafted_this_mock,
                    draft_rules=rules,
                    current_round=pick_info["round"],
                    current_round_pick=pick_info["round_pick"],
                )
                picks.append({
                    **pick_info,
                    "player": best["name"],
                    "player_pos": best["position"],
                    "player_rank": best[rank_col],
                })
                owner = pick_info["owner"]
                drafted_this_mock.setdefault(owner, {})
                drafted_this_mock[owner][best["position"]] = drafted_this_mock[owner].get(best["position"], 0) + 1
                drafted_names.add(best["name"])
                available = available[available["name"] != best["name"]]
                current_idx += 1

            st.session_state["draft_picks"] = picks
            st.session_state["draft_current_pick"] = current_idx

        # Re-check state after picks
        current_idx = st.session_state["draft_current_pick"]
        if current_idx >= total_picks:
            st.session_state["draft_active"] = False
            _render_draft_board_grid(draft_order, picks, num_teams, num_rounds)
            st.success("Draft complete!")
            _render_your_haul(picks)
            return

        available = rookies[~rookies["name"].isin({p["player"] for p in picks})].copy()
        if available.empty:
            st.session_state["draft_active"] = False
            _render_draft_board_grid(draft_order, picks, num_teams, num_rounds)
            st.success("Draft complete!")
            _render_your_haul(picks)
            return

        current_pick = draft_order[current_idx]
        if not current_pick["is_user"]:
            # Still not user's turn (batch mode showing intermediate state)
            _render_draft_board_grid(draft_order, picks, num_teams, num_rounds)
            return

    # --- Draft board grid (tap your 🎯 pick tile to toggle best available) ---
    _render_draft_board_grid(draft_order, picks, num_teams, num_rounds,
                             on_pick_click=(current_pick["round"], current_pick["round_pick"]))

    # --- User's turn ---
    st.markdown("---")
    st.markdown(
        f"### Your Pick: Round {current_pick['round']}, "
        f"Pick {current_pick['round_pick']} (#{current_pick['pick']} overall)"
    )

    from views.draft_board import render_best_available_cards, render_sortable_board
    pick_pos = st.radio("Filter", ["All"] + POSITIONS, horizontal=True, key="dw_pick_pos")
    if pick_pos != "All":
        pick_available = available[available["position"] == pick_pos]
    else:
        pick_available = available

    if st.session_state.get("dw_best_avail_open", True):
        render_best_available_cards(pick_available, rank_col, top_n=3)
    else:
        st.caption("Tap your 🎯 pick tile above to show best available by position.")

    render_sortable_board(pick_available.head(30))

    player_options = pick_available["name"].head(30).tolist()
    if player_options:
        selected_player = st.selectbox("Select player to draft", player_options, key="dw_pick_select")
        if st.button(f"Draft {selected_player}", type="primary", key="dw_draft_btn"):
            player_row = available[available["name"] == selected_player].iloc[0]
            picks.append({
                **current_pick,
                "player": selected_player,
                "player_pos": player_row["position"],
                "player_rank": player_row[rank_col],
            })
            st.session_state["draft_picks"] = picks
            st.session_state["draft_current_pick"] = current_idx + 1
            st.rerun()


POS_COLORS = {"QB": "#e41a1c", "RB": "#377eb8", "WR": "#4daf4a", "TE": "#ff7f00"}


def _board_row_html(rd, rp, owner, is_user, is_traded, original, pick) -> str:
    """One full-width draft-board row (mobile-friendly), shown in draft order."""
    lb = "#4CAF50" if is_user else "#444"
    via = f" <span style='color:#777'>via {original}</span>" if is_traded else ""
    if pick:
        pos = pick.get("player_pos", "")
        color = POS_COLORS.get(pos, "#666")
        rank = pick.get("player_rank")
        rstr = f"#{rank:.0f}" if rank else ""
        right = (f"<b style='color:{color}'>{pick.get('player', '')}</b>"
                 f" <span style='color:#888;font-size:0.85em'>{pos} {rstr}</span>")
        bg = "#1a1a2e"
    else:
        right = "<span style='color:#666'>—</span>"
        bg = "#111"
    return (
        f"<div style='display:flex;justify-content:space-between;align-items:center;gap:10px;"
        f"border-left:4px solid {lb};background:{bg};border-radius:6px;padding:5px 9px;margin:2px 0'>"
        f"<span style='color:#9aa;font-size:0.78em;white-space:nowrap'>{rd}.{rp} · {owner}{via}</span>"
        f"<span style='font-size:0.9em;text-align:right'>{right}</span></div>"
    )


def _render_draft_board_grid(draft_order: list[dict], picks: list[dict],
                              num_teams: int, num_rounds: int,
                              on_pick_click: tuple | None = None):
    """Mobile-friendly vertical draft board: rounds as headers, picks as full-width
    rows in draft order (snake-aware). The user's on-the-clock pick (on_pick_click)
    renders as a button toggling the best-available cards (`dw_best_avail_open`)."""
    pick_map = {(p["round"], p["round_pick"]): p for p in picks}
    order_map = {(p["round"], p["round_pick"]): p for p in draft_order}

    for rd in range(1, num_rounds + 1):
        st.markdown(f"**Round {rd}**")
        buffer: list[str] = []  # batch HTML rows; flush around the clickable button
        for rp in range(1, num_teams + 1):
            info = order_map.get((rd, rp), {})
            owner = info.get("owner", f"Slot {rp}")
            is_user = info.get("is_user", False)
            is_traded = info.get("is_traded", False)
            original = info.get("original_owner", "")
            pick = pick_map.get((rd, rp))

            if pick is None and on_pick_click is not None and (rd, rp) == on_pick_click:
                if buffer:
                    st.markdown("".join(buffer), unsafe_allow_html=True)
                    buffer = []
                is_open = st.session_state.get("dw_best_avail_open", True)
                label = f"🎯 {rd}.{rp} YOU — " + ("hide best avail" if is_open else "best available")
                if st.button(label, key=f"dw_picktile_{rd}_{rp}", use_container_width=True):
                    st.session_state["dw_best_avail_open"] = not is_open
                    st.rerun()
            else:
                buffer.append(_board_row_html(rd, rp, owner, is_user, is_traded, original, pick))
        if buffer:
            st.markdown("".join(buffer), unsafe_allow_html=True)


def _render_your_haul(picks: list[dict]):
    user_picks = [p for p in picks if p["is_user"]]
    if user_picks:
        st.subheader("Your Haul")
        cols = st.columns(len(user_picks))
        for col, p in zip(cols, user_picks):
            pos = p.get("player_pos", "")
            color = POS_COLORS.get(pos, "#666")
            via = f" (via {p['original_owner']})" if p.get("is_traded") else ""
            with col:
                st.markdown(
                    f"<div style='border:2px solid #4CAF50;border-radius:10px;padding:12px;"
                    f"background:#1a1a2e;text-align:center'>"
                    f"<div style='font-size:0.8em;color:#aaa'>Rd {p['round']} Pick {p['round_pick']}{via}</div>"
                    f"<div style='font-size:1.2em;font-weight:bold;color:{color}'>{p['player']}</div>"
                    f"<div style='font-size:0.85em;color:#888'>{pos} — Rank {p['player_rank']:.0f}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
