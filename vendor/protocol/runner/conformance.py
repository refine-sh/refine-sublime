#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import socket
import struct
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


MAX_FRAME_BYTES = 8_388_608
MAX_SOURCE_BYTES = 1_048_576
MAX_SAFE_INTEGER = 9_007_199_254_740_991
PROTOCOL = {"major": 1, "minor": 0}
EXCLUDED_ROOTS = {".git", "__pycache__"}
EXCLUDED_FILES = {"manifest.json", ".DS_Store"}


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


def generated_value(generator: Mapping[str, Any]) -> Any:
    kind = generator.get("kind")
    if kind == "helloCapabilities":
        count = generator["count"]
        return {
            "type": "hello",
            "protocol": PROTOCOL,
            "client": {"id": "com.example.writer", "version": "1", "host": "host"},
            "hostCapabilities": {"interceptableSuggestionActionKeys": []},
            "runId": "run",
            "launchToken": "A" * 64,
            "capabilities": ["com.example.feature-%d.v1" % index for index in range(count)],
        }
    if kind == "sourceBytes":
        return {
            "type": "command",
            "sequence": 1,
            "id": "command-source-limit",
            "command": {
                "type": "openDocument",
                "snapshot": {
                    "revision": "revision",
                    "sources": [{
                        "sourceId": "document",
                        "text": "a" * generator["bytes"],
                        "sourceSyntax": "plainText",
                    }],
                },
            },
        }
    if kind == "capabilityRegistry":
        count = generator["count"]
        publisher = generator["publisher"]
        return {
            "registrySchema": "../schema/capability-registry.schema.json",
            "schemaVersion": 1,
            "protocol": PROTOCOL,
            "capabilities": [
                {
                    "id": "%s.feature-%d.v1" % (publisher, index),
                    "specification": "capabilities/feature-%d.md" % index,
                    "digest": "%064x" % index,
                }
                for index in range(count)
            ],
        }
    if kind == "invalidProgress":
        return {
            "type": "event",
            "sequence": 1,
            "epoch": "epoch",
            "event": {
                "type": "presentationContentReplaced",
                "checkId": "check",
                "content": {
                    "documentRevision": "revision",
                    "status": "checking",
                    "progress": {"completedUnitCount": 2, "totalUnitCount": 1},
                    "suggestions": [],
                    "appearance": {
                        "highlight": {"style": "underline", "grammarColor": "#FF2D55", "fluencyColor": "#007AFF"},
                        "diff": {"additionColor": "#34C759", "deletionColor": "#FF3B30", "showHiddenWhitespace": True},
                    },
                    "interaction": {
                        "automaticChecksEnabled": True,
                        "quickApply": {"enabled": True, "applyKey": "tab", "dismissKey": "escape", "activationStyle": "showTipAndHighlight"},
                    },
                },
            },
        }
    if kind == "invalidPresentation":
        content: Dict[str, Any] = {
            "documentRevision": "revision",
            "status": generator["status"],
            "suggestions": [],
            "appearance": {
                "highlight": {"style": "underline", "grammarColor": "#FF2D55", "fluencyColor": "#007AFF"},
                "diff": {"additionColor": "#34C759", "deletionColor": "#FF3B30", "showHiddenWhitespace": True},
            },
            "interaction": {
                "automaticChecksEnabled": True,
                "quickApply": {"enabled": True, "applyKey": "tab", "dismissKey": "escape", "activationStyle": "showTipAndHighlight"},
            },
        }
        defect = generator["defect"]
        if generator["status"] == "complete" and defect != "missingCoverage":
            content["coverage"] = "full"
        if generator["status"] == "unavailable" and defect != "missingReason":
            content["unavailableReason"] = "checkFailed"
        if defect == "progress":
            content["progress"] = {"completedUnitCount": 0, "totalUnitCount": 1}
        elif defect == "suggestion":
            content["suggestions"] = [{}]
        elif defect == "closedMembers":
            content["coverage"] = "full"
            content["unavailableReason"] = "checkFailed"
            content["progress"] = {"completedUnitCount": 0, "totalUnitCount": 1}
        elif defect == "duplicateActions":
            content["suggestions"] = [{
                "id": "suggestion",
                "sourceId": "document",
                "kind": "grammar",
                "attribution": {
                    "languageDisplayName": "English",
                    "textDirection": "ltr",
                    "checkModelDisplayName": "Model",
                },
                "activationRange": {"location": 0, "length": 1},
                "highlightRanges": [{"location": 0, "length": 1}],
                "diff": [{"kind": "unchanged", "text": "a"}],
                "availableActions": ["apply", "apply"],
            }]
        elif defect not in ("missingCoverage", "missingReason"):
            raise ConformanceError("vector", "unknown invalid presentation defect")
        return {
            "type": "event",
            "sequence": 1,
            "epoch": "epoch",
            "event": {"type": "presentationContentReplaced", "checkId": "check", "content": content},
        }
    raise ConformanceError("vector", "unknown generator %r" % kind)


