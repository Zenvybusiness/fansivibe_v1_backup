// TodayLook DTOs for the M9 Today's Look surface (STEP 19.25, DEC-017/018).
//
// Wire shapes follow the frozen backend contract exactly (camelCase):
// `TodayLook {title, occasion?, description, matchScore, styleScore,
// components[], reasons[], styleDna?, wardrobeContext, alternatives[],
// selectedItemIds[]}` — the honesty subset from `today.py` (no `weather`,
// no `colorHex`, no `aiSelectionReason`/`confidenceBoost`/`aiInsights`/
// `dailyStyleTip`, no `wardrobeContext.insight`). `weather` has no provider
// in v1 and is always absent, so it has no field here — callers treat a
// missing weather as normal, never as a failure.
//
// `id` values are always backend UUID strings. Local numeric IDs are never
// produced, stored, or sent by this layer: component and selected-item IDs
// pass through verbatim, and save sends the backend snapshot verbatim (the
// backend fail-closes with 422 on non-UUID IDs).
//
// Parsing is strict — wrong types throw into the client's failure path
// rather than posing garbage as look data. Nothing here derives occasions,
// recomputes scores, logs wears, or writes learning signals: the backend is
// the sole source of truth.

/// One owned wardrobe item inside a TodayLook (no reason/hex — the
/// derived-look component shape).
class TodayLookComponent {
  const TodayLookComponent({
    required this.id,
    required this.name,
    required this.category,
    required this.color,
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

  /// Wardrobe material code, when the item carries one.
  final String? material;

  factory TodayLookComponent.fromJson(Map<String, dynamic> json) =>
      TodayLookComponent(
        id: json['id'] as String,
        name: json['name'] as String,
        category: json['category'] as String,
        color: json['color'] as String,
        material: json['material'] as String?,
      );

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'category': category,
    'color': color,
    'material': material,
  };
}

/// StyleProfile projection — only present subfields travel (absent profile
/// gaps never fail, DEC-018 C12).
class TodayLookStyleDna {
  const TodayLookStyleDna({
    this.styleType,
    this.bodyType,
    this.skinTone,
    this.faceShape,
  });

  final String? styleType;
  final String? bodyType;
  final String? skinTone;
  final String? faceShape;

  factory TodayLookStyleDna.fromJson(Map<String, dynamic> json) =>
      TodayLookStyleDna(
        styleType: json['styleType'] as String?,
        bodyType: json['bodyType'] as String?,
        skinTone: json['skinTone'] as String?,
        faceShape: json['faceShape'] as String?,
      );

  Map<String, dynamic> toJson() => {
    'styleType': styleType,
    'bodyType': bodyType,
    'skinTone': skinTone,
    'faceShape': faceShape,
  };
}

/// Grounded wardrobe counts (`insight` omitted — no grounded prose).
class TodayLookWardrobeContext {
  const TodayLookWardrobeContext({
    required this.totalItems,
    required this.matchingItems,
  });

  final int totalItems;
  final int matchingItems;

  factory TodayLookWardrobeContext.fromJson(Map<String, dynamic> json) =>
      TodayLookWardrobeContext(
        totalItems: json['totalItems'] as int,
        matchingItems: json['matchingItems'] as int,
      );

  Map<String, dynamic> toJson() => {
    'totalItems': totalItems,
    'matchingItems': matchingItems,
  };
}

/// One ranked runner-up (minimal mapping: stable member-derived id + score).
class TodayLookAlternative {
  const TodayLookAlternative({required this.id, required this.matchScore});

  final String id;
  final int matchScore;

  factory TodayLookAlternative.fromJson(Map<String, dynamic> json) =>
      TodayLookAlternative(
        id: json['id'] as String,
        matchScore: json['matchScore'] as int,
      );

  Map<String, dynamic> toJson() => {'id': id, 'matchScore': matchScore};
}

/// Derived today's look (endpoints #31–32, UC-16/UC-17).
///
/// [snapshot] is the decoded response body itself, kept so
/// `POST /v1/looks/today/save` can send the TodayLook back verbatim.
class TodayLook {
  const TodayLook({
    required this.title,
    required this.description,
    required this.matchScore,
    required this.styleScore,
    required this.components,
    required this.reasons,
    required this.wardrobeContext,
    required this.selectedItemIds,
    required this.snapshot,
    this.occasion,
    this.styleDna,
    this.alternatives = const [],
  });

  final String title;

