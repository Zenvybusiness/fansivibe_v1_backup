"""FFO knowledge corpus — versioned curated-document ingestion (Phase 2A).

File-backed K9.1 seed layer: `knowledge/documents/*.json` are the source of
truth. Stdlib only (`json`, `pathlib`, `re`, `datetime`).

Validation is structural, fail-fast per document (first error raises):
envelope shape, enums, provenance, timestamps, per-type rules, FFO schema
references, and required payload keys. It is NOT full JSON Schema
evaluation (noOf/oneOf/discriminators beyond the declared if/then are not
executed) — add `jsonschema` only when a consumer needs deeper checks.
# ponytail: flat functions over a registry class; per-doc version ints over
a migration log until curation volume demands one.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from app.data.ffo import list_schemas, load_schema

DOCUMENTS_DIR = Path(__file__).resolve().parent / "knowledge" / "documents"
_RELATIONSHIPS_PATH = (
    Path(__file__).resolve().parent / "knowledge" / "relationships" / "relationship_types.json"
)

DOC_TYPES = ("term", "alias", "relationship", "rule")
STATUSES = ("draft", "reviewed", "published", "deprecated")
SOURCE_TYPES = (
    "AUTHORITATIVE",
    "PROFESSIONAL",
    "INDUSTRY",
    "COMMUNITY",
    "INFERRED",
    "MODEL_GENERATED",
)

_DOC_ID_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
_LANGUAGE_RE = re.compile(r"^[a-z]{2}(?:-[A-Z]{2})?$")


class CorpusError(ValueError):
    """A corpus document failed to load, validate, or index.

    Subclasses :class:`ValueError` (mirrors the KnowledgeError rationale)
    so callers treating bad system-owned content as a value problem keep
    working unchanged. Never carries user data.
    """


def _is_nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_timestamp(errors: list, doc: dict, field: str, doc_id: str) -> None:
    value = doc.get(field)
    if value is None:
        return
    if not isinstance(value, str):
        errors.append(f"{doc_id}: '{field}' must be an ISO-8601 string")
        return
    try:
        datetime.fromisoformat(value)
    except ValueError:
        errors.append(f"{doc_id}: '{field}' is not parseable ISO-8601")


def validate_document(doc: dict) -> list[str]:
    """Structural validation of one knowledge document; [] means valid."""
    if not isinstance(doc, dict):
        return ["document must be an object"]
    doc_id = doc.get("doc_id") if isinstance(doc.get("doc_id"), str) else "<unknown>"
    errors: list[str] = []

    if not _is_nonempty_str(doc.get("doc_id")) or not _DOC_ID_RE.match(doc["doc_id"]):
        errors.append(f"{doc_id}: 'doc_id' must be a slug like 'term-wide-leg-jeans'")
    doc_type = doc.get("doc_type")
    if doc_type not in DOC_TYPES:
        errors.append(f"{doc_id}: 'doc_type' must be one of {list(DOC_TYPES)}")
    if doc.get("status") not in STATUSES:
        errors.append(f"{doc_id}: 'status' must be one of {list(STATUSES)}")
    version = doc.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        errors.append(f"{doc_id}: 'version' must be an integer >= 1")
    language = doc.get("language")
    if not isinstance(language, str) or not _LANGUAGE_RE.match(language):
        errors.append(f"{doc_id}: 'language' must look like 'en' or 'en-IN'")
    region = doc.get("region")
    if region is not None and not _is_nonempty_str(region):
        errors.append(f"{doc_id}: 'region' must be a non-empty string when present")
    _check_timestamp(errors, doc, "published_at", doc_id)
    _check_timestamp(errors, doc, "retrieved_at", doc_id)
    _check_timestamp(errors, doc, "created_at", doc_id)
    _check_timestamp(errors, doc, "updated_at", doc_id)

    provenance = doc.get("provenance")
    if not isinstance(provenance, dict):
        errors.append(f"{doc_id}: 'provenance' is required")
    else:
        if not _is_nonempty_str(provenance.get("source")):
            errors.append(f"{doc_id}: 'provenance.source' is required")
        if provenance.get("source_type") not in SOURCE_TYPES:
            errors.append(f"{doc_id}: 'provenance.source_type' must be one of {list(SOURCE_TYPES)}")
        confidence = provenance.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            errors.append(f"{doc_id}: 'provenance.confidence' must be a number")
        elif not (0.0 <= float(confidence) <= 1.0):
            errors.append(f"{doc_id}: 'provenance.confidence' must be within 0..1")

    canonical_id = doc.get("canonical_id")
    if doc_type in ("term", "alias"):
        if not _is_nonempty_str(canonical_id):
            errors.append(f"{doc_id}: 'canonical_id' is required for '{doc_type}' docs")
    elif canonical_id is not None and not _is_nonempty_str(canonical_id):
        errors.append(f"{doc_id}: 'canonical_id' must be a non-empty string when present")

    entity_kind = doc.get("entity_kind")
    if doc_type == "term":
        if entity_kind not in list_schemas():
            errors.append(f"{doc_id}: 'entity_kind' must be a registered FFO schema")
        payload = doc.get("payload")
        if not isinstance(payload, dict):
            errors.append(f"{doc_id}: 'payload' object is required for 'term' docs")
        elif entity_kind in list_schemas():
            required = load_schema(entity_kind).get("required", [])
            missing = [key for key in required if key not in payload]
            if missing:
                errors.append(f"{doc_id}: payload missing FFO required keys {missing}")
    elif entity_kind is not None and entity_kind not in list_schemas():
        errors.append(f"{doc_id}: 'entity_kind' must be a registered FFO schema")

    if doc_type == "alias" and not _is_nonempty_str(doc.get("alias")):
        errors.append(f"{doc_id}: 'alias' is required for 'alias' docs")

    if doc_type == "relationship":
        rel_types = json.loads(_RELATIONSHIPS_PATH.read_text(encoding="utf-8"))["relationships"]
        if doc.get("rel_type") not in rel_types:
            errors.append(f"{doc_id}: 'rel_type' must be a known relationship type")
        if not _is_nonempty_str(doc.get("subject")):
            errors.append(f"{doc_id}: 'subject' is required for 'relationship' docs")
        if not _is_nonempty_str(doc.get("object")):
            errors.append(f"{doc_id}: 'object' is required for 'relationship' docs")

    if doc_type == "rule":
        payload = doc.get("payload")
        if not isinstance(payload, dict):
            errors.append(f"{doc_id}: 'payload' object is required for 'rule' docs")
        else:
            if "when" not in payload:
                errors.append(f"{doc_id}: rule payload requires 'when'")
            if "effect" not in payload:
                errors.append(f"{doc_id}: rule payload requires 'effect'")

    return errors


def load_documents(directory: Path | None = None) -> list[dict]:
    """Load `*.json` documents in sorted filename order; JSON errors raise."""
    docs = []
    for path in sorted(Path(directory or DOCUMENTS_DIR).glob("*.json")):
        try:
            docs.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as exc:
            raise CorpusError(f"cannot load corpus document '{path.name}': {exc}") from exc
    return docs


def build_index(docs: list) -> dict:
    """Validate + index documents; duplicates/collisions raise CorpusError.

    Index: by_id, by_canonical {(doc_type, canonical_id): doc} for terms
    (terms own canonicals — aliases legally share targets, FFO §35),
    aliases {alias: canonical_id}, versions {doc_id: version}.
    Same doc_id twice is always a duplicate (files are the source of
    truth — no merge). Alias targets must resolve to a term canonical_id
    in the same set (relationship subjects/objects stay free strings:
    they may name external concepts).
    """
    by_id: dict[str, dict] = {}
    by_canonical: dict[tuple, dict] = {}
    aliases: dict[str, str] = {}
    versions: dict[str, int] = {}

    for doc in docs or []:
        errors = validate_document(doc)
        doc_id = doc.get("doc_id") if isinstance(doc, dict) else None
        if errors:
            raise CorpusError("; ".join(errors))
        if doc_id in by_id:
            raise CorpusError(f"duplicate doc_id '{doc_id}'")
        canonical_id = doc.get("canonical_id")
        if doc["doc_type"] == "term":
            key = ("term", canonical_id)
            if key in by_canonical:
                raise CorpusError(
                    f"canonical collision: '{canonical_id}' already claimed by a 'term' doc"
                )
            by_canonical[key] = doc
        by_id[doc_id] = doc
        versions[doc_id] = doc["version"]

    term_canonicals = {
        canonical for (doc_type, canonical) in by_canonical if doc_type == "term"
    }
    for doc_id, doc in by_id.items():
        if doc["doc_type"] != "alias":
            continue
        alias, target = doc["alias"], doc["canonical_id"]
        if alias in aliases and aliases[alias] != target:
            raise CorpusError(f"alias collision: '{alias}' maps to two canonicals")
        aliases[alias] = target
        if target not in term_canonicals:
            raise CorpusError(f"alias '{alias}' targets unknown term '{target}'")

    return {"by_id": by_id, "by_canonical": by_canonical, "aliases": aliases, "versions": versions}


def corpus_versions(index: dict) -> dict:
    """Per-document versions {doc_id: version} from a built index."""
    return dict(index.get("versions", {}))


def evidence_content(doc: dict) -> dict:
    """Validated knowledge content for the reasoning layer (Phase 3D).

    Returns the knowledge-bearing subset of a validated corpus document,
    always including its doc_id so consumers can verify belonging. Raises
    CorpusError on invalid docs (missing content where required) — never
    invents or summarizes. Per type:
      term → entity_kind + canonical_id + full payload
      alias → alias + canonical_id (+ entity_kind when present)
      relationship → rel_type + subject + object
      rule → full payload (when/effect)
    """
    errors = validate_document(doc)
    if errors:
        raise CorpusError("; ".join(errors))
    doc_type = doc["doc_type"]
    base: dict = {"doc_id": doc["doc_id"]}
    if doc_type == "term":
        base.update({
            "entity_kind": doc["entity_kind"],
            "canonical_id": doc["canonical_id"],
            "payload": dict(doc["payload"]),
        })
    elif doc_type == "alias":
        base.update({"alias": doc["alias"], "canonical_id": doc["canonical_id"]})
        if doc.get("entity_kind") is not None:
            base["entity_kind"] = doc["entity_kind"]
    elif doc_type == "relationship":
        base.update({
            "rel_type": doc["rel_type"],
            "subject": doc["subject"],
            "object": doc["object"],
        })
    elif doc_type == "rule":
        base.update({"payload": dict(doc["payload"])})
    else:  # unreachable post-validation; defensive, never silent
        raise CorpusError(f"unknown doc_type '{doc_type}'")
    return base
