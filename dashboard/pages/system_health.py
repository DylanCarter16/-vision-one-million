from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from db import get_system_health

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ACCENT = "#00C853"
WARN = "#FFB300"
DANGER = "#FF5252"
CARD_BG = "#1E2329"

def _badge(status: str) -> str:
    s = (status or "").lower()
    if s == "success":
        color, bg = "#2E7D32", "#0a2a0a"
    elif s == "fallback":
        color, bg = "#1565C0", "#0a1a2e"
    else:
        color, bg = "#C62828", "#2d0a0a"
    return (
        f"<span style='display:inline-block;padding:2px 10px;border-radius:10px;"
        f"background:{bg};color:{color};border:1px solid {color}44;"
        f"font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;'>"
        f"{s or 'unknown'}</span>"
    )


def render() -> None:
    st.markdown(
        "<h1 style='font-size:1.6rem;font-weight:800;color:#E6EDF3;margin-bottom:4px;'>System Health</h1>"
        "<p style='color:#8B949E;font-size:0.9rem;margin-bottom:24px;'>Pipeline status and data refresh controls</p>",
        unsafe_allow_html=True,
    )

    # ── Refresh button ─────────────────────────────────────────────────────
    if "last_refresh" not in st.session_state:
        st.session_state["last_refresh"] = None

    last_refresh = st.session_state["last_refresh"]
    last_refresh_str = (
        f"Last refreshed: **{last_refresh}**"
        if last_refresh
        else "Pipeline has not been run this session."
    )

    col_btn, col_status = st.columns([2, 5], gap="large")
    with col_btn:
        run_clicked = st.button("🔄 Refresh Data Now", type="primary", use_container_width=True)
    with col_status:
        st.markdown(
            f"<p style='color:#8B949E;font-size:0.88rem;padding-top:8px;'>{last_refresh_str}</p>",
            unsafe_allow_html=True,
        )

    if run_clicked:
        with st.spinner("Running pipeline — fetching latest data…"):
            try:
                from main import run_pipeline  # noqa: PLC0415
                successes, total = run_pipeline()
                now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                st.session_state["last_refresh"] = now
                result_text = f"Pipeline complete: {successes}/{total} metrics updated"
                st.success(f"{result_text} — refreshed at {now}")
            except ImportError:
                # Fall back to subprocess when direct import is unavailable
                import subprocess
                proc = subprocess.run(
                    [sys.executable, str(ROOT / "main.py")],
                    capture_output=True, text=True, cwd=str(ROOT),
                )
                now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                st.session_state["last_refresh"] = now
                if proc.returncode == 0:
                    st.success(f"Pipeline complete — refreshed at {now}")
                else:
                    st.error(f"Pipeline error (subprocess):\n{proc.stderr[-800:]}")
            except Exception as exc:
                st.error(f"Pipeline error: {exc}")

        # Bust st.cache_data so tables reload with fresh data
        st.cache_data.clear()

    st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)

    # ── Summary counters ───────────────────────────────────────────────────
    health = get_system_health()
    if health.empty:
        st.info("No health records in the database yet.")
        return

    statuses = health["source_status"].astype(str).str.lower()
    n_success = int((statuses == "success").sum())
    n_fallback = int((statuses == "fallback").sum())
    n_failed = int((statuses == "failed").sum())

    c1, c2, c3 = st.columns(3, gap="small")
    for col, label, val, color in [
        (c1, "Successful", n_success, ACCENT),
        (c2, "Fallback", n_fallback, WARN),
        (c3, "Failed", n_failed, DANGER),
    ]:
        col.markdown(
            f"""<div style='background:{CARD_BG};border:1px solid #30363D;border-radius:12px;padding:18px 20px;text-align:center;'>
            <p style='color:#8B949E;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;margin:0 0 6px;'>{label}</p>
            <p style='color:{color};font-size:2rem;font-weight:800;margin:0;'>{val}</p>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)

    # ── Per-metric table ───────────────────────────────────────────────────
    st.markdown(
        "<h2 style='font-size:1.1rem;font-weight:700;color:#E6EDF3;margin-bottom:12px;'>Metric Source Status</h2>",
        unsafe_allow_html=True,
    )

    display = health.copy()
    display["Status"] = display["source_status"].astype(str).str.lower()
    display["Last Updated"] = display["last_updated"].astype(str).str[:16].str.replace("T", " ")
    display = display.rename(columns={"label": "Metric", "domain": "Domain", "metric_id": "Metric ID"})
    cols_show = ["Domain", "Metric", "Metric ID", "Last Updated", "Status"]
    cols_show = [c for c in cols_show if c in display.columns]

    st.dataframe(
        display[cols_show],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Domain":      st.column_config.TextColumn("Domain"),
            "Metric":      st.column_config.TextColumn("Metric"),
            "Metric ID":   st.column_config.TextColumn("Metric ID"),
            "Last Updated": st.column_config.TextColumn("Last Updated"),
            "Status":      st.column_config.TextColumn("Status"),
        },
    )
