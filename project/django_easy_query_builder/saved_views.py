import hashlib
import json

JSONPrimitive = str | int | float | bool | None
JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]

_VOLATILE_QUERY_KEYS = {"id", "fieldRef", "valueRef"}
_VOLATILE_TRANSFORM_KEYS = {"id"}


def canonicalize_query_payload(value: JSONValue) -> JSONValue:
    if isinstance(value, dict):
        cleaned: dict[str, JSONValue] = {}
        for key in sorted(value.keys()):
            if key in _VOLATILE_QUERY_KEYS:
                continue
            if key == "transforms" and isinstance(value.get(key), list):
                cleaned[key] = [
                    {
                        transform_key: canonicalize_query_payload(transform_value)
                        for transform_key, transform_value in sorted(transform.items())
                        if transform_key not in _VOLATILE_TRANSFORM_KEYS
                    }
                    for transform in value[key]
                    if isinstance(transform, dict)
                ]
                continue
            cleaned[key] = canonicalize_query_payload(value[key])
        return cleaned

    if isinstance(value, list):
        return [canonicalize_query_payload(item) for item in value]

    return value


def canonicalize_query_payload_json(payload: dict[str, JSONValue]) -> str:
    canonical_payload = canonicalize_query_payload(payload)
    return json.dumps(
        canonical_payload,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=True,
    )


def hash_string_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_query_hash(payload: dict[str, JSONValue]) -> str:
    canonical_json = canonicalize_query_payload_json(payload)
    return hash_string_sha256(canonical_json)
