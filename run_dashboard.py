"""Start the local review dashboard; no discovery, AI calls or applications."""
import argparse
from src.dashboard import ReviewServer


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', help='Candidate profile ID')
    parser.add_argument('--db', help='Optional candidate-owned database override')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535')
    try:
        with ReviewServer(args.candidate, args.db, args.port) as server:
            print(f'{server.candidate.display_name} review dashboard: {server.origin}', flush=True)
            print('Local saved jobs only. Stop with Ctrl+C. Applications remain manual.', flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
