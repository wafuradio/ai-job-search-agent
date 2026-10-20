"""List, validate, or scaffold separate candidate profiles. No API calls."""
import argparse
import json
import shutil
from pathlib import Path
from src.candidates import PROJECT_ROOT, get_candidate, validate_candidate_id


def main(argv=None, *, root=PROJECT_ROOT):
    root = Path(root)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    validation = commands.add_parser('validate')
    validation.add_argument('--candidate', help='Defaults to configured candidate')
    creation = commands.add_parser('init')
    creation.add_argument('--candidate', required=True)
    creation.add_argument('--display-name', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            candidate_id = validate_candidate_id(args.candidate)
            if not args.display_name.strip():
                raise ValueError('Display name must not be empty')
            destination = root / 'profiles' / candidate_id
            if destination.exists():
                raise ValueError(f'Profile already exists: {candidate_id}; refusing to overwrite it')
            shutil.copytree(root / 'templates/candidate-profile', destination)
            (destination / 'candidate.json').write_text(json.dumps({
                'candidate_id': candidate_id, 'display_name': args.display_name.strip(),
            }, indent=2) + '\n', encoding='utf-8')
            print(f'Created unconfigured profile: {destination}')
            print('Fill in target roles, Scout role families, evidence, preferences, and discovery sources (public job boards or company boards), then run validate. No database was created.')
        elif args.command == 'validate':
            selected = get_candidate(args.candidate, root=root)
            from src.scout import load_scout_config
            from src.discovery import load_boards, load_job_boards
            load_scout_config(candidate=selected)
            load_boards(candidate=selected, allow_empty=bool(load_job_boards(candidate=selected)))
            print(f'Valid: {selected.display_name} ({selected.candidate_id})')
            print(f'Database: {selected.database_path}')
        else:
            for directory in sorted((root / 'profiles').iterdir()):
                if not directory.is_dir() or directory.name.startswith('.'):
                    continue
                try:
                    selected = get_candidate(directory.name, root=root)
                    print(f'{selected.candidate_id} | {selected.display_name} | profile configured')
                except (ValueError, OSError) as exc:
                    print(f'{directory.name} | needs configuration: {exc}')
    except (ValueError, OSError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
