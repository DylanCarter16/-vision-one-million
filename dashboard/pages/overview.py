from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.db import get_all_metrics

DOMAIN_ORDER = ["housing", "transportation", "healthcare", "employment", "placemaking"]
TARGETS = {d: 1_000_000 for d in DOMAIN_ORDER}


def render() -> None:
    st.subheader("Overview")
    df = get_all_metrics()
    if df.empty:
        st.info("No metrics available yet in data/scorecard.db.")
        return

    cols = st.columns(len(DOMAIN_ORDER))
    for i, domain in enumerate(DOMAIN_ORDER):
        d = df[df["domain"].str.lower() == domain]
        headline = float(d["value"].dropna().iloc[0]) if not d.empty else 0.0
        label = d["label"].iloc[0] if not d.empty else "No metric"
        cols[i].metric(domain.title(), f"{headline:,.2f}", help=label)

    st.markdown("### Progress Toward One Million")
    for domain in DOMAIN_ORDER:
        d = df[df["domain"].str.lower() == domain]
        current = float(pd.to_numeric(d["value"], errors="coerce").fillna(0).sum()) if not d.empty else 0.0
        target = float(TARGETS[domain])
        pct = max(0.0, min(1.0, current / target if target else 0.0))
        st.write(f"{domain.title()}: {current:,.0f} / {target:,.0f} ({pct * 100:.1f}%)")
        st.progress(pct)

    out = df.copy()
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.sort_values(["domain", "metric_id"])
    st.markdown("### Latest Metrics")
    st.dataframe(out, use_container_width=True)
