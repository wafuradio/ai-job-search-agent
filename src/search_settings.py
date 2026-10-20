"""Combine one candidate's discovery preferences without importing AI clients."""
from copy import deepcopy
from src.candidates import PROJECT_ROOT, get_candidate

ROOT = PROJECT_ROOT


def load_search_settings(root=ROOT, *, candidate=None):
    selected = get_candidate(candidate, root=root)
    return selected.load('search_config.json'), selected.load('career_profile.json')


def discovery_scout_config(config, candidate=None):
    search, profile = load_search_settings(candidate=candidate)
    result = deepcopy(config)
    titles = search.get('role_searches', []) + profile['target_roles'].get('primary', []) + profile['target_roles'].get('selective', [])
    titles = [title.replace('Management', 'Manager') for title in titles]
    titles += result.get('additional_role_terms', [])
    if titles:
        result['priority_role_families'].append({
            'family': 'Career profile and search preferences', 'priority': 'High',
            'search_titles': list(dict.fromkeys(titles)),
        })
    result['positive_signals'] = list(dict.fromkeys(
        result.get('positive_signals', []) + search.get('concept_searches', [])
        + result.get('additional_positive_signals', [])))
    result['excluded_title_terms'] = list(dict.fromkeys(
        result.get('excluded_title_terms', []) + search.get('early_rejection_terms', [])))
    return result
