"""
Central catalogue of all scorecard subcategory metrics.
Shared by domain_detail.py, overview.py, and seed helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Rating thresholds (% of target achieved)
# ---------------------------------------------------------------------------
RATING_NEEDS_ATTENTION = ("NEEDS ATTENTION", "#C62828", "#3b0a0a")   # < 40 %
RATING_IN_PROGRESS     = ("IN PROGRESS",     "#F9A825", "#3b2a00")   # 40–69 %
RATING_ON_TRACK        = ("ON TRACK",        "#2E7D32", "#0a2b0a")   # 70–89 %
RATING_ACHIEVED        = ("ACHIEVED",        "#00838F", "#00222a")   # ≥ 90 %


def get_rating(pct: float) -> tuple[str, str, str]:
    """Return (label, text_color, bg_color) for a given % of target achieved."""
    if pct >= 90:
        return RATING_ACHIEVED
    if pct >= 70:
        return RATING_ON_TRACK
    if pct >= 40:
        return RATING_IN_PROGRESS
    return RATING_NEEDS_ATTENTION


# ---------------------------------------------------------------------------
# Metric definition
# ---------------------------------------------------------------------------
@dataclass
class Metric:
    metric_id: str
    domain: str
    label: str
    target: float
    current: float          # seeded "baseline" current value
    unit: str
    jitter: float = 0.0     # seed noise std-dev (0 = flat across months)
    integer: bool = False   # round to int when seeding


# ---------------------------------------------------------------------------
# Domain colours
# ---------------------------------------------------------------------------
DOMAIN_COLOR: dict[str, str] = {
    "housing":        "#1B5E20",
    "transportation": "#E65100",
    "healthcare":     "#1A237E",
    "employment":     "#4A148C",
    "placemaking":    "#004D40",
}

DOMAIN_ICON: dict[str, str] = {
    "housing":        "🏠",
    "transportation": "🚌",
    "healthcare":     "🏥",
    "employment":     "💼",
    "placemaking":    "🌳",
}

DOMAIN_PRIMARY_METRIC: dict[str, str] = {
    "housing":        "building_homes_needed",
    "transportation": "transit_ridership_target",
    "healthcare":     "residents_with_doctor",
    "employment":     "jobs_secured",
    "placemaking":    "childcare_access",
}


# ---------------------------------------------------------------------------
# Full catalogue
# ---------------------------------------------------------------------------
SCORECARD_METRICS: list[Metric] = [
    # ── HOUSING ────────────────────────────────────────────────────────────
    Metric("building_homes_needed",    "housing",  "Building the Homes We Need",
           target=15000, current=10500, unit="units/yr",   jitter=250,  integer=True),
    Metric("affordable_housing_units", "housing",  "New Affordable Housing Units",
           target=3000,  current=2800,  unit="units",      jitter=50,   integer=True),
    Metric("water_wastewater_capacity","housing",  "Water & Wastewater Capacity",
           target=100,   current=72,    unit="percent",    jitter=1.5),
    Metric("balanced_rental_market",   "housing",  "Balanced Market for Rental Housing",
           target=3.0,   current=2.4,   unit="vacancy_pct",jitter=0.1),
    Metric("homelessness_funding",     "housing",  "Funding for People Experiencing Homelessness",
           target=100,   current=35,    unit="percent",    jitter=1.5),

    # ── TRANSPORTATION ─────────────────────────────────────────────────────
    Metric("rail_transit_investment",  "transportation", "Investing in Rail & Transit Infrastructure",
           target=100,  current=55,    unit="percent",      jitter=1.0),
    Metric("highway_7",                "transportation", "New Highway 7",
           target=100,  current=45,    unit="percent",      jitter=1.0),
    Metric("ykf_expansion",            "transportation", "Expanding YKF Airport",
           target=100,  current=50,    unit="percent",      jitter=1.0),
    Metric("transit_ridership_target", "transportation", "Increase Use of Public Transit",
           target=2_000_000, current=1_830_051, unit="trips/month", jitter=30_000, integer=True),
    Metric("go_train_service",         "transportation", "Better GO Train Service",
           target=100,  current=40,    unit="percent",      jitter=1.0),

    # ── HEALTHCARE ─────────────────────────────────────────────────────────
    Metric("new_hospital",             "healthcare", "New Hospital",
           target=100, current=85,  unit="percent",   jitter=0.5),
    Metric("residents_with_doctor",    "healthcare", "Residents Connected to a Doctor",
           target=100, current=78,  unit="percent",   jitter=0.8),
    Metric("ltc_access",               "healthcare", "Improved Access to LTC",
           target=100, current=45,  unit="percent",   jitter=1.0),
    Metric("acute_care",               "healthcare", "Acute Care Capacity",
           target=100, current=38,  unit="percent",   jitter=1.0),
    Metric("er_wait_target",           "healthcare", "Emergency Department Wait Times",
           target=3.0, current=3.8, unit="hours",     jitter=0.15),
    Metric("mental_health_support",    "healthcare", "Mental Health & Addiction Support",
           target=100, current=52,  unit="percent",   jitter=1.0),

    # ── EMPLOYMENT ─────────────────────────────────────────────────────────
    Metric("employment_lands",         "employment", "Adding Employment Lands",
           target=100,   current=35,    unit="percent",       jitter=0.8),
    Metric("megasite",                 "employment", "Shovel-Ready Megasite",
           target=100,   current=72,    unit="percent",       jitter=0.5),
    Metric("jobs_secured",             "employment", "Securing the Jobs Needed",
           target=50_000, current=28_000, unit="jobs",        jitter=500, integer=True),
    Metric("regional_employment",      "employment", "Strong Regional Employment",
           target=96,    current=95,    unit="percent_employed", jitter=0.2),
    Metric("tech_talent",              "employment", "Leading Region for Tech Talent",
           target=100,   current=65,    unit="percent",       jitter=0.8),
    Metric("postsecondary",            "employment", "Post-Secondary Investment",
           target=100,   current=38,    unit="percent",       jitter=1.0),
    Metric("electrical_capacity",      "employment", "Electrical Capacity",
           target=100,   current=55,    unit="percent",       jitter=0.8),

    # ── PLACEMAKING ────────────────────────────────────────────────────────
    Metric("tourism_recreation",       "placemaking", "Tourism & Recreation Facilities",
           target=100, current=32,  unit="percent",  jitter=0.8),
    Metric("school_spaces",            "placemaking", "Increase Spaces in Schools",
           target=100, current=61,  unit="percent",  jitter=0.8),
    Metric("childcare_access",         "placemaking", "Childcare for Everyone Who Needs It",
           target=100, current=55,  unit="percent",  jitter=0.8),
    Metric("ghg_reduction",            "placemaking", "Reducing Greenhouse Gases",
           target=100, current=48,  unit="percent",  jitter=0.8),
    Metric("community_safety",         "placemaking", "Creating a Safer Community",
           target=100, current=58,  unit="percent",  jitter=0.8),
    Metric("social_infrastructure",    "placemaking", "Increasing Social Infrastructure",
           target=100, current=50,  unit="percent",  jitter=0.8),
]

# Quick lookup by metric_id
METRIC_BY_ID: dict[str, Metric] = {m.metric_id: m for m in SCORECARD_METRICS}

# Grouped by domain
METRICS_BY_DOMAIN: dict[str, list[Metric]] = {}
for _m in SCORECARD_METRICS:
    METRICS_BY_DOMAIN.setdefault(_m.domain, []).append(_m)


# Metrics where a LOWER value is better; we invert the ratio so the dashboard
# correctly reads "below target = bad, at/above target = achieved".
LOWER_IS_BETTER: set[str] = {"er_wait_target"}


def pct_achieved(metric_id: str, current_value: float) -> float:
    """Return % of target achieved (0–100), capped at 100."""
    m = METRIC_BY_ID.get(metric_id)
    if m is None or m.target == 0:
        return 0.0
    if metric_id in LOWER_IS_BETTER:
        raw = (m.target / current_value) * 100 if current_value > 0 else 0.0
    else:
        raw = (current_value / m.target) * 100
    return round(min(raw, 100.0), 1)
