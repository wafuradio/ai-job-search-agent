from src.compensation_extractor import extract_compensation
from src.models import Job


def make_job(description, title="AI Operations Lead"):
    return Job(
        company="Test Company",
        title=title,
        job_url="https://example.com/job",
        source="test",
        raw_description=description,
    )


def test_anthropic_salary_range():
    job = make_job(
        "Annual Salary:\n$200,000&mdash;$265,000 USD"
    )

    extract_compensation(job)

    assert job.compensation.published_min == 200000
    assert job.compensation.published_max == 265000
    assert job.compensation.compensation_type == "Uncertain"
    assert job.compensation.base_min is None
    assert job.compensation.base_max is None


def test_explicit_base_salary_range():
    job = make_job(
        "Base salary: $180,000 - $240,000 annually."
    )

    extract_compensation(job)

    assert job.compensation.published_min == 180000
    assert job.compensation.published_max == 240000
    assert job.compensation.base_min == 180000
    assert job.compensation.base_max == 240000
    assert job.compensation.compensation_type == "Base Salary"


def test_em_dash_salary_range():
    job = make_job(
        "Annual Salary: $215,000—$300,000 USD"
    )

    extract_compensation(job)

    assert job.compensation.published_min == 215000
    assert job.compensation.published_max == 300000
    assert job.compensation.compensation_type == "Uncertain"
    assert job.compensation.base_min is None


def test_placeholder_salary_is_ignored():
    job = make_job(
        "Annual Salary:\n$1&mdash;$2 USD"
    )

    extract_compensation(job)

    assert job.compensation.published_min is None
    assert job.compensation.published_max is None
    assert job.compensation.base_min is None


def test_missing_salary_is_not_invented():
    job = make_job(
        "Competitive compensation and equity."
    )

    extract_compensation(job)

    assert job.compensation.published_min is None
    assert job.compensation.base_min is None


def test_existing_compensation_is_preserved():
    job = make_job(
        "Annual Salary: $200,000—$265,000 USD"
    )

    job.compensation.base_min = 175000
    job.compensation.base_max = 225000

    extract_compensation(job)

    assert job.compensation.base_min == 175000
    assert job.compensation.base_max == 225000
    assert job.compensation.published_min is None


def test_explicit_ote_is_not_base_salary():
    job = make_job(
        "On Target Earnings (OTE): $250,000—$350,000 USD"
    )

    extract_compensation(job)

    assert job.compensation.published_min == 250000
    assert job.compensation.published_max == 350000
    assert job.compensation.compensation_type == "OTE"
    assert job.compensation.base_min is None


def test_generic_ote_disclaimer():
    job = make_job(
        "For sales roles, the range provided is the role's "
        "On Target Earnings (OTE) range.\n"
        "Annual Salary:\n"
        "$200,000—$265,000 USD"
    )

    extract_compensation(job)

    assert job.compensation.published_min == 200000
    assert job.compensation.published_max == 265000
    assert job.compensation.compensation_type == "Uncertain"
    assert job.compensation.base_min is None


def test_sales_adjacent_role_remains_uncertain():
    job = make_job(
        "For sales roles, the range provided is the role's "
        "On Target Earnings (OTE) range.\n"
        "Annual Salary:\n"
        "$365,000—$425,000 USD",
        title="AWS GTM Partnership Lead",
    )

    extract_compensation(job)

    assert job.compensation.published_min == 365000
    assert job.compensation.published_max == 425000
    assert job.compensation.compensation_type == "Uncertain"
    assert job.compensation.base_min is None


def test_total_compensation_is_not_base_salary():
    job = make_job(
        "Total compensation: $300,000—$450,000 annually."
    )

    extract_compensation(job)

    assert job.compensation.published_min == 300000
    assert job.compensation.published_max == 450000
    assert job.compensation.compensation_type == "Total Compensation"
    assert job.compensation.base_min is None
    assert job.compensation.total_comp_estimate is None


def test_compensation_evidence_is_preserved():
    job = make_job(
        "Annual Salary:\n$200,000&mdash;$265,000 USD"
    )

    extract_compensation(job)

    assert "Annual Salary:" in job.compensation.compensation_text
    assert "$200,000—$265,000" in job.compensation.compensation_text