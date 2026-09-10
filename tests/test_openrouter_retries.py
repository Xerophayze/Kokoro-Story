from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import patch

import pytest
import requests

from src.openrouter_processor import OpenRouterProcessor, OpenRouterProcessorError, _retry_after_seconds


class Reply:
    def __init__(self, code=200, payload=None, headers=None):
        self.status_code = code
        self.headers = headers or {}
        self.payload = payload if payload is not None else {'choices':[{'message':{'content':'OK'}}]}
        self.text = ''

    def json(self):
        return self.payload


def error(code=429, headers=None, raw='Temporarily rate limited upstream'):
    return Reply(code, {'error':{'code':code, 'message':'Provider returned error',
        'metadata':{'provider_name':'Alibaba','raw':raw}}}, headers)


@patch('src.openrouter_processor.time.sleep')
@patch('src.openrouter_processor.requests.post')
def test_retry_after_and_backoff(post, sleep):
    post.side_effect = [error(headers={'Retry-After':'7'}), error(503), Reply()]
    p = OpenRouterProcessor('key', 'model')
    assert p.generate_text('hello') == 'OK'
    assert [c.args[0] for c in sleep.call_args_list] == [7,10]
    assert len(p.last_attempts) == 3
    assert all(c.kwargs['json'] == post.call_args.kwargs['json'] for c in post.call_args_list)


@patch('src.openrouter_processor.time.sleep')
@patch('src.openrouter_processor.requests.post')
def test_exhaustion_is_bounded(post, sleep):
    post.return_value = error()
    with pytest.raises(OpenRouterProcessorError) as caught:
        OpenRouterProcessor('key','model').generate_text('hello')
    assert post.call_count == 3
    assert caught.value.retries_exhausted
    assert caught.value.attempts == 3
    assert 'Alibaba' in str(caught.value)


@patch('src.openrouter_processor.time.sleep')
@patch('src.openrouter_processor.requests.post')
def test_long_retry_after_never_retried_early(post, sleep):
    post.return_value = error(headers={'Retry-After':'120'})
    with pytest.raises(OpenRouterProcessorError) as caught:
        OpenRouterProcessor('key','model').generate_text('hello')
    assert caught.value.retry_after == 120
    assert caught.value.retries_exhausted
    assert post.call_count == 1
    sleep.assert_not_called()


def test_http_date_and_invalid_retry_after():
    value = format_datetime(datetime.now(timezone.utc)+timedelta(seconds=30),usegmt=True)
    assert 28 <= _retry_after_seconds(value) <= 30
    assert _retry_after_seconds('nonsense') is None
    assert _retry_after_seconds('NaN') is None
    assert _retry_after_seconds('-1') == 0


@pytest.mark.parametrize('status', [400,401,402,403])
@patch('src.openrouter_processor.time.sleep')
@patch('src.openrouter_processor.requests.post')
def test_permanent_errors_are_not_retried(post, sleep, status):
    post.return_value = error(status)
    with pytest.raises(OpenRouterProcessorError):
        OpenRouterProcessor('key','model').generate_text('hello')
    assert post.call_count == 1
    sleep.assert_not_called()


@patch('src.openrouter_processor.time.sleep')
@patch('src.openrouter_processor.requests.post')
def test_embedded_200_provider_error_retries(post, sleep):
    failed = error()
    failed.status_code = 200
    post.side_effect = [failed,Reply()]
    assert OpenRouterProcessor('key','model').generate_text('hello') == 'OK'
    sleep.assert_called_once_with(5)


def test_raw_details_are_selected_and_redacted():
    r = error(raw='{"code":"Throttling","message":"Slow down secret-key Bearer abc sk-testtoken", "headers":{"Authorization":"never-print-this"}}')
    e = OpenRouterProcessor._response_error(r,'generation','secret-key')
    assert e.provider_code == 'Throttling'
    assert 'Slow down' in str(e)
    for secret in ('secret-key','abc','sk-testtoken','never-print-this'):
        assert secret not in str(e)


@patch('src.openrouter_processor.requests.post')
def test_timeout_is_not_replayed(post):
    post.side_effect = requests.ReadTimeout('Timed out')
    with pytest.raises(OpenRouterProcessorError):
        OpenRouterProcessor('key','model').generate_text('hello')
    assert post.call_count == 1


@patch('src.openrouter_processor.requests.post')
def test_structured_token_exhaustion_is_not_replayed(post):
    post.return_value = Reply(payload={'choices':[{'message':{'content':'{}'},'finish_reason':'length'}]})
    p = OpenRouterProcessor('key','model')
    with pytest.raises(OpenRouterProcessorError,match='token limit'):
        p.generate_text('hello',response_schema={'type':'object'})
    assert post.call_count == 1
    assert p.last_response_text == '{}'
    assert p.last_finish_reason == 'length'


@patch('src.openrouter_processor.time.sleep')
@patch('src.openrouter_processor.requests.post')
def test_partial_generation_is_never_replayed(post, sleep):
    reply = error()
    reply.status_code = 200
    reply.payload['choices'] = [{'message':{'content':'partial output'}}]
    post.return_value = reply
    with pytest.raises(OpenRouterProcessorError):
        OpenRouterProcessor('key','model').generate_text('hello')
    assert post.call_count == 1
    sleep.assert_not_called()


def test_app_retry_cap_and_failover(monkeypatch, tmp_path):
    import app as a
    monkeypatch.setattr(a,'LLM_PROFILE_USAGE_FILE',tmp_path/'usage.json')
    config = {'llm_provider':'openrouter','openrouter_model':'primary','openrouter_api_key':'key',
              'llm_backup_profiles':[{'id':'backup','provider':'openrouter','model':'backup','api_key':'key'}]}
    with patch('src.openrouter_processor.requests.post') as post, patch('src.openrouter_processor.time.sleep'):
        post.side_effect = [error(),error(),error(),Reply()]
        text, used, failures = a._run_llm_prompt_with_failover('hello',config,defer_transient_failover=True)
        assert text == 'OK' and used['id'] == 'backup'
        assert post.call_count == 4
        assert failures[0]['failure_kind'] == 'advance_profile'


def test_app_daily_cap_counts_retries(monkeypatch, tmp_path):
    import app as a
    monkeypatch.setattr(a,'LLM_PROFILE_USAGE_FILE',tmp_path/'usage.json')
    profile = {'id':'test','name':'test','provider':'openrouter','api_key':'key','model':'test','daily_request_limit':2}
    monkeypatch.setattr(a,'_resolve_llm_profile_chain',lambda _: [profile])
    with patch('src.openrouter_processor.requests.post',return_value=error()) as post, patch('src.openrouter_processor.time.sleep'):
        with pytest.raises(a.LLMProviderChainError):
            a._run_llm_prompt_with_failover('hello',{})
        assert post.call_count == 2
