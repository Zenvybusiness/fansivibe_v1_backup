"""Unit tests for the hairstyle knowledge layer.

Covers the KN-10 access paths against the deterministic approved catalog
(`app/data/catalog.py`), the version surface (KN-1), and the invalid/missing
knowledge paths — malformed entries and an empty catalog are truthful errors
(KNOWLEDGE_ARCHITECTURE §3.3, KN-3). No database; no user data.
"""

from __future__ import annotations

import pytest

from app.data import catalog
from app.domain.ports.external import KnowledgeError, KnowledgeSource
from app.domain.services.analysis_rules import recommend_hairstyle
from app.domain.value_objects import AppearanceProfile
from app.infrastructure.external.knowledge import CatalogKnowledgeSource


@pytest.fixture
def source() -> CatalogKnowledgeSource:
    return CatalogKnowledgeSource()


def _all_entries() -> list[dict]:
    return [dict(entry) for entry in catalog.HAIRSTYLE_LOOKS]


# --- retrieval -------------------------------------------------------------


def test_retrieval_returns_the_full_catalog(source):
    looks = source.retrieve_hairstyle_looks()
    assert len(looks) == 4
    assert sorted(look.id for look in looks) == [
        "brushed_up_undercut",
        "classic_pompadour",
        "side_part",
        "textured_quiff",
    ]


def test_retrieval_is_deterministic(source):
    first = [look.id for look in source.retrieve_hairstyle_looks()]
    second = [look.id for look in source.retrieve_hairstyle_looks()]
    assert first == second


def test_retrieval_maps_catalog_fields(source):
    by_id = {look.id: look for look in source.retrieve_hairstyle_looks()}
    quiff = by_id["textured_quiff"]
    assert quiff.name == "Textured Quiff"
    assert quiff.description
    assert quiff.matchScore == 0.94
    assert quiff.reasons
    assert quiff.stylingTips
    assert quiff.maintenance
    assert quiff.bestFor


def test_retrieval_is_knowledge_only_no_user_data(source):
    for look in source.retrieve_hairstyle_looks():
        assert not hasattr(look, "user_id")


# --- lookup -----------------------------------------------------------------


def test_lookup_returns_exact_look(source):
    look = source.lookup_hairstyle_look("side_part")
    assert look is not None
    assert look.id == "side_part"
    assert look.name == "Side Part"


def test_lookup_unknown_code_returns_none(source):
    assert source.lookup_hairstyle_look("no_such_look") is None


# --- version handling (KN-1) ------------------------------------------------


def test_knowledge_version_is_exposed_and_stable(source):
    assert source.knowledge_version == catalog.KNOWLEDGE_VERSION
    assert isinstance(source.knowledge_version, str)
    assert CatalogKnowledgeSource().knowledge_version == source.knowledge_version


def test_knowledge_version_distinct_from_engine_version():
    assert catalog.KNOWLEDGE_VERSION != "rules-v1"


# --- deprecated filtering (KN-3) --------------------------------------------


def test_deprecated_look_filtered_from_retrieval_but_lookupable(monkeypatch):
    entries = _all_entries()
    entries[0]["deprecated"] = True
    monkeypatch.setattr(catalog, "HAIRSTYLE_LOOKS", entries)

    source = CatalogKnowledgeSource()
    ids = [look.id for look in source.retrieve_hairstyle_looks()]
    assert entries[0]["code"] not in ids
    assert len(ids) == 3
    # KN-3: deprecated codes remain reference-able (never removed).
    assert source.lookup_hairstyle_look(entries[0]["code"]) is not None


# --- invalid knowledge --------------------------------------------------------


def test_malformed_entry_raises_on_retrieval(monkeypatch):
    entries = _all_entries()
    del entries[0]["title"]
    monkeypatch.setattr(catalog, "HAIRSTYLE_LOOKS", entries)

    with pytest.raises(KnowledgeError):
        CatalogKnowledgeSource().retrieve_hairstyle_looks()


def test_empty_reasons_raises_on_retrieval(monkeypatch):
    entries = _all_entries()
    entries[0]["reasons"] = []
    monkeypatch.setattr(catalog, "HAIRSTYLE_LOOKS", entries)

    with pytest.raises(KnowledgeError):
        CatalogKnowledgeSource().retrieve_hairstyle_looks()


def test_out_of_range_score_raises_on_retrieval(monkeypatch):
    entries = _all_entries()
    entries[0]["scoreSeed"] = 1.5
    monkeypatch.setattr(catalog, "HAIRSTYLE_LOOKS", entries)

    with pytest.raises(KnowledgeError):
        CatalogKnowledgeSource().retrieve_hairstyle_looks()


def test_missing_code_raises_on_retrieval(monkeypatch):
    entries = _all_entries()
    del entries[0]["code"]
    monkeypatch.setattr(catalog, "HAIRSTYLE_LOOKS", entries)

    with pytest.raises(KnowledgeError):
        CatalogKnowledgeSource().retrieve_hairstyle_looks()


# --- missing knowledge --------------------------------------------------------


def test_empty_catalog_engine_raises_knowledge_error(monkeypatch):
    monkeypatch.setattr(catalog, "HAIRSTYLE_LOOKS", [])
    with pytest.raises(KnowledgeError):
        recommend_hairstyle(
            CatalogKnowledgeSource(), AppearanceProfile(faceShape="Oval")
        )


def test_empty_catalog_retrieval_returns_empty(monkeypatch):
    monkeypatch.setattr(catalog, "HAIRSTYLE_LOOKS", [])
    assert CatalogKnowledgeSource().retrieve_hairstyle_looks() == []


def test_protocol_is_satisfied_by_catalog_source():
    source: KnowledgeSource = CatalogKnowledgeSource()
    assert source.lookup_hairstyle_look("textured_quiff") is not None
    assert source.retrieve_hairstyle_looks()


# --- STEP 12.3: OI rule knowledge version + combined provenance ----------------


def test_oi_knowledge_version_exists_and_is_1_0():
    """1. OI rule knowledge carries its own explicit version beside the maps."""
    from app.domain.services.analysis_rules import OI_KNOWLEDGE_VERSION

    assert OI_KNOWLEDGE_VERSION == "1.0"


def test_catalog_knowledge_version_unchanged():
    """2. The existing catalog version is untouched."""
    assert catalog.KNOWLEDGE_VERSION == "1.1"


def test_combined_provenance_resolves_to_1_1_plus_1_0():
    """3. The persisted provenance is built from the two constants (no literal)."""
    from app.domain.services.analysis_rules import (
        OI_KNOWLEDGE_VERSION,
        knowledge_provenance,
    )

    assert knowledge_provenance() == f"{catalog.KNOWLEDGE_VERSION}+{OI_KNOWLEDGE_VERSION}"
    assert knowledge_provenance() == "1.1+1.0"
