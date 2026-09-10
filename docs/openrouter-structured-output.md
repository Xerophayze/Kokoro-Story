# Structured OpenRouter directions (opt-in)

This API feature is separate from ordinary Prep Text. Existing presets, plain
chat requests, and production model settings are unchanged. It is **not enabled
automatically** by selecting Strict Book Conversion V2 - Directed in the UI.

## Direction-only workflow

First approve and lock speaker/text segmentation. Submit a **complete containing
chapter or scene**, not isolated dialogue, to `POST /api/gemini/process-section`
(the legacy URL is provider-neutral):

```json
{
  "content": "[narrator]Chapter Three\n******[/narrator]\n[eira-female]Exact approved dialogue.[/eira-female]",
  "directed_mode": true
}
```

The application builds numbered immutable blocks and an exact-ID schema. The
LLM returns only `{"directions":{"S1-B001":"...","S1-B002":"..."}}`.
Validated directions are inserted deterministically. It cannot rewrite, reorder,
or delete source blocks. Existing direction metadata is replaced; all remaining
source bytes, speaker tags, whitespace, and pause controls are locked. Untagged
prose, nested tags, and incomplete speaker bookends are rejected, not repaired.

The response includes `result_text` and `direction_audit`. A successful formatting
audit is **not approval for synthesis**: contextual delivery still requires
review. A conservative audible-word vocabulary sends unknown phrasing to review
instead of claiming that arbitrary natural language is semantically safe.
This can reject legitimate synonyms. Do not weaken the gate by accepting every
word observed in a manuscript or by silently stripping invalid directions.

The ordinary automatic speaker-attribution workflow remains unstructured. This
new mode only adds directions to an already approved segmentation. There is no
new global default or automatic production-model promotion.

## General structured output

The same endpoint accepts `response_schema`, `response_schema_name`, and
`response_schema_strict` (default `true`). These are also keyword parameters of
`OpenRouterProcessor.generate_text` and survive the application's failover chain.
Do not use `directed_mode` together with a custom schema: Directed mode constructs
its own exact-ID schema and uses strict validation.

Schemas must be valid JSON objects, no more than 128 KiB and 24 nested levels.
Remote/recursive references and regex keywords are deliberately unsupported.
Schema names are sanitized to 64 ASCII letters, digits, underscores, and hyphens.
Schemas are data only and are never executed. Responses are parsed as JSON (no
Markdown-fence repair), duplicate keys rejected, and validated locally.

Structured OpenRouter requests include `response_format.type=json_schema` and
`provider.require_parameters=true`, as documented by
[OpenRouter](https://openrouter.ai/docs/guides/features/structured-outputs) and its
[provider-routing guide](https://openrouter.ai/docs/guides/routing/provider-selection).
These routing flags do not replace local validation: live testing found invalid
responses despite the requested strict schema.

Only OpenRouter profiles currently support this application path. Unsupported
Gemini, Atlas, and local profiles are skipped without spending their daily
request allowance. If no compatible profile succeeds, the operation fails; it
never drops the schema. Schema/content validation failures stop the operation
instead of silently passing malformed output to another consumer. Ordinary
unstructured failover behavior is unchanged.

## OpenRouter diagnostics and bounded retries

Generation errors now include the upstream provider name/code, a redacted
provider message, and `Retry-After` when supplied. Only selected error fields are
retained; response headers, full request bodies, and credentials are not logged.
Errors embedded in an HTTP 200 response are also recognized.

Temporary 429/502/503/504 failures receive up to **three total attempts** per
profile (initial request plus two retries). Default waits are 5 and 10 seconds;
a larger `Retry-After`, in seconds or HTTP-date form, takes precedence. There is
a 60-second cumulative wait budget. If a requested delay exceeds that budget,
the operation stops or advances to a backup instead of retrying too early.
Every retry reserves another request against the selected profile's daily cap.
Exhausted internal retries advance to the next profile, when available, without
starting another browser retry cycle for that same profile.

Authentication, insufficient-credit, invalid-request, permanent-quota, schema,
and direction-quality failures are not automatically replayed here. Neither are
partial generations or ambiguous network timeouts; the existing caller-level
policy can handle network failures separately. Structured responses that report
an output-token limit are rejected, not treated as complete manuscripts.

The processor exposes `last_attempts`, `last_finish_reason`, and the last usage
record for diagnostics. Benchmark reports record costs for every attempt where
the provider supplies them; missing usage is unknown, not zero. Request timeouts
apply per attempt in addition to the bounded waits. Model-discovery requests
remain single-attempt. Ordinary successful plain-request payloads are unchanged.

## Validation and benchmark

Run `venv\Scripts\python.exe -m pytest tests/test_structured_directed.py
tests/test_openrouter_processor.py tests/test_llm_provider_failover.py -q`.

`scripts/benchmark_directed_openrouter.py` is an explicit live-test tool. It reads
existing credentials without printing or copying them, creates a NEW output
directory, and never imports the Flask app, modifies settings, or synthesizes
audio. Without `--live`, it only prepares test inputs. Each selected model gets
at most three calls per invocation; all successes and failures count. The Gemini
control uses Google's direct API; structured Gemini support here is benchmark-
only, not an application-provider capability. Google cost figures are estimates
at paid list rates, not proof of actual billing/free-tier eligibility.

The September 6 benchmark did **not** qualify either Qwen model for production.
See the local `data/benchmarks/openrouter-directed-20260906-final/REPORT.md`.

## Rollback

No production configuration changed, so no credential-bearing configuration
backup was created or is needed. Stop sending `directed_mode` / schema options
to return to the unchanged plain workflow. Keep the existing production model.
If reverting the implementation, selectively revert only this feature's hunks
in `app.py`, `src/openrouter_processor.py`, and `requirements.txt`, plus its new
structured/directed modules, tests, benchmark scripts, and this document. Do not
use `git reset --hard`, `git checkout -- app.py`, or remove existing user changes.
The jsonschema dependency is inert when not used; it need not be uninstalled.
Restart the backend manually after a selective code rollback when no job is active.
