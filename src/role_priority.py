"""Profile-driven review order from posting evidence, never approval or fit judgment."""
import re
from dataclasses import dataclass, field
from src.normalizer import clean_html

PRIORITY_LABELS = {
    'operational': 'Operational focus',
    'adjacent': 'Adjacent — investigate',
    'specialist': 'Specialist focus',
    'limited': 'Limited role evidence',
    'unconfigured': 'Not configured',
}
PRIORITY_ORDER = {'operational': 0, 'adjacent': 1, 'specialist': 2, 'limited': 3, 'unconfigured': 1}


@dataclass
class RolePriority:
    band: str = 'unconfigured'
    reason: str = 'No role-priority rules configured for this candidate.'
    evidence: list[dict] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    specialist_evidence: list[dict] = field(default_factory=list)

    @property
    def order(self):
        return PRIORITY_ORDER[self.band]


def validate_priority_config(config):
    if config is None:
        return
    if not isinstance(config, dict) or not isinstance(config.get('enabled', True), bool):
        raise ValueError('role_priority must be an object with a boolean enabled setting')
    for key in ('target_title_pattern',):
        if not isinstance(config.get(key), str):
            raise ValueError(f'role_priority.{key} must be a regex string')
        _validate_pattern(config[key])
    for key in ('operational_signals', 'specialist_checks', 'investigation_checks'):
        if not isinstance(config.get(key), list):
            raise ValueError(f'role_priority.{key} must be a list')
        for item in config[key]:
            if not isinstance(item, dict) or not isinstance(item.get('label'), str) or not item['label'].strip():
                raise ValueError(f'Each {key} entry needs a label')
            if key == 'operational_signals':
                _validate_pattern(item.get('pattern'))
            else:
                patterns = item.get('requirement_patterns')
                if not isinstance(patterns, list) or not patterns:
                    raise ValueError(f'{key} entries need requirement_patterns')
                for pattern in patterns:
                    _validate_pattern(pattern)
                if item.get('title_pattern') is not None:
                    _validate_pattern(item['title_pattern'])
                if not isinstance(item.get('question'), str) or not item['question'].strip():
                    raise ValueError(f'{key} entries need a question')
                if item.get('evidence_scope', 'required') not in ('required', 'role'):
                    raise ValueError('evidence_scope must be required or role')
                if 'demote_to_adjacent' in item and not isinstance(item['demote_to_adjacent'], bool):
                    raise ValueError('demote_to_adjacent must be true or false')


def _validate_pattern(pattern):
    if not isinstance(pattern, str) or not pattern:
        raise ValueError('Role-priority patterns must be nonempty regex strings')
    try:
        re.compile(pattern, re.I)
    except re.error as exc:
        raise ValueError(f'Invalid role-priority regex: {pattern}') from exc


def _heading(text):
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', text.lower()).split())


def role_passages(description):
    """Separate role/qualification text from company, benefits, and preferred skills.

    Missing/novel headings remain a heuristic limitation. Evidence is retained so
    reviewers can check the classification against the complete saved posting.
    """
    lines = [line.strip(' \t-*•') for line in clean_html(description or '').splitlines() if line.strip()]
    starts = [i for i, line in enumerate(lines) if (
        _heading(line) in ('about the role', 'about this role', 'position overview', 'the role', 'what you ll do', 'responsibilities', 'key responsibilities')
        or re.match(r"(?:we are seeking|we.re looking for|we are looking for)", line, re.I))]
    if starts:
        lines = lines[starts[0]:]
    section = 'role'
    result = []
    for line in lines:
        heading = _heading(line)
        if heading in ('logistics', 'why fireworks', 'benefits', 'about anthropic', 'about us'):
            break
        if heading.startswith(('preferred qualifications', 'preferred experience', 'preferred attributes',
                               'strong candidates may', 'nice to have', 'bonus qualifications')):
            section = 'preferred'
            continue
        if (heading in ('qualifications', 'requirements', 'minimum qualifications', 'required qualifications',
                        'what we re looking for', 'what we are looking for')
                or heading.startswith(('you may be a good fit', 'you might be a good fit'))):
            section = 'required'
            continue
        if heading in ('responsibilities', 'key responsibilities', 'what you ll do', 'what you ll own',
                       'what success looks like', 'about the role', 'position overview', 'the role'):
            section = 'role'
            continue
        # Avoid treating a long paragraph containing one optional clause as entirely optional.
        for sentence in re.split(r'(?<=[.!?])\s+', line):
            if not sentence:
                continue
            optional = section == 'preferred' or bool(re.search(r'\b(preferred|a plus|nice to have|optional)\b', sentence, re.I))
            negated = bool(re.search(r"\b(not required|not a requirement|no .{0,40} required|do not need|don.t need|without prior)\b", sentence, re.I))
            explicit_requirement = bool(re.search(r'\b(experience|background|expertise|knowledge|must|required|requires|need|proficiency|certified)\b', sentence, re.I))
            requirement = not optional and not negated and (section == 'required' or explicit_requirement)
            result.append({'text': sentence, 'section': section, 'requirement': requirement,
                           'preferred': optional, 'negated': negated})
    return result


def _evidence(label, passage):
    return {'signal': label, 'text': passage['text'], 'section': passage['section']}


def prioritize_role(job, config=None):
    if not config or not config.get('enabled', True):
        return RolePriority()
    passages = role_passages(job.raw_description)
    evidence, specialist, questions = [], [], []
    for signal in config['operational_signals']:
        # Reward actual work; a qualification or company slogan alone earns no role signal.
        found = next((p for p in passages if p['section'] == 'role' and not p['negated']
                      and re.search(signal['pattern'], p['text'], re.I)), None)
        if found:
            evidence.append(_evidence(signal['label'], found))
    demote = False
    for key in ('specialist_checks', 'investigation_checks'):
        for check in config[key]:
            if check.get('title_pattern') and not re.search(check['title_pattern'], job.title, re.I):
                continue
            found = next((p for p in passages if not p['preferred'] and not p['negated']
                          and (p['requirement'] or (check.get('evidence_scope') == 'role' and p['section'] == 'role')) and any(
                re.search(pattern, p['text'], re.I) for pattern in check['requirement_patterns'])), None)
            if found:
                if key == 'specialist_checks':
                    specialist.append(_evidence(check['label'], found))
                else:
                    evidence.append(_evidence(check['label'], found))
                    demote = demote or check.get('demote_to_adjacent', False)
                questions.append(check['question'])
    operational_count = sum(item['signal'] in {s['label'] for s in config['operational_signals']} for item in evidence)
    if specialist:
        band, reason = 'specialist', 'Posting requires specialist experience to verify; generic operations keywords do not establish suitability.'
    elif operational_count >= 2 and re.search(config['target_title_pattern'], job.title, re.I) and not demote:
        band, reason = 'operational', 'Multiple responsibilities concern the candidate’s target work. Qualifications and practical fit still need review.'
    elif evidence:
        band, reason = 'adjacent', 'Some relevant work or transferable scope is visible; investigate domain requirements before prioritizing.'
    else:
        band, reason = 'limited', 'The parsed role text supplies little evidence of the configured target work; title keywords alone are insufficient.'
    return RolePriority(band, reason, evidence, list(dict.fromkeys(questions)), specialist)
