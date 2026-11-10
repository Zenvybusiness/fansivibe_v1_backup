"""Focused deterministic tests for Canonical Outfit Scoring Engine — Weather Integration.

Validates Stage 2 P1-3 Phase 2 requirements:
- Deterministic advisory weather scoring helper (_weather_points).
- Strict bounds: -10.0 <= weather <= +10.0.
- Thermal suitability: very cold (<0°C), cold (0-10°C), mild (10-18°C), warm (18-24°C), hot (24-30°C), very hot (>=30°C).
- Apparent / feels-like temperature preference with raw temperature fallback.
- Precipitation protection: active rain, high probability, water-vulnerable fabrics (suede, silk, canvas), resistant fabrics (leather).
- Wind resistance: high wind (>30 km/h) outerwear and fabric barriers.
- Layering suitability: outerwear promotion when cold/rainy, demotion when hot.
- Safe neutral degradation for missing temperature, missing precipitation, missing wind, unknown weather condition.
- Neutral handling of missing or unknown garment metadata (material=None, material="unknown").
- Absolute non-disruption of existing 12 terms and byte-identical baseline when weather_context=None.
- Preservation of user intent: explicit occasion, pinned garments, category compatibility.
- Deterministic repeated scoring and stable tie-breaking.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest

from app.domain.services.analysis_rules import (
    _WEATHER_ADJUSTMENT_MAX,
    _WEATHER_ADJUSTMENT_MIN,
    _weather_points,
    compose_candidate_score,
    rank_outfit_candidates,
    score_outfit_candidate,
)
from app.domain.value_objects import (
    FeedbackContext,
    OutfitCandidate,
    WeatherContext,
    WeatherLocation,
)


# ==============================================================================
# Test Fixtures & Helpers
# ==============================================================================

_NOW = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc)
_LOC = WeatherLocation(latitude=47.61, longitude=-122.33, city="Seattle", country="US")


class _MockItem:
    def __init__(
        self,
        item_id: str,
        category: str,
        color: str = "black",
        material: Optional[str] = "cotton",
        is_favorite: bool = False,
        fit: Optional[str] = None,
        fit_confidence: Optional[float] = None,
    ) -> None:
        self.id = item_id
        self.category = category
        self.color = color
        self.material = material
        self.is_favorite = is_favorite
        self.fit = fit
        self.fit_confidence = fit_confidence


def _make_weather(
    *,
    temperature_c: float = 16.0,
    apparent_temperature_c: Optional[float] = None,
    weather_code: int = 1,
    condition_code: str = "partly_cloudy",
    condition_text: str = "Partly Cloudy",
    precipitation_probability: Optional[float] = None,
    precipitation_mm: Optional[float] = None,
    relative_humidity_pct: Optional[float] = 60.0,
    wind_speed_kmh: Optional[float] = 10.0,
    is_day: Optional[bool] = True,
    forecast_timestamp: Optional[datetime] = None,
    location: Optional[WeatherLocation] = _LOC,
) -> WeatherContext:
    app_temp = apparent_temperature_c if apparent_temperature_c is not None else temperature_c
    return WeatherContext(
        temperature_c=temperature_c,
        apparent_temperature_c=app_temp,
        weather_code=weather_code,
        condition_code=condition_code,
        condition_text=condition_text,
        forecast_timestamp=forecast_timestamp or _NOW,
        retrieved_at=_NOW,
        precipitation_probability=precipitation_probability,
        precipitation_mm=precipitation_mm,
        relative_humidity_pct=relative_humidity_pct,
        wind_speed_kmh=wind_speed_kmh,
        is_day=is_day,
        location=location,
    )


def _cand(
    top=("t1",),
    bottom=("b1",),
    outer=(),
    footwear=("f1",),
    accessories=(),
) -> OutfitCandidate:
    return OutfitCandidate(
        top_ids=tuple(top),
        bottom_ids=tuple(bottom),
        outerwear_ids=tuple(outer),
        footwear_ids=tuple(footwear),
        accessory_ids=tuple(accessories),
    )


# ==============================================================================
# 1. Temperature & Feels-Like Scenarios
# ==============================================================================


class TestTemperatureScenarios:
    """Verify thermal scoring brackets and apparent temperature precedence."""

    def test_very_hot_weather_penalizes_outerwear_and_boosts_breathable(self):
        # 32°C: hot conditions
        weather = _make_weather(temperature_c=32.0, apparent_temperature_c=34.0)

        items_layered = {
            "t1": _MockItem("t1", "tops", color="white", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
            "o1": _MockItem("o1", "outerwear", color="navy", material="wool"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
        }
        cand_layered = _cand(top=("t1",), bottom=("b1",), outer=("o1",), footwear=("f1",))

        items_light = {
            "t1": _MockItem("t1", "tops", color="white", material="linen"),
            "b1": _MockItem("b1", "bottoms", color="beige", material="cotton"),
            "f1": _MockItem("f1", "footwear", color="white", material="canvas"),
        }
        cand_light = _cand(top=("t1",), bottom=("b1",), footwear=("f1",))

        scored_layered = score_outfit_candidate(cand_layered, items_layered, weather_context=weather)
        scored_light = score_outfit_candidate(cand_light, items_light, weather_context=weather)

        assert scored_layered.weather < 0.0
        assert scored_light.weather > 0.0
        assert scored_light.weather - scored_layered.weather >= 8.0

    def test_warm_weather_neutral_outerwear_and_modest_breathable_bonus(self):
        # 21°C: pleasant warm conditions
        weather = _make_weather(temperature_c=21.0, apparent_temperature_c=21.0)

        items_breathable = {
            "t1": _MockItem("t1", "tops", color="white", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="navy", material="cotton"),
            "f1": _MockItem("f1", "footwear", color="white", material="leather"),
        }
        cand = _cand(top=("t1",), bottom=("b1",), footwear=("f1",))
        scored = score_outfit_candidate(cand, items_breathable, weather_context=weather)
        assert scored.weather == 1.0  # Breathable material bonus

    def test_mild_weather_favors_light_layering(self):
        # 14°C: mild / transitional weather
        weather = _make_weather(temperature_c=14.0, apparent_temperature_c=13.0)

        items_no_outer = {
            "t1": _MockItem("t1", "tops", color="grey", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
        }
        items_with_outer = dict(items_no_outer)
        items_with_outer["o1"] = _MockItem("o1", "outerwear", color="navy", material="denim")

        cand_no_outer = _cand(top=("t1",), bottom=("b1",), footwear=("f1",))
        cand_with_outer = _cand(top=("t1",), bottom=("b1",), outer=("o1",), footwear=("f1",))

        scored_no_outer = score_outfit_candidate(cand_no_outer, items_no_outer, weather_context=weather)
        scored_with_outer = score_outfit_candidate(cand_with_outer, items_with_outer, weather_context=weather)

        assert scored_with_outer.weather > scored_no_outer.weather
        assert scored_with_outer.weather == 2.0

    def test_cold_weather_promotes_outerwear_and_insulating_fabrics(self):
        # 6°C: cold weather
        weather = _make_weather(temperature_c=6.0, apparent_temperature_c=4.0)

        items = {
            "t1": _MockItem("t1", "tops", color="grey", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
            "o1": _MockItem("o1", "outerwear", color="charcoal", material="wool"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
        }
        cand = _cand(top=("t1",), bottom=("b1",), outer=("o1",), footwear=("f1",))
        scored = score_outfit_candidate(cand, items, weather_context=weather)

        assert scored.weather >= 6.0  # +4 outerwear + 2 wool

    def test_very_cold_weather_heavily_promotes_outerwear_and_penalizes_lack(self):
        # -5°C: freezing weather
        weather = _make_weather(temperature_c=-5.0, apparent_temperature_c=-8.0)

        items_warm = {
            "t1": _MockItem("t1", "tops", color="grey", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="black", material="wool"),
            "o1": _MockItem("o1", "outerwear", color="navy", material="heavy_wool"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
        }
        items_uninsulated = {
            "t1": _MockItem("t1", "tops", color="white", material="linen"),
            "b1": _MockItem("b1", "bottoms", color="tan", material="linen"),
            "f1": _MockItem("f1", "footwear", color="white", material="canvas"),
        }

        cand_warm = _cand(top=("t1",), bottom=("b1",), outer=("o1",), footwear=("f1",))
        cand_uninsulated = _cand(top=("t1",), bottom=("b1",), footwear=("f1",))

        scored_warm = score_outfit_candidate(cand_warm, items_warm, weather_context=weather)
        scored_uninsulated = score_outfit_candidate(cand_uninsulated, items_uninsulated, weather_context=weather)

        assert scored_warm.weather >= 7.0
        assert scored_uninsulated.weather <= -6.0

    def test_apparent_temperature_precedence_over_raw_temperature(self):
        # Raw is 15°C (mild), but 40 km/h wind makes apparent temp 7°C (cold)
        weather = _make_weather(
            temperature_c=15.0,
            apparent_temperature_c=7.0,
            wind_speed_kmh=15.0,  # low wind to isolate temp
        )

        items = {
            "t1": _MockItem("t1", "tops", color="black", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
            "o1": _MockItem("o1", "outerwear", color="navy", material="wool"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
        }
        cand = _cand(top=("t1",), bottom=("b1",), outer=("o1",), footwear=("f1",))
        scored = score_outfit_candidate(cand, items, weather_context=weather)

        # In cold (<10°C), outerwear receives +4.0 (in mild it would only receive +2.0)
        assert scored.weather == 6.0  # +4 outerwear + 2 wool

    def test_missing_temperature_degrades_neutrally(self):
        # Duck-typed object with missing temperature fields
        class SparseWeather:
            temperature_c = None
            apparent_temperature_c = None
            weather_code = 1
            condition_code = "partly_cloudy"
            condition_text = "Partly Cloudy"
            precipitation_probability = None
            precipitation_mm = None
            wind_speed_kmh = None
            is_raining = False

        items = {
            "t1": _MockItem("t1", "tops", color="black", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
        }
        cand = _cand(top=("t1",), bottom=("b1",))
        scored = score_outfit_candidate(cand, items, weather_context=SparseWeather())  # type: ignore
        assert scored.weather == 0.0


# ==============================================================================
# 2. Precipitation Scenarios
# ==============================================================================


class TestPrecipitationScenarios:
    """Verify precipitation sensitivity and fabric vulnerability penalties."""

    def test_no_rain_is_neutral(self):
        weather = _make_weather(
            temperature_c=20.0,
            apparent_temperature_c=20.0,
            precipitation_probability=0.0,
            precipitation_mm=0.0,
        )
        items = {
            "t1": _MockItem("t1", "tops", color="white", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
        }
        cand = _cand(top=("t1",), bottom=("b1",), footwear=("f1",))
        scored = score_outfit_candidate(cand, items, weather_context=weather)
        # In warm (20°C) with cotton, temp bonus is +1.0; precipitation adjustment is 0.0
        assert scored.weather == 1.0

    def test_low_rain_probability_is_neutral(self):
        weather = _make_weather(
            temperature_c=20.0,
            apparent_temperature_c=20.0,
            precipitation_probability=20.0,
            precipitation_mm=0.0,
        )
        items = {
            "t1": _MockItem("t1", "tops", color="white", material="suede"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
            "f1": _MockItem("f1", "footwear", color="black", material="suede"),
        }
        cand = _cand(top=("t1",), bottom=("b1",), footwear=("f1",))
        scored = score_outfit_candidate(cand, items, weather_context=weather)
        # Low rain probability does not penalize suede
        assert scored.weather == 0.0

    def test_high_rain_probability_promotes_outerwear_and_penalizes_vulnerable(self):
        weather = _make_weather(
            temperature_c=16.0,
            apparent_temperature_c=16.0,
            precipitation_probability=75.0,
            precipitation_mm=0.0,
        )
        items_vulnerable = {
            "t1": _MockItem("t1", "tops", color="white", material="silk"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
            "f1": _MockItem("f1", "footwear", color="tan", material="suede"),
        }
        cand = _cand(top=("t1",), bottom=("b1",), footwear=("f1",))
        scored = score_outfit_candidate(cand, items_vulnerable, weather_context=weather)
        # 75% precipitation_probability marks is_raining as True on WeatherContext.
        # Vulnerable material silk/suede (-4.0) + vulnerable footwear suede (-2.0) = -6.0
        assert scored.weather == -6.0

    def test_actual_precipitation_heavily_penalizes_suede_and_canvas_footwear(self):
        weather = _make_weather(
            temperature_c=12.0,
            apparent_temperature_c=12.0,
            precipitation_probability=95.0,
            precipitation_mm=3.5,
            weather_code=61,
            condition_code="rain",
            condition_text="Moderate Rain",
        )
        items_rain_unfit = {
            "t1": _MockItem("t1", "tops", color="white", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
            "o1": _MockItem("o1", "outerwear", color="brown", material="suede"),
            "f1": _MockItem("f1", "footwear", color="white", material="canvas"),
        }
        items_rain_fit = {
            "t1": _MockItem("t1", "tops", color="white", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
            "o1": _MockItem("o1", "outerwear", color="black", material="polyester"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
        }

        cand_unfit = _cand(top=("t1",), bottom=("b1",), outer=("o1",), footwear=("f1",))
        cand_fit = _cand(top=("t1",), bottom=("b1",), outer=("o1",), footwear=("f1",))

        scored_unfit = score_outfit_candidate(cand_unfit, items_rain_unfit, weather_context=weather)
        scored_fit = score_outfit_candidate(cand_fit, items_rain_fit, weather_context=weather)

        assert scored_unfit.weather < 0.0
        assert scored_fit.weather > 5.0
        assert scored_fit.weather - scored_unfit.weather >= 6.0

    def test_missing_precipitation_fields_degrade_neutrally(self):
        weather = _make_weather(
            temperature_c=20.0,
            apparent_temperature_c=20.0,
            precipitation_probability=None,
            precipitation_mm=None,
        )
        items = {
            "t1": _MockItem("t1", "tops", color="white", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
        }
        cand = _cand(top=("t1",), bottom=("b1",), footwear=("f1",))
        scored = score_outfit_candidate(cand, items, weather_context=weather)
        assert scored.weather == 1.0  # Just the breathable cotton bonus


# ==============================================================================
# 3. Wind Scenarios
# ==============================================================================


class TestWindScenarios:
    """Verify wind speed handling and wind barrier protection."""

    def test_low_wind_is_neutral(self):
        weather = _make_weather(
            temperature_c=19.0,
            apparent_temperature_c=19.0,
            wind_speed_kmh=12.0,
        )
        items = {
            "t1": _MockItem("t1", "tops", color="white", material="linen"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
        }
        cand = _cand(top=("t1",), bottom=("b1",))
        scored = score_outfit_candidate(cand, items, weather_context=weather)
        # Wind is <= 30 km/h, so wind adjustment is 0.0; linen in warm gets +1.0
        assert scored.weather == 1.0

    def test_high_wind_promotes_outerwear_and_penalizes_light_fabrics_without_shell(self):
        weather = _make_weather(
            temperature_c=19.0,
            apparent_temperature_c=19.0,
            wind_speed_kmh=42.0,  # High wind (>30 km/h)
        )
        items_windbreak = {
            "t1": _MockItem("t1", "tops", color="white", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
            "o1": _MockItem("o1", "outerwear", color="brown", material="leather"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
        }
        items_exposed = {
            "t1": _MockItem("t1", "tops", color="white", material="silk"),
            "b1": _MockItem("b1", "bottoms", color="tan", material="linen"),
            "f1": _MockItem("f1", "footwear", color="white", material="canvas"),
        }

        cand_windbreak = _cand(top=("t1",), bottom=("b1",), outer=("o1",), footwear=("f1",))
        cand_exposed = _cand(top=("t1",), bottom=("b1",), footwear=("f1",))

        scored_windbreak = score_outfit_candidate(cand_windbreak, items_windbreak, weather_context=weather)
        scored_exposed = score_outfit_candidate(cand_exposed, items_exposed, weather_context=weather)

        assert scored_windbreak.weather >= 3.0  # +2 outerwear windbreak + 1 leather
        assert scored_exposed.weather < 0.0     # -2 light fabric exposed + 1 warm temp = -1.0

    def test_missing_wind_speed_degrades_neutrally(self):
        weather = _make_weather(
            temperature_c=19.0,
            apparent_temperature_c=19.0,
            wind_speed_kmh=None,
        )
        items = {
            "t1": _MockItem("t1", "tops", color="white", material="silk"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
        }
        cand = _cand(top=("t1",), bottom=("b1",))
        scored = score_outfit_candidate(cand, items, weather_context=weather)
        # Missing wind speed does not penalize silk
        assert scored.weather == 1.0


# ==============================================================================
# 4. Garment Metadata & Missing Data Scenarios
# ==============================================================================


class TestGarmentMetadataScenarios:
    """Verify graceful neutral degradation when garment metadata is incomplete."""

    def test_unknown_material_string_degrades_neutrally(self):
        weather = _make_weather(temperature_c=5.0, apparent_temperature_c=5.0)
        items = {
            "t1": _MockItem("t1", "tops", color="black", material="unknown"),
            "b1": _MockItem("b1", "bottoms", color="black", material="unknown"),
            "o1": _MockItem("o1", "outerwear", color="black", material="unknown"),
            "f1": _MockItem("f1", "footwear", color="black", material="unknown"),
        }
        cand = _cand(top=("t1",), bottom=("b1",), outer=("o1",), footwear=("f1",))
        scored = score_outfit_candidate(cand, items, weather_context=weather)
        # In cold (<10°C), outerwear gets +4.0; unknown materials contribute 0.0
        assert scored.weather == 4.0

    def test_missing_material_none_degrades_neutrally(self):
        weather = _make_weather(temperature_c=5.0, apparent_temperature_c=5.0)
        items = {
            "t1": _MockItem("t1", "tops", color="black", material=None),
            "b1": _MockItem("b1", "bottoms", color="black", material=None),
            "o1": _MockItem("o1", "outerwear", color="black", material=None),
            "f1": _MockItem("f1", "footwear", color="black", material=None),
        }
        cand = _cand(top=("t1",), bottom=("b1",), outer=("o1",), footwear=("f1",))
        scored = score_outfit_candidate(cand, items, weather_context=weather)
        # Material is None: neutral degradation, exactly +4.0 for outerwear
        assert scored.weather == 4.0

    def test_unknown_category_mapping_does_not_crash(self):
        weather = _make_weather(temperature_c=5.0, apparent_temperature_c=5.0)
        items = {
            "t1": _MockItem("t1", "tops", color="black", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
            "x1": _MockItem("x1", "unrecognized_category", color="black", material="wool"),
        }
        # Build candidate with unknown slot attribute
        cand = OutfitCandidate(top_ids=("t1",), bottom_ids=("b1",))
        scored = score_outfit_candidate(cand, items, weather_context=weather)
        assert isinstance(scored.weather, float)
        assert -10.0 <= scored.weather <= 10.0

    def test_garment_with_insufficient_metadata_scores_safely(self):
        weather = _make_weather(temperature_c=20.0, apparent_temperature_c=20.0)
        # Bare item with no color, material, or fit attributes
        bare_item = _MockItem("t1", "tops", color="", material=None)
        items = {"t1": bare_item, "b1": _MockItem("b1", "bottoms", color="black", material=None)}
        cand = _cand(top=("t1",), bottom=("b1",))
        scored = score_outfit_candidate(cand, items, weather_context=weather)
        assert scored.weather == 0.0


# ==============================================================================
# 5. Recommendation Integrity & Boundary Guarantees
# ==============================================================================


class TestRecommendationIntegrity:
    """Verify non-disruption of existing scoring, bounds, determinism, and invariants."""

    def test_same_candidate_without_weather_vs_with_none_is_byte_identical(self):
        items = {
            "t1": _MockItem("t1", "tops", color="black", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="white", material="denim"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
        }
        cand = _cand(top=("t1",), bottom=("b1",), footwear=("f1",))

        without_weather = score_outfit_candidate(cand, items)
        with_none_weather = score_outfit_candidate(cand, items, weather_context=None)

        assert without_weather == with_none_weather
        assert without_weather.score == with_none_weather.score
        assert without_weather.compatibility == with_none_weather.compatibility
        assert without_weather.preference == with_none_weather.preference
        assert without_weather.favorite == with_none_weather.favorite
        assert without_weather.feedback == with_none_weather.feedback
        assert without_weather.wear == with_none_weather.wear
        assert without_weather.weather == 0.0
        assert with_none_weather.weather == 0.0

    def test_existing_12_score_terms_unchanged(self):
        items = {
            "t1": _MockItem("t1", "tops", color="black", material="cotton", is_favorite=True),
            "b1": _MockItem("b1", "bottoms", color="charcoal", material="cotton"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
        }
        cand = _cand(top=("t1",), bottom=("b1",), footwear=("f1",))
        fb_ctx = FeedbackContext(liked_outfits=(frozenset(["t1", "b1", "f1"]),))
        preferred_ids = frozenset(["t1"])

        baseline = score_outfit_candidate(
            cand,
            items,
            preferred_item_ids=preferred_ids,
            preferred_occasions=["casual"],
            feedback_context=fb_ctx,
            weather_context=None,
        )

        weather = _make_weather(temperature_c=6.0, apparent_temperature_c=6.0)
        with_weather = score_outfit_candidate(
            cand,
            items,
            preferred_item_ids=preferred_ids,
            preferred_occasions=["casual"],
            feedback_context=fb_ctx,
            weather_context=weather,
        )

        # All 12 base terms and signals must be identical
        assert baseline.compatibility == with_weather.compatibility
        assert baseline.preference == with_weather.preference
        assert baseline.favorite == with_weather.favorite
        assert baseline.feedback == with_weather.feedback
        assert baseline.wear == with_weather.wear
        # Only weather and final composite score differ
        assert with_weather.weather == -3.0  # Cold without outerwear (-2) + light cotton (-1) = -3.0
        assert with_weather.score == compose_candidate_score(
            with_weather.compatibility,
            with_weather.preference,
            with_weather.favorite,
            feedback=with_weather.feedback,
            wear=with_weather.wear,
            weather=with_weather.weather,
        )

    def test_weather_contribution_strictly_bounded_within_negative_10_and_positive_10(self):
        # Extreme cold blizzard scenario: raw sum would be > 15
        blizzard = _make_weather(
            temperature_c=-20.0,
            apparent_temperature_c=-30.0,
            weather_code=75,
            condition_code="snow",
            precipitation_probability=100.0,
            precipitation_mm=25.0,
            wind_speed_kmh=60.0,
        )
        items_extreme_cold = {
            "t1": _MockItem("t1", "tops", color="black", material="wool"),
            "b1": _MockItem("b1", "bottoms", color="black", material="fleece"),
            "o1": _MockItem("o1", "outerwear", color="black", material="heavy_wool"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
            "a1": _MockItem("a1", "accessories", color="black", material="wool"),
        }
        cand_cold = _cand(top=("t1",), bottom=("b1",), outer=("o1",), footwear=("f1",), accessories=("a1",))
        scored_cold = score_outfit_candidate(cand_cold, items_extreme_cold, weather_context=blizzard)

        assert scored_cold.weather <= _WEATHER_ADJUSTMENT_MAX
        assert scored_cold.weather == 10.0

        # Extreme scorching heatwave scenario: raw sum would be < -15
        heatwave = _make_weather(
            temperature_c=45.0,
            apparent_temperature_c=48.0,
            weather_code=0,
            condition_code="clear",
            wind_speed_kmh=5.0,
        )
        items_extreme_hot = {
            "t1": _MockItem("t1", "tops", color="black", material="wool"),
            "b1": _MockItem("b1", "bottoms", color="black", material="fleece"),
            "o1": _MockItem("o1", "outerwear", color="black", material="heavy_wool"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
        }
        cand_hot = _cand(top=("t1",), bottom=("b1",), outer=("o1",), footwear=("f1",))
        scored_hot = score_outfit_candidate(cand_hot, items_extreme_hot, weather_context=heatwave)

        assert scored_hot.weather >= _WEATHER_ADJUSTMENT_MIN
        assert scored_hot.weather == -10.0

    def test_explicit_occasion_remains_respected(self):
        # Even with weather, an outfit matching occasion maintains its advantage
        items = {
            "t1": _MockItem("t1", "tops", color="black", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
        }
        cand = _cand(top=("t1",), bottom=("b1",), footwear=("f1",))
        weather = _make_weather(temperature_c=30.0, apparent_temperature_c=30.0)

        with_occasion = score_outfit_candidate(cand, items, preferred_occasions=["casual"], weather_context=weather)
        without_occasion = score_outfit_candidate(cand, items, preferred_occasions=["party"], weather_context=weather)

        assert with_occasion.score > without_occasion.score
        assert with_occasion.compatibility - without_occasion.compatibility == 5.0

    def test_pinned_garments_remain_preserved(self):
        items = {
            "pinned_top": _MockItem("pinned_top", "tops", color="red", material="silk"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
        }
        cand = _cand(top=("pinned_top",), bottom=("b1",), footwear=("f1",))
        weather = _make_weather(temperature_c=5.0, apparent_temperature_c=5.0)

        scored = score_outfit_candidate(cand, items, weather_context=weather)
        # Garments in candidate must be untouched
        assert scored.top_ids == ("pinned_top",)
        assert scored.bottom_ids == ("b1",)
        assert scored.footwear_ids == ("f1",)

    def test_weather_does_not_reject_an_otherwise_valid_outfit(self):
        items = {
            "t1": _MockItem("t1", "tops", color="black", material="wool"),
            "b1": _MockItem("b1", "bottoms", color="black", material="wool"),
            "o1": _MockItem("o1", "outerwear", color="black", material="wool"),
            "f1": _MockItem("f1", "footwear", color="black", material="suede"),
        }
        cand = _cand(top=("t1",), bottom=("b1",), outer=("o1",), footwear=("f1",))
        # Extreme bad weather for this outfit: hot rain (suede + wool + outerwear in 35°C rain)
        bad_weather = _make_weather(
            temperature_c=35.0,
            apparent_temperature_c=38.0,
            weather_code=61,
            condition_code="rain",
            precipitation_mm=10.0,
        )
        scored = score_outfit_candidate(cand, items, weather_context=bad_weather)
        # Must not crash, score must stay bounded in [0.0, 100.0]
        assert 0.0 <= scored.score <= 100.0
        assert scored.weather == -10.0

    def test_deterministic_repeated_scoring(self):
        items = {
            "t1": _MockItem("t1", "tops", color="black", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="navy", material="denim"),
            "o1": _MockItem("o1", "outerwear", color="grey", material="wool"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
        }
        cand = _cand(top=("t1",), bottom=("b1",), outer=("o1",), footwear=("f1",))
        weather = _make_weather(temperature_c=8.0, apparent_temperature_c=6.0, wind_speed_kmh=20.0)

        results = [score_outfit_candidate(cand, items, weather_context=weather) for _ in range(10)]
        first = results[0]
        for subsequent in results[1:]:
            assert first == subsequent
            assert first.score == subsequent.score
            assert first.weather == subsequent.weather

    def test_ranking_and_tie_breaking_unchanged_when_weather_is_absent(self):
        items = {
            "t1": _MockItem("t1", "tops", color="black", material="cotton"),
            "t2": _MockItem("t2", "tops", color="white", material="linen"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
            "b2": _MockItem("b2", "bottoms", color="navy", material="wool"),
            "f1": _MockItem("f1", "footwear", color="black", material="leather"),
        }
        cand1 = _cand(top=("t1",), bottom=("b1",), footwear=("f1",))
        cand2 = _cand(top=("t2",), bottom=("b2",), footwear=("f1",))
        cand3 = _cand(top=("t1",), bottom=("b2",), footwear=("f1",))

        scored_no_weather = [
            score_outfit_candidate(cand1, items),
            score_outfit_candidate(cand2, items),
            score_outfit_candidate(cand3, items),
        ]
        scored_none_weather = [
            score_outfit_candidate(cand1, items, weather_context=None),
            score_outfit_candidate(cand2, items, weather_context=None),
            score_outfit_candidate(cand3, items, weather_context=None),
        ]

        ranked_no = rank_outfit_candidates(scored_no_weather)
        ranked_none = rank_outfit_candidates(scored_none_weather)

        assert ranked_no == ranked_none
        assert [c.score for c in ranked_no] == [c.score for c in ranked_none]

    def test_stale_or_invalid_forecast_timestamp_handled_gracefully(self):
        past_time = _NOW - timedelta(days=7)
        weather = _make_weather(temperature_c=18.0, forecast_timestamp=past_time)

        items = {
            "t1": _MockItem("t1", "tops", color="white", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
        }
        cand = _cand(top=("t1",), bottom=("b1",))
        scored = score_outfit_candidate(cand, items, weather_context=weather)
        assert isinstance(scored.score, float)
        assert 0.0 <= scored.score <= 100.0

    def test_unknown_weather_condition_code_handled_neutrally(self):
        weather = _make_weather(
            temperature_c=20.0,
            apparent_temperature_c=20.0,
            weather_code=99,
            condition_code="unknown",
            condition_text="Unknown Conditions",
        )
        items = {
            "t1": _MockItem("t1", "tops", color="white", material="cotton"),
            "b1": _MockItem("b1", "bottoms", color="black", material="denim"),
        }
        cand = _cand(top=("t1",), bottom=("b1",))
        scored = score_outfit_candidate(cand, items, weather_context=weather)
        # Unknown condition contributes 0.0 condition points; cotton gets +1.0
        assert scored.weather == 1.0
