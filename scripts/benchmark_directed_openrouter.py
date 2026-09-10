"""Explicit, bounded live benchmark. No app import, config writes, or audio jobs.

Run with --source locked-directed.txt --output NEW_DIRECTORY --live.
Reads credentials from config.json without printing or copying them.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import requests
from src.directed_output import lock_manuscript, prepare_direction_request, assemble_directed
from src.openrouter_processor import OpenRouterProcessor


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--qwen-only', action='store_true')
    parser.add_argument('--trials', type=int, choices=(1, 2, 3), default=3)
    parser.add_argument('--max-output-tokens', type=int, choices=(4096,8192), default=4096)
    parser.add_argument('--models', nargs='+', choices=(
        'qwen/qwen3.8-flash', 'qwen/qwen3.5-flash-02-23', 'gemini-2.5-flash'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    original = args.source.read_bytes()
    full = lock_manuscript(original.decode('utf-8-sig'))
    starts = [b for b in full['blocks'] if b['text'].lstrip().startswith('Chapter Three')]
    ends = [b for b in full['blocks'] if b['text'].lstrip().startswith('Chapter Four')]
    if len(starts) != 1 or len(ends) != 1:
        raise ValueError('Expected unique Chapter Three/Four boundaries')
    scene = full['source'][starts[0]['start']:ends[0]['start']]
    locked, prompt, schema = prepare_direction_request(scene)
    (args.output / 'locked-scene.txt').write_bytes(scene.encode('utf-8'))
    (args.output / 'prompt.txt').write_text(prompt, encoding='utf-8')
    save(args.output / 'schema.json', schema)
    save(args.output / 'input-audit.json', {
        'source_path': str(args.source), 'source_file_sha256': hashlib.sha256(original).hexdigest(),
        'locked_scene_sha256': locked['sha256'], 'block_count': len(locked['blocks']),
        'scope': 'Entire Chapter Three, including Eira/Matron confrontation, opening context and aftermath',
        'blocks': [{k: b[k] for k in ('id','speaker','text')} for b in locked['blocks']],
        'pause_controls': scene.count('******')})
    if not args.live:
        print('Dry run: prepared immutable benchmark input; no API calls.', flush=True)
        return
    cfg_bytes = (ROOT / 'config.json').read_bytes()
    config = json.loads(cfg_bytes)
    key = config.get('openrouter_api_key') or ''
    gemini_key = config.get('gemini_api_key') or ''
    if not key or not gemini_key:
        raise RuntimeError('Existing OpenRouter and Gemini keys are required; none were changed')
    catalog = requests.get('https://openrouter.ai/api/v1/models', timeout=30).json()['data']
    models = ['qwen/qwen3.8-flash', 'qwen/qwen3.5-flash-02-23', 'gemini-2.5-flash']
    if args.qwen_only:
        models = models[:2]
    if args.models:
        models = args.models
    prices = {m['id']: m['pricing'] for m in catalog if m['id'] in models}
    save(args.output / 'pricing-snapshot.json', prices)
    results = []
    for model in models:
        for trial in range(1, args.trials + 1):
            label = model.replace('/', '_') + f'-trial-{trial}'
            row = dict(model=model, trial=trial, schema_valid=False, max_output_tokens=args.max_output_tokens)
            start = time.monotonic()
            usage = {}
            p = None
            print(f'Starting {label}', flush=True)
            try:
                if model.startswith('qwen/'):
                    p = OpenRouterProcessor(key, model, timeout=180, temperature=.4, max_tokens=args.max_output_tokens)
                    response = p.generate_text(prompt, response_schema=schema,
                                               response_schema_name='tts_story_directions')
                    usage = p.last_usage
                    row['response_id'] = p.last_response_id
                    rate = prices[model]
                    row['estimated_cost_usd'] = (usage.get('prompt_tokens',0)*float(rate['prompt']) +
                                                  usage.get('completion_tokens',0)*float(rate['completion']))
                    row['reported_cost_usd'] = usage.get('cost')
                else:
                    # Control uses the user's existing direct Google provider.
                    r = requests.post(
                        f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                        headers={'x-goog-api-key': gemini_key}, timeout=180,
                        json={'contents': [{'parts':[{'text':prompt}]}], 'generationConfig': {
                            'temperature': .4, 'maxOutputTokens':args.max_output_tokens,
                            'responseMimeType':'application/json', 'responseJsonSchema':schema}})
                    if r.status_code >= 400:
                        raise RuntimeError(f'Google control HTTP {r.status_code}: ' +
                                           str(r.json().get('error',{}).get('message',''))[:300])
                    payload = r.json()
                    response = ''.join(p.get('text','') for p in payload['candidates'][0]['content']['parts']
                                       if not p.get('thought'))
                    usage = payload.get('usageMetadata',{})
                    row['estimated_cost_usd'] = (usage.get('promptTokenCount',0)*.3 +
                        (usage.get('candidatesTokenCount',0)+usage.get('thoughtsTokenCount',0))*2.5)/1e6
                    row['reported_cost_usd'] = None
                (args.output / f'{label}.json').write_text(response, encoding='utf-8')
                directed, audit = assemble_directed(locked, response, enforce_quality=False)
                row.update(schema_valid=True, audit=audit)
                (args.output / f'{label}-REVIEW-ONLY.txt').write_bytes(directed.encode('utf-8'))
            except Exception as exc:
                if p is not None:
                    usage = p.last_usage
                    row['response_id'] = p.last_response_id
                    row['reported_cost_usd'] = usage.get('cost')
                    if usage:
                        rate = prices[model]
                        row['estimated_cost_usd'] = (usage.get('prompt_tokens',0)*float(rate['prompt']) +
                                                      usage.get('completion_tokens',0)*float(rate['completion']))
                    if p.last_response_text is not None:
                        (args.output / f'{label}-REJECTED.json').write_text(p.last_response_text, encoding='utf-8')
                # Scrub even vendor error strings defensively before persistence.
                row['error'] = str(exc).replace(key, '[redacted]').replace(gemini_key, '[redacted]')[:700]
            if p is not None:
                row['attempts'] = p.last_attempts
                row['finish_reason'] = p.last_finish_reason
                costs = [a.get('usage',{}).get('cost') for a in p.last_attempts]
                row['reported_attempt_costs_usd'] = sum(c for c in costs if isinstance(c,(int,float)))
                row['attempts_without_reported_cost'] = sum(c is None for c in costs)
            row.update(elapsed_seconds=round(time.monotonic()-start,3), usage=usage)
            results.append(row)
            save(args.output / 'results.json', results)
            print(f"Finished {label}: schema_valid={row['schema_valid']}, seconds={row['elapsed_seconds']}", flush=True)
    save(args.output / 'preservation-audit.json', {
        'config_unchanged': (ROOT/'config.json').read_bytes()==cfg_bytes,
        'source_unchanged': args.source.read_bytes()==original,
        'no_audio_synthesis': True, 'production_model_changed': False})


if __name__ == '__main__':
    main()
