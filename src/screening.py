"""Explain deterministic discovery decisions. Never changes human review status."""
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

from src.models import Job, Compensation
from src.gatekeeper import evaluate_job, REJECT
from src.scout import load_scout_config, score_job_relevance, is_us_job, has_excluded_title
from src.search_settings import load_search_settings
from src.candidates import get_candidate
from src.role_priority import prioritize_role


@dataclass
class DiscoveryScreening:
    accepted: bool
    score: int
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    matches: dict = field(default_factory=dict)
    gatekeeper: dict = field(default_factory=dict)
    priority: dict = field(default_factory=dict)


def job_from_dict(data):
    data = dict(data)
    data['compensation'] = Compensation(**data.get('compensation', {}))
    if isinstance(data.get('discovered_at'), str):
        data['discovered_at'] = datetime.fromisoformat(data['discovered_at'])
    return Job(**data)


def screen_job(job, config=None, search=None, profile=None, *, candidate=None):
    selected = get_candidate(candidate)
    rules = selected.load('screening_rules.json')
    config = config if config is not None else load_scout_config(candidate=selected)
    if search is None or profile is None:
        default_search, default_profile = load_search_settings(candidate=selected)
        search = default_search if search is None else search
        profile = default_profile if profile is None else profile
    relevance = score_job_relevance(job.title, job.raw_description or '', config)
    gate = evaluate_job(job, candidate=selected, profile=profile)
    reasons, flags = [], list(gate.flags)
    scope_country = search.get('search_scope', {}).get('country', 'United States')
    if scope_country != 'United States':
        raise ValueError('Discovery currently supports United States search scope only')
    worldwide = (job.location_text or '').strip().casefold() in ('worldwide', 'anywhere in the world', 'anywhere', 'global', 'remote - worldwide')
    if worldwide:
        flags.append('Source advertises worldwide eligibility; confirm U.S. hiring and any description-specific restrictions.')
    if not worldwide and not is_us_job(job.location_text or '') and job.country not in ('United States', 'USA', 'US'):
        reasons.append('U.S. eligibility not identified; geography needs confirmation.')
    if has_excluded_title(job.title, config):
        reasons.append('Title matches an excluded profession or junior role.')
    elif not relevance.relevant:
        reasons.append('Scout relevance below discovery threshold (2).')
    reasons.extend(gate.reasons if gate.status == REJECT else [])
    if gate.status != REJECT:
        flags.extend(gate.reasons)
    # Inspect individual responsibility lines, not global sales compensation boilerplate.
    for line in ((job.raw_description or '').splitlines() if rules['exclude_sales_ownership'] else []):
        if re.search(r'\b(?:not|no|without|non)[ -]+(?:\w+[ -]+){0,3}(?:quota|revenue target)', line, re.I):
            continue
        if re.search(r'\b(?:own|carry|carrying|meet|hit)\b[^.!?]{0,100}\b(?:quota|revenue targets?)\b', line, re.I):
            reasons.append('Explicit sales quota or revenue-target ownership: ' + line.strip())
            break
    text = (job.title + '\n' + (job.raw_description or '')).lower()
    if rules['flag_technical_depth'] and re.search(r'\b(engineer|engineering|technical|research|silicon)\b', job.title, re.I):
        flags.append('Confirm required hands-on engineering or domain depth against candidate evidence.')
    if rules['flag_technical_depth'] and re.search(r'\b(ml engineering|ml research|rlhf|silicon/so[cC]|model training)\b', text):
        flags.append('Specialist technical requirements need investigation; program leadership alone may not satisfy them.')
    if rules['flag_commercial_context'] and re.search(r'\b(gtm|sales|commercial|partnerships?)\b', job.title, re.I):
        flags.append('Commercial context: distinguish operational improvement from direct selling.')
    if not job.compensation.compensation_text:
        flags.append('Compensation is undisclosed or not extracted; investigate.')
    scope = search.get('search_scope', {})
    remote = (job.remote_status or '').casefold()
    if scope.get('remote_only') or profile.get('work_model', {}).get('remote_is_hard_requirement'):
        if 'remote' not in remote:
            reasons.append('Current search configuration requires confirmed remote work.')
    if scope.get('include_hybrid') is False and 'hybrid' in remote:
        reasons.append('Hybrid roles are disabled in the current search configuration.')
    if scope.get('include_onsite') is False and remote in ('on-site', 'onsite', 'office-based'):
        reasons.append('Onsite roles are disabled in the current search configuration.')
    company_key = job.company.strip().casefold()
    if company_key in {name.casefold() for name in profile.get('market_intelligence_only_companies', [])}:
        reasons.append('Company is configured for market intelligence only.')
    if (search.get('market_intelligence', {}).get('surface_as_application_opportunity') is False
            and company_key in {name.casefold() for name in search.get('market_intelligence', {}).get('companies', [])}):
        reasons.append('Company is configured for market intelligence only.')
    return DiscoveryScreening(
        accepted=not reasons, score=relevance.score,
        reasons=list(dict.fromkeys(reasons)), flags=list(dict.fromkeys(flags)),
        matches={'role_terms': relevance.matched_role_terms,
                 'positive_signals': relevance.matched_positive_signals,
                 'caution_signals': relevance.matched_caution_signals},
        gatekeeper=asdict(gate),
        priority=asdict(prioritize_role(job, rules.get("role_priority"))),
    )
