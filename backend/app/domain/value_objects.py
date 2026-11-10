"""Domain value objects for the hairstyle and grooming recommendation pipelines.

Pure Python (no FastAPI, no SQLAlchemy, no HTTP — BA-3). These mirror the
canonical wire DTOs (`FANSIVIBE_API_CONTRACT_V1.md` §4.2/§4.3 and
`hairstyle_mock_data.dart`, `grooming_mock_data.dart`) and are the typed
structure the decision engine produces and the API serializes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class HairstyleRecommendation:
    """A single hairstyle recommendation (the `top` pick or an `alternative`).

    Mirrors `HairstyleRecommendation` in `hairstyle_mock_data.dart` and the
    wire DTO: ``id`` is the stable catalog look code (PR-3).
    """

    id: str
    name: str
    description: str
    matchScore: float
    reasons: list[str]
    stylingTips: str
    maintenance: str
    bestFor: str


@dataclass(frozen=True)
class GroomingRecommendation:
    """A single grooming recommendation (the `top` pick or an `alternative`).

    Mirrors `GroomingRecommendation` in `grooming_mock_data.dart` and the
    wire DTO: ``id`` is the stable catalog look code (PR-3).
    """

    id: str
    name: str
    description: str
    matchScore: float
    reasons: list[str]
    stylingTips: str
    maintenance: str
    bestFor: str
    icon: Optional[str] = None


@dataclass(frozen=True)
class HairstylePreferences:
    """Bounded user preferences that influence the hairstyle decision.

    Hard constraints feed the Filtering stage; soft weights feed the Scoring
    stage (`DECISION_ENGINE_ARCHITECTURE.md` §6 — preferences may influence
    filtering + scoring, never fabricate inputs). Empty by default so the
    engine runs identically when no preferences are supplied.
    """

    excludedLookIds: frozenset[str] = frozenset()
    preferredLookIds: frozenset[str] = frozenset()


@dataclass(frozen=True)
class AppearanceProfile:
    """The face attributes the ranking was grounded on (run-level snapshot).

    ``sourceRunId`` is the producing run (provenance, R-1).
    """

    faceShape: str
    skinTone: str = ""
    bodyType: str = ""
    styleType: str = ""
    sourceRunId: str = ""


@dataclass(frozen=True)
class GarmentProfile:
    """Observed garment attributes from a real garment image (M11).

    Every attribute is either observed from the supplied pixels or None.
    None means "not clearly visible" — never a guess, never a default.
    ``category`` uses the canonical wardrobe category codes
    (tops/bottoms/outerwear/footwear/accessories) or None.
    Free-form attributes (subcategory/color/pattern/material/style/fit)
    are short observed strings or None; mapping them onto the controlled
    vocabularies happens at wardrobe-save time (user-confirmed, 422 on
    unknown codes) — not here. ``sourceRunId`` is the producing run
    (provenance, R-1).
    """

    category: str | None = None
    subcategory: str | None = None
    color: str | None = None
    pattern: str | None = None
    material: str | None = None
    style: str | None = None
    fit: str | None = None
    confidence: float = 0.0
    needs_review: bool = True
    sourceRunId: str = ""

    def to_snapshot(self) -> dict:
        return {
            "category": self.category,
            "subcategory": self.subcategory,
            "color": self.color,
            "pattern": self.pattern,
            "material": self.material,
            "style": self.style,
            "fit": self.fit,
            "confidence": self.confidence,
            "needs_review": self.needs_review,
            "sourceRunId": self.sourceRunId,
        }


@dataclass(frozen=True)
class HairstyleResult:
    """The immutable completed-run snapshot (TRX-5 `result`).

    ``confidence`` is the engine's derived run-level value in [0, 1]
    (`AI_DOMAIN_MODEL.md` §4.4: derived from the model run, never stored as
    truth); ``needs_more_data`` honestly signals a sparse grounding profile
    instead of fabricating one (AI-0).
    """

    appearance: AppearanceProfile
    top: HairstyleRecommendation
    alternatives: list[HairstyleRecommendation] = field(default_factory=list)
    confidence: float = 0.0
    needs_more_data: bool = False

    def to_snapshot(self) -> dict:
        return {
            "appearance": {
                "faceShape": self.appearance.faceShape,
                "skinTone": self.appearance.skinTone,
                "bodyType": self.appearance.bodyType,
                "styleType": self.appearance.styleType,
                "sourceRunId": self.appearance.sourceRunId,
            },
            "confidence": self.confidence,
            "needs_more_data": self.needs_more_data,
            "recommendations": {
                "top": _recommendation_to_snapshot(self.top),
                "alternatives": [_recommendation_to_snapshot(a) for a in self.alternatives],
            },
        }


def _recommendation_to_snapshot(rec: HairstyleRecommendation) -> dict:
    return {
        "id": rec.id,
        "name": rec.name,
        "description": rec.description,
        "matchScore": rec.matchScore,
        "reasons": list(rec.reasons),
        "stylingTips": rec.stylingTips,
        "maintenance": rec.maintenance,
        "bestFor": rec.bestFor,
    }


@dataclass(frozen=True)
class GroomingResult:
    """The immutable completed-run snapshot for grooming (TRX-5 `result`).

    ``confidence`` is the engine's derived run-level value in [0, 1]
    (`AI_DOMAIN_MODEL.md` §4.4: derived from the model run, never stored as
    truth); ``needs_more_data`` honestly signals a sparse grounding profile
    instead of fabricating one (AI-0).
    """

    appearance: AppearanceProfile
    top: GroomingRecommendation
    alternatives: list[GroomingRecommendation] = field(default_factory=list)
    confidence: float = 0.0
    needs_more_data: bool = False

    def to_snapshot(self) -> dict:
        return {
            "appearance": {
                "faceShape": self.appearance.faceShape,
                "skinTone": self.appearance.skinTone,
                "bodyType": self.appearance.bodyType,
                "styleType": self.appearance.styleType,
                "sourceRunId": self.appearance.sourceRunId,
            },
            "confidence": self.confidence,
            "needs_more_data": self.needs_more_data,
            "recommendations": {
                "top": _recommendation_to_grooming_snapshot(self.top),
                "alternatives": [
                    _recommendation_to_grooming_snapshot(a) for a in self.alternatives
                ],
            },
        }


def _recommendation_to_grooming_snapshot(rec: GroomingRecommendation) -> dict:
    return {
        "id": rec.id,
        "name": rec.name,
        "description": rec.description,
        "matchScore": rec.matchScore,
        "reasons": list(rec.reasons),
        "stylingTips": rec.stylingTips,
        "maintenance": rec.maintenance,
        "bestFor": rec.bestFor,
        "icon": rec.icon,
    }

###############################################################################
# Clothing Intelligence — domain value objects
# Mirrors the pattern from hairstyle/grooming result DTOs
# BA-3: application/domain layer depends on these only
###############################################################################


@dataclass(frozen=True)
class ColorCharacteristics:
    """Color characteristics of a wardrobe item.

    Deterministic / reference-derived fields only for the MVP.
    AI-inferred color harmonies are out of scope.
    """

    item_color: str  # the item's color code (e.g. 'charcoal', 'navy')
    is_neutral: bool = False  # true if black/white/grey/navy


@dataclass(frozen=True)
class MaterialCharacteristics:
    """Material characteristics of a wardrobe item.

    Reference-derived natural/synthetic classification for MVP.
    """

    material: str  # the item's material code (e.g. 'wool', 'cotton')
    is_natural: bool = False  # true if cotton/linen/wool/silk/leather/suede
    is_seasonal: bool = False  # derived seasonal mapping


@dataclass(frozen=True)
class SeasonSuitability:
    """Season suitability derived from item category + material.

    Baseline heuristics — not personalized certainty.
    """

    suitable_for_spring: bool = False
    suitable_for_summer: bool = False
    suitable_for_fall: bool = False
    suitable_for_winter: bool = False
    rationale: str = ""


@dataclass(frozen=True)
class Formality:
    """Formality classification based on item category.

    Baseline heuristics — not personalized certainty.
    """

    is_formal: bool = False
    is_casual: bool = True
    is_business: bool = False
    rationale: str = ""


@dataclass(frozen=True)
class StylingCharacteristic:
    """A styling characteristic for an item.

    Type determines how the label/rationale should be interpreted.
    """

    type: str  # e.g. 'favorite', 'seasonal', 'baseline', 'key-piece'
    label: str
    rationale: str


@dataclass(frozen=True)
class CompatibleCategory:
    """A category that complements the item's category.

    Rationale explains the pairing.
    """

    category: str  # e.g. 'tops', 'bottoms'
    rationale: str


@dataclass(frozen=True)
class OccasionContext:
    """An occasion this item is suitable for.

    Confidence reflects the degree of support from available data.
    """

    occasion: str  # e.g. 'casual', 'date', 'office', 'party', 'travel'
    confidence: float = 0.0
    rationale: str = ""


@dataclass(frozen=True)
class WardrobeContext:
    """The user's full wardrobe context surrounding a single item.

    Derived from LearningService.wardrobe — deterministic counts.
    """

    total_items: int
    favorite_count: int
    items_per_category: dict[str, int]
    style_score: int


@dataclass(frozen=True)
class StylingExplanation:
    """Human-readable explanation for the Clothing Intelligence result.

    Synthesized from deterministic + reference-derived fields only.
    """

    text: str


@dataclass(frozen=True)
class OutfitConflict:
    """A detected conflict in an outfit combination."""

    type: str  # e.g. 'color_conflict', 'seasonal_conflict', 'formality_mismatch'
    severity: str  # 'mild', 'moderate', 'severe'
    description: str


@dataclass(frozen=True)
class OutfitConfidenceLevel:
    """Maps a confidence float to a human-readable level."""

    level: str  # 'strong', 'reasonable', 'insufficient'
    range_start: float
    range_end: float


@dataclass(frozen=True)
class OutfitHarmony:
    """Color harmony assessment for an outfit."""

    is_harmonious: bool
    rationale: str
    accent_color: str


@dataclass(frozen=True)
class OutfitFormalityBalance:
    """Formality balance assessment for an outfit."""

    is_balanced: bool
    formality_desc: str
    items: list[str]


@dataclass(frozen=True)
class OutfitCoverage:
    """Category coverage assessment for an outfit."""

    covered_categories: list[str]
    missing_categories: list[str]
    coverage_ratio: float


@dataclass(frozen=True)
class OutfitIntelligence:
    """The minimum viable Outfit Intelligence result.

    Built on top of ClothingIntelligence from Steps 6A-6C, adding
    outfit-level assessment: category pairing, color harmony,
    seasonal consistency, formality balance, favorite boost,
    occasion handling, category coverage, sparse wardrobe handling,
    conflicts, confidence, confidence level, data availability,
    and explanation.
    """

    item_id: str
    item_category: str
    item_color: str
    item_is_favorite: bool

    wardrobe_context: "WardrobeContext"

    clothing_intelligence: ClothingIntelligence

    compatible_categories: list[CompatibleCategory]
    suitable_occasions: list[OccasionContext]

    color_harmony: OutfitHarmony
    formality_balance: OutfitFormalityBalance
    outfit_coverage: OutfitCoverage

    conflicts: list[OutfitConflict]

    confidence: float  # 0.0–1.0, derived from data availability + outfit rules
    confidence_level: OutfitConfidenceLevel

    data_availability: str  # 'full', 'partial', 'sparse'

    selected_item_ids: list[str]  # IDs of selected wardrobe items, from ClothingIntelligence

    outfit_composition: OutfitComposition  # selected items by category

    explanation: StylingExplanation


@dataclass(frozen=True)
class OutfitComposition:
    """Selected wardrobe items grouped by category."""

    top_ids: list[str]
    bottom_ids: list[str]
    outerwear_ids: list[str]
    footwear_ids: list[str]
    accessory_ids: list[str]


@dataclass(frozen=True)
class OutfitCandidate:
    """Internal outfit candidate (STEP 13.2) — deterministic selection contract.

    Not a wire object: no Pydantic mirror, no API surface. Buckets hold real
    wardrobe item IDs only (tuples preserve slot order; empty tuple = slot
    not filled — never placeholder or null IDs). ``score`` is the candidate
    score (0–100, see ``compose_candidate_score``), conceptually separate
    from final OutfitIntelligence confidence and from styleScore. Component
    fields record the separated signals (compatibility / preference /
    favorite) that composed the score.
    """

    top_ids: tuple[str, ...] = ()
    bottom_ids: tuple[str, ...] = ()
    outerwear_ids: tuple[str, ...] = ()
    footwear_ids: tuple[str, ...] = ()
    accessory_ids: tuple[str, ...] = ()
    compatibility: float = 0.0
    preference: float = 0.0
    favorite: float = 0.0
    feedback: float = 0.0
    wear: float = 0.0
    weather: float = 0.0
    score: float = 0.0


@dataclass(frozen=True)
class FeedbackContext:
    """Feedback and wear evidence for outfit candidate personalization (Phase 2 Step 1)."""

    liked_outfits: tuple[frozenset[str], ...] = ()
    disliked_outfits: tuple[frozenset[str], ...] = ()
    worn_combinations: tuple[frozenset[str], ...] = ()


@dataclass(frozen=True)
class ClothingIntelligence:
    """The minimum viable Clothing Intelligence result.

    Only fields justified by the existing product architecture and
    producible from current WardrobeItem + available user context
    without new DB columns, API changes, or AI provider calls.

    All fields are classified in Step 6B §3.
    """

    item_id: str
    item_category: str
    item_color: str
    item_is_favorite: bool

    wardrobe_context: WardrobeContext

    color_characteristics: ColorCharacteristics
    material_characteristics: MaterialCharacteristics
    season_suitability: SeasonSuitability
    formality: Formality

    compatible_categories: list[CompatibleCategory]
    suitable_occasions: list[OccasionContext]

    confidence: float  # 0.0–1.0, derived from data availability
    explanation: StylingExplanation


###############################################################################
# Weather Context — domain value objects (Stage 2 P1-3)
# BA-3: application/domain layer depends on these normalized objects only
###############################################################################


@dataclass(frozen=True)
class WeatherLocation:
    """Coarse geographic location for weather retrieval (privacy-preserving).

    In accordance with Phase 0 audit §6:
    - Coordinates are coarse (rounded to at most 2 decimal places, ~1.1km resolution).
    - Precise GPS coordinates (meter-level) are never collected or stored.
    - Valid latitude range: -90.0 to +90.0.
    - Valid longitude range: -180.0 to +180.0.
    """

    latitude: float
    longitude: float
    city: Optional[str] = None
    country: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.latitude, (int, float)) or isinstance(
            self.latitude, bool
        ):
            raise ValueError(
                f"Latitude must be a number, got {type(self.latitude).__name__}"
            )
        if not isinstance(self.longitude, (int, float)) or isinstance(
            self.longitude, bool
        ):
            raise ValueError(
                f"Longitude must be a number, got {type(self.longitude).__name__}"
            )
        lat = float(self.latitude)
        lon = float(self.longitude)
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(
                f"Latitude must be between -90.0 and 90.0, got {lat}"
            )
        if not (-180.0 <= lon <= 180.0):
            raise ValueError(
                f"Longitude must be between -180.0 and 180.0, got {lon}"
            )

        # Enforce coarse resolution: round to 2 decimal places (~1.1km)
        object.__setattr__(self, "latitude", round(lat, 2))
        object.__setattr__(self, "longitude", round(lon, 2))
        if self.city is not None:
            object.__setattr__(self, "city", str(self.city).strip() or None)
        if self.country is not None:
            object.__setattr__(self, "country", str(self.country).strip() or None)


@dataclass(frozen=True)
class WeatherContext:
    """Application-owned normalized weather representation.

    Normalized fields reflect the requirements of Phase 0 audit §5:
    - temperature_c: dry-bulb ambient temperature in degrees Celsius.
    - apparent_temperature_c: perceived "feels-like" temperature in degrees Celsius.
    - weather_code: WMO weather interpretation code (0-99).
    - condition_code: semantic category code ('clear', 'partly_cloudy', 'cloudy',
      'fog', 'drizzle', 'rain', 'snow', 'thunderstorm', 'unknown').
    - condition_text: human-readable weather condition description.
    - forecast_timestamp: datetime for which the forecast applies.
    - retrieved_at: datetime when the data was retrieved/normalized.
    - precipitation_probability: estimated chance of precipitation (0.0 to 100.0) or None.
    - precipitation_mm: precipitation amount in millimeters (>= 0.0) or None.
    - relative_humidity_pct: relative humidity percentage (0.0 to 100.0) or None.
    - wind_speed_kmh: wind speed in kilometers per hour (>= 0.0) or None.
    - is_day: optional boolean indicating daylight vs night.
    - location: optional coarse WeatherLocation context.
    """

    temperature_c: float
    apparent_temperature_c: float
    weather_code: int
    condition_code: str
    condition_text: str
    forecast_timestamp: datetime
    retrieved_at: datetime
    precipitation_probability: Optional[float] = None
    precipitation_mm: Optional[float] = None
    relative_humidity_pct: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    is_day: Optional[bool] = None
    location: Optional[WeatherLocation] = None

    def __post_init__(self) -> None:
        if not isinstance(self.temperature_c, (int, float)) or isinstance(
            self.temperature_c, bool
        ):
            raise ValueError(
                f"temperature_c must be numeric, got {type(self.temperature_c).__name__}"
            )
        temp_val = float(self.temperature_c)
        if not (-90.0 <= temp_val <= 70.0):
            raise ValueError(
                f"temperature_c outside reasonable terrestrial range (-90 to 70°C): {temp_val}"
            )
        object.__setattr__(self, "temperature_c", round(temp_val, 1))

        if not isinstance(
            self.apparent_temperature_c, (int, float)
        ) or isinstance(self.apparent_temperature_c, bool):
            raise ValueError(
                f"apparent_temperature_c must be numeric, got {type(self.apparent_temperature_c).__name__}"
            )
        app_temp_val = float(self.apparent_temperature_c)
        if not (-100.0 <= app_temp_val <= 80.0):
            raise ValueError(
                f"apparent_temperature_c outside reasonable range (-100 to 80°C): {app_temp_val}"
            )
        object.__setattr__(self, "apparent_temperature_c", round(app_temp_val, 1))

        if not isinstance(self.weather_code, int) or isinstance(
            self.weather_code, bool
        ):
            raise ValueError(
                f"weather_code must be an integer, got {type(self.weather_code).__name__}"
            )
        if not (0 <= self.weather_code <= 99):
            raise ValueError(
                f"weather_code must be in WMO range 0-99, got {self.weather_code}"
            )

        if not isinstance(self.condition_code, str) or not self.condition_code.strip():
            raise ValueError("condition_code must be a non-empty string")
        object.__setattr__(
            self, "condition_code", self.condition_code.strip().lower()
        )

        if not isinstance(self.condition_text, str) or not self.condition_text.strip():
            raise ValueError("condition_text must be a non-empty string")
        object.__setattr__(self, "condition_text", self.condition_text.strip())

        if not isinstance(self.forecast_timestamp, datetime):
            raise ValueError("forecast_timestamp must be a datetime instance")
        if not isinstance(self.retrieved_at, datetime):
            raise ValueError("retrieved_at must be a datetime instance")

        if self.precipitation_probability is not None:
            if not isinstance(
                self.precipitation_probability, (int, float)
            ) or isinstance(self.precipitation_probability, bool):
                raise ValueError("precipitation_probability must be numeric")
            p_val = float(self.precipitation_probability)
            if not (0.0 <= p_val <= 100.0):
                raise ValueError(
                    f"precipitation_probability must be between 0.0 and 100.0, got {p_val}"
                )
            object.__setattr__(
                self, "precipitation_probability", round(p_val, 1)
            )

        if self.precipitation_mm is not None:
            if not isinstance(self.precipitation_mm, (int, float)) or isinstance(
                self.precipitation_mm, bool
            ):
                raise ValueError("precipitation_mm must be numeric")
            mm_val = float(self.precipitation_mm)
            if mm_val < 0.0:
                raise ValueError(
                    f"precipitation_mm cannot be negative, got {mm_val}"
                )
            object.__setattr__(self, "precipitation_mm", round(mm_val, 2))

        if self.relative_humidity_pct is not None:
            if not isinstance(
                self.relative_humidity_pct, (int, float)
            ) or isinstance(self.relative_humidity_pct, bool):
                raise ValueError("relative_humidity_pct must be numeric")
            h_val = float(self.relative_humidity_pct)
            if not (0.0 <= h_val <= 100.0):
                raise ValueError(
                    f"relative_humidity_pct must be between 0.0 and 100.0, got {h_val}"
                )
            object.__setattr__(self, "relative_humidity_pct", round(h_val, 1))

        if self.wind_speed_kmh is not None:
            if not isinstance(self.wind_speed_kmh, (int, float)) or isinstance(
                self.wind_speed_kmh, bool
            ):
                raise ValueError("wind_speed_kmh must be numeric")
            w_val = float(self.wind_speed_kmh)
            if w_val < 0.0:
                raise ValueError(
                    f"wind_speed_kmh cannot be negative, got {w_val}"
                )
            object.__setattr__(self, "wind_speed_kmh", round(w_val, 1))

        if self.is_day is not None and not isinstance(self.is_day, bool):
            raise ValueError(
                f"is_day must be a boolean or None, got {type(self.is_day).__name__}"
            )

        if self.location is not None and not isinstance(
            self.location, WeatherLocation
        ):
            raise ValueError(
                f"location must be a WeatherLocation instance or None, got {type(self.location).__name__}"
            )

    @property
    def temperature_f(self) -> float:
        """Temperature converted to Fahrenheit."""
        return round((self.temperature_c * 9.0 / 5.0) + 32.0, 1)

    @property
    def apparent_temperature_f(self) -> float:
        """Apparent temperature converted to Fahrenheit."""
        return round((self.apparent_temperature_c * 9.0 / 5.0) + 32.0, 1)

    @property
    def is_raining(self) -> bool:
        """Whether current conditions indicate active or imminent rain."""
        rain_codes = {
            51, 53, 55, 56, 57,  # Drizzle
            61, 63, 65, 66, 67,  # Rain
            80, 81, 82,          # Rain showers
            95, 96, 99,          # Thunderstorms
        }
        if self.weather_code in rain_codes:
            return True
        if self.precipitation_mm is not None and self.precipitation_mm > 0.1:
            return True
        if (
            self.precipitation_probability is not None
            and self.precipitation_probability >= 50.0
        ):
            return True
        return False
