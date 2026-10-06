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

def test_relevance_finds_exact_role_title():
    from src.scout import score_job_relevance

    config = load_scout_config()

    result = score_job_relevance(
        title="AI Transformation Lead",
        description="Lead enterprise transformation.",
        config=config,
    )

    assert result.relevant is True
    assert result.score >= 3
    assert "AI Transformation" in result.matched_role_terms


def test_relevance_finds_adjacent_role_from_description():
    from src.scout import score_job_relevance

    config = load_scout_config()

    result = score_job_relevance(
        title="Principal Strategic Initiatives Manager",
        description=(
            "Lead operating models, governance, AI adoption, "
            "cross-functional leadership, and strategic initiatives."
        ),
        config=config,
    )

    assert result.relevant is True
    assert result.score >= 2
    assert len(result.matched_positive_signals) >= 2


def test_irrelevant_role_does_not_pass():
    from src.scout import score_job_relevance

    config = load_scout_config()

    result = score_job_relevance(
        title="Accounts Payable Clerk",
        description=(
            "Process invoices, reconcile payments, and maintain "
            "vendor records."
        ),
        config=config,
    )

    assert result.relevant is False
    assert result.score < 2


def test_caution_signal_reduces_score():
    from src.scout import score_job_relevance

    config = load_scout_config()

    clean = score_job_relevance(
        title="AI Operations Lead",
        description=(
            "Lead AI adoption, workflow automation, governance, "
            "and cross-functional leadership."
        ),
        config=config,
    )

    cautioned = score_job_relevance(
        title="AI Operations Lead",
        description=(
            "Lead AI adoption, workflow automation, governance, "
            "and cross-functional leadership. "
            "This role requires deep machine learning engineering."
        ),
        config=config,
    )

    assert cautioned.score < clean.score


def test_caution_signal_does_not_automatically_reject():
    from src.scout import score_job_relevance

    config = load_scout_config()

    result = score_job_relevance(
        title="Director AI Transformation",
        description=(
            "Lead AI transformation, AI adoption, governance, "
            "operating models, and cross-functional leadership. "
            "Some deep machine learning engineering collaboration "
            "is involved."
        ),
        config=config,
    )

    assert result.relevant is True
    assert "deep machine learning engineering" in (
        result.matched_caution_signals
    )       


def test_us_job_recognizes_state_location():
    from src.scout import is_us_job

    assert is_us_job("San Francisco, CA") is True
    assert is_us_job("New York City, NY") is True


def test_us_job_recognizes_multiple_us_locations():
    from src.scout import is_us_job

    location = (
        "San Francisco, CA | New York City, NY | Seattle, WA"
    )

    assert is_us_job(location) is True


def test_us_job_recognizes_remote_united_states():
    from src.scout import is_us_job

    location = (
        "London, UK; Ontario, CAN; "
        "Remote-Friendly, United States; San Francisco, CA"
    )

    assert is_us_job(location) is True


def test_non_us_job_is_rejected_by_geography():
    from src.scout import is_us_job

    assert is_us_job("Singapore") is False
    assert is_us_job("London, UK") is False
    assert is_us_job("Seoul, South Korea") is False


def test_missing_location_is_not_assumed_us():
    from src.scout import is_us_job

    assert is_us_job("") is False   
    

def test_excluded_profession_does_not_pass():
    from src.scout import score_job_relevance

    config = load_scout_config()

    result = score_job_relevance(
        title="Commercial Counsel, GTM",
        description=(
            "Lead strategic initiatives, governance, "
            "and cross-functional leadership."
        ),
        config=config,
    )

    assert result.relevant is False
    assert result.score == 0


def test_account_executive_does_not_pass():
    from src.scout import score_job_relevance

    config = load_scout_config()

    result = score_job_relevance(
        title="Growth Account Executive, Startups",
        description=(
            "Drive strategic initiatives and "
            "cross-functional leadership."
        ),
        config=config,
    )

    assert result.relevant is False


def test_adjacent_technical_title_is_not_excluded():
    from src.scout import score_job_relevance

    config = load_scout_config()

    result = score_job_relevance(
        title="AI Operations Engineer, Partnerships",
        description=(
            "Build AI-enabled workflows, improve systems, "
            "and lead cross-functional initiatives."
        ),
        config=config,
    )

    assert result.relevant is True    