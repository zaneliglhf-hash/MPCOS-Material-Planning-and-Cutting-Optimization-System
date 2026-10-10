"""Isolated, deadline-controlled deterministic calculation process."""
import json
from pathlib import Path
import sys
import signal
from ..agent_tools import plan_cutting


def main():
    # The parent enforces the subprocess deadline on every platform. Unix
    # additionally bounds an orphaned worker if the parent stops unexpectedly.
    if hasattr(signal, 'alarm'):
        signal.alarm(90)
    folder = Path(sys.argv[1])
    job = json.loads((folder / 'request.json').read_text(encoding='utf-8'))
    # Bound the search space without changing any process parameter.
    job.setdefault('max_bars', max(job.get('min_bars', 1), sum(job['demand'].values())))
    result = plan_cutting(job, output_root=folder / 'artifacts', time_limit_seconds=2)
    (folder / 'response.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
