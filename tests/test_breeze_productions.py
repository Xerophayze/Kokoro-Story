import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
import soundfile as sf

from src.breeze_productions import BreezeProductions, ProductionError
from src.engines.breeze_api_engine import BreezeAPIEngine, BreezeAPIError


@pytest.fixture
def production(tmp_path):
    samples = tmp_path / 'voices'
    samples.mkdir()
    path = samples / 'alice.wav'
    sf.write(path, np.zeros(24000 * 3), 24000)
    store = BreezeProductions(tmp_path / 'productions', samples)
    job_id = str(uuid.uuid4())
    assignments = {'alice': {'audio_prompt_path': str(path), 'extra': {'prompt_text': 'Local transcript'}}}
    return store, job_id, assignments, path


def engine():
    fake = Mock(api_key='test-only-key')
    fake.clone_preview.return_value = {'generated_voice_id': 'gvi_test'}
    fake.save_preview.return_value = {'voice_id': 'voc_production'}
    return fake


@pytest.mark.parametrize('state', ['uploading', 'saving'])
def test_recovery_requires_confirmation_and_preserves_preview(production, state):
    store, job_id, assignments, _ = production
    extra = store.bind(job_id, assignments, consent=True)['alice']['extra']
    fake = engine()
    fake.clone_preview.side_effect = BreezeAPIError('Timeout')
    with pytest.raises(BreezeAPIError):
        store.resolve_voice(fake, extra)
    directory = store.directory(job_id)
    data = store.read(directory)
    record = data['voices'][extra['breeze_sample_key']]
    record['state'] = state
    if state == 'saving':
        record['preview_id'] = 'gvi_existing'
    store.write(directory, data)
    fake.request.return_value.json.return_value = {'voices': [], 'has_more': False}
    assert store.recover(job_id, extra['breeze_sample_key'], fake)['needs_confirmation']
    assert store.read(directory)['voices'][extra['breeze_sample_key']]['state'] == state
    result = store.recover(job_id, extra['breeze_sample_key'], fake, confirm_absent=True)
    assert result['state'] == ('preview' if state == 'saving' else 'pending')
    fake.clone_preview.assert_called_once()  # only the original attempt
    fake.save_preview.assert_not_called()


def test_recovery_adopts_exact_personal_voice_and_reuses_it(production):
    store, job_id, assignments, _ = production
    extra = store.bind(job_id, assignments, consent=True)['alice']['extra']
    fake = engine()
    fake.clone_preview.side_effect = BreezeAPIError('Timeout')
    with pytest.raises(BreezeAPIError):
        store.resolve_voice(fake, extra)
    record = store.read(store.directory(job_id))['voices'][extra['breeze_sample_key']]
    fake.request.return_value.json.return_value = {'voices': [
        {'name': record['remote_name'], 'voice_id': 'voc_recovered'}], 'has_more': False}
    assert store.recover(job_id, extra['breeze_sample_key'], fake)['state'] == 'ready'
    assert store.resolve_voice(fake, extra) == 'voc_recovered'
    fake.clone_preview.assert_called_once()
    fake.save_preview.assert_not_called()
    assert fake.request.call_args.kwargs['params']['voice_type'] == 'personal'


def test_recovery_rejects_other_account_and_bad_catalog(production):
    store, job_id, assignments, _ = production
    extra = store.bind(job_id, assignments, consent=True)['alice']['extra']
    fake = engine()
    fake.clone_preview.side_effect = BreezeAPIError('Timeout')
    with pytest.raises(BreezeAPIError):
        store.resolve_voice(fake, extra)
    fake.api_key = 'different'
    with pytest.raises(ProductionError, match='original'):
        store.recover(job_id, extra['breeze_sample_key'], fake, confirm_absent=True)
    fake.api_key = 'test-only-key'
    fake.request.return_value.json.return_value = {}
    with pytest.raises(ProductionError, match='catalog'):
        store.recover(job_id, extra['breeze_sample_key'], fake, confirm_absent=True)
    assert store.read(store.directory(job_id))['voices'][extra['breeze_sample_key']]['state'] == 'uploading'