def published_capability_ids(root: Path, store: SchemaStore) -> List[str]:
    registry = load_json(root / "registry" / "capabilities.json")
    validate_portable_value(registry)
    validate_with_schema(registry, "schema/capability-registry.schema.json", store)
    capabilities = registry["capabilities"]
    for entry in capabilities:
        specification = root / entry["specification"]
        if not specification.is_file() or sha256(specification) != entry["digest"]:
            raise ConformanceError("registry", "capability specification digest mismatch")
    return [entry["id"] for entry in capabilities]


def verify_json_vectors(root: Path, store: SchemaStore, published: Sequence[str]) -> Tuple[int, int]:
    counts = [0, 0]
    for validity_index, validity in enumerate(("positive", "negative")):
        directory = root / "vectors" / "json" / validity
        for path in sorted(directory.glob("*.json")):
            collection = load_json(path)
            if collection.get("formatVersion") != 1 or not isinstance(collection.get("cases"), list):
                raise ConformanceError("vector", "%s is not a vector collection" % path)
            for case in collection["cases"]:
                counts[validity_index] += 1
                if validity == "positive":
                    value = generated_value(case["generate"]) if "generate" in case else case["value"]
                    validate_portable_value(value)
                    validate_with_schema(value, case["schema"], store)
                    validate_semantics(value, published, case["schema"])
                    continue

                expected = case["error"]
                try:
                    if "documentText" in case:
                        value = strict_loads(case["documentText"])
                    elif "generate" in case:
                        value = generated_value(case["generate"])
                    else:
                        value = case["value"]
                    validate_portable_value(value)
                    validate_with_schema(value, case["schema"], store)
                    validate_semantics(value, published, case["schema"])
                except ConformanceError as error:
                    if error.code != expected:
                        raise ConformanceError(
                            "vector",
                            "%s expected %s but observed %s: %s" % (
                                case["id"], expected, error.code, error,
                            ),
                        ) from error
                else:
                    raise ConformanceError("vector", "%s unexpectedly passed" % case["id"])
    return counts[0], counts[1]


def decode_frame(frame: bytes) -> Any:
    if len(frame) < 4:
        raise ConformanceError("truncated-frame", "frame has no complete length prefix")
    length = struct.unpack(">I", frame[:4])[0]
    if length == 0:
        raise ConformanceError("zero-length", "zero-length frames are invalid")
    if length > MAX_FRAME_BYTES:
        raise ConformanceError("frame-too-large", "frame length exceeds maxFrameBytes")
    if len(frame) != 4 + length:
        raise ConformanceError("truncated-frame", "frame length does not match payload")
    try:
        text = frame[4:].decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ConformanceError("invalid-utf8", str(error)) from error
    try:
        value = strict_loads(text)
    except ConformanceError as error:
        if error.code == "malformed-json":
            raise
        raise
    if not isinstance(value, dict):
        raise ConformanceError("object-root-required", "frame payload root is not an object")
    return value


def encode_frame(value: Mapping[str, Any]) -> bytes:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if not payload or len(payload) > MAX_FRAME_BYTES:
        raise ConformanceError("frame-too-large", "encoded payload is outside the frame limit")
    return struct.pack(">I", len(payload)) + payload


