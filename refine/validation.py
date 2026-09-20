# Derived from refine-protocol runner/conformance.py; MIT, Copyright 2026 Runjuu.
# This is the protocol validator, not the socket test runner. See vendor/protocol.
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

MAX_FRAME_BYTES = 8_388_608
MAX_SOURCE_BYTES = 1_048_576
MAX_SAFE_INTEGER = 9_007_199_254_740_991

class ConformanceError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


class SchemaError(ConformanceError):
    def __init__(self, path: str, detail: str):
        super().__init__("schema", "%s: %s" % (path, detail))


def strict_loads(text: str, enforce_portable_profile: bool = True) -> Any:
    def object_pairs(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ConformanceError("duplicate-key", "duplicate object member %r" % key)
            result[key] = value
        return result

    def reject_float(token: str) -> None:
        raise ConformanceError(
            "non-integer-number-token",
            "numeric token %r is not an integer lexical form" % token,
        )

    def portable_integer(token: str) -> int:
        if token.startswith("-"):
            raise ConformanceError(
                "negative-number-token",
                "numeric token %r is negative" % token,
            )
        value = int(token)
        if value > MAX_SAFE_INTEGER:
            raise ConformanceError(
                "unsafe-number-token",
                "numeric token %r exceeds the interoperable integer range" % token,
            )
        return value

    def reject_constant(token: str) -> None:
        raise ConformanceError("malformed-json", "non-JSON constant %r" % token)

    try:
        arguments: Dict[str, Any] = {
            "object_pairs_hook": object_pairs,
            "parse_constant": reject_constant,
        }
        if enforce_portable_profile:
            arguments["parse_float"] = reject_float
            arguments["parse_int"] = portable_integer
        value = json.loads(text, **arguments)
    except ConformanceError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ConformanceError("malformed-json", str(error)) from error

    def validate_value(item: Any) -> None:
        if enforce_portable_profile and item is None:
            raise ConformanceError("null-value", "JSON null is outside the portable profile")
        if enforce_portable_profile and isinstance(item, int) and not isinstance(item, bool):
            if item < 0:
                raise ConformanceError("negative-number-token", "numeric value is negative")
            if item > MAX_SAFE_INTEGER:
                raise ConformanceError(
                    "unsafe-number-token",
                    "numeric value exceeds the interoperable integer range",
                )
        if enforce_portable_profile and isinstance(item, float):
            raise ConformanceError(
                "non-integer-number-token",
                "numeric value is not an integer lexical form",
            )
        if isinstance(item, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in item):
                raise ConformanceError("unpaired-surrogate", "string contains a surrogate code point")
        elif isinstance(item, list):
            for child in item:
                validate_value(child)
        elif isinstance(item, dict):
            for key, child in item.items():
                validate_value(key)
                validate_value(child)

    validate_value(value)
    return value


def validate_portable_value(value: Any) -> None:
    # Round-tripping is intentionally avoided: generated and decoded values may
    # already have lost a token's original spelling, but their semantic domain
    # must still obey the same global profile.
    if value is None:
        raise ConformanceError("null-value", "JSON null is outside the portable profile")
    if isinstance(value, bool) or isinstance(value, str):
        if isinstance(value, str) and any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ConformanceError("unpaired-surrogate", "string contains a surrogate code point")
        return
    if isinstance(value, int):
        if value < 0:
            raise ConformanceError("negative-number-token", "numeric value is negative")
        if value > MAX_SAFE_INTEGER:
            raise ConformanceError(
                "unsafe-number-token",
                "numeric value exceeds the interoperable integer range",
            )
        return
    if isinstance(value, float):
        raise ConformanceError(
            "non-integer-number-token",
            "numeric value is not an integer lexical form",
        )
    if isinstance(value, list):
        for child in value:
            validate_portable_value(child)
        return
    if isinstance(value, dict):
        for key, child in value.items():
            validate_portable_value(key)
            validate_portable_value(child)
        return
    raise ConformanceError("portable-json", "value is outside the portable JSON data model")


def load_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ConformanceError("invalid-utf8", "%s: %s" % (path, error)) from error
    return strict_loads(text, enforce_portable_profile=False)


def json_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(json_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(json_equal(a, b) for a, b in zip(left, right))
    return bool(left == right)


def ecma_pattern_matches(pattern: str, value: str) -> bool:
    # JSON Schema patterns use ECMA-262 semantics, whose terminal `$` does not
    # have Python's special match-before-a-final-newline behavior.
    backslashes = 0
    for character in reversed(pattern[:-1]):
        if character != "\\":
            break
        backslashes += 1
    translated = pattern
    if pattern.endswith("$") and backslashes % 2 == 0:
        translated = pattern[:-1] + r"\Z"
    try:
        return re.search(translated, value) is not None
    except re.error as error:
        raise SchemaError("$schema", "invalid pattern %r" % pattern) from error


class SchemaStore:
    def __init__(self, root: Path):
        self.root = root
        self.documents: Dict[str, Any] = {}

    def load(self, relative_path: str) -> Any:
        normalized = str(Path(relative_path))
        if normalized not in self.documents:
            self.documents[normalized] = load_json(self.root / normalized)
        return self.documents[normalized]

    def resolve(self, reference: str, current_document: str) -> Tuple[Any, str]:
        document_name, separator, fragment = reference.partition("#")
        if document_name:
            current_parent = Path(current_document).parent
            document = str((current_parent / document_name).as_posix())
        else:
            document = current_document
        value = self.load(document)
        if separator and fragment:
            if not fragment.startswith("/"):
                raise SchemaError("$ref", "unsupported fragment %r" % fragment)
            for token in fragment[1:].split("/"):
                token = token.replace("~1", "/").replace("~0", "~")
                try:
                    value = value[int(token)] if isinstance(value, list) else value[token]
                except (KeyError, TypeError, ValueError, IndexError) as error:
                    raise SchemaError("$ref", "unresolved reference %r" % reference) from error
        return value, document


def matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    raise SchemaError("$schema", "unsupported type %r" % expected)


def validate_schema(
    value: Any,
    schema: Any,
    store: SchemaStore,
    document: str,
    path: str = "$",
) -> None:
    if isinstance(schema, bool):
        if not schema:
            raise SchemaError(path, "boolean schema is false")
        return
    if not isinstance(schema, dict):
        raise SchemaError(path, "schema node is not an object")

    if "$ref" in schema:
        target, target_document = store.resolve(schema["$ref"], document)
        validate_schema(value, target, store, target_document, path)

    for child in schema.get("allOf", []):
        validate_schema(value, child, store, document, path)

    if "anyOf" in schema:
        if not any(schema_matches(value, child, store, document, path) for child in schema["anyOf"]):
            raise SchemaError(path, "does not match any allowed shape")

    if "oneOf" in schema:
        matches = sum(
            1 for child in schema["oneOf"]
            if schema_matches(value, child, store, document, path)
        )
        if matches != 1:
            raise SchemaError(path, "matches %d oneOf branches, expected exactly one" % matches)

    if "not" in schema and schema_matches(value, schema["not"], store, document, path):
        raise SchemaError(path, "matches a forbidden shape")

    expected_type = schema.get("type")
    if expected_type is not None:
        types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(matches_type(value, item) for item in types):
            raise SchemaError(path, "expected type %s" % "/".join(types))

    if "const" in schema and not json_equal(value, schema["const"]):
        raise SchemaError(path, "expected constant %r" % schema["const"])
    if "enum" in schema and not any(json_equal(value, option) for option in schema["enum"]):
        raise SchemaError(path, "unknown enum value %r" % value)

    if isinstance(value, dict):
        missing = [key for key in schema.get("required", []) if key not in value]
        if missing:
            raise SchemaError(path, "missing required member(s): %s" % ", ".join(missing))
        properties = schema.get("properties", {})
        for key, child in value.items():
            if key in properties:
                validate_schema(child, properties[key], store, document, "%s.%s" % (path, key))

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise SchemaError(path, "has fewer than %d items" % schema["minItems"])
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise SchemaError(path, "has more than %d items" % schema["maxItems"])
        if schema.get("uniqueItems"):
            for index, item in enumerate(value):
                if any(json_equal(item, prior) for prior in value[:index]):
                    raise SchemaError(path, "contains duplicate items")
        if "items" in schema:
            for index, item in enumerate(value):
                validate_schema(item, schema["items"], store, document, "%s[%d]" % (path, index))

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise SchemaError(path, "is shorter than %d characters" % schema["minLength"])
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise SchemaError(path, "is longer than %d characters" % schema["maxLength"])
        if "pattern" in schema and not ecma_pattern_matches(schema["pattern"], value):
            raise SchemaError(path, "does not match %s" % schema["pattern"])

    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaError(path, "is below minimum %d" % schema["minimum"])
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaError(path, "is above maximum %d" % schema["maximum"])


def schema_matches(value: Any, schema: Any, store: SchemaStore, document: str, path: str) -> bool:
    try:
        validate_schema(value, schema, store, document, path)
        return True
    except SchemaError:
        return False


def validate_with_schema(value: Any, schema_path: str, store: SchemaStore) -> None:
    if "#" in schema_path:
        schema, document = store.resolve(schema_path, "")
        validate_schema(value, schema, store, document)
    else:
        validate_schema(value, store.load(schema_path), store, schema_path)


def validate_snapshot(snapshot: Any) -> None:
    if not isinstance(snapshot, dict):
        return
    sources = snapshot.get("sources")
    if not isinstance(sources, list):
        return
    source_ids: List[str] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_id = source.get("sourceId")
        if isinstance(source_id, str):
            source_ids.append(source_id)
        text = source.get("text")
        if isinstance(text, str) and len(text.encode("utf-8")) > MAX_SOURCE_BYTES:
            raise ConformanceError("source-byte-limit", "source text exceeds maxSourceBytes")
    if len(source_ids) != len(set(source_ids)):
        raise ConformanceError("duplicate-source-id", "snapshot source IDs are not unique")


def validate_range(value: Any) -> None:
    if not isinstance(value, dict):
        return
    location = value.get("location")
    length = value.get("length")
    if (
        isinstance(location, int)
        and not isinstance(location, bool)
        and isinstance(length, int)
        and not isinstance(length, bool)
        and location + length > MAX_SAFE_INTEGER
    ):
        raise ConformanceError(
            "range-overflow",
            "range location + length exceeds the interoperable integer range",
        )


def validate_visible_ranges(attention: Any) -> None:
    if not isinstance(attention, dict) or not isinstance(attention.get("visibleRanges"), list):
        return
    prior_end: Optional[int] = None
    for item in attention["visibleRanges"]:
        validate_range(item)
        if not isinstance(item, dict):
            continue
        location = item.get("location")
        length = item.get("length")
        if not isinstance(location, int) or not isinstance(length, int):
            continue
        if length <= 0 or (prior_end is not None and location < prior_end):
            raise ConformanceError(
                "visible-range",
                "visible ranges must be nonempty, ordered, and nonoverlapping",
            )
        prior_end = location + length


def validate_apply_edits(request: Any) -> None:
    if not isinstance(request, dict) or not isinstance(request.get("edits"), list):
        return
    prior_location: Optional[int] = None
    for edit in request["edits"]:
        if not isinstance(edit, dict) or not isinstance(edit.get("range"), dict):
            continue
        validate_range(edit["range"])
        location = edit["range"].get("location")
        length = edit["range"].get("length")
        if not isinstance(location, int) or not isinstance(length, int):
            continue
        if edit.get("expectedText") == edit.get("replacement"):
            raise ConformanceError("apply-edits", "Apply edits must not be no-ops")
        if prior_location is not None:
            if location >= prior_location or location + length > prior_location:
                raise ConformanceError(
                    "apply-edits",
                    "Apply edits must be descending without ties or overlaps",
                )
        prior_location = location


def validate_progress(content: Any) -> None:
    if not isinstance(content, dict) or not isinstance(content.get("progress"), dict):
        return
    progress = content["progress"]
    completed = progress.get("completedUnitCount")
    total = progress.get("totalUnitCount")
    if isinstance(completed, int) and isinstance(total, int) and completed > total:
        raise ConformanceError("progress-order", "completedUnitCount exceeds totalUnitCount")


def validate_presentation(content: Any) -> None:
    validate_progress(content)
    if not isinstance(content, dict) or not isinstance(content.get("suggestions"), list):
        return
    for suggestion in content["suggestions"]:
        if not isinstance(suggestion, dict):
            continue
        validate_range(suggestion.get("activationRange"))
        highlight_ranges = suggestion.get("highlightRanges")
        if isinstance(highlight_ranges, list):
            for highlight_range in highlight_ranges:
                validate_range(highlight_range)


def validate_registry(registry: Any) -> None:
    if not isinstance(registry, dict) or not isinstance(registry.get("capabilities"), list):
        return
    identifiers = [
        entry.get("id") for entry in registry["capabilities"]
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    ]
    if len(identifiers) != len(set(identifiers)):
        raise ConformanceError("duplicate-capability-id", "capability registry IDs are not unique")


def validate_semantics(
    value: Any,
    published_capabilities: Sequence[str],
    schema_path: Optional[str] = None,
) -> None:
    if not isinstance(value, dict):
        return
    if schema_path in (
        "schema/shared.schema.json#/$defs/utf16Range",
        "schema/shared.schema.json#/$defs/nonEmptyUTF16Range",
    ):
        validate_range(value)
        return
    if schema_path == "schema/shared.schema.json#/$defs/hostApplyRequest":
        validate_apply_edits(value)
        return
    if schema_path == "schema/shared.schema.json#/$defs/presentationContent":
        validate_presentation(value)
        return
    message_type = value.get("type")
    if message_type == "welcome" and isinstance(value.get("capabilities"), list):
        unpublished = set(value["capabilities"]) - set(published_capabilities)
        if unpublished:
            raise ConformanceError("unpublished-capability", "welcome activates an unpublished capability")
        return
    if message_type == "command" and isinstance(value.get("command"), dict):
        command = value["command"]
        command_type = command.get("type")
        if command_type in ("openDocument", "replaceDocument"):
            validate_snapshot(command.get("snapshot"))
        elif command_type == "updateAttention":
            validate_visible_ranges(command.get("attention"))
        elif command_type == "requestCheck" and isinstance(command.get("intent"), dict):
            selection = command["intent"].get("selection")
            if isinstance(selection, dict):
                validate_range(selection.get("range"))
        elif command_type == "completeApply" and isinstance(command.get("outcome"), dict):
            validate_snapshot(command["outcome"].get("snapshot"))
        return
    if message_type == "event" and isinstance(value.get("event"), dict):
        event = value["event"]
        if event.get("type") == "presentationContentReplaced":
            validate_presentation(event.get("content"))
        elif event.get("type") == "applyRequested":
            validate_apply_edits(event.get("request"))
        return
    if value.get("schemaVersion") == 1 and "capabilities" in value:
        validate_registry(value)


