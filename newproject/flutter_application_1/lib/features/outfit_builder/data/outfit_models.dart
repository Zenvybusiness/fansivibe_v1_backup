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
    this.role,
    this.imageUrl,
    this.imageRef,
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

  /// Garment role in the outfit (top, bottom, footwear, outerwear, accessory).
  final String? role;

  /// Presigned image URL when available.
  final String? imageUrl;

  /// Raw media reference dictionary.
  final Map<String, dynamic>? imageRef;

  factory OutfitComponent.fromJson(Map<String, dynamic> json) =>
      OutfitComponent(
        id: json['id'] as String,
        name: json['name'] as String,
        category: json['category'] as String,
        color: json['color'] as String,
        reason: json['reason'] as String,
        material: json['material'] as String?,
        role: json['role'] as String?,
        imageUrl: json['imageUrl'] as String?,
        imageRef: json['imageRef'] as Map<String, dynamic>?,
      );

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'category': category,
    'color': color,
    'reason': reason,
    if (material != null) 'material': material,
    if (role != null) 'role': role,
    if (imageUrl != null) 'imageUrl': imageUrl,
    if (imageRef != null) 'imageRef': imageRef,
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

  OutfitCandidate toCandidate({String? id}) => OutfitCandidate(
    id: id ?? 'cand-${title.hashCode.abs()}',
    title: title,
    occasion: selectedOccasion,
    styleDescription: '$selectedOccasion outfit in $selectedColorPalette',
    matchScore: matchScore,
    components: components,
    reasons: reasons,
    stylingRationale: reasons.isNotEmpty ? reasons.join('. ') : 'Coordinated pieces.',
    colorHarmony: colorHarmony,
    stylingTips: const [],
    missingPieces: const [],
    selectedOccasion: selectedOccasion,
    selectedMood: selectedMood,
    selectedColorPalette: selectedColorPalette,
    snapshot: snapshot,
  );
}

/// Preference selections for one outfit derivation (#41).
class OutfitGenerateRequest {
  const OutfitGenerateRequest({
    required this.occasion,
    required this.mood,
    required this.fit,
    required this.colorPalette,
    this.preferredItemIds,
  });

  final String occasion;
  final String mood;
  final String fit;
  final String colorPalette;

  /// C-03 explicit preferred wardrobe IDs (owned UUIDs only).
  /// Null/empty ≡ baseline (omitted from the wire).
  final List<String>? preferredItemIds;

  factory OutfitGenerateRequest.fromJson(Map<String, dynamic> json) =>
      OutfitGenerateRequest(
        occasion: json['occasion'] as String,
        mood: json['mood'] as String,
        fit: json['fit'] as String,
        colorPalette: json['colorPalette'] as String,
        preferredItemIds: (json['preferredItemIds'] as List?)
            ?.map((e) => e as String)
            .toList(),
      );

