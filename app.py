"""Streamlit front end for GeoQuiz.  Run with:  streamlit run app.py"""

import random

import streamlit as st

from geoquiz.kg import load_countries
from geoquiz.quiz import make_quiz

st.set_page_config(page_title="GeoQuiz", page_icon="🌍", layout="centered")


@st.cache_data(ttl=3600, show_spinner="Querying Wikidata…")
def get_countries(prefer_live: bool):
    return load_countries(prefer_live)


def start_quiz(countries, n, same_continent):
    st.session_state.questions = make_quiz(countries, n, random.Random(), same_continent)
    st.session_state.index = 0
    st.session_state.answers = []      # chosen QIDs, one per answered question
    st.session_state.submitted = False


# ---- Sidebar: settings ---------------------------------------------------
with st.sidebar:
    st.header("Settings")
    prefer_live = st.toggle("Query Wikidata live", value=True,
                            help="If off, or if Wikidata is unreachable, the bundled RDF snapshot is used.")
    countries, source = get_countries(prefer_live)
    n_questions = st.slider("Number of questions", 3, min(30, len(countries)), 10)
    same_continent = st.checkbox("Harder distractors (same continent)", value=True)
    if st.button("New quiz", type="primary", use_container_width=True):
        start_quiz(countries, n_questions, same_continent)
    st.caption(f"Data source: **{source}** · {len(countries)} countries")

st.title("🌍 GeoQuiz")
st.write("Questions are generated from country → capital (P36) facts in the Wikidata knowledge graph.")

if "questions" not in st.session_state:
    start_quiz(countries, n_questions, same_continent)

questions = st.session_state.questions
i = st.session_state.index

# ---- Final score ---------------------------------------------------------
if i >= len(questions):
    correct = sum(q.is_correct(a) for q, a in zip(questions, st.session_state.answers))
    st.subheader(f"Your score: {correct} / {len(questions)}")
    st.progress(correct / len(questions))
    if correct == len(questions):
        st.balloons()
    with st.expander("Review answers", expanded=True):
        for q, a in zip(questions, st.session_state.answers):
            chosen = next(o.label for o in q.options if o.qid == a)
            mark = "✅" if q.is_correct(a) else "❌"
            extra = "" if q.is_correct(a) else f" (correct: **{q.answer.label}**)"
            st.markdown(f"{mark} {q.prompt} — you answered **{chosen}**{extra}")
    if st.button("Play again", type="primary"):
        start_quiz(countries, n_questions, same_continent)
        st.rerun()
    st.stop()

# ---- Current question ----------------------------------------------------
q = questions[i]
st.progress(i / len(questions), text=f"Question {i + 1} of {len(questions)}")
st.subheader(q.prompt)

letters = "ABCD"
labels = {o.qid: f"{letters[k]}. {o.label}" for k, o in enumerate(q.options)}
choice = st.radio("Choose an answer:", list(labels), format_func=labels.get,
                  index=None, key=f"q{i}", disabled=st.session_state.submitted)

if not st.session_state.submitted:
    if st.button("Submit", type="primary", disabled=choice is None):
        st.session_state.answers.append(choice)
        st.session_state.submitted = True
        st.rerun()
else:
    chosen = st.session_state.answers[-1]
    if q.is_correct(chosen):
        st.success(f"Correct! {q.answer.label} is the capital of {q.country.label}.")
    else:
        st.error(f"Wrong. The correct answer is **{q.answer.label}**.")
    st.caption(f"Source: [wd:{q.country.qid}](https://www.wikidata.org/wiki/{q.country.qid}) "
               f"→ P36 (capital) → [wd:{q.answer.qid}](https://www.wikidata.org/wiki/{q.answer.qid})")
    last = i + 1 == len(questions)
    if st.button("See results" if last else "Next question", type="primary"):
        st.session_state.index += 1
        st.session_state.submitted = False
        st.rerun()
