"""Bounded, data-only JSON schema validation for optional LLM responses."""
import json
import re

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


class StructuredOutputError(ValueError):
    pass


def validate_schema(schema, name=None, strict=True):
    if not isinstance(schema, dict):
        raise StructuredOutputError("response_schema must be a JSON object")
    if not isinstance(strict, bool):
        raise StructuredOutputError("response_schema_strict must be a boolean")
    try:
        encoded = json.dumps(schema, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise StructuredOutputError("Schema must contain finite JSON data only") from exc
    if len(encoded.encode("utf-8")) > 131072:
        raise StructuredOutputError("Schema exceeds 128 KiB limit")

    def walk(value, depth=0):
        if depth > 24:
            raise StructuredOutputError("Schema exceeds nesting limit")
        if isinstance(value, dict):
            # No remote retrieval, recursive references, or user-supplied regex
            # execution during validation. Schema descriptions are data, not code.
            if any(k in value for k in ("$ref", "$dynamicRef", "pattern", "patternProperties")):
                raise StructuredOutputError("Schema references and regex keywords are not supported")
            for child in value.values():
                walk(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                walk(child, depth + 1)
    walk(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise StructuredOutputError("Invalid JSON schema: " + exc.message[:200]) from exc
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", str(name or "tts_story_response"))[:64]
    return {"type": "json_schema", "json_schema": {
        "name": safe_name, "strict": strict, "schema": json.loads(encoded),
    }}


def parse_structured_response(text, schema):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StructuredOutputError("Duplicate JSON key: " + key[:80])
            result[key] = value
        return result
    try:
        value = json.loads(text, object_pairs_hook=unique_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        Draft202012Validator(schema).validate(value)
    except (ValueError, ValidationError, RecursionError) as exc:
        detail = exc.message if isinstance(exc, ValidationError) else str(exc)
        raise StructuredOutputError("Response failed JSON/schema validation: " + detail[:240]) from exc
    return value
