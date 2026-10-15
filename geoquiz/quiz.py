"""Generate multiple-choice questions from country/capital facts and score them."""

from __future__ import annotations

import random
from dataclasses import dataclass

from .kg import City, Country

NUM_OPTIONS = 4


@dataclass
class Question:
    country: Country
    prompt: str
    options: list[City]   # shuffled, exactly one is a capital of `country`
    answer: City          # the correct option

    def is_correct(self, choice: City | str) -> bool:
        qid = choice.qid if isinstance(choice, City) else choice
        return qid == self.answer.qid


def make_question(country: Country, pool: list[Country], rng: random.Random,
                  same_continent: bool = True) -> Question:
    """Build one question for `country`.

    The correct answer is one of the country's capitals (from P36). The three
    distractors are capitals of other countries, preferring countries on the
    same continent so the options are plausible, and never another capital of
    the country being asked about.
    """
    answer = rng.choice(country.capitals)
    own = {c.qid for c in country.capitals}
    own_labels = {c.label for c in country.capitals}

    def candidates(filter_continent: bool) -> list[City]:
        out = []
        for other in pool:
            if other.qid == country.qid:
                continue
            if filter_continent and (country.continent is None or other.continent != country.continent):
                continue
            out.extend(c for c in other.capitals if c.qid not in own and c.label not in own_labels)
        return out

    distractors: list[City] = []
    used_labels = set(own_labels)
    passes = [True, False] if same_continent else [False]
    for filter_continent in passes:
        cands = candidates(filter_continent)
        rng.shuffle(cands)
        for c in cands:
            if len(distractors) == NUM_OPTIONS - 1:
                break
            if c.label not in used_labels:   # avoid two options with the same text
                distractors.append(c)
                used_labels.add(c.label)
    if len(distractors) < NUM_OPTIONS - 1:
        raise ValueError("Not enough capitals in the dataset to build distractors")

    options = distractors + [answer]
    rng.shuffle(options)
    return Question(country, f"What is the capital of {country.label}?", options, answer)


def make_quiz(countries: list[Country], n: int, rng: random.Random | None = None,
              same_continent: bool = True) -> list[Question]:
    """Pick `n` distinct random countries and build a question for each."""
    rng = rng or random.Random()
    eligible = [c for c in countries if c.capitals]
    if len(eligible) < NUM_OPTIONS:
        raise ValueError("Need at least four countries with capitals")
    picked = rng.sample(eligible, min(n, len(eligible)))
    return [make_question(c, eligible, rng, same_continent) for c in picked]


def score(questions: list[Question], answers: list[str | None]) -> int:
    """Number of correct answers; `answers` holds chosen city QIDs (or None)."""
    return sum(1 for q, a in zip(questions, answers) if a is not None and q.is_correct(a))
