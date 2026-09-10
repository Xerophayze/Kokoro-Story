"""Re-audit saved benchmark responses offline, without LLM/audio/config access."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.directed_output import prepare_direction_request, assemble_directed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    locked, _, _ = prepare_direction_request((args.directory/'locked-scene.txt').read_bytes().decode('utf-8'))
    result = []
    for entry in json.loads((args.directory/'results.json').read_text(encoding='utf-8')):
        label = entry['model'].replace('/','_') + f"-trial-{entry['trial']}"
        path = args.directory / f'{label}.json'
        row = {'model':entry['model'], 'trial':entry['trial'], 'accepted_for_production':False}
        if path.exists():
            try:
                _, audit = assemble_directed(locked, path.read_text(encoding='utf-8'), enforce_quality=False)
                row['audit'] = audit
                row['deterministic_pass'] = not audit['deterministic_quality_errors']
            except Exception as exc:
                row['validation_error'] = str(exc)
        else:
            row['validation_error'] = entry.get('error','No model response available')
        result.append(row)
    (args.directory/'final-deterministic-audit.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'trials':len(result),'deterministic_passes':sum(r.get('deterministic_pass',False) for r in result),
                      'production_approved':False}))


if __name__ == '__main__':
    main()