def generated_frame(generator: Mapping[str, Any]) -> bytes:
    if generator.get("kind") != "paddedObject":
        raise ConformanceError("vector", "unknown frame generator")
    size = generator["payloadBytes"]
    if size < 10:
        raise ConformanceError("vector", "padded object needs at least ten bytes")
    payload = b'{"pad":"' + (b"a" * (size - 10)) + b'"}'
    return struct.pack(">I", size) + payload


def verify_frame_vectors(root: Path, store: SchemaStore, published: Sequence[str]) -> int:
    count = 0
    for path in sorted((root / "vectors" / "frames").glob("*.json")):
        collection = load_json(path)
        for case in collection["cases"]:
            count += 1
            frame = generated_frame(case["generate"]) if "generate" in case else bytes.fromhex(case["hex"])
            expected = case["expected"]
            try:
                value = decode_frame(frame)
                if "schema" in case:
                    validate_with_schema(value, case["schema"], store)
                    validate_semantics(value, published, case["schema"])
            except ConformanceError as error:
                if expected != "invalid":
                    raise ConformanceError("vector", "%s unexpectedly failed: %s" % (case["id"], error)) from error
                if error.code != case["error"]:
                    raise ConformanceError("vector", "%s expected %s, observed %s" % (case["id"], case["error"], error.code)) from error
            else:
                if expected == "invalid":
                    raise ConformanceError("vector", "%s unexpectedly passed" % case["id"])
    return count


def substitute(value: Any, token: str, epoch: str) -> Any:
    if value == "${launchToken}":
        return token
    if value == "${serverEpoch}":
        return epoch
    if isinstance(value, list):
        return [substitute(item, token, epoch) for item in value]
    if isinstance(value, dict):
        return {key: substitute(item, token, epoch) for key, item in value.items()}
    return value


def state_step_message(step: Mapping[str, Any], messages: Mapping[str, Any]) -> Mapping[str, Any]:
    if "message" in step:
        return step["message"]
    reference = step.get("messageRef")
    if not isinstance(reference, str) or reference not in messages:
        raise ConformanceError("state", "state step has no resolvable message")
    message = messages[reference]
    if not isinstance(message, dict):
        raise ConformanceError("state", "state message reference is not an object")
    return message


