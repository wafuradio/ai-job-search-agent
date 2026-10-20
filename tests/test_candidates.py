"""Synthetic candidates verify configuration, evidence, and approval isolation."""
import contextlib
import hashlib
import io
import json
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.candidates import PROJECT_ROOT, get_candidate, app_settings
from src.models import Job
from src.review_store import ReviewStore
from src.scout import load_scout_config, score_job_relevance
from src.screening import screen_job
from src.evaluator import build_evaluation_payload, build_evaluation_instructions, AIJobEvaluation
from src import evaluator, career_gaps, discovery
from src.career_gaps import DevelopmentOpportunity
from src.review_display import shortlist_records, write_html_report
from candidate_profiles import main as profiles_main
from test_evaluator import make_valid_ai_evaluation


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def change_json(candidate_dir, name, update):
    path = candidate_dir / name
    data = json.loads(path.read_text())
    update(data)
    write_json(path, data)


@pytest.fixture
def candidate_root(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    shutil.copytree(PROJECT_ROOT / 'templates', root / 'templates')
    write_json(root / 'config/app_config.json', {'default_candidate':'alex', 'legacy_database_owner':'alex'})
    for candidate_id, role, target in [('alex', 'Data Engineer', 120000), ('sam', 'Junior Account Executive', 90000)]:
        profiles_main(['init', '--candidate', candidate_id, '--display-name', candidate_id.title()], root=root)
        directory = root / 'profiles' / candidate_id
        change_json(directory, 'career_profile.json', lambda data: data.update(
            target_roles={'primary':[role], 'selective':[]}, compensation={'target_total_compensation_usd':target},
            career_objective=f'{candidate_id}-only objective'))
        change_json(directory, 'scout_config.json', lambda data: data.update(
            priority_role_families=[{'family':role,'priority':'High','search_titles':[role]}]))
        change_json(directory, 'candidate_evidence.json', lambda data: data.update(
            experience_evidence=[{'capability':candidate_id + '-only evidence','evidence':['Verified synthetic example']}]))
        change_json(directory, 'career_gap_context.json', lambda data: data.update(work_context=candidate_id + '-only development context'))
        change_json(directory, 'company_boards.json', lambda data: data.update(boards=[{
            'company':candidate_id.title(),'source':'ashby','board_token':candidate_id}]))
    return root


def synthetic_job():
    return Job(company='Example',title='Junior Account Executive',job_url='https://example.test/same-job',source='test',
               location_text='New York, NY',remote_status='Hybrid',employment_type='Part-time',
               raw_description='Own revenue targets for this sales territory.')


def test_default_profile_preserves_example_preferences():
    candidate = get_candidate()
    assert candidate.candidate_id == 'example'
    assert candidate.database_path == PROJECT_ROOT / 'data/jobs.db'
    assert candidate.load('career_profile.json')['compensation']['target_total_compensation_usd'] == 200000
    assert candidate.load('candidate_evidence.json')['experience_evidence']


def test_explicit_profiles_do_not_inherit_default_terms(candidate_root):
    alex, sam = (get_candidate(name, root=candidate_root) for name in ('alex','sam'))
    config = load_scout_config(candidate=sam)
    assert not config.get('additional_role_terms')
    assert not score_job_relevance('AI Transformation Lead', '', config).relevant
    assert screen_job(synthetic_job(), candidate=sam).accepted
    assert not screen_job(synthetic_job(), candidate=alex).accepted
    assert not screen_job(synthetic_job()).accepted  # Example Candidate excludes junior/sales/part-time work.
    assert sam.database_path == candidate_root / 'data/candidates/sam/jobs.db'
    assert alex.database_path == candidate_root / 'data/jobs.db'


def test_evaluation_payload_uses_only_selected_candidate(candidate_root):
    alex, sam = (get_candidate(name, root=candidate_root) for name in ('alex','sam'))
    job = synthetic_job()
    first = build_evaluation_payload(job, alex)
    second = build_evaluation_payload(job, sam)
    assert first['context']['candidate_id'] == 'alex'
    assert second['context']['candidate_id'] == 'sam'
    first_text, second_text = json.dumps(first), json.dumps(second)
    assert 'alex-only evidence' in first_text and 'alex-only evidence' not in second_text
    assert 'sam-only evidence' in second_text and 'sam-only evidence' not in first_text
    assert '$120,000' in first['instructions'] and '$90,000' in second['instructions']
    assert '$200,000' not in first_text + second_text
    assert 'Private Employer' not in first_text + second_text
    assert 'Remote work is strongly preferred' not in first['instructions']
    # Interleaved calls cannot change the default profile or each other's inputs.
    assert build_evaluation_payload(job, alex) == first
    assert get_candidate().candidate_id == 'example'


def test_missing_compensation_stays_unknown(candidate_root):
    path = candidate_root / 'profiles/sam'
    change_json(path,'career_profile.json',lambda data:data.update(compensation={}))
    instructions = build_evaluation_instructions(get_candidate('sam',root=candidate_root))
    assert 'No compensation target is supplied' in instructions
    assert '$200,000' not in instructions


def test_career_gap_context_is_candidate_specific_and_legacy_analysis_readable(candidate_root):
    sam = get_candidate('sam',root=candidate_root)
    evaluation = AIJobEvaluation(**make_valid_ai_evaluation())
    payload = career_gaps.build_career_gap_payload(synthetic_job(),evaluation,sam)
    assert 'sam-only development context' in payload['instructions']
    assert 'Private Employer' not in payload['instructions']
    assert 'alex-only' not in json.dumps(payload)
    values = dict(title='Example', mongodb_connection='Legacy saved context', practical_steps=['Check'],
                  evidence_to_capture=['Document'],success_measure='Measure',prerequisites_to_confirm=['Permission'])
    legacy = DevelopmentOpportunity(**values)
    assert legacy.context_connection == legacy.mongodb_connection == 'Legacy saved context'
    assert 'context_connection' in legacy.model_dump()
    assert 'mongodb_connection' not in legacy.model_dump()


def test_mocked_ai_call_and_gap_wrapper_propagate_profile(candidate_root, monkeypatch):
    sam = get_candidate('sam',root=candidate_root)
    evaluation = AIJobEvaluation(**make_valid_ai_evaluation())
    parse = Mock(return_value=SimpleNamespace(output_parsed=evaluation))
    monkeypatch.setattr(evaluator,'OpenAI',lambda:SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    assert evaluator.evaluate_job_with_ai(synthetic_job(),model='offline',candidate=sam) == evaluation
    content = parse.call_args.kwargs['input'][1]['content']
    assert 'sam-only evidence' in content and 'Private Employer' not in content
    evaluate = Mock(return_value=evaluation)
    analyze = Mock(return_value=career_gaps.CareerGapIntelligence(gaps=[]))
    monkeypatch.setattr(career_gaps,'evaluate_job_with_ai',evaluate)
    monkeypatch.setattr(career_gaps,'analyze_career_gaps',analyze)
    job=synthetic_job()
    career_gaps.evaluate_job_with_career_gaps(job,model='offline',candidate=sam)
    evaluate.assert_called_once_with(job,model='offline',candidate=sam)
    analyze.assert_called_once_with(job,evaluation,model='offline',candidate=sam)


def test_same_job_has_independent_evaluations_decisions_and_approval(candidate_root):
    alex,sam=(get_candidate(name,root=candidate_root) for name in ('alex','sam'))
    evaluation = AIJobEvaluation(**make_valid_ai_evaluation())
    with ReviewStore(candidate=alex) as a, ReviewStore(candidate=sam) as b:
        a_id=a.save_job(synthetic_job());b_id=b.save_job(synthetic_job())
        assert a_id == b_id == 1
        a.save_evaluation(a_id,evaluation,revision=1)
        a.approve_job(a_id,confirmation='APPROVE 1',revision=1,notes='Alex approval only')
        b.set_status(b_id,'Rejected','Sam decision only')
        a.require_job_approval(1)
        with pytest.raises(PermissionError):b.require_job_approval(1)
        assert not b.get_job(1)['evaluations']
        assert 'Sam decision' not in json.dumps(a.get_job(1))
        assert 'Alex approval' not in json.dumps(b.get_job(1))
        with pytest.raises(PermissionError):a.require_submission_approval(1,materials_digest='abc')
    with ReviewStore(candidate=sam,readonly=True) as store:
        assert store.get_job(1)['status']=='Rejected'
        assert store.get_job(1)['candidate_id']=='sam'


@pytest.mark.parametrize('readonly',[False,True])
def test_wrong_candidate_database_override_refused_before_mutation(candidate_root,readonly):
    alex,sam=(get_candidate(name,root=candidate_root) for name in ('alex','sam'))
    with ReviewStore(candidate=sam) as store:store.save_job(synthetic_job())
    before=sam.database_path.read_bytes()
    with pytest.raises(ValueError,match='belongs to candidate sam'):
        ReviewStore(sam.database_path,candidate=alex,readonly=readonly)
    assert before==sam.database_path.read_bytes()
    with pytest.raises(ValueError,match='legacy database belongs'):
        ReviewStore(alex.database_path,candidate=sam,readonly=readonly)


def test_legacy_database_binding_preserves_every_record(candidate_root):
    alex=get_candidate('alex',root=candidate_root)
    with ReviewStore(candidate=alex) as store:
        job_id=store.save_job(synthetic_job())
        store.set_status(job_id,'Interested','Preserve original decision')
        before=store.get_job(job_id)
        store.connection.execute('DROP TABLE database_metadata');store.connection.commit()
    original_bytes=alex.database_path.read_bytes()
    with ReviewStore(candidate=alex,readonly=True) as store:
        assert store.get_job(job_id)==before
    assert original_bytes==alex.database_path.read_bytes()
    with ReviewStore(candidate=alex) as store:
        assert store.get_job(job_id)==before
        assert store.connection.execute("SELECT value FROM database_metadata WHERE key='candidate_id'").fetchone()[0]=='alex'


def test_unowned_existing_database_not_silently_assigned(candidate_root,tmp_path):
    alex=get_candidate('alex',root=candidate_root)
    with ReviewStore(candidate=alex) as store:
        store.save_job(synthetic_job())
        store.connection.execute('DROP TABLE database_metadata');store.connection.commit()
    copied=tmp_path/'ambiguous.db';shutil.copy2(alex.database_path,copied)
    before=copied.read_bytes()
    with pytest.raises(ValueError,match='unowned database'):
        ReviewStore(copied,candidate=alex)
    assert before==copied.read_bytes()


def test_changing_default_never_reassigns_legacy_database(candidate_root):
    settings=app_settings(candidate_root);settings['default_candidate']='sam'
    write_json(candidate_root/'config/app_config.json',settings)
    assert get_candidate(root=candidate_root).candidate_id=='sam'
    assert get_candidate(root=candidate_root).database_path==candidate_root/'data/candidates/sam/jobs.db'
    assert get_candidate('alex',root=candidate_root).database_path==candidate_root/'data/jobs.db'


@pytest.mark.parametrize('bad',['../example','/tmp/example','Example Candidate','a/b','a\\b','', 'x'*65])
def test_invalid_candidate_id_rejected(candidate_root,bad):
    with pytest.raises(ValueError):get_candidate(bad,root=candidate_root)


def test_unknown_or_incomplete_candidate_does_not_fall_back(candidate_root):
    with pytest.raises(ValueError,match='Unknown candidate'):get_candidate('missing',root=candidate_root)
    (candidate_root/'profiles/sam/candidate_evidence.json').unlink()
    with pytest.raises(ValueError,match='missing candidate_evidence'):get_candidate('sam',root=candidate_root)


def test_profiles_cannot_disable_human_approval(candidate_root):
    path=candidate_root/'profiles/sam'
    change_json(path,'career_profile.json',lambda data:data.update(human_review={'required_before_application':False,'automatic_application_allowed':True}))
    with pytest.raises(ValueError,match='human approval'):get_candidate('sam',root=candidate_root)


def test_profile_symlink_cannot_read_another_profile(candidate_root):
    directory=candidate_root/'profiles/sam'
    (directory/'candidate_evidence.json').unlink()
    (directory/'candidate_evidence.json').symlink_to(candidate_root/'profiles/alex/candidate_evidence.json')
    with pytest.raises(ValueError,match='own directory'):get_candidate('sam',root=candidate_root)


def test_scaffold_is_neutral_incomplete_and_does_not_create_db(candidate_root):
    profiles_main(['init','--candidate','new-person','--display-name','New Person'],root=candidate_root)
    folder=candidate_root/'profiles/new-person'
    content=''.join(path.read_text() for path in folder.glob('*.json'))
    assert 'Private Employer' not in content and '200000' not in content
    assert json.loads((folder/'candidate_evidence.json').read_text())['experience_evidence']==[]
    with pytest.raises(ValueError,match='at least one target'):get_candidate('new-person',root=candidate_root)
    assert not (candidate_root/'data/candidates/new-person/jobs.db').exists()
    with pytest.raises(SystemExit):profiles_main(['init','--candidate','new-person','--display-name','Other'],root=candidate_root)


def test_discovery_and_html_use_selected_profile(candidate_root,monkeypatch,tmp_path):
    sam=get_candidate('sam',root=candidate_root)
    monkeypatch.setattr(discovery,'fetch_ashby_jobs',lambda *args:[synthetic_job()])
    with ReviewStore(candidate=sam) as store:
        result=discovery.discover_boards(store,discovery.load_boards(candidate=sam))
        assert result.accepted_ids == {1}
        rows=shortlist_records(store)
        assert rows[0]['candidate_id']=='sam'
        report=write_html_report(rows,tmp_path/'report.html').read_text()
        assert '--candidate sam' in report
        assert 'Candidate: Sam' in report
        assert '--candidate example' not in report


def test_review_cli_selects_candidate_and_rejects_cross_database(candidate_root,monkeypatch,capsys):
    import review_jobs
    resolve=lambda candidate=None:get_candidate(candidate,root=candidate_root)
    monkeypatch.setattr(review_jobs,'get_candidate',resolve)
    sam=resolve('sam');alex=resolve('alex')
    with ReviewStore(candidate=sam) as store:store.save_job(synthetic_job())
    with ReviewStore(candidate=alex) as store:store.save_job(synthetic_job())
    review_jobs.main(['--candidate','sam','status','1','Interested','--notes','Only Sam'])
    review_jobs.main(['--candidate','sam','show','1','--json'])
    assert 'Only Sam' in capsys.readouterr().out
    with ReviewStore(candidate=alex,readonly=True) as store:assert store.get_job(1)['status']=='New'
    with pytest.raises(SystemExit) as error:
        review_jobs.main(['--candidate','alex','--db',str(sam.database_path),'status','1','Rejected'])
    assert error.value.code==1
    with ReviewStore(candidate=sam,readonly=True) as store:assert store.get_job(1)['status']=='Interested'


def test_free_runner_selects_profile_boards_and_database(candidate_root,monkeypatch):
    import run_discovery
    monkeypatch.setattr(run_discovery,'get_candidate',lambda candidate=None:get_candidate(candidate,root=candidate_root))
    seen=[]
    def fake_fetch(token,company):
        seen.append((token,company))
        return [synthetic_job()]
    monkeypatch.setattr(discovery,'fetch_ashby_jobs',fake_fetch)
    assert run_discovery.main(['--candidate','sam'])==0
    assert seen==[('sam','Sam')]
    assert not get_candidate('alex',root=candidate_root).database_path.exists()
    with ReviewStore(candidate=get_candidate('sam',root=candidate_root),readonly=True) as store:
        assert len(store.list_jobs())==1
        assert store.get_job(1)['candidate_id']=='sam'


def test_new_opportunity_schema_is_candidate_neutral():
    from openai.lib._pydantic import to_strict_json_schema
    schema=to_strict_json_schema(career_gaps.CareerGapIntelligence)
    opportunity=schema['$defs']['DevelopmentOpportunity']
    assert 'context_connection' in opportunity['properties']
    assert 'mongodb_connection' not in opportunity['properties']


def test_candidate_profiles_validate_without_network(candidate_root,capsys):
    profiles_main(['validate','--candidate','sam'],root=candidate_root)
    assert 'Valid: Sam' in capsys.readouterr().out


def test_empty_html_report_retains_selected_candidate(candidate_root,tmp_path):
    sam=get_candidate('sam',root=candidate_root)
    report=write_html_report([],tmp_path/'empty.html',candidate=sam).read_text()
    assert 'Local job shortlist — Sam' in report
    assert 'Example Candidate' not in report


def test_new_role_priority_rules_are_not_inherited_by_other_candidates(candidate_root):
    sam=get_candidate('sam',root=candidate_root)
    result=screen_job(synthetic_job(),candidate=sam)
    assert result.priority['band']=='unconfigured'
    assert not result.priority['specialist_evidence']
    assert not result.priority['questions']
