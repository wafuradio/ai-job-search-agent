import json
import re
import unicodedata
from src.normalizer import clean_html
from src.candidates import get_candidate
from dataclasses import dataclass
from pathlib import Path
from typing import List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCOUT_CONFIG = get_candidate().directory / "scout_config.json"


@dataclass(frozen=True)
class ScoutQuery:
    role_family: str
    priority: str
    search_title: str
    country: str
    employment_type: str


def load_scout_config(
    config_path: Path = None,
    *, candidate=None,
) -> dict:
    """Load and perform basic validation of Scout configuration."""

    selected = get_candidate(candidate)
    config_path = Path(config_path) if config_path is not None else selected.directory / "scout_config.json"
    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    required_sections = [
        "search_strategy",
        "priority_role_families",
        "target_levels",
        "discovery_sources",
        "rules",
    ]

    for section in required_sections:
        if section not in config:
            raise ValueError(
                f"Scout config is missing required section: {section}"
            )

    search_strategy = config["search_strategy"]

    if not search_strategy.get("country"):
        raise ValueError("Scout config must define a country.")

    employment_types = search_strategy.get("employment_types", [])

    if not employment_types:
        raise ValueError(
            "Scout config must define at least one employment type."
        )

    role_families = config["priority_role_families"]

    if not role_families:
        raise ValueError(
            "Scout config must define at least one priority role family."
        )

    for family in role_families:
        if not family.get("family"):
            raise ValueError("Every role family must have a name.")

        if not family.get("priority"):
            raise ValueError(
                f"Role family '{family['family']}' must have a priority."
            )

        if not family.get("search_titles"):
            raise ValueError(
                f"Role family '{family['family']}' must have search titles."
            )

    from src.search_settings import discovery_scout_config
    return discovery_scout_config(config, selected)


def build_scout_queries(config: dict) -> List[ScoutQuery]:
    """
    Convert Scout configuration into structured discovery queries.

    Scout intentionally searches adjacent titles rather than requiring
    exact title matches. Fit decisions happen later in the pipeline.
    """

    country = config["search_strategy"]["country"]
    employment_types = config["search_strategy"]["employment_types"]

    queries: List[ScoutQuery] = []

    for family in config["priority_role_families"]:
        for search_title in family["search_titles"]:
            for employment_type in employment_types:
                queries.append(
                    ScoutQuery(
                        role_family=family["family"],
                        priority=family["priority"],
                        search_title=search_title,
                        country=country,
                        employment_type=employment_type,
                    )
                )

    return queries


def get_scout_queries(
    config_path: Path = None,
    *, candidate=None,
) -> List[ScoutQuery]:
    """Load Scout configuration and return discovery queries."""

    config = load_scout_config(config_path, candidate=candidate)
    return build_scout_queries(config)

@dataclass(frozen=True)
class ScoutRelevance:
    relevant: bool
    score: int
    matched_role_terms: List[str]
    matched_positive_signals: List[str]
    matched_caution_signals: List[str]


def _match_text(text):
    text = unicodedata.normalize("NFKC", clean_html(text)).casefold().replace("&", " and ")
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


def _find_matches(text: str, terms: List[str]) -> List[str]:
    normalized = " " + _match_text(text) + " "
    return [term for term in dict.fromkeys(terms)
            if " " + _match_text(term) + " " in normalized]


def has_excluded_title(
    title: str,
    config: dict,
) -> bool:
    """
    Return True when the job title clearly belongs to an
    out-of-scope profession.

    Exclusions apply only to titles, not job descriptions.
    """

    if not title:
        return False

    normalized_title = " " + _match_text(title) + " "

    excluded_terms = config.get(
        "excluded_title_terms",
        [],
    )

    return any(
        " " + _match_text(term) + " " in normalized_title
        for term in excluded_terms
    )


def score_job_relevance(
    title: str,
    description: str,
    config: dict,
) -> ScoutRelevance:
    """
    Perform a cheap deterministic relevance check before AI evaluation.

    This is intentionally permissive. Its purpose is to remove clearly
    irrelevant jobs, not to determine candidate fit.
    """

    title_text = title or ""
    description_text = description or ""
    if has_excluded_title(title_text, config):
        return ScoutRelevance(
        relevant=False,
        score=0,
        matched_role_terms=[],
        matched_positive_signals=[],
        matched_caution_signals=[],
    )
    combined_text = f"{title_text}\n{description_text}"

    role_terms = [
        search_title
        for family in config["priority_role_families"]
        for search_title in family["search_titles"]
    ]

    positive_signals = config.get("positive_signals", [])
    caution_signals = config.get("caution_signals", [])

    matched_role_terms = _find_matches(
        title_text,
        role_terms,
    )

    matched_positive_signals = _find_matches(
        combined_text,
        positive_signals,
    )

    matched_caution_signals = _find_matches(
        combined_text,
        caution_signals,
    )

    score = 0

    # A relevant title is useful, but not mandatory.
    score += 3 if matched_role_terms else 0

    # Description signals allow adjacent titles to surface.
    score += min(len(matched_positive_signals), 8)

    # Caution terms reduce priority but do not automatically reject.
    score -= min(len(matched_caution_signals), 4)

    # Keep the discovery filter permissive.
    relevant = score >= 2

    return ScoutRelevance(
        relevant=relevant,
        score=score,
        matched_role_terms=matched_role_terms,
        matched_positive_signals=matched_positive_signals,
        matched_caution_signals=matched_caution_signals,
    )

US_STATE_ABBREVIATIONS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

US_LOCATION_MARKERS = [
    "united states",
    "usa",
    "u.s.",
    "remote - us",
    "remote, us",
    "remote us",
    "remote-friendly, united states",
]


def is_us_job(location: str) -> bool:
    """
    Return True when a job location indicates United States eligibility.

    This is a discovery filter, not a remote-work determination.
    Hybrid and onsite U.S. roles are still allowed through Scout and
    can be flagged later by the Gatekeeper.
    """

    if not location:
        return False

    normalized_location = location.lower()

    location_parts = re.split(r"[;|]", normalized_location)

    for part in location_parts:
        cleaned_part = part.strip()

        if "," in cleaned_part:
            possible_state = cleaned_part.rsplit(",", 1)[-1].strip().upper()

            if possible_state in US_STATE_ABBREVIATIONS:
                return True    

    return bool(re.search(r"(?<!\w)(?:united states|usa|u\.s\.?|us)(?!\w)", normalized_location))