def verify_state_vector(
    vector: Mapping[str, Any],
    store: SchemaStore,
    published: Sequence[str],
) -> None:
    if vector.get("formatVersion") != 1 or not isinstance(vector.get("connections"), list):
        raise ConformanceError("state", "invalid state vector")

    messages = vector.get("messages", {})
    if not isinstance(messages, dict):
        raise ConformanceError("state", "state messages must be an object")
    token = "A" * 64
    epoch_placeholder = "epoch-vector"
    for name, message in messages.items():
        if not isinstance(message, dict):
            raise ConformanceError("state", "%s is not a message object" % name)
        substituted_message = substitute(message, token, epoch_placeholder)
        validate_portable_value(substituted_message)
        if substituted_message.get("type") in ("hello", "welcome", "rejected"):
            validate_with_schema(substituted_message, "schema/handshake.schema.json", store)
        else:
            validate_with_schema(substituted_message, "schema/envelope.schema.json", store)
        validate_semantics(substituted_message, published)

    for case in vector.get("coordinateCases", []):
        text = case["text"]
        boundaries = {0}
        utf16_length = 0
        for character in text:
            utf16_length += 2 if ord(character) > 0xFFFF else 1
            boundaries.add(utf16_length)
        location = case["range"]["location"]
        end = location + case["range"]["length"]
        actual = (
            location >= 0
            and end >= location
            and end <= utf16_length
            and location in boundaries
            and end in boundaries
        )
        if actual is not case["valid"]:
            raise ConformanceError("state", "%s coordinate expectation is incorrect" % case["id"])

    for case in vector.get("applyEditCases", []):
        ranges = sorted(
            (item["location"], item["location"] + item["length"])
            for item in case["ranges"]
        )
        actual = all(start >= prior_end for (_, prior_end), (start, _) in zip(ranges, ranges[1:]))
        if actual is not case["valid"]:
            raise ConformanceError("state", "%s Apply edit overlap expectation is incorrect" % case["id"])

    for connection in vector["connections"]:
        starts = connection.get("sequenceStarts", {})
        expected_sequence = {
            "client": starts.get("client", 1),
            "server": starts.get("server", 1),
        }
        welcome: Optional[Mapping[str, Any]] = None
        restore_order: List[str] = []
        steps = connection.get("steps", [])
        for index, step in enumerate(steps):
            if step.get("close") is True:
                continue
            if "rawFrameHex" in step:
                try:
                    frame = bytes.fromhex(step["rawFrameHex"])
                except (TypeError, ValueError) as error:
                    raise ConformanceError("state", "invalid rawFrameHex") from error
                try:
                    decode_frame(frame)
                except ConformanceError:
                    continue
                raise ConformanceError("state", "rawFrameHex is not an invalid frame")
            message = substitute(state_step_message(step, messages), token, epoch_placeholder)
            validate_portable_value(message)
            invalid = step.get("invalid")
            message_schema = (
                "schema/handshake.schema.json"
                if message.get("type") in ("hello", "welcome", "rejected")
                else "schema/envelope.schema.json"
            )
            if invalid == "schema":
                if step.get("direction") != "server":
                    raise ConformanceError("state", "invalid schema fixture is not server-directed")
                try:
                    validate_with_schema(message, message_schema, store)
                except SchemaError:
                    continue
                raise ConformanceError("state", "schema fixture is not invalid")
            if invalid == "eventSemantics":
                if step.get("direction") != "server" or message_schema != "schema/envelope.schema.json":
                    raise ConformanceError("state", "invalid semantic fixture is not a server envelope")
                validate_with_schema(message, message_schema, store)
                try:
                    validate_semantics(message, published, message_schema)
                except ConformanceError:
                    continue
                raise ConformanceError("state", "semantic fixture is not invalid")
            if invalid == "faultUnion":
                event = message.get("event", {}) if isinstance(message, dict) else {}
                expected_epoch = welcome.get("serverEpoch") if welcome is not None else None
                if (
                    step.get("direction") != "server"
                    or message.get("type") != "event"
                    or message.get("sequence") != expected_sequence["server"]
                    or message.get("epoch") != expected_epoch
                    or not isinstance(event, dict)
                    or event.get("type") != "fault"
                    or event.get("code") != "invalidSequence"
                    or event.get("fatal") is not False
                ):
                    raise ConformanceError("state", "invalid fault fixture is not server-directed")
                try:
                    validate_with_schema(message, "schema/envelope.schema.json", store)
                except SchemaError:
                    continue
                raise ConformanceError("state", "faultUnion fixture is not invalid")
            if message.get("type") in ("hello", "welcome", "rejected"):
                validate_with_schema(message, "schema/handshake.schema.json", store)
                if message["type"] == "welcome":
                    welcome = message
            else:
                validate_with_schema(message, "schema/envelope.schema.json", store)
                direction = step["direction"]
                sequence = message["sequence"]
                if invalid is not None:
                    if direction != "server":
                        raise ConformanceError("state", "invalid server fixture has the wrong direction")
                    if invalid == "eventSequence":
                        if message.get("type") != "event" or sequence == expected_sequence["server"]:
                            raise ConformanceError("state", "eventSequence fixture has a valid sequence")
                    elif invalid == "eventEpoch":
                        expected_epoch = welcome.get("serverEpoch") if welcome is not None else None
                        if (
                            message.get("type") != "event"
                            or sequence != expected_sequence["server"]
                            or message.get("epoch") == expected_epoch
                        ):
                            raise ConformanceError("state", "eventEpoch fixture has a valid epoch")
                    elif invalid == "serverEnvelope":
                        if message.get("type") == "event":
                            raise ConformanceError("state", "serverEnvelope fixture is an event")
                    else:
                        raise ConformanceError("state", "unknown invalid state fixture %r" % invalid)
                    continue
                if sequence != expected_sequence[direction]:
                    raise ConformanceError("state", "%s has noncontiguous %s sequence" % (vector["id"], direction))
                expected_sequence[direction] += 1
                if step.get("exhaustsSequence") is True:
                    next_step = steps[index + 1] if index + 1 < len(steps) else {}
                    if sequence != 4_294_967_295 or next_step.get("close") is not True or next_step.get("direction") != direction:
                        raise ConformanceError("state", "%s does not close at sequence exhaustion" % vector["id"])
                if message["type"] == "event" and welcome is not None:
                    if message["epoch"] != welcome["serverEpoch"]:
                        raise ConformanceError("state", "%s event epoch differs from welcome" % vector["id"])
            validate_semantics(message, published)
            if "restore" in step:
                restore_order.append(step["restore"])
        if restore_order:
            if restore_order != vector.get("expectedRestoreOrder"):
                raise ConformanceError("state", "%s restore order is wrong" % vector["id"])
            resumed = bool(welcome and welcome.get("runResumed"))
            if not resumed and "receipt" in restore_order:
                raise ConformanceError("state", "%s replays a receipt after lost state" % vector["id"])
        fatal_positions = [
            index for index, step in enumerate(steps)
            if not step.get("close")
            and "rawFrameHex" not in step
            and state_step_message(step, messages).get("type") == "event"
            and state_step_message(step, messages).get("event", {}).get("type") == "fault"
            and state_step_message(step, messages)["event"].get("fatal") is True
        ]
        for position in fatal_positions:
            if position + 1 >= len(steps) or steps[position + 1].get("close") is not True:
                raise ConformanceError("state", "%s fatal fault is not followed by close" % vector["id"])
    if vector.get("mutationRetried") is True:
        raise ConformanceError("state", "%s retries a host mutation" % vector["id"])
    if vector.get("wrappedToZero") is True:
        raise ConformanceError("state", "%s wraps a sequence to zero" % vector["id"])


