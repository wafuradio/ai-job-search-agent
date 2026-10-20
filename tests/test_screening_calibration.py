"""Synthetic and saved-posting-inspired regression cases; no fit/approval labels."""
from dataclasses import replace
from src.models import Job
from src.screening import screen_job, job_from_dict
from src.scout import score_job_relevance, load_scout_config, is_us_job
from src.evaluator import job_to_dict
from src.search_settings import load_search_settings


def job(title='Commercial Operations Program Manager', description='Lead process and system changes, workflow tooling and operational excellence.'):
    return Job(company='Example', title=title, job_url='https://example.com/1', source='test',
               location_text='New York, NY', remote_status='Hybrid', raw_description=description)


def test_missed_program_operations_role_now_surfaces():
    result = screen_job(job())
    assert result.accepted
    assert 'Program Manager' in result.matches['role_terms']
    assert any('Hybrid' in flag for flag in result.flags)


def test_explicit_revenue_ownership_filtered_but_generic_sales_disclaimer_is_not():
    actual = screen_job(job('AWS GTM Partnership Lead',
                           'Lead strategic initiatives and scalable processes.\nOwn forecasting, pipeline development, and revenue targets for partner-sourced business'))
    assert not actual.accepted
    assert any('revenue-target ownership' in reason for reason in actual.reasons)
    disclaimer = screen_job(job(description='Lead workflow automation and operational excellence.\nFor sales roles, ranges include commissions and bonuses.'))
    assert disclaimer.accepted


def test_nonquota_work_and_supporting_sales_not_rejected():
    result = screen_job(job(description='Lead workflow automation and operational excellence.\nThis role is not quota carrying. Support sellers as they meet revenue targets.'))
    assert result.accepted


def test_adjacent_engineering_title_flagged_without_blanket_rejection():
    result = screen_job(job('AI Operations Engineer, Partnerships', 'Build agentic workflows and business systems.'))
    assert result.accepted
    assert any('engineering' in flag for flag in result.flags)


def test_research_tpm_technical_depth_is_visible():
    result = screen_job(job('Technical Program Manager, RL Research', 'Own program management and cross-functional programs. Background in ML engineering and RLHF required.'))
    assert result.accepted
    assert any('Specialist technical' in flag for flag in result.flags)


def test_html_and_punctuation_do_not_hide_matches():
    config = load_scout_config()
    result = score_job_relevance('Strategy &amp; Operations', '<p>Lead cross functional programs and AI-enabled workflows.</p>', config)
    assert result.relevant
    assert 'cross-functional programs' in result.matched_positive_signals
    assert not is_us_job('Remote, Australia')
    assert is_us_job('Remote - U.S.')


def test_overlapping_title_strings_do_not_inflate_score():
    config = load_scout_config()
    assert score_job_relevance('AI Transformation Lead', '', config).score == 4
    # One title bonus, plus one AI transformation positive signal.


def test_unknown_compensation_is_question_not_rejection():
    result = screen_job(job())
    assert result.accepted
    assert any('Compensation' in flag for flag in result.flags)


def test_market_intelligence_only_company_is_not_application_candidate():
    result = screen_job(replace(job(), company='Example Research Only'))
    assert not result.accepted
    assert any('market intelligence' in reason for reason in result.reasons)


def test_explicit_geography_and_scope_preferences():
    result = screen_job(replace(job(), location_text='Remote', country='United States'))
    assert result.accepted
    search, profile = load_search_settings()
    search['search_scope']['include_hybrid'] = False
    assert not screen_job(job(), search=search, profile=profile).accepted


def test_serialized_job_roundtrip_preserves_facts():
    original = job()
    assert job_from_dict(job_to_dict(original)) == original
