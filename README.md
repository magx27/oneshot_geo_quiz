# GeoQuiz

An interactive geography quiz whose multiple-choice questions are generated automatically from
the **Wikidata knowledge graph** (country → `P36` capital → city).

## Run

```bash
pip install -r requirements.txt
streamlit run app.py          # opens http://localhost:8501
pytest                        # run the tests
```

## How it works

| Step | Where | What happens |
|---|---|---|
| 1. Retrieve | `geoquiz/kg.py` | A SPARQL query to `https://query.wikidata.org/sparql` gets every current country (`wdt:P31 wd:Q6256` / `wd:Q3624078`, not dissolved, `P576`), its current capital(s) (`p:P36` statements without an end time `pq:P582`, not deprecated), its continent (`P30`) and the English labels. |
| 2. Fallback | `data/capitals.ttl` | If Wikidata is unreachable (or the sidebar toggle is off), a local RDF/Turtle snapshot with the same Wikidata URIs is loaded with **RDFLib** and queried with an equivalent SPARQL query. |
| 3. Generate | `geoquiz/quiz.py` | Picks N random countries. The correct answer is the capital from P36; 3 distractors are capitals of *other* countries, preferably on the same continent (more plausible), never another capital of the same country (e.g. Bolivia: Sucre / La Paz). Options are shuffled. |
| 4. Evaluate | `app.py` | The user picks A–D and gets immediate feedback plus a link to the Wikidata entities used. At the end: the final score and a review of all answers. |

## Refreshing the offline snapshot

The bundled snapshot covers 51 countries. With internet access you can replace it with the full live dataset:

```bash
python -m geoquiz.kg --refresh   # query Wikidata and rewrite data/capitals.ttl
python -m geoquiz.kg             # show which source is used and a sample of the data
```

## Project layout

```
app.py               Streamlit UI (quiz flow, feedback, score)
geoquiz/kg.py        SPARQL retrieval (live + RDFLib), Turtle export
geoquiz/quiz.py      Question and distractor generation, scoring
data/capitals.ttl    Offline RDF snapshot
tests/               pytest suite (incl. a mocked Wikidata response)
```
