"""Plain-language outputs built from one building's row: viewing questions and a text summary."""

import pandas as pd

from tsplus.store import has_plus, per_100_units, season_columns, season_label

HEAT_RULES = (
    "Heat season runs from 1 October to 31 May.",
    "6 am–10 pm: if it is below 55°F outside, it must be at least 68°F inside.",
    "10 pm–6 am: it must be at least 62°F inside, whatever the outside temperature.",
    "Hot water must be at least 120°F at the tap, every day of the year.",
    "No heat or hot water? Tell the owner or super first, then report it to 311 (phone, app or 311 online).",
)
HEAT_RULES_URL = "https://www.nyc.gov/site/hpd/services-and-information/heat-and-hot-water-information.page"


def _count(row: pd.Series, column: str) -> int:
    value = row.get(column)
    return 0 if value is None or pd.isna(value) else int(value)


def plural(count: int, noun: str) -> str:
    return f"{count:,} {noun}" if count == 1 else f"{count:,} {noun}s"


def viewing_questions(row: pd.Series, chronic_threshold: int, data_through: str) -> list[str]:
    """Questions tailored to what the records show. Every number quoted comes from the row."""
    questions = []
    if not has_plus(row):
        return ["Did residents experience any interruptions to heat or hot water last winter?"]
    seasons = season_columns(row.to_frame().T)
    last = seasons[-1] if seasons else None
    last_count = _count(row, last) if last else 0
    to_date = _count(row, "SeasonToDate")
    if to_date:
        questions.append(f"HPD has recorded {plural(to_date, 'heat or hot-water complaint')} for this building "
                         f"since 1 October (data through {data_through}). What caused them, and is the repair finished?")
    if last and last_count >= chronic_threshold:
        questions.append(f"{plural(last_count, 'complaint')} were recorded in the {season_label(last)} season. "
                         "Ask a current tenant, not only the agent, how often the heat or hot water went out "
                         "and how long each outage lasted.")
    wide = _count(row, "BuildingWideLastSeason")
    if wide:
        questions.append(f"{plural(wide, 'complaint')} last season were reported as building-wide. "
                         "How old is the boiler, when was it last serviced, and is a replacement planned?")
    apartments = _count(row, "ApartmentsLastSeason")
    if apartments >= 3:
        questions.append(f"Apartment-level complaints came from {apartments:,} different apartments last season. "
                         "Which floors or lines were affected, and is this apartment on one of them?")
    summer = _count(row, "OffSeasonBefore")
    if summer:
        questions.append(f"{plural(summer, 'complaint')} were recorded between June and September, when heat is "
                         "not required. These usually concern hot water: were there hot-water outages this summer?")
    if not (to_date or last_count):
        questions.append("No complaint is on record here for last season or this one. That is not proof of "
                         "reliable heat: when did the heat last go out, and how quickly was it fixed?")
    questions += [
        "Who do tenants contact about heat problems, and is there a super on site or on call?",
        "Is heat included in the rent, and who controls the thermostat for this apartment?",
        "During the viewing: feel the radiators if the heat is on, and run the hot tap for a full minute.",
    ]
    return questions


def text_summary(row: pd.Series, report: dict, questions: list[str]) -> str:
    """A Markdown summary the renter can download and take to a viewing."""
    season, through = report["deploy_season"], report["data_through"]
    lines = [
        f"# TenantShield summary: {row.FullAddress or 'Address unavailable'}",
        f"BIN {row.BIN or 'unavailable'} · Building ID {row.BuildingID} · ZIP {row.get('Zip') or 'unavailable'}",
        "",
        f"## Estimates for the {season} heating season",
        f"- Chance of at least one recorded heat or hot-water complaint: {row.PredictedRisk:.1%} (original TenantShield model)",
    ]
    if has_plus(row):
        lines += [
            f"- Chance of {report['chronic_threshold']} or more recorded complaints: {row.ChronicRisk:.1%} (companion model)",
            f"- Expected number of recorded complaints: about {row.ExpectedComplaints:.1f} (companion model)",
            f"- Chance of at least one more complaint between {through} and 31 May: {row.RestOfSeasonRisk:.1%} (companion model)",
            "",
            "## Recorded heat and hot-water complaints",
            f"- This season so far (1 October to {through}): {_count(row, 'SeasonToDate'):,}",
        ]
        for column in reversed(season_columns(row.to_frame().T)):
            value = row.get(column)
            if not pd.isna(value):
                rate = per_100_units(value, row.get("Units"))
                extra = f" ({rate:.0f} per 100 units)" if rate is not None and value else ""
                lines.append(f"- {season_label(column)} season (1 October to 31 May): {int(value):,}{extra}")
    lines += ["", "## Questions for the viewing", *[f"- [ ] {question}" for question in questions], "",
              "## Your rights in New York City", *[f"- {rule}" for rule in HEAT_RULES], f"- Source: {HEAT_RULES_URL}", "",
              "## Read this before relying on the numbers",
              "These are building-level estimates of recorded HPD complaints, not apartment-level risks, verified "
              "heating failures or safety ratings. Complaint records depend on tenants choosing to report. A count "
              "of zero does not show that a building had no problems. Estimates may be too high or too low. "
              "TenantShield is an educational prototype.", ""]
    return "\n".join(lines)