  Map<String, dynamic> toJson() => {
    'occasion': occasion,
    'mood': mood,
    'fit': fit,
    'colorPalette': colorPalette,
    if (preferredItemIds != null && preferredItemIds!.isNotEmpty)
      'preferredItemIds': preferredItemIds,
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

/// M11 P4 typed empty reasons (`X-Outfit-Empty-Reason` on 204).
/// Verbatim backend codes — never inferred locally.
class OutfitEmptyReason {
  static const String emptyWardrobe = 'empty_wardrobe';
  static const String missingRequiredCategory = 'missing_required_category';
  static const String noLegalCandidate = 'no_legal_candidate';
}

/// Outcome of `POST /v1/outfits/generate`.
///
/// 200 carries the outfit; 204 ([noneAvailable]) is a truthful "no
/// matching wardrobe" state — never an error and never a fabricated
/// outfit. [failure] means the request itself failed and is safe to
/// retry.
class OutfitResult {
  const OutfitResult._({this.outfit, this.failure, this.emptyReason})
    : available = outfit != null,
      noneAvailable = outfit == null && failure == null;

  /// Backend derived an outfit (200).
  const OutfitResult.available(OutfitRecommendation outfit)
    : this._(outfit: outfit);

  /// Backend answered 204: no outfit is derivable right now.
  /// [emptyReason] is the verbatim `X-Outfit-Empty-Reason` header when
  /// present (null for older responses) — unknown future codes pass
  /// through untouched so the screen can fall back to generic copy.
  const OutfitResult.noneAvailable({this.emptyReason})
    : outfit = null,
      failure = null,
      available = false,
      noneAvailable = true;

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

  /// Verbatim backend empty reason, when [noneAvailable].
  final String? emptyReason;
}

/// Eligible replacement wardrobe candidate for an outfit slot (P1-1).
class OutfitCandidateItem {
  const OutfitCandidateItem({
    required this.id,
    required this.name,
    required this.category,
    required this.color,
    this.material,
    this.isFavorite = false,
    this.fit,
    this.fitConfidence,
    this.imageRef,
    this.imageUrl,
  });

  final String id;
  final String name;
  final String category;
  final String color;
  final String? material;
  final bool isFavorite;
  final String? fit;
  final double? fitConfidence;
  final Map<String, dynamic>? imageRef;
  final String? imageUrl;

  factory OutfitCandidateItem.fromJson(Map<String, dynamic> json) =>
      OutfitCandidateItem(
        id: json['id'] as String,
        name: json['name'] as String,
        category: json['category'] as String,
        color: json['color'] as String,
        material: json['material'] as String?,
        isFavorite: (json['isFavorite'] as bool?) ?? false,
        fit: json['fit'] as String?,
        fitConfidence: (json['fitConfidence'] as num?)?.toDouble(),
        imageRef: json['imageRef'] as Map<String, dynamic>?,
        imageUrl: json['imageUrl'] as String?,
      );

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'category': category,
    'color': color,
    if (material != null) 'material': material,
    'isFavorite': isFavorite,
    if (fit != null) 'fit': fit,
    if (fitConfidence != null) 'fitConfidence': fitConfidence,
    if (imageRef != null) 'imageRef': imageRef,
    if (imageUrl != null) 'imageUrl': imageUrl,
  };
}

/// Request payload for swapping an outfit component slot (P1-1).
class OutfitSlotSwapRequest {
  const OutfitSlotSwapRequest({
    required this.occasion,
    required this.mood,
    required this.fit,
    required this.colorPalette,
    required this.currentGarmentIds,
    required this.slot,
    required this.replacementGarmentId,
    this.pinnedGarmentIds,
    this.seed,
  });

  final String occasion;
  final String mood;
  final String fit;
  final String colorPalette;
  final List<String> currentGarmentIds;
  final String slot;
  final String replacementGarmentId;
  final List<String>? pinnedGarmentIds;
  final String? seed;

  Map<String, dynamic> toJson() => {
    'occasion': occasion,
    'mood': mood,
    'fit': fit,
    'colorPalette': colorPalette,
    'currentGarmentIds': currentGarmentIds,
    'slot': slot,
    'replacementGarmentId': replacementGarmentId,
    if (pinnedGarmentIds != null && pinnedGarmentIds!.isNotEmpty)
      'pinnedGarmentIds': pinnedGarmentIds,
    if (seed != null) 'seed': seed,
  };
}

/// Response payload from swapping an outfit component slot (P1-1).
class OutfitSlotSwapResponse {
  const OutfitSlotSwapResponse({
    required this.outfit,
    required this.replacedSlot,
    required this.replacementGarmentId,
    required this.compatibilityScore,
    required this.reasons,
    this.previousGarmentId,
    this.previousCompatibilityScore,
    this.warnings = const [],
  });

  final OutfitRecommendation outfit;
  final String replacedSlot;
  final String replacementGarmentId;
  final double compatibilityScore;
  final List<String> reasons;
  final String? previousGarmentId;
  final double? previousCompatibilityScore;
  final List<String> warnings;

