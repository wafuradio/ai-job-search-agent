"""Offline contract and integration checks; no paid API calls."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openai.lib._pydantic import to_strict_json_schema
from pydantic import ValidationError

from src import career_gaps
from src.career_gaps import CareerGap, CareerGapIntelligence
from src.evaluator import AIJobEvaluation
from test_evaluator import make_job, make_valid_ai_evaluation


def gap_data(gap_type="Evidence"):
    return {
        "requirement": "Demonstrated AI workflow impact",
        "gap_type": gap_type,
        "rationale": "Reported time savings need a documented measurement method.",
        "supporting_evidence": ["MongoDB automations eliminated 15+ hours of manual work weekly."],
        "confidence": "Medium",
        "questions_to_investigate": ["Is a before/after baseline available?"],
        "next_step": "Confirm the baseline and document personal contribution.",
        "opportunity": {
            "title": "Document an existing automation case study",
            "mongodb_connection": "Speaker invitation and agreement workflows",
            "practical_steps": ["Select one existing workflow and verify its baseline."],
            "evidence_to_capture": ["Sanitized workflow map, timing method, sample size and limitations"],
            "success_measure": "Comparable manual time per item before and after automation",
            "prerequisites_to_confirm": ["Owner approval and access to baseline data"],
        },
    }


@pytest.mark.parametrize("gap_type", ["Evidence", "Development", "Structural"])
def test_gap_categories_round_trip(gap_type):
    data = gap_data(gap_type)
    if gap_type == "Structural":
        data.update(
            requirement="Years of production ML engineering ownership",
            rationale="Not demonstrated and cannot be established by a small pilot.",
            supporting_evidence=[],
            next_step="Ask whether hands-on ML ownership is central to this role.",
            opportunity=None,
        )
    intelligence = CareerGapIntelligence(gaps=[CareerGap(**data)])
    assert CareerGapIntelligence.model_validate_json(intelligence.model_dump_json()) == intelligence


def test_unknown_category_is_rejected():
    with pytest.raises(ValidationError):
        CareerGap(**gap_data("Learnable"))


def test_evidence_gap_requires_existing_evidence():
    data = gap_data()
    data["supporting_evidence"] = []
    with pytest.raises(ValidationError, match="existing candidate evidence"):
        CareerGap(**data)


@pytest.mark.parametrize("gap_type", ["Evidence", "Development"])
def test_actionable_gaps_require_opportunities(gap_type):
    data = gap_data(gap_type)
    data["opportunity"] = None
    with pytest.raises(ValidationError, match="practical opportunity"):
        CareerGap(**data)


def test_structural_gap_cannot_be_closed_by_small_project():
    with pytest.raises(ValidationError, match="not a small project"):
        CareerGap(**gap_data("Structural"))


@pytest.mark.parametrize("field", ["practical_steps", "evidence_to_capture", "prerequisites_to_confirm"])
def test_opportunities_cannot_omit_action_or_capture_plan(field):
    data = gap_data()
    data["opportunity"][field] = []
    with pytest.raises(ValidationError):
        CareerGap(**data)


def test_context_preserves_evaluation_and_candidate_evidence():
    evaluation = AIJobEvaluation(**make_valid_ai_evaluation())
    original = deepcopy(evaluation.model_dump(mode="json"))
    payload = career_gaps.build_career_gap_payload(make_job(), evaluation)
    assert payload["context"]["evaluation"] == original
    assert payload["context"]["candidate_evidence"]["experience_evidence"]
    payload["context"]["evaluation"]["score_breakdown"]["compensation"] = 0
    assert evaluation.model_dump(mode="json") == original


def test_analyzer_passes_context_and_schema_without_mutating_score(monkeypatch):
    evaluation = AIJobEvaluation(**make_valid_ai_evaluation())
    original = evaluation.model_dump_json()
    intelligence = CareerGapIntelligence(gaps=[CareerGap(**gap_data())])
    parse = Mock(return_value=SimpleNamespace(output_parsed=intelligence))
    monkeypatch.setattr(career_gaps, "OpenAI", lambda: SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    result = career_gaps.analyze_career_gaps(make_job(), evaluation, model="test-model")
    assert result == intelligence
    assert evaluation.model_dump_json() == original
    args = parse.call_args.kwargs
    assert args["text_format"] is CareerGapIntelligence
    assert args["model"] == "test-model"
    assert '"candidate_evidence"' in args["input"][1]["content"]


def test_empty_model_response_raises_without_changing_evaluation(monkeypatch):
    evaluation = AIJobEvaluation(**make_valid_ai_evaluation())
    original = evaluation.model_dump_json()
    parse = Mock(return_value=SimpleNamespace(output_parsed=None))
    monkeypatch.setattr(career_gaps, "OpenAI", lambda: SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    with pytest.raises(RuntimeError, match="no structured analysis"):
        career_gaps.analyze_career_gaps(make_job(), evaluation)
    assert evaluation.model_dump_json() == original


def test_opt_in_wrapper_retains_all_original_evaluation_fields(monkeypatch):
    evaluation = AIJobEvaluation(**make_valid_ai_evaluation())
    original = evaluation.model_dump(mode="json")
    evaluate = Mock(return_value=evaluation)
    analyze = Mock(return_value=CareerGapIntelligence(gaps=[]))
    monkeypatch.setattr(career_gaps, "evaluate_job_with_ai", evaluate)
    monkeypatch.setattr(career_gaps, "analyze_career_gaps", analyze)
    job = make_job()
    result = career_gaps.evaluate_job_with_career_gaps(job, model="test-model")
    evaluate.assert_called_once_with(job, model="test-model")
    analyze.assert_called_once_with(job, evaluation, model="test-model")
    assert result.evaluation.model_dump(mode="json") == original
    assert result.evaluation.score_breakdown.total == 87
    assert result.career_gap_intelligence.gaps == []


def test_schema_can_be_used_for_strict_structured_output():
    schema = to_strict_json_schema(CareerGapIntelligence)
    assert schema["additionalProperties"] is False
    gap_schema = schema["$defs"]["CareerGap"]
    assert set(gap_schema["required"]) == set(gap_schema["properties"])
    assert "null" in [item.get("type") for item in gap_schema["properties"]["opportunity"]["anyOf"]]


def test_unresolved_information_is_separate_from_gaps():
    intelligence = CareerGapIntelligence(
        gaps=[],
        open_questions=[{
            "topic": "State eligibility",
            "why_unresolved": "Candidate residence is not supplied.",
            "question": "Does the candidate reside in an eligible state?",
        }],
    )
    assert intelligence.gaps == []
    assert CareerGapIntelligence.model_validate_json(intelligence.model_dump_json()) == intelligence


def test_older_saved_gap_analysis_remains_readable():
    intelligence = CareerGapIntelligence.model_validate({"gaps": [gap_data()]})
    assert intelligence.open_questions == []


def test_open_question_requires_an_actionable_question():
    with pytest.raises(ValidationError):
        CareerGapIntelligence(gaps=[], open_questions=[{
            "topic": "Total compensation",
            "why_unresolved": "Only base salary is disclosed.",
            "question": "",
        }])