def test_recovery_route_blocks_active_jobs_and_requires_management_access(production, monkeypatch):
    import app as application
    store, job_id, assignments, _ = production
    extra = store.bind(job_id, assignments, consent=True)['alice']['extra']
    fake = engine()
    fake.clone_preview.side_effect = BreezeAPIError('Timeout')
    with pytest.raises(BreezeAPIError):
        store.resolve_voice(fake, extra)
    fake.request.return_value.json.return_value = {'voices': [], 'has_more': False}
    monkeypatch.setattr(application, 'BREEZE_PRODUCTIONS', store)
    monkeypatch.setattr(application, '_create_engine', lambda *a: fake)
    monkeypatch.setattr(application, 'load_config', lambda: {})
    monkeypatch.setattr(application, 'jobs', {job_id: {'status': 'processing'}})
    with application.app.test_client() as client:
        url = f'/api/breeze-api/productions/{job_id}/recover'
        body = {'sample_key': extra['breeze_sample_key']}
        assert client.post(url, json=body).status_code == 409
        application.jobs[job_id]['status'] = 'failed'
        assert client.post(url, json=body, environ_base={'REMOTE_ADDR': '192.168.1.1'}).status_code == 403
        assert client.post(url, json=body).json['needs_confirmation']
        assert client.post(url, json={**body, 'confirm_absent': True}).json['state'] == 'pending'
    fake.clone_preview.assert_called_once()
    fake.save_preview.assert_not_called()


def test_snapshot_and_consent(production):
    store, job_id, assignments, original = production
    with pytest.raises(ProductionError, match='Confirm'):
        store.bind(job_id, assignments)
    bound = store.bind(job_id, assignments, consent=True, title='My production')
    snapshot = Path(bound['alice']['audio_prompt_path'])
    assert snapshot != original and snapshot.read_bytes() == original.read_bytes()
    assert assignments['alice']['audio_prompt_path'] == str(original)
    assert store.bind(job_id, bound) == bound  # restored job doesn't need reapproval
    assert store.list()[0]['title'] == 'My production'


def test_concurrent_chunks_reuse_one_upload_and_survive_restart(production):
    store, job_id, assignments, original = production
    bound = store.bind(job_id, assignments, consent=True)
    extra = bound['alice']['extra']
    fake = engine()
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda _: store.resolve_voice(fake, extra), range(8))) == ['voc_production'] * 8
    recreated = BreezeProductions(store.root, store.samples)
    assert recreated.resolve_voice(fake, extra) == 'voc_production'
    fake.clone_preview.assert_called_once()
    fake.save_preview.assert_called_once()
    data = json.loads((store.directory(job_id) / 'manifest.json').read_text())
    assert data['voices'][extra['breeze_sample_key']]['voice_id'] == 'voc_production'
    assert fake.api_key not in json.dumps(data)
    assert 'credential_fingerprint' not in store.list()[0]


def test_productions_isolated_and_cleanup_keeps_local_audio(production):
    store, first, assignments, original = production
    second = str(uuid.uuid4())
    a = store.bind(first, assignments, consent=True)['alice']['extra']
    b = store.bind(second, assignments, consent=True)['alice']['extra']
    fake = engine()
    fake.save_preview.side_effect = [{'voice_id': 'voc_first'}, {'voice_id': 'voc_second'}]
    assert store.resolve_voice(fake, a) == 'voc_first'
    assert store.resolve_voice(fake, b) == 'voc_second'
    assert fake.clone_preview.call_count == 2
    store.release(first, fake)
    fake.delete_voice.assert_called_once_with('voc_first')
    assert original.exists()
    assert (store.directory(first) / store.list()[0]['voices'][a['breeze_sample_key']]['sample']).exists()
    assert store.resolve_voice(fake, b) == 'voc_second'
    with pytest.raises(ProductionError, match='released'):
        store.resolve_voice(fake, a)
    store.release(first, fake)
    fake.delete_voice.assert_called_once()


