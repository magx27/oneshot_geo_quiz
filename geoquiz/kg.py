"""Knowledge-graph access: country/capital facts from Wikidata.

Two sources share one data model:

* live   - the public Wikidata SPARQL endpoint (https://query.wikidata.org/sparql)
* local  - a Turtle snapshot in data/capitals.ttl, queried with RDFLib's
           SPARQL engine. Used offline or when the endpoint is unreachable.

Both return a list of ``Country`` records. ``save_snapshot`` writes live
results back to Turtle so the offline snapshot can be refreshed.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import requests
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "GeoQuiz/1.0 (student project; https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service)"
SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "data" / "capitals.ttl"

WD = Namespace("http://www.wikidata.org/entity/")
WDT = Namespace("http://www.wikidata.org/prop/direct/")

# Live query. Only current countries (instance of country / sovereign state,
# not dissolved) and current, non-deprecated capital statements (no end time).
LIVE_QUERY = """
SELECT DISTINCT ?country ?countryLabel ?capital ?capitalLabel ?continentLabel WHERE {
  VALUES ?type { wd:Q6256 wd:Q3624078 }
  ?country wdt:P31 ?type ;
           p:P36 ?capStmt .
  ?capStmt ps:P36 ?capital ;
           wikibase:rank ?rank .
  FILTER(?rank != wikibase:DeprecatedRank)
  FILTER NOT EXISTS { ?capStmt pq:P582 ?capEnd }
  FILTER NOT EXISTS { ?country wdt:P576 ?dissolved }
  OPTIONAL { ?country wdt:P30 ?continent }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""

# The same facts, queried from the local RDF snapshot with RDFLib.
LOCAL_QUERY = """
PREFIX wd:   <http://www.wikidata.org/entity/>
PREFIX wdt:  <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?country ?countryLabel ?capital ?capitalLabel ?continentLabel WHERE {
  ?country wdt:P31 wd:Q6256 ;
           wdt:P36 ?capital ;
           rdfs:label ?countryLabel .
  ?capital rdfs:label ?capitalLabel .
  OPTIONAL { ?country wdt:P30 ?continent . ?continent rdfs:label ?continentLabel }
}
"""

_QID_LABEL = re.compile(r"^Q\d+$")


@dataclass
class City:
    qid: str
    label: str


@dataclass
class Country:
    qid: str
    label: str
    capitals: list[City] = field(default_factory=list)
    continent: str | None = None


def _qid(uri: str) -> str:
    return str(uri).rsplit("/", 1)[-1]


def _rows_to_countries(rows) -> list[Country]:
    """Group (country, capital, continent) rows into Country records.

    A country may have several capitals (e.g. Bolivia) and several continents
    (e.g. Russia, Turkey); all capitals are kept, the first continent wins.
    Rows whose label is missing in English (label == QID) are dropped.
    """
    countries: dict[str, Country] = {}
    seen_caps: dict[str, set[str]] = defaultdict(set)
    for country, c_label, capital, cap_label, continent in rows:
        if not c_label or not cap_label or _QID_LABEL.match(c_label) or _QID_LABEL.match(cap_label):
            continue
        cqid, capqid = _qid(country), _qid(capital)
        rec = countries.setdefault(cqid, Country(cqid, c_label))
        if rec.continent is None and continent:
            rec.continent = continent
        if capqid not in seen_caps[cqid]:
            seen_caps[cqid].add(capqid)
            rec.capitals.append(City(capqid, cap_label))
    return sorted(countries.values(), key=lambda c: c.label)


def fetch_live(timeout: float = 30) -> list[Country]:
    """Query the Wikidata SPARQL endpoint. Raises on network/HTTP errors."""
    resp = requests.get(
        WIKIDATA_ENDPOINT,
        params={"query": LIVE_QUERY, "format": "json"},
        headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"},
        timeout=timeout,
    )
    resp.raise_for_status()

    def val(b, key):
        return b[key]["value"] if key in b else None

    rows = [
        (val(b, "country"), val(b, "countryLabel"), val(b, "capital"),
         val(b, "capitalLabel"), val(b, "continentLabel"))
        for b in resp.json()["results"]["bindings"]
    ]
    return _rows_to_countries(rows)


def load_local(path: Path = SNAPSHOT_PATH) -> list[Country]:
    """Load the Turtle snapshot and query it with SPARQL via RDFLib."""
    g = Graph()
    g.parse(path, format="turtle")
    rows = [
        tuple(str(v) if v is not None else None for v in row)
        for row in g.query(LOCAL_QUERY)
    ]
    return _rows_to_countries(rows)


def load_countries(prefer_live: bool = True) -> tuple[list[Country], str]:
    """Return (countries, source_name). Falls back to the local snapshot."""
    if prefer_live:
        try:
            countries = fetch_live()
            if countries:
                return countries, "Wikidata (live SPARQL)"
        except (requests.RequestException, ValueError, KeyError):
            pass
    return load_local(), "Local RDF snapshot (data/capitals.ttl)"


def save_snapshot(countries: list[Country], path: Path = SNAPSHOT_PATH) -> None:
    """Serialize Country records to Turtle using Wikidata URIs."""
    g = Graph()
    g.bind("wd", WD)
    g.bind("wdt", WDT)
    g.bind("rdfs", RDFS)
    continents: dict[str, URIRef] = {}
    for c in countries:
        cu = WD[c.qid]
        g.add((cu, WDT.P31, WD.Q6256))
        g.add((cu, RDFS.label, Literal(c.label, lang="en")))
        for cap in c.capitals:
            g.add((cu, WDT.P36, WD[cap.qid]))
            g.add((WD[cap.qid], RDFS.label, Literal(cap.label, lang="en")))
        if c.continent:
            # Continent QIDs are not in the label-only live result, so use a
            # local URI derived from the label.
            node = continents.setdefault(
                c.continent, URIRef(f"urn:geoquiz:continent:{c.continent.replace(' ', '_')}")
            )
            g.add((cu, WDT.P30, node))
            g.add((node, RDFS.label, Literal(c.continent, lang="en")))
    g.serialize(path, format="turtle")


def _main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or refresh the country/capital data.")
    parser.add_argument("--refresh", action="store_true",
                        help="query Wikidata live and overwrite the local snapshot")
    args = parser.parse_args()
    if args.refresh:
        countries = fetch_live()
        save_snapshot(countries)
        print(f"Wrote {len(countries)} countries to {SNAPSHOT_PATH}")
    else:
        countries, source = load_countries()
        print(f"{len(countries)} countries from {source}")
        for c in countries[:10]:
            print(f"  {c.label}: {', '.join(cap.label for cap in c.capitals)} ({c.continent})")


if __name__ == "__main__":
    _main()
