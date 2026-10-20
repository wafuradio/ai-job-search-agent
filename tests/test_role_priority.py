"""Role-function and qualification regression cases, not human fit decisions."""
from copy import deepcopy
from dataclasses import asdict
import json

import pytest

from src.candidates import get_candidate
from src.models import Job
from src.role_priority import prioritize_role, role_passages, validate_priority_config
from src.review_store import ReviewStore
from src.review_display import shortlist_records, render_summary, write_html_report
from review_jobs import main


def rules():
    return get_candidate().load('screening_rules.json')['role_priority']


def job(title, description):
    return Job(company='Synthetic Example', title=title, source='offline-test',
               job_url='https://example.test/' + str(len(title)), location_text='Remote - US',
               remote_status='Fully Remote', raw_description=description)


@pytest.mark.parametrize('title,description,band,question', [
    ('Commercial Operations Program Manager',
     'About the role\nResponsibilities\nImplement process and system changes across partner teams.\nTake ownership of workflow tooling and automation.\nMinimum qualifications\nStrong working knowledge of billing systems and payments platforms.',
     'operational', 'billing/payments'),
    ('Head of AI Enabled Business Systems',
     'ABOUT THE ROLE\nDefine the business systems strategy and roadmap.\nRedesign workflows across the company.\nEvaluate AI tooling for business applications.\nWHAT WE’RE LOOKING FOR\nDemonstrated ownership of large-scale enterprise application portfolios.',
     'operational', 'enterprise-platform'),
    ('Program Manager, Workforce Operations',
     'About the role\nTurn broken processes into scalable processes.\nEstablish service levels and a system of record.\nMinimum qualifications\nHave personally run onboarding for BPO workforces.',
     'operational', 'BPO'),
    ('Head of Tax',
     'POSITION OVERVIEW\nImprove processes and drive automation across tax operations.\nQUALIFICATIONS\n8+ years of progressive tax experience and significant experience in indirect taxation.',
     'specialist', 'tax practice'),
    ('Global Senior Equity Program Manager',
     'About the role\nBuild scalable processes for equity transactions.\nYou may be a good fit if you have\nA Certified Equity Professional designation.\n8+ years in stock plan management.',
     'specialist', 'stock-plan'),
    ('Technical Program Manager, RL Research',
     'About the role\nCoordinate cross-functional programs.\nYou May Be a Good Fit If You\nHave a background in ML engineering and deep experience with ML training pipelines.',
     'specialist', 'ML/research'),
    ('Technical Program Manager, Infrastructure',
     'About the Role\nDrive cross-functional programs and improve processes.\nMinimum qualifications\n5+ years delivering programs in large-scale distributed systems.',
     'specialist', 'large-scale infrastructure'),
    ('AI Operations Engineer, Partnerships',
     'About the role\nRedesign workflows and define an operating model.\nDesign agentic workflows for internal operations.\nMinimum qualifications\nHands-on experience building with LLMs and scripting the glue between APIs.',
     'adjacent', 'scripting'),
    ('Strategic Projects Lead, Recruiting',
     'About the role\nOwn the operating rhythm and improve processes across teams.\nMinimum qualifications\nHave been part of a talent team and understand how recruiting operates day to day.',
     'adjacent', 'recruiting-centered'),
    ('Member of Technical Staff, Software Engineer',
     'ABOUT US\nOur company builds AI.\nTHE ROLE\nDesign and build scalable backend services.\nMINIMUM QUALIFICATIONS\nExperience shipping production systems.',
     'specialist', 'production software'),
])
def test_saved_posting_inspired_cases(title, description, band, question):
    result = prioritize_role(job(title, description), rules())
    assert result.band == band
    assert any(question in q for q in result.questions)
    evidence = result.specialist_evidence or result.evidence
    assert evidence
    assert all(item['text'] in description for item in evidence)


def test_title_only_never_establishes_operational_alignment_or_specialist_requirement():
    assert prioritize_role(job('Head of Tax', ''), rules()).band == 'limited'
    assert prioritize_role(job('AI Transformation Lead', 'Our company is growing.'), rules()).band == 'limited'


def test_company_ai_boilerplate_does_not_supply_role_evidence():
    description = ('ABOUT US\nWe design agentic workflows, improve processes and build AI tools.\n'
                   'ABOUT THE ROLE\nKeep the calendar up to date.\nQUALIFICATIONS\nGood organization skills.')
    result = prioritize_role(job('Program Manager', description), rules())
    assert result.band == 'limited' and not result.evidence


def test_generic_engineering_collaboration_is_not_prior_ml_ownership():
    description = ('About the role\nBuild an operating model and improve processes.\n'
                   'Work with ML engineering colleagues to coordinate launches.\n'
                   'Minimum qualifications\nProgram management experience.')
    result = prioritize_role(job('Technical Program Manager', description), rules())
    assert result.band == 'operational'
    assert not result.specialist_evidence


