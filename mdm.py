"""A small, readable master data management (MDM) engine.

It illustrates the concepts — probabilistic matching, survivorship and
householding — not any employer's algorithm. All data is fictional.
"""

from __future__ import annotations

import json
import math
import re
from functools import cmp_to_key
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SAMPLE_FILE = ROOT / "data" / "sample.json"

FIELDS = ("name", "dob", "address", "email")
TRUST_ORDER = ["Policy", "Claims", "Marketing"]  # most trusted first
ABBREVIATIONS = {"ln": "lane", "st": "street", "rd": "road", "ave": "avenue"}
POSTCODE = re.compile(r"\b([a-z]{1,2}\d[a-z\d]?)\s*(\d[a-z]{2})\b", re.IGNORECASE)


def load_sample(path: Path = SAMPLE_FILE):
    """Return (records, defaults) from the sample JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["records"], data["defaults"]


# ------------------------------------------------------------------ normalising

def normalise_name(name: str) -> tuple[str, str]:
    """Lower-case, strip punctuation, return (first name, last name)."""
    parts = re.sub(r"[^a-z\s]", " ", name.lower()).split()
    return (parts[0] if parts else "", parts[-1] if parts else "")


def parse_dob(dob: str):
    """Accept YYYY-MM-DD, DD/MM/YYYY and DD-MM-YYYY; return (year, month, day) or None."""
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", dob)
    if iso:
        return int(iso[1]), int(iso[2]), int(iso[3])
    uk = re.fullmatch(r"(\d{2})[/-](\d{2})[/-](\d{4})", dob)
    if uk:
        return int(uk[3]), int(uk[2]), int(uk[1])
    return None


def normalise_address(address: str) -> dict:
    """Split an address into postcode, house number and expanded words."""
    lower = address.lower()
    pc = POSTCODE.search(lower)
    postcode = (pc[1] + pc[2]).upper() if pc else ""
    without_postcode = lower.replace(pc[0], " ", 1) if pc else lower
    tokens = [ABBREVIATIONS.get(t, t) for t in re.sub(r"[^a-z\d\s]", " ", without_postcode).split()]
    house = next((t for t in tokens if re.fullmatch(r"\d+[a-z]?", t)), "")
    return {"postcode": postcode, "house": house, "tokens": tokens}


def household_key(address: str) -> str:
    """House number + postcode identifies a household."""
    a = normalise_address(address)
    return f"{a['house']} {a['postcode']}" if a["postcode"] else " ".join(a["tokens"])


def standardise_address(address: str) -> str:
    """Display form: expanded words, title case, formatted postcode."""
    a = normalise_address(address)
    street = " ".join(t[:1].upper() + t[1:] for t in a["tokens"])
    pc = f"{a['postcode'][:-3]} {a['postcode'][-3:]}" if a["postcode"] else ""
    return ", ".join(part for part in (street, pc) if part)


# ------------------------------------------------------------------ similarity

# region similarity
def jaro_winkler(a: str, b: str) -> float:
    """Jaro–Winkler similarity, 0–1. Good at typos and short name variants."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    match_range = max(0, max(len(a), len(b)) // 2 - 1)
    a_match = [False] * len(a)
    b_match = [False] * len(b)
    matches = 0
    for i, ch in enumerate(a):
        for j in range(max(0, i - match_range), min(len(b), i + match_range + 1)):
            if b_match[j] or ch != b[j]:
                continue
            a_match[i] = b_match[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0
    transpositions = 0
    k = 0
    for i, ch in enumerate(a):
        if not a_match[i]:
            continue
        while not b_match[k]:
            k += 1
        if ch != b[k]:
            transpositions += 1
        k += 1
    m = matches
    jaro = (m / len(a) + m / len(b) + (m - transpositions / 2) / m) / 3
    prefix = 0
    while prefix < 4 and prefix < len(a) and prefix < len(b) and a[prefix] == b[prefix]:
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)
# endregion


def field_scores(a: dict, b: dict) -> dict:
    """Per-field similarity, 0–1, or None when a field is missing on either side."""
    # Name: an initial ("J.") is a strong-but-not-certain match for a full first name.
    a_first, a_last = normalise_name(a["name"])
    b_first, b_last = normalise_name(b["name"])
    if len(a_first) == 1 or len(b_first) == 1:
        first = 0.85 if a_first[:1] == b_first[:1] else 0.0
    else:
        first = jaro_winkler(a_first, b_first)
    name = 0.4 * first + 0.6 * jaro_winkler(a_last, b_last)

    # Date of birth: exact, or partial credit when only one part differs.
    da, db = parse_dob(a["dob"]), parse_dob(b["dob"])
    dob = None
    if da and db:
        same = sum(x == y for x, y in zip(da, db))
        dob = 1.0 if same == 3 else 0.5 if same == 2 else 0.0

    # Address: same house number and postcode is a match; otherwise compare the words.
    aa, ab = normalise_address(a["address"]), normalise_address(b["address"])
    if aa["postcode"] and aa["postcode"] == ab["postcode"] and aa["house"] == ab["house"]:
        address = 1.0
    else:
        sa, sb = set(aa["tokens"]), set(ab["tokens"])
        address = len(sa & sb) / len(sa | sb)

    # Email: exact or nothing; missing emails don't count against a match.
    email = None
    if a["email"] and b["email"]:
        email = 1.0 if a["email"].lower() == b["email"].lower() else 0.0

    return {"name": name, "dob": dob, "address": address, "email": email}


