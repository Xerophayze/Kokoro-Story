import json
from unittest.mock import patch

import pytest

from src.openrouter_processor import OpenRouterProcessor
from src.structured_output import StructuredOutputError, validate_schema, parse_structured_response
from src.directed_output import prepare_direction_request, assemble_directed


SCHEMA = {'type': 'object', 'properties': {'answer': {'type': 'string'}},
          'required': ['answer'], 'additionalProperties': False}


def test_structured_request_and_plain_request_are_separate():
    with patch('src.openrouter_processor.requests.post') as post:
        post.return_value.status_code = 200
        post.return_value.json.return_value = {'choices': [{'message': {'content': '{"answer":"yes"}'}}]}
        p = OpenRouterProcessor('test-key', 'test-model')
        p.generate_text('prompt', response_schema=SCHEMA, response_schema_name='bad name /<>')
        payload = post.call_args.kwargs['json']
        assert payload['provider'] == {'require_parameters': True}
        assert payload['response_format']['json_schema'] == {
            'name': 'bad_name____', 'strict': True, 'schema': SCHEMA}
        p.generate_text('prompt')
        assert post.call_args.kwargs['json'] == {
            'model': 'test-model', 'messages': [{'role': 'user', 'content': 'prompt'}], 'stream': False}


@pytest.mark.parametrize('schema', [[], '', {'type': 'invalid'}, {'$ref': 'https://example.com'},
                                    {'pattern': '(a+)+$'}, {'description': 'x' * 131073}])
def test_bad_schemas_fail_before_network(schema):
    with patch('src.openrouter_processor.requests.post') as post:
        with pytest.raises(StructuredOutputError):
            OpenRouterProcessor('key', 'model').generate_text('prompt', response_schema=schema)
        post.assert_not_called()


@pytest.mark.parametrize('response', ['{"answer":"a","answer":"b"}', '{}', '{"answer":3}',
                                      '{"answer":"a","extra":1}', '```json\n{}\n```'])
def test_response_fails_closed(response):
    with pytest.raises(StructuredOutputError):
        parse_structured_response(response, SCHEMA)


def test_exact_locked_assembly():
    text = '[narrator]Chapter Three\r\n******\r\n[/narrator]\r\n[eira-female]“Please, stop!”[/eira-female]\r\n******'
    locked, prompt, schema = prepare_direction_request(text)
    assert 'COMPLETE SCENE' in prompt
    result, audit = assemble_directed(locked, json.dumps({'directions': {
        'S1-B001': 'Narrate slowly with solemn restraint.',
        'S1-B002': 'Speak urgently with breathless rising panic.'}}))
    assert audit['exact_source_reconstruction']
    assert text.encode() == locked['source'].encode()
    assert result.count('******') == 2
    assert schema['properties']['directions']['required'] == ['S1-B001', 'S1-B002']


@pytest.mark.parametrize('text', ['[narrator]Missing close', '[direction]Oops[/direction]',
                                 'Unwrapped prose[narrator]Hello[/narrator]',
                                 '[narrator][bob]Hello[/bob][/narrator]'])
def test_invalid_manuscripts_rejected(text):
    with pytest.raises(StructuredOutputError):
        prepare_direction_request(text)


@pytest.mark.parametrize('direction', ['Describe the dark room and its symbolic shadows.',
    'Speak as if standing near the sea.', 'Speak urgently to convey impending danger.',
    'Speak softly.', 'Speak in a voice that is not loud and not theatrical.'])
def test_direction_rules_fail_closed(direction):
    locked, _, _ = prepare_direction_request('[narrator]Hello.[/narrator]')
    with pytest.raises(StructuredOutputError):
        assemble_directed(locked, json.dumps({'directions': {'S1-B001': direction}}))


def test_schema_survives_failover_and_endpoint(monkeypatch, tmp_path):
    import app as a
    from src.openrouter_processor import OpenRouterProcessorError
    monkeypatch.setattr(a, 'LLM_PROFILE_USAGE_FILE', tmp_path / 'usage.json')
    config = {'llm_provider': 'openrouter', 'openrouter_model': 'primary', 'openrouter_api_key': 'key',
              'llm_backup_profiles': [{'id': 'backup', 'provider': 'openrouter', 'model': 'backup', 'api_key': 'key'}]}
    seen = []
    def fake(self, prompt, **kwargs):
        seen.append(kwargs)
        if self.model_name == 'primary':
            raise OpenRouterProcessorError('429 quota exceeded')
        return '{"answer":"yes"}'
    monkeypatch.setattr(a.OpenRouterProcessor, 'generate_text', fake)
    monkeypatch.setattr(a, 'load_config', lambda: config)
    response = a.app.test_client().post('/api/gemini/process-section', json={
        'content': 'Test section', 'response_schema': SCHEMA, 'response_schema_name': 'test'})
    assert response.status_code == 200, response.json
    assert len(seen) == 2
    assert all(v['response_schema'] == SCHEMA for v in seen)
    assert all(v['response_schema_strict'] is True for v in seen)


def test_unsupported_provider_never_drops_schema():
    import app as a
    with pytest.raises(StructuredOutputError, match='schema was not dropped'):
        a._run_llm_prompt_for_provider('prompt', {}, 'gemini', response_schema=SCHEMA)


def test_endpoint_rejects_invalid_schema_before_llm(monkeypatch):
    import app as a
    with patch.object(a, '_run_llm_prompt_with_failover') as call:
        response = a.app.test_client().post('/api/gemini/process-section', json={
            'content': 'hello', 'response_schema': []})
        assert response.status_code == 400
        call.assert_not_called()


def test_incompatible_backup_is_skipped_without_reserving_usage(monkeypatch):
    import app as a
    monkeypatch.setattr(a, '_resolve_llm_profile_chain', lambda _: [
        {'id':'g', 'name':'Gemini', 'provider':'gemini'}])
    with patch.object(a, '_reserve_llm_profile_request') as reserve:
        with pytest.raises(StructuredOutputError, match='No compatible'):
            a._run_llm_prompt_with_failover('prompt', {}, response_schema=SCHEMA)
        reserve.assert_not_called()


def test_directed_endpoint_assembles_not_rewrites(monkeypatch):
    import app as a
    monkeypatch.setattr(a, 'load_config', lambda: {'llm_provider':'openrouter'})
    def fake(prompt, config, **kwargs):
        assert kwargs['response_schema']['properties']['directions']['required'] == ['S1-B001']
        return '{"directions":{"S1-B001":"Narrate with quiet, measured restraint."}}', {'provider':'openrouter'}, []
    monkeypatch.setattr(a, '_run_llm_prompt_with_failover', fake)
    source = '\r\n[narrator]Exact words.******[/narrator]\r\n'
    response = a.app.test_client().post('/api/gemini/process-section', json={
        'content':source, 'directed_mode':True})
    assert response.status_code == 200, response.json
    assert response.json['result_text'].endswith('[narrator]Exact words.******[/narrator]\r\n')
    assert response.json['result_text'].startswith('\r\n[direction]')
    assert response.json['direction_audit']['exact_source_reconstruction']


@pytest.mark.parametrize('value', ['Speak with quiet grief.******', 'Speak [direction]quietly[/direction].'])
def test_review_mode_still_rejects_control_injection(value):
    locked, _, _ = prepare_direction_request('[narrator]Hello.[/narrator]')
    with pytest.raises(StructuredOutputError):
        assemble_directed(locked, json.dumps({'directions':{'S1-B001':value}}), enforce_quality=False)
