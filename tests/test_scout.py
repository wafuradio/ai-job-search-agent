import json

import pytest

from src.scout import (
    ScoutQuery,
    build_scout_queries,
    get_scout_queries,
    load_scout_config,
)


def test_load_scout_config():
    config = load_scout_config()

    assert config["version"] == "1.0"
    assert config["search_strategy"]["country"] == "United States"
    assert config["rules"]["ai_in_title_required"] is False
    assert config["rules"]["exact_title_match_required"] is False


def test_build_scout_queries_returns_queries():
    config = load_scout_config()

    queries = build_scout_queries(config)

    assert len(queries) > 0
    assert all(isinstance(query, ScoutQuery) for query in queries)


def test_scout_includes_ai_transformation():
    queries = get_scout_queries()

    assert any(
        query.search_title == "AI Transformation"
        for query in queries
    )


def test_scout_includes_strategic_projects():
    queries = get_scout_queries()

    assert any(
        query.search_title == "Strategic Projects Lead"
        for query in queries
    )


def test_scout_includes_non_ai_titles():
    queries = get_scout_queries()

    assert any(
        query.search_title == "Principal Program Manager"
        for query in queries
    )


def test_queries_preserve_role_family():
    queries = get_scout_queries()

    strategic_project_query = next(
        query
        for query in queries
        if query.search_title == "Strategic Projects Lead"
    )

    assert strategic_project_query.role_family == "Strategic Operations"
    assert strategic_project_query.priority == "High"


def test_queries_use_full_time():
    queries = get_scout_queries()

    assert all(
        query.employment_type == "Full-time"
        for query in queries
    )


def test_missing_required_section_raises_error(tmp_path):
    config_path = tmp_path / "scout_config.json"

    config_path.write_text(
        json.dumps(
            {
                "search_strategy": {
                    "country": "United States",
                    "employment_types": ["Full-time"],
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_scout_config(config_path)


def test_role_family_without_titles_raises_error(tmp_path):
    config_path = tmp_path / "scout_config.json"

    config = {
        "search_strategy": {
            "country": "United States",
            "employment_types": ["Full-time"],
        },
        "priority_role_families": [
            {
                "family": "AI Transformation",
                "priority": "Highest",
                "search_titles": [],
            }
        ],
        "target_levels": ["Principal"],
        "discovery_sources": ["Company career sites"],
        "rules": {},
    }

    config_path.write_text(
        json.dumps(config),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_scout_config(config_path)