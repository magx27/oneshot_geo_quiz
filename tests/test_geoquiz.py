import random
from unittest import mock

import pytest

from geoquiz import kg
from geoquiz.kg import City, Country, load_local, save_snapshot
from geoquiz.quiz import NUM_OPTIONS, make_question, make_quiz, score


@pytest.fixture(scope="module")
def countries():
    return load_local()


def test_snapshot_loads_via_sparql(countries):
    by_name = {c.label: c for c in countries}
    assert len(countries) >= 40
    assert by_name["Germany"].qid == "Q183"
    assert [cap.label for cap in by_name["Germany"].capitals] == ["Berlin"]
    assert by_name["Germany"].continent == "Europe"


def test_question_shape(countries):
    rng = random.Random(0)
    for c in countries:
        q = make_question(c, countries, rng)
        assert len(q.options) == NUM_OPTIONS
        assert len({o.label for o in q.options}) == NUM_OPTIONS
        assert sum(o.qid in {cap.qid for cap in c.capitals} for o in q.options) == 1
        assert q.answer in q.options
        assert q.prompt == f"What is the capital of {c.label}?"


def test_same_continent_distractors(countries):
    germany = next(c for c in countries if c.label == "Germany")
    q = make_question(germany, countries, random.Random(1), same_continent=True)
    europe_caps = {cap.qid for c in countries if c.continent == "Europe" for cap in c.capitals}
    assert all(o.qid in europe_caps for o in q.options)


def test_falls_back_to_other_continents_when_needed():
    pool = [Country(f"Q{i}", f"C{i}", [City(f"Q{100 + i}", f"Cap{i}")], "Oceania" if i < 2 else "Europe")
            for i in range(5)]
    q = make_question(pool[0], pool, random.Random(0))
    assert len(q.options) == NUM_OPTIONS


def test_multiple_capitals_never_used_as_distractor():
    bolivia = Country("Q750", "Bolivia", [City("Q1491", "Sucre"), City("Q1490x", "La Paz")], "South America")
    others = [Country(f"Q{i}", f"C{i}", [City(f"Q{100 + i}", f"Cap{i}")], "South America") for i in range(3)]
    for seed in range(20):
        q = make_question(bolivia, [bolivia] + others, random.Random(seed))
        assert sum(o.label in {"Sucre", "La Paz"} for o in q.options) == 1


def test_quiz_distinct_countries_and_scoring(countries):
    quiz = make_quiz(countries, 10, random.Random(42))
    assert len(quiz) == 10
    assert len({q.country.qid for q in quiz}) == 10
    answers = [q.answer.qid for q in quiz]
    assert score(quiz, answers) == 10
    wrong = next(o for o in quiz[0].options if o != quiz[0].answer)
    assert score(quiz, [wrong.qid] + answers[1:]) == 9
    assert score(quiz, [None] * 10) == 0


def test_live_response_parsing():
    def b(country, clabel, cap, caplabel, cont=None):
        row = {"country": {"value": kg.WD[country]}, "countryLabel": {"value": clabel},
               "capital": {"value": kg.WD[cap]}, "capitalLabel": {"value": caplabel}}
        if cont:
            row["continentLabel"] = {"value": cont}
        return row

    payload = {"results": {"bindings": [
        b("Q183", "Germany", "Q64", "Berlin", "Europe"),
        b("Q159", "Russia", "Q649", "Moscow", "Europe"),
        b("Q159", "Russia", "Q649", "Moscow", "Asia"),   # duplicate via 2nd continent
        b("Q750", "Bolivia", "Q1491", "Sucre", "South America"),
        b("Q750", "Bolivia", "Q2933", "La Paz", "South America"),
        b("Q999", "Q999", "Q1", "Somewhere"),            # no English label -> dropped
    ]}}
    resp = mock.Mock(json=lambda: payload, raise_for_status=lambda: None)
    with mock.patch.object(kg.requests, "get", return_value=resp):
        result = {c.label: c for c in kg.fetch_live()}
    assert set(result) == {"Germany", "Russia", "Bolivia"}
    assert len(result["Russia"].capitals) == 1 and result["Russia"].continent == "Europe"
    assert {c.label for c in result["Bolivia"].capitals} == {"Sucre", "La Paz"}


def test_load_countries_falls_back_when_offline():
    with mock.patch.object(kg.requests, "get", side_effect=kg.requests.ConnectionError):
        countries, source = kg.load_countries(prefer_live=True)
    assert countries and "snapshot" in source


def test_snapshot_roundtrip(tmp_path, countries):
    path = tmp_path / "out.ttl"
    save_snapshot(countries, path)
    again = load_local(path)
    assert [(c.qid, c.label, c.continent, [x.qid for x in c.capitals]) for c in again] == \
           [(c.qid, c.label, c.continent, [x.qid for x in c.capitals]) for c in countries]
