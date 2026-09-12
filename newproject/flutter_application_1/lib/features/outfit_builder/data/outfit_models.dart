// Outfit DTOs for the M13 builder surface (PHASE 2).
//
// Wire shapes follow the frozen ensemble contract exactly (camelCase):
// `OutfitRecommendation {title, matchScore, components[], reasons[],
// colorHarmony, bodyFit, occasionMatch, styleScoreImpact,
// improvementSuggestion, selectedOccasion, selectedMood,
// selectedColorPalette}` (REC_API §4.3, V1 §6.7). `matchScore` is the
// family 0..1 float scale — never rescaled, never 0–100.
//
// Honesty subset (AI-0, M8-C/M9 precedent): per-component `colorHex`
// has no server source and has no field here; the DTO carries no
// alternatives. `id` values are always backend wardrobe UUID strings —
// local mock IDs are never produced, stored, or sent by this layer.
//
// Parsing is strict — wrong types throw into the client's failure path
// rather than posing garbage as outfit data. Nothing here derives
// occasions, logs wears, or writes signals: the backend is the sole
// source of truth.

/// One owned wardrobe item inside a derived outfit.
class OutfitComponent {
  const OutfitComponent({
    required this.id,
    required this.name,
    required this.category,
    required this.color,
    required this.reason,
    this.material,
  });

  /// Backend wardrobe UUID (verbatim — never resolved against local IDs).
  final String id;

  /// Wardrobe item name (verbatim backend text — never invented).
  final String name;

  /// Wardrobe category code (verbatim).
  final String category;

  /// Wardrobe color code (verbatim; hex has no server source).
  final String color;

  /// Grounded slot-pick reason (verbatim backend text).
  final String reason;

  /// Wardrobe material code, when the item carries one.
  final String? material;

  factory OutfitComponent.fromJson(Map<String, dynamic> json) =>
      OutfitComponent(
        id: json['id'] as String,
        name: json['name'] as String,
        category: json['category'] as String,
        color: json['color'] as String,
        reason: json['reason'] as String,
        material: json['material'] as String?,
      );

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'category': category,
    'color': color,
    'reason': reason,
    'material': material,
  };
}

/// Derived outfit value object (endpoint #41, UC-28/UC-29).
///
/// [snapshot] is the decoded response body itself, kept so
/// `POST /v1/outfits/saved` can send the outfit back verbatim.
class OutfitRecommendation {
  const OutfitRecommendation({
    required this.title,
    required this.matchScore,
    required this.components,
    required this.reasons,
    required this.colorHarmony,
    required this.bodyFit,
    required this.occasionMatch,
    required this.styleScoreImpact,
    required this.improvementSuggestion,
    required this.selectedOccasion,
    required this.selectedMood,
    required this.selectedColorPalette,
    required this.snapshot,
  });

  final String title;

  /// Ensemble match score, family 0..1 float scale (verbatim).
  final double matchScore;
  final List<OutfitComponent> components;
  final List<String> reasons;
  final String colorHarmony;
  final String bodyFit;
  final String occasionMatch;
  final String styleScoreImpact;
  final String improvementSuggestion;

  /// Request prefs echoed back verbatim.
  final String selectedOccasion;
  final String selectedMood;
  final String selectedColorPalette;

  /// The outfit response body verbatim (for `.../outfits/saved`).
  final Map<String, dynamic> snapshot;

  factory OutfitRecommendation.fromJson(Map<String, dynamic> json) =>
      OutfitRecommendation(
        title: json['title'] as String,
        matchScore: (json['matchScore'] as num).toDouble(),
        components: (json['components'] as List<dynamic>)
            .map((e) => OutfitComponent.fromJson(e as Map<String, dynamic>))
            .toList(),
        reasons: (json['reasons'] as List<dynamic>)
            .map((e) => e as String)
            .toList(),
        colorHarmony: json['colorHarmony'] as String,
        bodyFit: json['bodyFit'] as String,
        occasionMatch: json['occasionMatch'] as String,
        styleScoreImpact: json['styleScoreImpact'] as String,
        improvementSuggestion: json['improvementSuggestion'] as String,
        selectedOccasion: json['selectedOccasion'] as String,
        selectedMood: json['selectedMood'] as String,
        selectedColorPalette: json['selectedColorPalette'] as String,
        snapshot: json,
      );

