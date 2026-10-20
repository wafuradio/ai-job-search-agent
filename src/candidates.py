"""Explicit candidate profiles; no global mutable candidate or cross-profile fallback."""
import json
import math
import re
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get('AI_JOB_SEARCH_ROOT', Path(__file__).resolve().parent.parent)).resolve()
PROFILE_FILES = (
    'candidate.json', 'career_profile.json', 'candidate_evidence.json',
    'scout_config.json', 'search_config.json', 'company_boards.json',
    'screening_rules.json', 'relationships.json', 'career_gap_context.json',
)


def validate_candidate_id(candidate_id):
    if not isinstance(candidate_id, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', candidate_id):
        raise ValueError('Candidate ID must start with a lowercase letter and use only lowercase letters, digits, _ or - (maximum 64 characters).')
    return candidate_id


def app_settings(root=PROJECT_ROOT):
    path = Path(root) / 'config/app_config.json'
    with path.open(encoding='utf-8') as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError('app_config.json must contain an object')
    for key in ('default_candidate', 'legacy_database_owner'):
        validate_candidate_id(data.get(key))
    return data


@dataclass(frozen=True)
class CandidateProfile:
    candidate_id: str
    root: Path

    @property
    def directory(self):
        return self.root / 'profiles' / self.candidate_id

    def load(self, filename):
        if filename not in PROFILE_FILES:
            raise ValueError(f'Unsupported candidate profile file: {filename}')
        path = self.directory / filename
        if path.resolve().parent != self.directory.resolve():
            raise ValueError('Candidate profile files must remain inside their own directory')
        try:
            with path.open(encoding='utf-8') as file:
                value = json.load(file)
        except FileNotFoundError as exc:
            raise ValueError(f'Candidate {self.candidate_id}: missing {filename}; no other profile will be used.') from exc
        if not isinstance(value, dict):
            raise ValueError(f'Candidate {self.candidate_id}: {filename} must contain a JSON object')
        return value

    @property
    def display_name(self):
        return self.load('candidate.json')['display_name']

    @property
    def database_path(self):
        # The legacy owner is stable even if the default candidate changes.
        if self.candidate_id == app_settings(self.root)['legacy_database_owner']:
            return self.root / 'data/jobs.db'
        return self.root / 'data/candidates' / self.candidate_id / 'jobs.db'

    @property
    def legacy_database_path(self):
        return self.root / 'data/jobs.db'

    def validate(self):
        data = {name: self.load(name) for name in PROFILE_FILES}
        metadata = data['candidate.json']
        if metadata.get('candidate_id') != self.candidate_id or not isinstance(metadata.get('display_name'), str) or not metadata['display_name'].strip():
            raise ValueError('Candidate metadata must match its directory ID and include a display name')
        career = data['career_profile.json']
        targets = career.get('target_roles', {})
        if not targets.get('primary') and not targets.get('selective'):
            raise ValueError(f'Candidate {self.candidate_id}: specify at least one target role before use')
        for key in ('primary', 'selective'):
            if not isinstance(targets.get(key, []), list) or any(not isinstance(item, str) or not item.strip() for item in targets.get(key, [])):
                raise ValueError(f'Candidate {self.candidate_id}: target roles must be nonempty strings')
        target = career.get('compensation', {}).get('target_total_compensation_usd')
        if target is not None and (isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target) or target < 0):
            raise ValueError('Compensation target must be a nonnegative USD number or null for unknown')
        if data['search_config.json'].get('search_scope', {}).get('country') != 'United States':
            raise ValueError('Discovery currently supports United States search scope only')
        sources = data['search_config.json'].get('public_job_boards', [])
        if (not isinstance(sources, list) or any(not isinstance(source, str) or source not in ('remotive', 'weworkremotely') for source in sources)
                or len(sources) != len(set(sources))):
            raise ValueError('public_job_boards must contain unique supported source IDs: remotive, weworkremotely')
        plan = data['search_config.json'].get('discovery_plan', {})
        if not isinstance(plan, dict):
            raise ValueError('discovery_plan must be an object')
        if 'terms' in plan and (not isinstance(plan['terms'], list) or any(not isinstance(term, str) or not term.strip() for term in plan['terms'])):
            raise ValueError('discovery_plan terms must be nonempty strings')
        human = career.get('human_review', {})
        if human.get('required_before_application') is not True or human.get('automatic_application_allowed') is not False:
            raise ValueError('Every candidate must require human approval and prohibit automatic applications')
        rules = data['screening_rules.json']
        for key in ('employment_reject_terms', 'employment_flag_terms'):
            if not isinstance(rules.get(key), list) or any(not isinstance(term, str) or not term for term in rules[key]):
                raise ValueError(f'{key} must be a list of nonempty strings')
        groups = rules.get('reject_title_groups')
        if not isinstance(groups, list):
            raise ValueError('reject_title_groups must be a list')
        for group in groups:
            if (not isinstance(group, dict) or not isinstance(group.get('terms'), list)
                    or not group['terms'] or any(not isinstance(term, str) or not term for term in group['terms'])
                    or not isinstance(group.get('reason'), str) or not group['reason'].strip()):
                raise ValueError('Each title exclusion group needs terms and a reason')
        for key in ('exclude_sales_ownership', 'flag_technical_depth', 'flag_commercial_context'):
            if not isinstance(rules.get(key), bool):
                raise ValueError(f'{key} must be true or false')
        from src.role_priority import validate_priority_config
        validate_priority_config(rules.get('role_priority'))
        if not isinstance(data['candidate_evidence.json'].get('experience_evidence'), list):
            raise ValueError('Candidate evidence requires an experience_evidence list; use an empty list for unknown experience')
        if not isinstance(data['company_boards.json'].get('boards'), list):
            raise ValueError('Candidate boards must contain a boards list')
        sites = data['company_boards.json'].get('career_sites', [])
        if not isinstance(sites, list) or any(not isinstance(site, dict) or not isinstance(site.get('company'), str)
                or not site['company'].strip() or not isinstance(site.get('url'), str)
                or not site['url'].startswith('https://') or type(site.get('enabled', True)) is not bool for site in sites):
            raise ValueError('Career sites require a company, HTTPS URL and optional enabled boolean')
        return self


def get_candidate(candidate=None, root=PROJECT_ROOT):
    if isinstance(candidate, CandidateProfile):
        return candidate
    root = Path(root).resolve()
    candidate_id = app_settings(root)['default_candidate'] if candidate is None else validate_candidate_id(candidate)
    directory = root / 'profiles' / candidate_id
    if not directory.is_dir() or directory.resolve().parent != (root / 'profiles').resolve():
        raise ValueError(f'Unknown candidate: {candidate_id}. Create and configure a separate profile first.')
    return CandidateProfile(candidate_id, root).validate()