def verify_state_vectors(root: Path, store: SchemaStore, published: Sequence[str]) -> int:
    count = 0
    for path in sorted((root / "vectors" / "state").glob("*.json")):
        vector = load_json(path)
        verify_state_vector(vector, store, published)
        count += 1
    return count


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_kind(relative: Path) -> str:
    first = relative.parts[0]
    if first in {"schema", "spec", "registry", "vectors", "runner", "reference"}:
        return first
    if relative.name == "LICENSE":
        return "license"
    return "documentation"


def shipped_artifact_paths(root: Path) -> set[str]:
    result: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if relative.parts[0] in EXCLUDED_ROOTS or path.name in EXCLUDED_FILES:
            continue
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise ConformanceError("manifest", "shipped artifact is a symbolic link: %s" % relative)
        if not path.is_file():
            continue
        result.add(relative.as_posix())
    return result


def case_inventory(paths: Sequence[Path], label: str) -> List[str]:
    identifiers: List[str] = []
    for path in paths:
        collection = load_json(path)
        cases = collection.get("cases") if isinstance(collection, dict) else None
        if not isinstance(cases, list):
            raise ConformanceError("manifest", "%s is not a case collection" % path)
        for case in cases:
            identifier = case.get("id") if isinstance(case, dict) else None
            if not isinstance(identifier, str) or not identifier:
                raise ConformanceError("manifest", "%s contains an invalid case ID" % path)
            identifiers.append(identifier)
    if len(identifiers) != len(set(identifiers)):
        raise ConformanceError("manifest", "%s inventory contains duplicate IDs" % label)
    return identifiers