  factory OutfitSlotSwapResponse.fromJson(Map<String, dynamic> json) =>
      OutfitSlotSwapResponse(
        outfit: OutfitRecommendation.fromJson(
          json['outfit'] as Map<String, dynamic>,
        ),
        replacedSlot: json['replacedSlot'] as String,
        replacementGarmentId: json['replacementGarmentId'] as String,
        compatibilityScore: (json['compatibilityScore'] as num).toDouble(),
        reasons: (json['reasons'] as List<dynamic>)
            .map((e) => e as String)
            .toList(),
        previousGarmentId: json['previousGarmentId'] as String?,
        previousCompatibilityScore: (json['previousCompatibilityScore'] as num?)
            ?.toDouble(),
        warnings:
            (json['warnings'] as List<dynamic>?)
                ?.map((e) => e as String)
                .toList() ??
            const [],
      );
}

/// Documented calculation breakdown for outfit match score.
class ScoreBreakdown {
  const ScoreBreakdown({
    required this.totalScore,
    this.occasionMatch = 0.0,
    this.paletteMatch = 0.0,
    this.fitMatch = 0.0,
    this.preferenceBonus = 0.0,
    this.feedbackBonus = 0.0,
    this.wearAdjustment = 0.0,
    this.calculation = '',
  });

  final double totalScore;
  final double occasionMatch;
  final double paletteMatch;
  final double fitMatch;
  final double preferenceBonus;
  final double feedbackBonus;
  final double wearAdjustment;
  final String calculation;

  factory ScoreBreakdown.fromJson(Map<String, dynamic> json) => ScoreBreakdown(
    totalScore: (json['totalScore'] as num).toDouble(),
    occasionMatch: ((json['occasionMatch'] as num?) ?? 0.0).toDouble(),
    paletteMatch: ((json['paletteMatch'] as num?) ?? 0.0).toDouble(),
    fitMatch: ((json['fitMatch'] as num?) ?? 0.0).toDouble(),
    preferenceBonus: ((json['preferenceBonus'] as num?) ?? 0.0).toDouble(),
    feedbackBonus: ((json['feedbackBonus'] as num?) ?? 0.0).toDouble(),
    wearAdjustment: ((json['wearAdjustment'] as num?) ?? 0.0).toDouble(),
    calculation: (json['calculation'] as String?) ?? '',
  );

  Map<String, dynamic> toJson() => {
    'totalScore': totalScore,
    'occasionMatch': occasionMatch,
    'paletteMatch': paletteMatch,
    'fitMatch': fitMatch,
    'preferenceBonus': preferenceBonus,
    'feedbackBonus': feedbackBonus,
    'wearAdjustment': wearAdjustment,
    'calculation': calculation,
  };
}

/// Suggested addition to complete an outfit (clearly labeled as unowned).
class MissingPieceSuggestion {
  const MissingPieceSuggestion({
    required this.category,
    required this.role,
    required this.suggestion,
    this.isOwned = false,
  });

  final String category;
  final String role;
  final String suggestion;
  final bool isOwned;

  factory MissingPieceSuggestion.fromJson(Map<String, dynamic> json) =>
      MissingPieceSuggestion(
        category: json['category'] as String,
        role: (json['role'] as String?) ?? (json['category'] as String),
        suggestion: json['suggestion'] as String,
        isOwned: (json['isOwned'] as bool?) ?? false,
      );

  Map<String, dynamic> toJson() => {
    'category': category,
    'role': role,
    'suggestion': suggestion,
    'isOwned': isOwned,
  };
}

/// Full candidate representation for multi-outfit generation.
class OutfitCandidate {
  const OutfitCandidate({
    required this.id,
    required this.title,
    required this.occasion,
    required this.styleDescription,
    required this.matchScore,
    required this.components,
    required this.reasons,
    required this.stylingRationale,
    required this.colorHarmony,
    required this.stylingTips,
    required this.selectedOccasion,
    required this.selectedMood,
    required this.selectedColorPalette,
    required this.snapshot,
    this.scoreBreakdown,
    this.missingPieces = const [],
  });

  final String id;
  final String title;
  final String occasion;
  final String styleDescription;
  final double matchScore;
  final ScoreBreakdown? scoreBreakdown;
  final List<OutfitComponent> components;
  final List<String> reasons;
  final String stylingRationale;
  final String colorHarmony;
  final List<String> stylingTips;
  final List<MissingPieceSuggestion> missingPieces;
  final String selectedOccasion;
  final String selectedMood;
  final String selectedColorPalette;
  final Map<String, dynamic> snapshot;