  Map<String, dynamic> toJson() => {
    'title': title,
    'matchScore': matchScore,
    'components': components.map((e) => e.toJson()).toList(),
    'reasons': reasons,
    'colorHarmony': colorHarmony,
    'bodyFit': bodyFit,
    'occasionMatch': occasionMatch,
    'styleScoreImpact': styleScoreImpact,
    'improvementSuggestion': improvementSuggestion,
    'selectedOccasion': selectedOccasion,
    'selectedMood': selectedMood,
    'selectedColorPalette': selectedColorPalette,
  };
}

/// Preference selections for one outfit derivation (#41).
class OutfitGenerateRequest {
  const OutfitGenerateRequest({
    required this.occasion,
    required this.mood,
    required this.fit,
    required this.colorPalette,
  });

  final String occasion;
  final String mood;
  final String fit;
  final String colorPalette;

  factory OutfitGenerateRequest.fromJson(Map<String, dynamic> json) =>
      OutfitGenerateRequest(
        occasion: json['occasion'] as String,
        mood: json['mood'] as String,
        fit: json['fit'] as String,
        colorPalette: json['colorPalette'] as String,
      );

  Map<String, dynamic> toJson() => {
    'occasion': occasion,
    'mood': mood,
    'fit': fit,
    'colorPalette': colorPalette,
  };
}

/// One persisted saved outfit as returned by `POST /v1/outfits/saved`
/// (#42, via M7 `SaveRecommendation`).
class SavedOutfit {
  const SavedOutfit({
    required this.id,
    required this.title,
    required this.snapshot,
    required this.createdAt,
    this.lookId,
    this.sourceContext,
    this.sourceRunId,
  });

  /// Backend UUID of the saved-look row.
  final String id;
  final String? lookId;
  final String title;
  final String? sourceContext;

  /// The frozen snapshot stored at save time (echo of what was sent).
  final Map<String, dynamic>? snapshot;
  final String? sourceRunId;
  final DateTime createdAt;

  factory SavedOutfit.fromJson(Map<String, dynamic> json) => SavedOutfit(
    id: json['id'] as String,
    lookId: json['lookId'] as String?,
    title: json['title'] as String,
    sourceContext: json['sourceContext'] as String?,
    snapshot: json['snapshot'] as Map<String, dynamic>?,
    sourceRunId: json['sourceRunId'] as String?,
    createdAt:
        DateTime.tryParse(json['createdAt'] as String? ?? '') ??
        DateTime.fromMillisecondsSinceEpoch(0),
  );
}

/// How an outfit fetch failed (for truthful screen states — never posed
/// as outfit data).
enum OutfitFailure {
  /// 401 — surfaced through the existing error slot (dev seam owns auth).
  unauthorized,

  /// 422 — request/input error (e.g. blank preference, bad seed).
  invalidInput,

  /// 429 — surfaced through the existing error slot with retry.
  rateLimited,

  /// 503 — retryable service failure for generation.
  serviceUnavailable,

  /// Unreachable backend / transport error — truthful offline state.
  networkError,

  /// Any other status or a malformed 200 body.
  unknown,
}

/// Outcome of `POST /v1/outfits/generate`.
///
/// 200 carries the outfit; 204 ([noneAvailable]) is a truthful "no
/// matching wardrobe" state — never an error and never a fabricated
/// outfit. [failure] means the request itself failed and is safe to
/// retry.
class OutfitResult {
  const OutfitResult._({this.outfit, this.failure})
    : available = outfit != null,
      noneAvailable = outfit == null && failure == null;

  /// Backend derived an outfit (200).
  const OutfitResult.available(OutfitRecommendation outfit)
    : this._(outfit: outfit);

  /// Backend answered 204: no outfit is derivable right now.
  const OutfitResult.noneAvailable() : this._();

  /// The request failed ([failure] describes how). Safe to retry.
  const OutfitResult.failure(OutfitFailure failure) : this._(failure: failure);

  /// Whether an outfit is present.
  final bool available;

  /// Whether the backend truthfully has no outfit (204).
  final bool noneAvailable;

  /// The outfit, when [available].
  final OutfitRecommendation? outfit;

  /// How the request failed, when neither [available] nor [noneAvailable].
  final OutfitFailure? failure;
}
