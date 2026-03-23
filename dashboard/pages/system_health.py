from __future__ import annotations

import subprocess
from pathlib import Path

import streamlit as st

from db import get_system_health


def _status_color(status: str) -> str:
    s = (status or "").lower()
    if s == "success":
        return "#00C853"
    if s in {"failed", "fallback"}:
        return "#ff5252"
    return "#b0bec5"


def render() -> None:
    st.subheader("System Health")
    health = get_system_health()
    if health.empty:
        st.info("No health records available yet.")
    else:
        statuses = health["source_status"].astype(str).str.lower()
        successes = int((statuses == "success").sum())
        failures = int((statuses.isin(["failed", "fallback"])).sum())
        c1, c2 = st.columns(2)
        c1.metric("Successes", successes)
        c2.metric("Failures/Fallbacks", failures)

        def _style_status(value: object) -> str:
            return f"color: {_status_color(str(value))}; font-weight: 700;"

        display = health.rename(columns={"label": "name"})[
            ["name", "last_updated", "source_status", "metric_id", "domain"]
        ]
        st.dataframe(
            display.style.map(_style_status, subset=["source_status"]),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("### Pipeline Control")
    if st.button("Run Pipeline Now", type="primary"):
        try:
            root = Path(__file__).resolve().parents[2]
            proc = subprocess.run(
                ["python", "main.py"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0:
                st.success("Pipeline run completed successfully.")
            else:
                st.error("Pipeline run failed.")
            if proc.stdout:
                st.code(proc.stdout[:8000])
            if proc.stderr:
                st.code(proc.stderr[:8000])
        except Exception as exc:
            st.error(f"Failed to execute pipeline: {exc}")
