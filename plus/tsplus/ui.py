"""Shared page shell for the Plus pages: settings, cached data, styling and navigation."""

from datetime import date
from html import escape
import os
from pathlib import Path

import streamlit as st

from tsplus import PLUS_DIR, REPO_ROOT
from tsplus.store import load_all, load_report
from tenantshield.data import DataError
from tenantshield.design import branding_image, section  # noqa: F401  (re-exported for pages)

PAGES = (
    ("app.py", "Building Check", ":material/apartment:"),
    ("pages/Compare_Shortlist.py", "Compare Shortlist", ":material/compare_arrows:"),
    ("pages/Area_Explorer.py", "Area Explorer", ":material/travel_explore:"),
    ("pages/Evidence.py", "Evidence & Method", ":material/menu_book:"),
)
MAX_SHORTLIST = 4


def setting(name: str, default: str = "") -> str:
    """Environment variables first, then Streamlit secrets. Never shown in the UI."""
    value = os.environ.get(name)
    if value is not None:
        return value.strip()
    try:
        return str(st.secrets.get(name, default)).strip()
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return default


def _path(name: str, default: Path) -> Path:
    path = Path(setting(name, str(default)))
    return path if path.is_absolute() else REPO_ROOT / path


@st.cache_data(show_spinner=False)
def _cached(base: str, plus: str, report: str, stamps: tuple):
    frame, warnings = load_all(base, plus)
    return frame, warnings, load_report(report)


def load():
    """Validated building table, load warnings and the offline backtest report; stops the page on bad data."""
    base = _path("TENANTSHIELD_DATA_PATH", REPO_ROOT / "TenantShield_App_Data.csv")
    plus = _path("TENANTSHIELD_PLUS_DATA_PATH", PLUS_DIR / "data" / "plus_predictions.csv")
    report = _path("TENANTSHIELD_PLUS_REPORT_PATH", PLUS_DIR / "data" / "plus_report.json")
    try:
        # File size and modification time invalidate the cache when a file is rebuilt.
        stamps = tuple((item.stat().st_mtime_ns, item.stat().st_size) for item in (base, plus, report))
        with st.spinner("Loading building records…"):
            frame, warnings, loaded = _cached(str(base), str(plus), str(report), stamps)
    except (OSError, DataError) as exc:
        st.error(str(exc) if isinstance(exc, DataError) else
                 "A data file is missing or unreadable. See plus/README.md to rebuild the Plus files.")
        st.stop()
    for warning in warnings:
        st.warning(warning)
    return frame, loaded


def shell(title: str = "TenantShield Plus") -> None:
    """Page config, shared styles and sidebar navigation. Call once at the top of every page."""
    st.set_page_config(page_title=f"{title} | TenantShield Plus",
                       page_icon=branding_image("tenantshield_favicon.png") or ":material/apartment:",
                       layout="wide", initial_sidebar_state="auto")
    css = (REPO_ROOT / "assets" / "style.css").read_text(encoding="utf-8")
    css += (PLUS_DIR / "assets" / "plus.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    with st.sidebar:
        shield = branding_image("tenantshield_icon.png")
        mark = f'<img class="ts-brand-shield" src="{shield}" alt="">' if shield else ""
        st.html(f'<div class="ts-brand">{mark}<span>TenantShield<span class="ts-brand-dot"> Plus</span></span></div>')
        for path, label, icon in PAGES:
            st.page_link(path, label=label, icon=icon)
        count = len(st.session_state.get("shortlist", []))
        st.caption(f"Shortlist: {count} of {MAX_SHORTLIST} buildings")


def pretty_date(iso: str) -> str:
    day = date.fromisoformat(iso)
    return f"{day.day} {day:%B %Y}"


def badges(labels: list[str]) -> None:
    st.markdown("".join(f'<span class="ts-badge">{escape(label)}</span>' for label in labels), unsafe_allow_html=True)


def note(html_text: str) -> None:
    """Quiet explanatory note. Pass trusted, already-escaped text only."""
    st.markdown(f'<div class="ts-risk-note">{html_text}</div>', unsafe_allow_html=True)


def building_label(frame, building_id: str) -> str:
    row = frame.loc[building_id]
    return f"{row.FullAddress or 'Address unavailable'} · BIN {row.BIN or 'unavailable'} · ID {building_id}"


def shortlist() -> list[str]:
    return st.session_state.setdefault("shortlist", [])
