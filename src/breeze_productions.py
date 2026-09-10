"""Production-scoped Breeze voice ownership and restart-safe upload checkpoints.

Local snapshots outlive library deletion. No remote voice is deleted unless its
ID was returned by this production's save operation (never a catalog selection).
"""
import copy
import hashlib
import json
import os
import re
import shutil
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class ProductionError(ValueError):
    pass


_locks = {}
_locks_guard = threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat()


class BreezeProductions:
    def __init__(self, root, samples):
        self.root = Path(root).resolve()
        self.samples = Path(samples).resolve()

    def directory(self, production_id):
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", str(production_id)):
            raise ProductionError("Invalid production ID.")
        path = (self.root / production_id).resolve()
        if path.parent != self.root:
            raise ProductionError("Invalid production folder.")
        return path

    @contextmanager
    def locked(self, production_id):
        directory = self.directory(production_id)
        directory.mkdir(parents=True, exist_ok=True)
        with _locks_guard:
            lock = _locks.setdefault(str(directory), threading.RLock())
        with lock:
            # OS lock also protects against two independently started backends.
            with (directory / '.lock').open('a+b') as handle:
                handle.seek(0)
                if handle.read(1) == b'':
                    handle.write(b'0')
                    handle.flush()
                handle.seek(0)
                try:
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise ProductionError("This production is busy in another backend. Try again after it finishes.") from exc
                try:
                    yield directory
                finally:
                    handle.seek(0)
                    if os.name == 'nt':
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def read(self, directory):
        path = directory / 'manifest.json'
        if not path.exists():
            raise ProductionError("No Breeze production record exists for this job.")
        return json.loads(path.read_text(encoding='utf-8'))

    def write(self, directory, data):
        data['updated_at'] = now()
        temp = directory / 'manifest.json.tmp'
        with temp.open('w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, directory / 'manifest.json')

    def bind(self, production_id, assignments, *, consent=False, title=''):
        """Snapshot selected files before queuing; never upload in the HTTP route."""
        result = copy.deepcopy(assignments)
        for assignment in result.values():
            if not assignment.get('audio_prompt_path'):
                extra = assignment.get('extra') or {}
                for key in ('breeze_production_id', 'breeze_sample_key'):
                    extra.pop(key, None)
        local = {s: a for s, a in result.items() if a.get('audio_prompt_path')}
        if not local:
            return result
        with self.locked(production_id) as directory:
            manifest_path = directory / 'manifest.json'
            data = self.read(directory) if manifest_path.exists() else {
                'production_id': production_id, 'title': str(title)[:160],
                'created_at': now(), 'released': False, 'voices': {},
            }
            if data.get('released'):
                raise ProductionError("This production's Breeze voices were released. Submit a new production to upload again.")
            for speaker, assignment in local.items():
                extra = assignment.get('extra') or {}
                old_key = extra.get('breeze_sample_key')
                old = data['voices'].get(old_key)
                source = Path(assignment['audio_prompt_path'])
                source = source.resolve() if source.is_absolute() else (Path.cwd() / source).resolve()
                if not source.is_file():
                    source = (self.samples / assignment['audio_prompt_path']).resolve()
                # Restored assignments use the immutable production snapshot.
                if old and extra.get('breeze_production_id') == production_id:
                    snapshot = (directory / old['sample']).resolve()
                    if source == snapshot and source.is_file():
                        continue
                if not consent:
                    raise ProductionError("Confirm production voice upload and rights before using new local samples with Breeze API.")
                if source.parent != self.samples or not source.is_file():
                    raise ProductionError("Select a local sample from TTS-Story's voice library.")
                if source.suffix.lower() not in {'.wav', '.mp3'} or source.stat().st_size > 5_000_000:
                    raise ProductionError("Breeze samples must be WAV/MP3 and no larger than 5 MB.")
                from pydub import AudioSegment
                if len(AudioSegment.from_file(source)) < 3000:
                    raise ProductionError("Breeze samples must contain at least three seconds of audio.")
                language = str(extra.get('breeze_language') or assignment.get('lang_code') or 'en').lower()
                if not re.fullmatch(r'[a-z]{2}', language):
                    raise ProductionError("Breeze sample language must be a two-letter language code (for example en).")
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                key = hashlib.sha256((digest + language).encode()).hexdigest()
                record = data['voices'].get(key)
                if not record:
                    sample = f'samples/{key}{source.suffix.lower()}'
                    target = directory / sample
                    target.parent.mkdir(exist_ok=True)
                    shutil.copyfile(source, target)
                    record = data['voices'][key] = {
                        'sample': sample, 'sha256': digest, 'language': language,
                        'source_name': source.name, 'speakers': [], 'state': 'pending',
                        'remote_name': f'TTS-{production_id}-{str(speaker)[:35]}',
                    }
                if speaker not in record['speakers']:
                    record['speakers'].append(speaker)
                assignment['audio_prompt_path'] = str(directory / record['sample'])
                assignment['voice'] = ''
                assignment['lang_code'] = language
                assignment['extra'] = {**extra, 'breeze_production_id': production_id, 'breeze_sample_key': key,
                                       'breeze_sample_name': source.stem}
            data['upload_consent_at'] = data.get('upload_consent_at') or now()
            self.write(directory, data)
        return result

    def resolve_voice(self, engine, extra, progress=lambda *_: None):
        production_id, key = extra.get('breeze_production_id'), extra.get('breeze_sample_key')
        if not production_id or not key:
            raise ProductionError("Start a production to upload this local sample; no untracked preview uploads are allowed.")
        with self.locked(production_id) as directory:
            data = self.read(directory)
            if data.get('released'):
                raise ProductionError("Production voices have been released. Start a new production to regenerate.")
            record = data['voices'].get(key)
            if not record:
                raise ProductionError("Production sample is not registered.")
            account = hashlib.sha256(engine.api_key.encode()).hexdigest()
            if data.get('credential_fingerprint') not in (None, account):
                raise ProductionError("The Breeze API key changed. Use the original production key to prevent uploads or deletion in the wrong account.")
            data['credential_fingerprint'] = account
            state = record['state']
            if state == 'ready':
                return record['voice_id']
            if state in {'uploading', 'saving'}:
                raise ProductionError("A previous Breeze upload/save has an uncertain result. Open Manage production voices and recover the interrupted upload before resuming; automatic duplication is blocked.")
            if state == 'verification':
                raise ProductionError("Breeze requires voice verification. Complete it on Breeze before continuing; automatic upload is stopped.")
            sample = (directory / record['sample']).resolve()
            if directory not in sample.parents or hashlib.sha256(sample.read_bytes()).hexdigest() != record['sha256']:
                raise ProductionError("Production sample is missing or changed.")
            if state == 'pending':
                progress(production_id, f"Uploading Breeze voice: {', '.join(record['speakers'])}")
                record['state'] = 'uploading'
                self.write(directory, data)
                try:
                    preview = engine.clone_preview(sample, record['remote_name'], record['language'])
                except Exception as exc:
                    # Explicit HTTP rejection is safe to retry; transport failures
                    # leave the intent checkpoint to prevent duplicate paid work.
                    if getattr(exc, 'status_code', None) in (400, 401, 402, 403, 404, 413, 422, 429):
                        record['state'] = 'pending'
                        self.write(directory, data)
                    raise
                record['preview_id'] = preview['generated_voice_id']
                record['state'] = 'verification' if preview.get('requires_verification') else 'preview'
                self.write(directory, data)
                if record['state'] == 'verification':
                    raise ProductionError("Breeze requires verification for this sample. Complete verification on the provider platform.")
            progress(production_id, f"Saving production voice: {', '.join(record['speakers'])}")
            record['state'] = 'saving'
            self.write(directory, data)
            try:
                saved = engine.save_preview(record['preview_id'], record['remote_name'], record['language'])
            except Exception as exc:
                if getattr(exc, 'status_code', None) in (400, 401, 402, 403, 404, 422, 429):
                    record['state'] = 'preview'
                    self.write(directory, data)
                raise
            voice_id = saved['voice_id']
            if not re.fullmatch(r'[A-Za-z0-9_-]+', str(voice_id)):
                raise ProductionError("Breeze returned an invalid saved voice ID.")
            record.update(state='ready', voice_id=voice_id, saved_at=now())
            self.write(directory, data)
            progress(production_id, 'Synthesizing audio with production voices')
            return voice_id

    def list(self):
        if not self.root.exists():
            return []
        result = []
        for path in self.root.glob('*/manifest.json'):
            try:
                data = self.read(path.parent)
                result.append(self.summary(data))
            except (OSError, ValueError):
                continue
        return sorted(result, key=lambda item: item.get('created_at', ''), reverse=True)

    @staticmethod
    def summary(data):
        return {k: v for k, v in data.items() if k != 'credential_fingerprint'}

    def recover(self, production_id, key, engine, *, confirm_absent=False):
        """Reconcile a saved voice, or explicitly authorize retry after account review.

        No upload, save, synthesis or deletion happens in this operation.
        A missing catalog entry cannot prove an unsaved preview never existed.
        """
        with self.locked(production_id) as directory:
            data = self.read(directory)
            if data.get('released'):
                raise ProductionError('Production voices have been released.')
            if data.get('credential_fingerprint') != hashlib.sha256(engine.api_key.encode()).hexdigest():
                raise ProductionError('Use the original production Breeze API key for recovery.')
            record = data['voices'].get(key)
            if not record or record['state'] not in {'uploading', 'saving'}:
                raise ProductionError('This voice has no interrupted upload/save to recover.')
            # Only personal voices are eligible; never adopt a public catalog voice.
            matches = []
            for page in range(1, 101):
                payload = engine.request('GET', '/voices', timeout=(5, 30),
                    params={'voice_type': 'personal', 'page': page, 'page_size': 100}).json()
                if not isinstance(payload, dict) or not isinstance(payload.get('voices'), list):
                    raise ProductionError('Could not verify the personal voice catalog; no state was changed.')
                matches.extend(v for v in payload['voices'] if v.get('name') == record['remote_name'])
                if not payload.get('has_more'):
                    break
            else:
                raise ProductionError('Personal voice catalog is incomplete; no state was changed.')
            if len(matches) > 1:
                raise ProductionError('Multiple matching production voices exist on Breeze. Resolve the duplicates on Breeze before recovery.')
            if matches:
                voice_id = matches[0].get('voice_id', '')
                if not re.fullmatch(r'[A-Za-z0-9_-]+', str(voice_id)):
                    raise ProductionError('Breeze returned an invalid saved voice ID.')
                record.update(state='ready', voice_id=voice_id, recovered_at=now())
            elif confirm_absent:
                record.update(state='preview' if record.get('preview_id') else 'pending',
                              retry_authorized_at=now())
            else:
                return {'needs_confirmation': True, 'remote_name': record['remote_name']}
            self.write(directory, data)
            return {'needs_confirmation': False, 'state': record['state']}

    def release(self, production_id, engine):
        with self.locked(production_id) as directory:
            data = self.read(directory)
            if data.get('credential_fingerprint') not in (None, hashlib.sha256(engine.api_key.encode()).hexdigest()):
                raise ProductionError("Use the original production's Breeze API key for cleanup.")
            # Close the production before deleting anything; resume cannot create
            # new uploads during or after a partially failed cleanup.
            data['released'] = True
            self.write(directory, data)
            for record in data['voices'].values():
                if record.get('voice_id') and record['state'] != 'deleted':
                    engine.delete_voice(record['voice_id'])
                    record.update(state='deleted', deleted_at=now())
                    self.write(directory, data)
            data['released_at'] = now()
            self.write(directory, data)
            return self.summary(data)