@pytest.mark.parametrize('description', [
    'About the role\nCoordinate launches.\nPreferred qualifications\nA background in ML engineering.',
    'About the role\nCoordinate launches.\nMinimum qualifications\nA background in ML engineering is preferred.',
    'About the role\nCoordinate launches.\nMinimum qualifications\nA background in ML engineering is not required.',
    'About the role\nCoordinate launches.\nMinimum qualifications\nYou do not need a background in ML engineering.',
])
def test_preferred_or_negated_ml_qualifications_do_not_establish_specialist_requirement(description):
    result = prioritize_role(job('Technical Program Manager', description), rules())
    assert not result.specialist_evidence
    assert result.band != 'specialist'


def test_preferred_credential_does_not_become_required():
    result = prioritize_role(job('Head of Equity Administration',
        'About the role\nImprove processes.\nPreferred qualifications\nCertified Equity Professional designation.'), rules())
    assert not result.specialist_evidence


def test_required_and_preferred_sentences_on_same_line_are_separate():
    passages = role_passages('Minimum qualifications\nBackground in ML engineering is preferred. Experience operating RLHF systems is required.')
    assert passages[0]['preferred']
    assert not passages[0]['requirement']
    assert passages[1]['requirement']


def test_html_headings_and_entities_preserve_qualification_sections():
    passages = role_passages('<h2>About the role</h2><p>Improve processes.</p><h2>Minimum qualifications</h2><p>Tax experience &amp; indirect taxation.</p>')
    assert any(p['requirement'] and 'Tax experience & indirect taxation.' in p['text'] for p in passages)


def test_absent_or_disabled_configuration_does_not_inherit_example_rules():
    posting = job('Head of Tax', 'Qualifications\nTax experience is required.')
    assert prioritize_role(posting).band == 'unconfigured'
    config = rules(); config['enabled'] = False
    assert prioritize_role(posting, config).band == 'unconfigured'


def test_profile_can_target_specialist_work_without_default_candidate_priority_penalty():
    config = {'enabled': True, 'target_title_pattern': r'\btax\b', 'operational_signals': [
        {'label': 'Tax process improvement', 'pattern': r'improve.*processes'},
        {'label': 'Tax program ownership', 'pattern': r'own.*tax programs'}],
        'specialist_checks': [], 'investigation_checks': []}
    validate_priority_config(config)
    result = prioritize_role(job('Head of Tax', 'About the role\nImprove tax processes and own tax programs.\nQualifications\nPrior tax experience.'), config)
    assert result.band == 'operational'
    assert not result.specialist_evidence


@pytest.mark.parametrize('change', [
    lambda config: config['operational_signals'][0].update(pattern='['),
    lambda config: config['specialist_checks'][0].update(evidence_scope='anything'),
    lambda config: config['investigation_checks'][0].update(question=''),
    lambda config: config.update(target_title_pattern=12),
])
def test_invalid_ranking_rules_fail_validation(change):
    config = rules(); change(config)
    with pytest.raises(ValueError): validate_priority_config(config)


def seed(path):
    with ReviewStore(path) as store:
        tax = job('Head of Tax', 'About the role\nLead workflow automation, strategic initiatives, governance, operating models, operational excellence, program management, AI adoption and process improvement.\nQualifications\n8+ years of tax experience and significant experience in indirect taxation.')
        ops = job('AI Transformation Lead', 'About the role\nImprove processes and define an operating model.\nLead cross-functional programs.')
        tax_id = store.save_job(tax)
        ops_id = store.save_job(ops)
        store.set_status(tax_id, 'Interested', 'Preserve my interest even if ranking changes')
        return tax_id, ops_id


def test_review_categories_override_keyword_order_without_mutating_decisions(tmp_path):
    path = tmp_path / 'review.db'
    tax_id, ops_id = seed(path)
    before = path.read_bytes()
    with ReviewStore(path, readonly=True) as store:
        rows = shortlist_records(store)
        by_id = {row['id']: row for row in rows}
        assert by_id[tax_id]['discovery'].score > by_id[ops_id]['discovery'].score
        assert rows[0]['id'] == ops_id
        assert by_id[tax_id]['status'] == 'Interested'
        assert by_id[tax_id]['discovery'].accepted
        specialist = shortlist_records(store, priority='specialist')
        assert [row['id'] for row in specialist] == [tax_id]
        report = write_html_report(rows, tmp_path / 'report.html').read_text()
        assert 'Specialist focus' in report and 'tax practice' in report
        assert 'not a fit verdict' in render_summary(by_id[tax_id])
    assert path.read_bytes() == before


def test_cli_exposes_priority_filter(tmp_path, capsys):
    path = tmp_path / 'review.db'
    seed(path)
    main(['--db', str(path), 'shortlist', '--priority', 'specialist'])
    output = capsys.readouterr().out
    assert 'Head of Tax' in output and 'AI Transformation Lead' not in output
