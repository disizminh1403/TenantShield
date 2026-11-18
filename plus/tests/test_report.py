import pandas as pd

from tsplus.report import HEAT_RULES, text_summary, viewing_questions

REPORT = {"deploy_season": "2026–27", "data_through": "2026-11-17", "chronic_threshold": 5}


def building(**changes) -> pd.Series:
    values = {"BuildingID": "1", "BIN": "3000001", "FullAddress": "1 TEST STREET, BROOKLYN", "Zip": "11201",
              "PredictedRisk": .5, "ChronicRisk": .2, "ExpectedComplaints": 2.5, "RestOfSeasonRisk": .4,
              "SeasonToDate": 0, "Complaints2024": 0, "Complaints2025": 0, "ApartmentsLastSeason": 0,
              "BuildingWideLastSeason": 0, "OffSeasonBefore": 0, "Units": 10.0}
    return pd.Series({**values, **changes})


def test_questions_follow_the_records():
    busy = building(SeasonToDate=3, Complaints2025=14, BuildingWideLastSeason=12, ApartmentsLastSeason=4, OffSeasonBefore=1)
    text = " ".join(viewing_questions(busy, 5, "17 November 2026"))
    for expected in ("3 heat or hot-water complaints", "14 complaints were recorded in the 2025–26 season",
                     "12 complaints last season were reported as building-wide", "4 different apartments",
                     "1 complaint were recorded between June and September"):
        assert expected in text
    assert "not proof" not in text


def test_quiet_building_gets_no_invented_numbers_and_no_reassurance():
    questions = viewing_questions(building(), 5, "17 November 2026")
    text = " ".join(questions)
    assert "not proof of reliable heat" in text and "building-wide" not in text
    assert not any(character.isdigit() for character in questions[0])


def test_building_without_plus_estimates_still_gets_a_question():
    assert len(viewing_questions(building(ChronicRisk=float("nan")), 5, "17 November 2026")) == 1


def test_text_summary_states_estimates_and_limits():
    row = building(SeasonToDate=2, Complaints2025=3)
    summary = text_summary(row, REPORT, viewing_questions(row, 5, "17 November 2026"))
    assert "50.0% (original TenantShield model)" in summary and "20.0% (companion model)" in summary
    assert "2025–26 season (1 October to 31 May): 3 (30 per 100 units)" in summary
    assert "not apartment-level risks" in summary and HEAT_RULES[0] in summary