def verify_manifest(root: Path) -> Mapping[str, Any]:
    manifest = load_json(root / "manifest.json")
    if manifest.get("formatVersion") != 1 or manifest.get("protocol") != PROTOCOL:
        raise ConformanceError("manifest", "unsupported manifest identity")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ConformanceError("manifest", "artifacts must be an array")
    shipped = shipped_artifact_paths(root)
    artifact_lines: List[str] = []
    base_artifact_lines: List[str] = []
    listed_paths: List[str] = []
    seen: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ConformanceError("manifest", "artifact entry must be an object")
        relative = artifact.get("path")
        if not isinstance(relative, str) or not relative:
            raise ConformanceError("manifest", "artifact path must be a nonempty string")
        relative_path = Path(relative)
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or relative_path.as_posix() != relative
        ):
            raise ConformanceError("manifest", "unsafe artifact path: %s" % relative)
        if relative in seen:
            raise ConformanceError("manifest", "duplicate artifact path: %s" % relative)
        if relative not in shipped:
            raise ConformanceError("manifest", "listed path is not a shipped regular file: %s" % relative)
        seen.add(relative)
        listed_paths.append(relative)
        actual = sha256(root / relative)
        if actual != artifact.get("sha256"):
            raise ConformanceError("manifest", "digest mismatch: %s" % relative)
        expected_kind = artifact_kind(relative_path)
        if artifact.get("kind") != expected_kind:
            raise ConformanceError("manifest", "incorrect artifact kind: %s" % relative)
        artifact_lines.append("%s\0%s\n" % (relative, actual))
        if expected_kind in ("schema", "spec", "vectors"):
            base_artifact_lines.append("%s\0%s\n" % (relative, actual))
    unlisted = shipped - seen
    if unlisted:
        raise ConformanceError("manifest", "unlisted artifact: %s" % sorted(unlisted)[0])
    if listed_paths != sorted(listed_paths):
        raise ConformanceError("manifest", "artifact paths are not in bytewise lexical order")
    aggregate = hashlib.sha256("".join(artifact_lines).encode("utf-8")).hexdigest()
    if aggregate != manifest.get("artifactDigest"):
        raise ConformanceError("manifest", "aggregate artifact digest mismatch")
    base_aggregate = hashlib.sha256("".join(base_artifact_lines).encode("utf-8")).hexdigest()
    if base_aggregate != manifest.get("baseArtifactDigest"):
        raise ConformanceError("manifest", "base artifact digest mismatch")
    registry_digest = sha256(root / "registry" / "capabilities.json")
    if registry_digest != manifest.get("capabilityRegistryDigest"):
        raise ConformanceError("manifest", "capability registry digest mismatch")
    inventories = {
        "jsonPositiveCaseIds": case_inventory(
            sorted((root / "vectors" / "json" / "positive").glob("*.json")),
            "positive JSON",
        ),
        "jsonNegativeCaseIds": case_inventory(
            sorted((root / "vectors" / "json" / "negative").glob("*.json")),
            "negative JSON",
        ),
        "frameCaseIds": case_inventory(
            sorted((root / "vectors" / "frames").glob("*.json")),
            "frame",
        ),
        "stateScenarioIds": [
        load_json(path)["id"]
        for path in sorted((root / "vectors" / "state").glob("*.json"))
        ],
    }
    if len(inventories["stateScenarioIds"]) != len(set(inventories["stateScenarioIds"])):
        raise ConformanceError("manifest", "state scenario inventory contains duplicate IDs")
    for name, expected in inventories.items():
        if manifest.get(name) != expected:
            raise ConformanceError("manifest", "%s does not match shipped vectors" % name)
    return manifest


def validate_suggestion_shortcut(value: Any, store: SchemaStore) -> None:
    validate_portable_value(value)
    validate_with_schema(value, "schema/suggestion-shortcuts.schema.json", store)
    code, modifiers = value["code"], value["modifiers"]
    if code.startswith(("Shift", "Alt", "Control")):
        if modifiers:
            raise ConformanceError("shortcut", "standalone modifier has additional modifiers")
    else:
        printable = code.startswith(("Key", "Digit", "Intl", "Numpad")) or code in {
            "Equal", "Minus", "BracketRight", "BracketLeft", "Quote", "Semicolon",
            "Backslash", "Comma", "Slash", "Period", "Backquote",
        }
        if printable and not set(modifiers) & {"control", "option", "command"}:
            raise ConformanceError("shortcut", "typing shortcut requires a modifier")


def validate_suggestion_binding(value: Any, store: SchemaStore) -> None:
    validate_portable_value(value)
    validate_with_schema(value, "schema/suggestion-shortcuts-v2.schema.json", store)
    if value["kind"] == "keyCombination":
        validate_suggestion_shortcut(value, store)


def verify_shortcut_vectors(root: Path, store: SchemaStore) -> None:
    for path, validator in [("bindings.json", validate_suggestion_shortcut),
                            ("bindings-v2.json", validate_suggestion_binding)]:
        for case in load_json(root / "vectors/shortcuts" / path)["cases"]:
            try:
                validator(case["value"], store)
                valid = True
            except ConformanceError:
                valid = False
            if valid != case["valid"]:
                raise ConformanceError("shortcut-vector", case["id"])


