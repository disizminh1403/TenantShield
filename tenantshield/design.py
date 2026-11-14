"""Presentation primitives; no prediction or provider logic lives here."""

from html import escape
import base64
from pathlib import Path

import streamlit as st


# Small, consistent outline drawings in the Lucide visual style. No external icon runtime.
ICONS = {
    "shield": '<path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    "risk": '<path d="M3 17a9 9 0 1 1 18 0"/><path d="m12 13 5-5M5 17h14"/><circle cx="12" cy="13" r="1"/>',
    "building": '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 7h1m4 0h1M9 11h1m4 0h1M9 15h1m4 0h1M10 21v-3h4v3"/>',
    "history": '<path d="M3 11a9 9 0 1 1 2.6 7.4M3 4v7h7"/><path d="M12 7v5l3 2"/>',
    "location": '<path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z"/><circle cx="12" cy="10" r="2.5"/>',
    "street": '<path d="M4 7h4l2-3h4l2 3h4v13H4Z"/><circle cx="12" cy="13" r="4"/>',
    "method": '<path d="M4 4h6l2 2 2-2h6v16h-6l-2 1-2-1H4ZM12 6v15M7 8h2m-2 4h2m6-4h2m-2 4h2"/>',
}


def icon(name: str) -> str:
    return ('<svg class="ts-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            + ICONS[name] + '</svg>')


def section(title: str, symbol: str, anchor: str | None = None) -> None:
    identifier = f' id="{escape(anchor, quote=True)}"' if anchor else ""
    # st.html preserves explicit IDs/classes; Markdown rewrites heading anchors.
    # st.html removes inline SVG, so embed the trusted local drawing as an image.
    drawing = icon(symbol).replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ', 1).replace('currentColor', '#64748B')
    encoded = base64.b64encode(drawing.encode()).decode()
    st.html(f'<h3 class="ts-section"{identifier}><img class="ts-icon" alt="" '
            f'src="data:image/svg+xml;base64,{encoded}">{escape(title)}</h3>')


def gauge_svg(probability: float) -> str:
    """A continuous 0–100% arc, not a categorical safety scale."""
    if not 0 <= probability <= 1:
        raise ValueError("Gauge requires a validated probability in [0,1].")
    return (
        '<svg class="ts-gauge" viewBox="0 0 320 210" role="img" '
        'aria-label="Continuous probability scale from 0 to 100 percent">'
        '<path d="M30 165 A130 130 0 0 1 290 165" fill="none" stroke="#EAF0F6" '
        'stroke-width="18" stroke-linecap="round"/>'
        '<path d="M30 165 A130 130 0 0 1 290 165" fill="none" stroke="#011F5B" '
        f'stroke-width="18" pathLength="100" stroke-dasharray="{probability * 100:.8f} 100" '
        'stroke-linecap="butt"/>'
        '<text x="30" y="198" text-anchor="middle" fill="#64748B" font-size="12">0%</text>'
        '<text x="290" y="198" text-anchor="middle" fill="#64748B" font-size="12">100%</text></svg>'
    )


def apply_design(page: str = "dashboard") -> None:
    css = (Path(__file__).resolve().parents[1] / "assets" / "style.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    with st.sidebar:
        st.markdown(f'<div class="ts-brand">{icon("shield")}<span>TenantShield<span class="ts-brand-dot">.</span></span></div>'
                    '<div class="ts-brand-sub">BUILDING INTELLIGENCE</div>', unsafe_allow_html=True)
        st.page_link("app.py", label="Building explorer", icon=":material/apartment:")
        st.page_link("pages/How_TenantShield_Works.py", label="How TenantShield Works", icon=":material/menu_book:")
        st.markdown('<div class="ts-sidebar-label">ON THIS PAGE</div>', unsafe_allow_html=True)
        navigation = [
            ("Find a building", "search", "search"), ("Risk assessment", "risk", "risk-assessment"),
            ("Building details", "building", "building-details"), ("Complaint history", "history", "complaint-history"),
            ("Location & imagery", "location", "building-location"), ("Methodology", "method", "methodology"),
        ] if page == "dashboard" else [
            ("What we predict", "risk", "prediction-target"),
            ("Data & method", "building", "data-method"),
            ("Evaluation", "history", "evaluation"),
            ("Performance", "risk", "performance"),
            ("Responsible use", "shield", "responsible-use"),
        ]
        for label, symbol, anchor in navigation:
            st.markdown(f'<a class="ts-nav" href="#{anchor}" target="_self">{icon(symbol)}{label}</a>', unsafe_allow_html=True)
        st.markdown('<div class="ts-sidebar-note"><span class="ts-status-dot"></span> BROOKLYN, NEW YORK'
                    '<h4>Know the building.<br>Understand the context.</h4>'
                    '<p>2026–27 heating season<br>Building-level complaint estimates.</p>'
                    '<small>Independent prototype.<br>No university affiliation or endorsement.</small></div>', unsafe_allow_html=True)