  /// Derivation occasion: the nearest-event type code, else the first
  /// preferred occasion, else absent. Displayed as-is when present; never
  /// recalculated locally.
  final String? occasion;
  final String description;

  /// Native 0–100 int scale (STEP-13 budget — no rescale).
  final int matchScore;

  /// Echoes the derivation's own score (never a local default).
  final int styleScore;
  final List<TodayLookComponent> components;
  final List<String> reasons;
  final TodayLookStyleDna? styleDna;
  final TodayLookWardrobeContext wardrobeContext;
  final List<TodayLookAlternative> alternatives;

  /// Canonical sorted-unique winner UUIDs (verbatim backend strings).
  final List<String> selectedItemIds;

  /// The TodayLook response body verbatim (for `.../today/save`).
  final Map<String, dynamic> snapshot;

  factory TodayLook.fromJson(Map<String, dynamic> json) => TodayLook(
    title: json['title'] as String,
    occasion: json['occasion'] as String?,
    description: json['description'] as String,
    matchScore: json['matchScore'] as int,
    styleScore: json['styleScore'] as int,
    components: (json['components'] as List<dynamic>)
        .map((e) => TodayLookComponent.fromJson(e as Map<String, dynamic>))
        .toList(),
    reasons: (json['reasons'] as List<dynamic>)
        .map((e) => e as String)
        .toList(),
    styleDna: json['styleDna'] == null
        ? null
        : TodayLookStyleDna.fromJson(json['styleDna'] as Map<String, dynamic>),
    wardrobeContext: TodayLookWardrobeContext.fromJson(
      json['wardrobeContext'] as Map<String, dynamic>,
    ),
    alternatives: (json['alternatives'] as List<dynamic>? ?? const [])
        .map((e) => TodayLookAlternative.fromJson(e as Map<String, dynamic>))
        .toList(),
    selectedItemIds: (json['selectedItemIds'] as List<dynamic>)
        .map((e) => e as String)
        .toList(),
    snapshot: json,
  );

  Map<String, dynamic> toJson() => {
    'title': title,
    'occasion': occasion,
    'description': description,
    'matchScore': matchScore,
    'styleScore': styleScore,
    'components': components.map((e) => e.toJson()).toList(),
    'reasons': reasons,
    'styleDna': styleDna?.toJson(),
    'wardrobeContext': wardrobeContext.toJson(),
    'alternatives': alternatives.map((e) => e.toJson()).toList(),
    'selectedItemIds': selectedItemIds,
  };
}

/// One persisted saved look as returned by `POST /v1/looks/today/save`
/// (#33, via M7 `SaveRecommendation`).
class SavedTodayLook {
  const SavedTodayLook({
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

  factory SavedTodayLook.fromJson(Map<String, dynamic> json) => SavedTodayLook(
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

/// How a TodayLook fetch failed (for truthful slot states — never posed as
/// look data).
enum TodayLookFailure {
  /// 401 — surfaced through the existing error slot (dev seam owns auth).
  unauthorized,

  /// 422 — request/input error (e.g. over-length seed).
  invalidInput,

  /// 429 — surfaced through the existing error slot with retry.
  rateLimited,

  /// 503 — retryable service failure for regenerate.
  serviceUnavailable,

  /// Unreachable backend / transport error — truthful offline state.
  networkError,

  /// Any other status or a malformed 200 body.
  unknown,
}

/// Outcome of `GET /v1/looks/today` / `POST /v1/looks/today`.
///
/// 200 carries the look; 404 ([noneAvailable]) is a truthful "no Today's
/// Look available" state — never an error and never a fabricated look.
/// [failure] means the request itself failed and is safe to retry.
class TodayLookResult {
  const TodayLookResult._({this.look, this.failure})
    : available = look != null,
      noneAvailable = look == null && failure == null;

  /// Backend derived a look (200).
  const TodayLookResult.available(TodayLook look) : this._(look: look);

  /// Backend answered 404: no legal candidate right now.
  const TodayLookResult.noneAvailable() : this._();

  /// The request failed ([failure] describes how). Safe to retry.
  const TodayLookResult.failure(TodayLookFailure failure)
    : this._(failure: failure);

  /// Whether a look is present.
  final bool available;

  /// Whether the backend truthfully has no look (404).
  final bool noneAvailable;

  /// The look, when [available].
  final TodayLook? look;

  /// How the request failed, when neither [available] nor [noneAvailable].
  final TodayLookFailure? failure;
}