def verify(root: Path) -> Mapping[str, Any]:
    manifest = verify_manifest(root)
    store = SchemaStore(root)
    for path in sorted((root / "schema").glob("*.json")):
        store.load(str(path.relative_to(root)))
    published = published_capability_ids(root, store)
    verify_shortcut_vectors(root, store)
    positive, negative = verify_json_vectors(root, store, published)
    frames = verify_frame_vectors(root, store, published)
    states = verify_state_vectors(root, store, published)
    return {
        "status": "ok",
        "protocol": PROTOCOL,
        "artifactDigest": manifest["artifactDigest"],
        "baseArtifactDigest": manifest["baseArtifactDigest"],
        "capabilityRegistryDigest": manifest["capabilityRegistryDigest"],
        "jsonPositive": positive,
        "jsonNegative": negative,
        "frameVectors": frames,
        "stateVectors": states,
    }


def receive_exact(connection: socket.socket, count: int) -> bytes:
    chunks: List[bytes] = []
    remaining = count
    while remaining:
        chunk = connection.recv(remaining)
        if not chunk:
            raise ConformanceError("socket", "peer closed during a frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def receive_message(connection: socket.socket) -> Any:
    header = receive_exact(connection, 4)
    length = struct.unpack(">I", header)[0]
    if length == 0 or length > MAX_FRAME_BYTES:
        return decode_frame(header)
    payload = receive_exact(connection, length)
    return decode_frame(header + payload)


def run_socket(root: Path, scenario: str, client: Sequence[str]) -> Mapping[str, Any]:
    if not client:
        raise ConformanceError("socket", "--client requires COMMAND [ARGS...]")
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", scenario) is None:
        raise ConformanceError("socket", "invalid scenario identifier")
    store = SchemaStore(root)
    published = published_capability_ids(root, store)
    vector_path = root / "vectors" / "state" / (scenario + ".json")
    vector = load_json(vector_path)
    verify_state_vector(vector, store, published)
    if vector.get("socketRunnable") is not True:
        raise ConformanceError("socket", "%s is not socket-runnable" % scenario)

    launch_token = secrets.token_hex(32).upper()
    server_epoch = str(uuid.uuid4()).upper()
    with tempfile.TemporaryDirectory(prefix="refine-protocol-") as directory_name:
        directory = Path(directory_name)
        os.chmod(directory, 0o700)
        socket_path = directory / "refine.sock"
        descriptor_path = directory / "endpoint.json"
        owner_path = directory / "owner.lock"
        owner_descriptor = os.open(owner_path, os.O_CREAT | os.O_RDWR, 0o600)
        os.fchmod(owner_descriptor, 0o600)
        fcntl.flock(owner_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        os.chmod(socket_path, 0o600)
        listener.listen(1)
        listener.settimeout(5.0)
        descriptor = {
            "version": 1,
            "socketPath": str(socket_path),
            "launchToken": launch_token,
            "serverEpoch": server_epoch,
            "protocolMajor": 1,
            "protocolMinor": 0,
            "pid": os.getpid(),
        }
        descriptor_path.write_text(json.dumps(descriptor, separators=(",", ":")), encoding="utf-8")
        os.chmod(descriptor_path, 0o600)
        command = list(client) + ["--descriptor", str(descriptor_path), "--scenario", scenario]
        process = subprocess.Popen(
            command,
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            messages = vector.get("messages", {})
            for connection_vector in vector["connections"]:
                connection, _ = listener.accept()
                connection.settimeout(5.0)
                with connection:
                    for step in connection_vector["steps"]:
                        if step.get("close") is True:
                            if step["direction"] == "server":
                                try:
                                    connection.shutdown(socket.SHUT_RDWR)
                                except OSError:
                                    pass
                            else:
                                if connection.recv(1):
                                    raise ConformanceError(
                                        "socket", "client sent bytes instead of closing",
                                    )
                            break
                        if "rawFrameHex" in step:
                            connection.sendall(bytes.fromhex(step["rawFrameHex"]))
                            continue
                        expected = substitute(
                            state_step_message(step, messages), launch_token, server_epoch,
                        )
                        if step["direction"] == "client":
                            actual = receive_message(connection)
                            if not json_equal(actual, expected):
                                raise ConformanceError(
                                    "socket", "client message differs at a scenario step",
                                )
                        else:
                            connection.sendall(encode_frame(expected))
            stdout, stderr = process.communicate(timeout=5.0)
        except BaseException:
            process.kill()
            process.communicate()
            raise
        finally:
            listener.close()
            fcntl.flock(owner_descriptor, fcntl.LOCK_UN)
            os.close(owner_descriptor)
        if process.returncode != 0:
            raise ConformanceError("socket", "client exited %d: %s" % (process.returncode, stderr.strip()))
        try:
            client_result = strict_loads(stdout.strip())
        except ConformanceError as error:
            raise ConformanceError("socket", "client did not return a JSON result") from error
        if not isinstance(client_result, dict):
            raise ConformanceError("socket", "client result is not a JSON object")
        if client_result.get("status") != "ok" or client_result.get("scenario") != scenario:
            raise ConformanceError("socket", "client reported an unsuccessful scenario")
    return {"status": "ok", "scenario": scenario, "transport": "AF_UNIX"}


def run_server(root: Path, scenario: str, adapter: Sequence[str]) -> Mapping[str, Any]:
    if not adapter:
        raise ConformanceError("server", "--adapter requires COMMAND [ARGS...]")
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", scenario) is None:
        raise ConformanceError("server", "invalid scenario identifier")
    store = SchemaStore(root)
    published = published_capability_ids(root, store)
    vector_path = root / "vectors" / "state" / (scenario + ".json")
    vector = load_json(vector_path)
    verify_state_vector(vector, store, published)
    if vector.get("socketRunnable") is not True:
        raise ConformanceError("server", "%s is not socket-runnable" % scenario)

    with tempfile.TemporaryDirectory(prefix="refine-protocol-server-") as directory_name:
        descriptor_directory = Path(directory_name)
        os.chmod(descriptor_directory, 0o700)
        command = list(adapter) + [
            "--scenario", scenario,
            "--descriptor-dir", str(descriptor_directory),
        ]
        try:
            process = subprocess.run(
                command,
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=300.0,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ConformanceError("server", "server adapter timed out") from error
        if process.returncode != 0:
            raise ConformanceError(
                "server",
                "adapter exited %d: %s" % (process.returncode, process.stderr.strip()),
            )
        try:
            adapter_result = strict_loads(process.stdout.strip())
        except ConformanceError as error:
            raise ConformanceError("server", "adapter did not return one JSON result") from error
        expected_result = {"status": "ok", "scenario": scenario}
        if not isinstance(adapter_result, dict) or not json_equal(adapter_result, expected_result):
            raise ConformanceError("server", "adapter reported an unexpected result")
        remaining = sorted(path.name for path in descriptor_directory.iterdir())
        if remaining:
            raise ConformanceError(
                "server",
                "adapter left descriptor-directory artifacts: %s" % ", ".join(remaining),
            )
    return {"status": "ok", "scenario": scenario, "transport": "AF_UNIX", "role": "server"}


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(description="Integration Protocol 1.0 conformance runner")
    argument_parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    commands = argument_parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify", help="verify the complete offline artifact")
    socket_parser = commands.add_parser("socket", help="exercise a client against the fake AF_UNIX peer")
    socket_parser.add_argument("--scenario", default="base-handshake")
    socket_parser.add_argument(
        "--client",
        nargs=argparse.REMAINDER,
        required=True,
        help="COMMAND [ARGS...]; this must be the final runner option",
    )
    server_parser = commands.add_parser(
        "server",
        help="invoke a self-driving production-server conformance adapter",
    )
    server_parser.add_argument("--scenario", default="base-handshake")
    server_parser.add_argument(
        "--adapter",
        nargs=argparse.REMAINDER,
        required=True,
        help="COMMAND [ARGS...]; this must be the final runner option",
    )
    return argument_parser


def main() -> int:
    arguments = parser().parse_args()
    root = arguments.root.resolve()
    try:
        if arguments.command == "verify":
            result = verify(root)
        elif arguments.command == "socket":
            result = run_socket(root, arguments.scenario, arguments.client)
        else:
            result = run_server(root, arguments.scenario, arguments.adapter)
    except (ConformanceError, KeyError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