def test_uncertain_upload_does_not_duplicate(production):
    store, job_id, assignments, _ = production
    extra = store.bind(job_id, assignments, consent=True)['alice']['extra']
    fake = engine()
    fake.clone_preview.side_effect = BreezeAPIError('Network timeout')
    with pytest.raises(BreezeAPIError):
        store.resolve_voice(fake, extra)
    with pytest.raises(ProductionError, match='uncertain'):
        store.resolve_voice(fake, extra)
    fake.clone_preview.assert_called_once()


def test_rejected_save_resumes_preview_without_uploading_again(production):
    store, job_id, assignments, _ = production
    extra = store.bind(job_id, assignments, consent=True)['alice']['extra']
    fake = engine()
    fake.save_preview.side_effect = [BreezeAPIError('Voice slots full', 402), {'voice_id': 'voc_production'}]
    with pytest.raises(BreezeAPIError):
        store.resolve_voice(fake, extra)
    assert store.resolve_voice(fake, extra) == 'voc_production'
    fake.clone_preview.assert_called_once()


def test_pause_after_upload_preserves_preview(production):
    store, job_id, assignments, _ = production
    extra = store.bind(job_id, assignments, consent=True)['alice']['extra']
    fake = engine()
    class Paused(Exception):
        pass
    def progress(_id, message):
        if message.startswith('Saving'):
            raise Paused()
    with pytest.raises(Paused):
        store.resolve_voice(fake, extra, progress)
    assert store.resolve_voice(fake, extra) == 'voc_production'
    fake.clone_preview.assert_called_once()


def test_changed_key_and_unapproved_sample_are_blocked(production, tmp_path):
    store, job_id, assignments, original = production
    bound = store.bind(job_id, assignments, consent=True)
    fake = engine()
    store.resolve_voice(fake, bound['alice']['extra'])
    fake.api_key = 'different-account-key'
    with pytest.raises(ProductionError, match='key changed'):
        store.resolve_voice(fake, bound['alice']['extra'])
    with pytest.raises(ProductionError, match='original'):
        store.release(job_id, fake)
    bound['alice']['audio_prompt_path'] = str(original)
    with pytest.raises(ProductionError, match='Confirm'):
        store.bind(job_id, bound)


def test_external_paths_and_shared_catalog_voices(production, tmp_path):
    store, job_id, assignments, original = production
    outside = tmp_path / 'outside.wav'
    outside.write_bytes(original.read_bytes())
    with pytest.raises(ProductionError, match='voice library'):
        store.bind(job_id, {'alice': {'audio_prompt_path': str(outside)}}, consent=True)
    catalog = {'alice': {'voice': 'voc_shared'}}
    assert store.bind(str(uuid.uuid4()), catalog) == catalog


def test_engine_resolves_managed_voice_and_keeps_direction(production):
    store, job_id, assignments, original = production
    bound = store.bind(job_id, assignments, consent=True)
    resolver = Mock(return_value='voc_production')
    store.resolve_voice = resolver
    request = Mock()
    request.return_value.status_code = 200
    request.return_value.content = original.read_bytes()
    engine = BreezeAPIEngine('test-only-key', productions=store, request_func=request,
                             audio_converter=lambda *a, **k: original.read_bytes())
    item = engine._work_items([{'speaker': 'alice', 'chunks': ['Hello.'], 'delivery_instruction': 'Warmly.'}], bound)[0]
    engine._synthesize(item['text'], item['assignment'])
    assert request.call_args.args[1].endswith('/voc_production')
    assert request.call_args.kwargs['json']['instructions'] == 'Warmly.'