  factory OutfitCandidate.fromJson(Map<String, dynamic> json) =>
      OutfitCandidate(
        id: json['id'] as String,
        title: json['title'] as String,
        occasion: json['occasion'] as String,
        styleDescription: (json['styleDescription'] as String?) ?? '',
        matchScore: (json['matchScore'] as num).toDouble(),
        scoreBreakdown: json['scoreBreakdown'] != null
            ? ScoreBreakdown.fromJson(
                json['scoreBreakdown'] as Map<String, dynamic>,
              )
            : null,
        components: (json['components'] as List<dynamic>)
            .map((e) => OutfitComponent.fromJson(e as Map<String, dynamic>))
            .toList(),
        reasons: (json['reasons'] as List<dynamic>)
            .map((e) => e as String)
            .toList(),
        stylingRationale: (json['stylingRationale'] as String?) ?? '',
        colorHarmony: (json['colorHarmony'] as String?) ?? '',
        stylingTips: (json['stylingTips'] as List<dynamic>?)
                ?.map((e) => e as String)
                .toList() ??
            const [],
        missingPieces: (json['missingPieces'] as List<dynamic>?)
                ?.map(
                  (e) =>
                      MissingPieceSuggestion.fromJson(e as Map<String, dynamic>),
                )
                .toList() ??
            const [],
        selectedOccasion: (json['selectedOccasion'] as String?) ?? '',
        selectedMood: (json['selectedMood'] as String?) ?? '',
        selectedColorPalette: (json['selectedColorPalette'] as String?) ?? '',
        snapshot: (json['snapshot'] as Map<String, dynamic>?) ?? json,
      );

  OutfitRecommendation toRecommendation() => OutfitRecommendation(
    title: title,
    matchScore: matchScore,
    components: components,
    reasons: reasons,
    colorHarmony: colorHarmony,
    bodyFit: 'Assembled for a $selectedMood and $occasion fit.',
    occasionMatch: 'Matched for $occasion.',
    styleScoreImpact: '${(matchScore * 100).round()}% match from owned pieces.',
    improvementSuggestion: missingPieces.isNotEmpty
        ? missingPieces.first.suggestion
        : 'Full coverage across core pieces.',
    selectedOccasion: selectedOccasion,
    selectedMood: selectedMood,
    selectedColorPalette: selectedColorPalette,
    snapshot: snapshot,
  );
}

/// Response payload from multi-outfit composition.
class OutfitCompositionResponse {
  const OutfitCompositionResponse({
    required this.candidates,
    required this.totalCandidates,
    required this.occasion,
    required this.mood,
    required this.fit,
    required this.colorPalette,
    this.query,
    this.weatherContext,
  });

  final List<OutfitCandidate> candidates;
  final int totalCandidates;
  final String occasion;
  final String mood;
  final String fit;
  final String colorPalette;
  final String? query;
  final String? weatherContext;

  factory OutfitCompositionResponse.fromJson(Map<String, dynamic> json) =>
      OutfitCompositionResponse(
        candidates: (json['candidates'] as List<dynamic>)
            .map((e) => OutfitCandidate.fromJson(e as Map<String, dynamic>))
            .toList(),
        totalCandidates: (json['totalCandidates'] as num).toInt(),
        occasion: json['occasion'] as String,
        mood: json['mood'] as String,
        fit: json['fit'] as String,
        colorPalette: json['colorPalette'] as String,
        query: json['query'] as String?,
        weatherContext: json['weatherContext'] as String?,
      );
}

/// Outcome of `POST /v1/outfits/compose`.
class OutfitCompositionResult {
  const OutfitCompositionResult._({
    this.composition,
    this.failure,
    this.emptyReason,
  })  : available = composition != null,
        noneAvailable = composition == null && failure == null;

  const OutfitCompositionResult.available(OutfitCompositionResponse composition)
      : this._(composition: composition);

  const OutfitCompositionResult.noneAvailable({this.emptyReason})
      : composition = null,
        failure = null,
        available = false,
        noneAvailable = true;

  const OutfitCompositionResult.failure(OutfitFailure failure)
      : this._(failure: failure);

  final bool available;
  final bool noneAvailable;
  final OutfitCompositionResponse? composition;
  final OutfitFailure? failure;
  final String? emptyReason;
}

