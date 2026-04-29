"""
Rule-based natural language query parser.
Converts plain-English queries into structured filter dicts.
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Country name → ISO-3166-1 alpha-2 code
# Sorted by name length (longest first) so multi-word names match before
# single-word substrings (e.g. "south africa" before "africa").
# ---------------------------------------------------------------------------
COUNTRY_MAP: dict[str, str] = {
    # Multi-word first (order matters for regex matching)
    "south africa": "ZA",
    "south african": "ZA",
    "burkina faso": "BF",
    "sierra leone": "SL",
    "ivory coast": "CI",
    "cote d'ivoire": "CI",
    "cape verde": "CV",
    "cabo verde": "CV",
    "democratic republic of congo": "CD",
    "central african republic": "CF",
    "equatorial guinea": "GQ",
    "dr congo": "CD",
    "drc": "CD",
    "the gambia": "GM",
    # Single-word countries
    "nigeria": "NG",
    "nigerian": "NG",
    "nigerians": "NG",
    "ghana": "GH",
    "ghanaian": "GH",
    "ghanaians": "GH",
    "kenya": "KE",
    "kenyan": "KE",
    "kenyans": "KE",
    "angola": "AO",
    "angolan": "AO",
    "ethiopia": "ET",
    "ethiopian": "ET",
    "tanzania": "TZ",
    "tanzanian": "TZ",
    "uganda": "UG",
    "ugandan": "UG",
    "cameroon": "CM",
    "cameroonian": "CM",
    "senegal": "SN",
    "senegalese": "SN",
    "mali": "ML",
    "malian": "ML",
    "niger": "NE",
    "nigerien": "NE",
    "benin": "BJ",
    "beninese": "BJ",
    "togo": "TG",
    "togolese": "TG",
    "liberia": "LR",
    "liberian": "LR",
    "guinea": "GN",
    "guinean": "GN",
    "gambia": "GM",
    "gambian": "GM",
    "mauritania": "MR",
    "mauritanian": "MR",
    "morocco": "MA",
    "moroccan": "MA",
    "egypt": "EG",
    "egyptian": "EG",
    "libya": "LY",
    "libyan": "LY",
    "tunisia": "TN",
    "tunisian": "TN",
    "algeria": "DZ",
    "algerian": "DZ",
    "sudan": "SD",
    "sudanese": "SD",
    "somalia": "SO",
    "somali": "SO",
    "rwanda": "RW",
    "rwandan": "RW",
    "burundi": "BI",
    "burundian": "BI",
    "mozambique": "MZ",
    "mozambican": "MZ",
    "zambia": "ZM",
    "zambian": "ZM",
    "zimbabwe": "ZW",
    "zimbabwean": "ZW",
    "malawi": "MW",
    "malawian": "MW",
    "botswana": "BW",
    "motswana": "BW",
    "namibia": "NA",
    "namibian": "NA",
    "madagascar": "MG",
    "malagasy": "MG",
    "congo": "CG",
    "congolese": "CG",
    "gabon": "GA",
    "gabonese": "GA",
    "chad": "TD",
    "chadian": "TD",
    "lesotho": "LS",
    "basotho": "LS",
    "eswatini": "SZ",
    "swaziland": "SZ",
    "swazi": "SZ",
    "djibouti": "DJ",
    "djiboutian": "DJ",
    "eritrea": "ER",
    "eritrean": "ER",
    "comoros": "KM",
    "mauritius": "MU",
    "seychelles": "SC",
    # Common non-African countries
    "united states": "US",
    "usa": "US",
    "america": "US",
    "american": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "britain": "GB",
    "british": "GB",
    "france": "FR",
    "french": "FR",
    "germany": "DE",
    "german": "DE",
    "italy": "IT",
    "italian": "IT",
    "spain": "ES",
    "spanish": "ES",
    "portugal": "PT",
    "portuguese": "PT",
    "brazil": "BR",
    "brazilian": "BR",
    "india": "IN",
    "indian": "IN",
    "china": "CN",
    "chinese": "CN",
    "japan": "JP",
    "japanese": "JP",
    "canada": "CA",
    "canadian": "CA",
    "australia": "AU",
    "australian": "AU",
}

# Sort by key length descending so multi-word names are tried first
_SORTED_COUNTRIES = sorted(COUNTRY_MAP.items(), key=lambda x: len(x[0]), reverse=True)

# ---------------------------------------------------------------------------
# Gender keyword sets
# ---------------------------------------------------------------------------
_MALE_PATTERN = re.compile(r"\b(male|males|man|men|boy|boys)\b")
_FEMALE_PATTERN = re.compile(r"\b(female|females|woman|women|girl|girls)\b")

# ---------------------------------------------------------------------------
# Age-group patterns
# ---------------------------------------------------------------------------
_AGE_GROUP_PATTERNS = [
    ("child", re.compile(r"\b(child|children|kid|kids)\b")),
    ("teenager", re.compile(r"\b(teenager|teenagers|teen|teens|adolescent|adolescents)\b")),
    ("adult", re.compile(r"\b(adult|adults)\b")),
    ("senior", re.compile(r"\b(senior|seniors|elderly)\b")),
]

# ---------------------------------------------------------------------------
# Age numeric patterns
# ---------------------------------------------------------------------------
_ABOVE_PATTERN = re.compile(r"\b(?:above|over|older than|at least)\s+(\d+)\b")
_BELOW_PATTERN = re.compile(r"\b(?:below|under|younger than|at most)\s+(\d+)\b")
_BETWEEN_PATTERN = re.compile(r"\bbetween\s+(\d+)\s+and\s+(\d+)\b")
_AGED_PATTERN = re.compile(r"\b(?:aged?)\s+(\d+)\b")


def _detect_country(query: str) -> Optional[str]:
    for name, code in _SORTED_COUNTRIES:
        pattern = r"\b" + re.escape(name) + r"\b"
        if re.search(pattern, query):
            return code
    return None


def parse_nlp_query(q: str) -> Optional[dict]:
    """
    Parse a plain-English query into a filter dict.
    Returns None if no recognisable filters can be extracted.

    Supported mappings
    ------------------
    Gender:
        male / males / man / men / boy / boys        → gender=male
        female / females / woman / women / girl/girls → gender=female
        (both detected)                              → no gender filter

    Age groups (stored values):
        child / children / kid / kids                → age_group=child
        teenager / teen / teens / adolescent         → age_group=teenager
        adult / adults                               → age_group=adult
        senior / seniors / elderly                   → age_group=senior

    Special age keyword (NOT a stored age_group):
        young                                        → min_age=16, max_age=24

    Age comparisons:
        above / over / older than / at least X       → min_age=X
        below / under / younger than / at most X     → max_age=X
        between X and Y                              → min_age=X, max_age=Y
        aged X                                       → min_age=X, max_age=X

    Country:
        from / in [country name or demonym]          → country_id=ISO code
        [country name alone in query]                → country_id=ISO code

    Rules:
        * Rule-based only — no external AI/LLM calls.
        * Filters are ANDed when multiple are detected.
        * If ZERO filters are extracted → returns None → caller returns 422.
    """
    if not q or not q.strip():
        return None

    query = q.lower().strip()
    filters: dict = {}

    # ── 1. Gender ─────────────────────────────────────────────────────────────
    has_male = bool(_MALE_PATTERN.search(query))
    has_female = bool(_FEMALE_PATTERN.search(query))

    if has_male and not has_female:
        filters["gender"] = "male"
    elif has_female and not has_male:
        filters["gender"] = "female"
    # Both detected → query mentions both genders → no gender filter applied

    # ── 2. Age group ──────────────────────────────────────────────────────────
    for group_name, pattern in _AGE_GROUP_PATTERNS:
        if pattern.search(query):
            filters["age_group"] = group_name
            break

    # ── 3. "young" → ages 16–24 ───────────────────────────────────────────────
    if re.search(r"\byoung\b", query):
        filters["min_age"] = 16
        filters["max_age"] = 24

    # ── 4. Age comparisons (can override/extend "young" bounds) ───────────────
    m = _ABOVE_PATTERN.search(query)
    if m:
        filters["min_age"] = int(m.group(1))

    m = _BELOW_PATTERN.search(query)
    if m:
        filters["max_age"] = int(m.group(1))

    m = _BETWEEN_PATTERN.search(query)
    if m:
        filters["min_age"] = int(m.group(1))
        filters["max_age"] = int(m.group(2))

    m = _AGED_PATTERN.search(query)
    if m:
        age_val = int(m.group(1))
        filters["min_age"] = age_val
        filters["max_age"] = age_val

    # ── 5. Country ────────────────────────────────────────────────────────────
    country_code = _detect_country(query)
    if country_code:
        filters["country_id"] = country_code

    # ── 6. Return None if nothing interpretable ───────────────────────────────
    return filters if filters else None