def test_release_route_requires_confirmation_authorization_and_inactive_job(production, monkeypatch):
    import app as application
    store, job_id, assignments, _ = production
    extra = store.bind(job_id, assignments, consent=True)['alice']['extra']
    fake = engine()
    store.resolve_voice(fake, extra)
    monkeypatch.setattr(application, 'BREEZE_PRODUCTIONS', store)
    monkeypatch.setattr(application, '_create_engine', lambda *a: fake)
    monkeypatch.setattr(application, 'jobs', {job_id: {'status': 'paused'}})
    monkeypatch.setattr(application, 'load_config', lambda: {})
    with application.app.test_client() as client:
        url = f'/api/breeze-api/productions/{job_id}/release'
        assert client.post(url, json={}).status_code == 400
        assert client.post(url, json={'confirm_release': True}).status_code == 409
        application.jobs[job_id]['status'] = 'completed'
        assert client.post(url, json={'confirm_release': True}, environ_base={'REMOTE_ADDR': '192.168.1.1'}).status_code == 403
        assert client.post(url, json={'confirm_release': True}).json['success']
    fake.delete_voice.assert_called_once_with('voc_production')


def test_generate_route_snapshots_without_remote_calls_and_resume_keeps_context(production, monkeypatch, tmp_path):
    import app as application
    from queue import Queue
    store, _id, assignments, original = production
    monkeypatch.setattr(application, 'BREEZE_PRODUCTIONS', store)
    monkeypatch.setattr(application, 'start_worker_thread', lambda: None)
    monkeypatch.setattr(application, '_persist_job_state', lambda *a, **k: None)
    monkeypatch.setattr(application, '_archive_old_jobs', lambda: None)
    monkeypatch.setattr(application, '_consume_engine_first_run_notice', lambda *a: False)
    monkeypatch.setattr(application, '_write_job_text', lambda *a: str(tmp_path / 'input.txt'))
    monkeypatch.setattr(application, 'OUTPUT_DIR', tmp_path / 'audio')
    monkeypatch.setattr(application, 'jobs', {})
    monkeypatch.setattr(application, 'job_queue', Queue())
    monkeypatch.setattr(application, 'load_config', lambda: {**application.DEFAULT_CONFIG, 'breeze_api_key': 'test-key'})
    remote = Mock(side_effect=AssertionError('No paid calls during job submission'))
    monkeypatch.setattr(application, 'get_tts_engine', remote)
    body = {'text': '[alice]Hello.[/alice]', 'tts_engine': 'breeze_api', 'voice_assignments': assignments,
            'production_title': 'Test production'}
    with application.app.test_client() as client:
        assert client.post('/api/generate', json=body).status_code == 400
        body['breeze_upload_consent'] = True
        response = client.post('/api/generate', json=body)
        assert response.status_code == 200, response.json
        job_id = response.json['job_id']
        queued = application.job_queue.get_nowait()
        saved = queued['voice_assignments']['alice']
        assert saved['extra']['breeze_production_id'] == job_id
        assert Path(saved['audio_prompt_path']).read_bytes() == original.read_bytes()
        assert queued['voice_assignments']['default'] == saved
        application.jobs[job_id]['status'] = 'failed'
        application.jobs[job_id]['processed_chunks'] = 0
        assert client.post(f'/api/jobs/{job_id}/resume').status_code == 200
        assert application.job_queue.get_nowait()['voice_assignments']['alice'] == saved
    remote.assert_not_called()


def test_failed_cleanup_is_retryable_and_never_reuploads(production):
    store, job_id, assignments, _ = production
    bound = store.bind(job_id, assignments, consent=True)
    fake = engine()
    store.resolve_voice(fake, bound['alice']['extra'])
    fake.delete_voice.side_effect = [BreezeAPIError('Unavailable', 503), None]
    with pytest.raises(BreezeAPIError):
        store.release(job_id, fake)
    with pytest.raises(ProductionError, match='released'):
        store.resolve_voice(fake, bound['alice']['extra'])
    assert store.release(job_id, fake)['voices'][bound['alice']['extra']['breeze_sample_key']]['state'] == 'deleted'
    assert fake.clone_preview.call_count == 1
