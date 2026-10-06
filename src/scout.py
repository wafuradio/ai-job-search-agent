import json
from dataclasses import dataclass
from pathlib import Path
from typing import List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCOUT_CONFIG = PROJECT_ROOT / "config" / "scout_config.json"


@dataclass(frozen=True)
class ScoutQuery:
    role_family: str
    priority: str
    search_title: str
    country: str
    employment_type: str


def load_scout_config(
    config_path: Path = DEFAULT_SCOUT_CONFIG,
) -> dict:
    """Load and perform basic validation of Scout configuration."""

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

    return config


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
    config_path: Path = DEFAULT_SCOUT_CONFIG,
) -> List[ScoutQuery]:
    """Load Scout configuration and return discovery queries."""

    config = load_scout_config(config_path)
    return build_scout_queries(config)