# ------------------------------------------------------------------ matching

# region score
def score_pair(a: dict, b: dict, weights: dict, thresholds: dict) -> dict:
    """Weighted score over the fields both records have, scaled to 0–100."""
    scores = field_scores(a, b)
    total = weight = 0.0
    for field in FIELDS:
        if scores[field] is None:
            continue
        total += weights[field] * scores[field]
        weight += weights[field]
    # Round half up, exactly like JavaScript's Math.round for positive numbers.
    score = math.floor((total / weight) * 100 + 0.5) if weight else 0
    if score >= thresholds["auto"]:
        decision = "match"
    elif score >= thresholds["review"]:
        decision = "review"
    else:
        decision = "no-match"
    return {"a": a, "b": b, "scores": scores, "score": score, "decision": decision}
# endregion


def score_all(records: list, weights: dict, thresholds: dict) -> list:
    """Score every pair of records, highest first (a stable sort, so ties keep their order)."""
    pairs = [
        score_pair(records[i], records[j], weights, thresholds)
        for i in range(len(records))
        for j in range(i + 1, len(records))
    ]
    return sorted(pairs, key=lambda p: -p["score"])


# region cluster
def cluster(records: list, pairs: list) -> list:
    """Group records into customers by following automatic matches (union–find)."""
    parent = {r["id"]: r["id"] for r in records}

    def find(record_id: str) -> str:
        return record_id if parent[record_id] == record_id else find(parent[record_id])

    for p in pairs:
        if p["decision"] == "match":
            parent[find(p["a"]["id"])] = find(p["b"]["id"])
    groups: dict[str, list] = {}
    for r in records:
        groups.setdefault(find(r["id"]), []).append(r)
    return list(groups.values())
# endregion


# ------------------------------------------------------------------ survivorship

def _by_trust(a: dict, b: dict) -> int:
    return TRUST_ORDER.index(a["source"]) - TRUST_ORDER.index(b["source"])


def _by_recency(a: dict, b: dict) -> int:
    return (b["updated"] > a["updated"]) - (b["updated"] < a["updated"])  # newest first


def _completeness(r: dict) -> int:
    """Prefer a full first name over an initial — not simply the longest string."""
    return 1 if len(normalise_name(r["name"])[0]) > 1 else 0


# region survive
def survive(group: list, rules: dict) -> dict:
    """Build one golden record; rules decide which source wins each field."""

    def pick(field: str, order) -> dict:
        candidates = sorted((r for r in group if r[field]), key=cmp_to_key(order))
        winner = candidates[0] if candidates else None
        return {"value": winner[field] if winner else "", "from": winner["source"] if winner else None}

    def most_complete(a: dict, b: dict) -> int:
        return (_completeness(b) - _completeness(a)) or _by_trust(a, b)

    return {
        "id": "+".join(r["id"] for r in group),
        "members": group,
        "values": {
            "name": pick("name", most_complete if rules["name"] == "most-complete" else _by_trust),
            "dob": pick("dob", _by_trust),  # date of birth: always the most trusted source
            "address": pick("address", _by_recency if rules["address"] == "most-recent" else _by_trust),
            "email": pick("email", _by_trust),  # email: from the most trusted source
        },
    }
# endregion


# region households
def households(golden: list) -> list:
    """Group golden records that share an address into households."""
    found: dict[str, list] = {}
    for g in golden:
        found.setdefault(household_key(g["values"]["address"]["value"]), []).append(g)
    return [{"key": key, "members": members} for key, members in found.items()]
# endregion


# ------------------------------------------------------------------ end to end

def run(records: list, weights: dict, thresholds: dict, rules: dict) -> dict:
    """The full pipeline, summarised in a form both languages can compare."""
    pairs = score_all(records, weights, thresholds)
    golden = [survive(g, rules) for g in cluster(records, pairs)]
    homes = households(golden)
    return {
        "summary": {
            "records": len(records),
            "customers": len(golden),
            "households": len(homes),
            "review": sum(p["decision"] == "review" for p in pairs),
        },
        "pairs": [
            {"a": p["a"]["id"], "b": p["b"]["id"], "score": p["score"], "decision": p["decision"]}
            for p in pairs
        ],
        "golden": [
            {"id": g["id"], **{f: g["values"][f]["value"] for f in FIELDS}} for g in golden
        ],
        "households": [[m["id"] for m in h["members"]] for h in homes],
    }


if __name__ == "__main__":
    recs, defaults = load_sample()
    result = run(recs, defaults["weights"], defaults["thresholds"], defaults["survivorship"])
    s = result["summary"]
    print(f"{s['records']} records -> {s['customers']} customers -> {s['households']} households "
          f"({s['review']} pairs for review)")
