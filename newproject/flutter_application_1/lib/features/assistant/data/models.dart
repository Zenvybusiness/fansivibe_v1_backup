import 'package:fansivibe/features/learning/data/models.dart';

/// Typed contract DTOs mirroring `backend/app/models/schemas.py`.
///
/// Keep these in sync with the backend so the JSON contract stays stable.

class OutfitComposition {
  const OutfitComposition({
    required this.topIds,
    required this.bottomIds,
    required this.outerwearIds,
    required this.footwearIds,
    required this.accessoryIds,
    required this.styleScore,
  });

  final List<String> topIds;
  final List<String> bottomIds;
  final List<String> outerwearIds;
  final List<String> footwearIds;
  final List<String> accessoryIds;
  final int styleScore;

  factory OutfitComposition.fromJson(Map<String, dynamic> json) => OutfitComposition(
    topIds: (json['topIds'] as List<dynamic>? ?? [])
        .map((e) => e as String)
        .toList(),
    bottomIds: (json['bottomIds'] as List<dynamic>? ?? [])
        .map((e) => e as String)
        .toList(),
    outerwearIds: (json['outerwearIds'] as List<dynamic>? ?? [])
        .map((e) => e as String)
        .toList(),
    footwearIds: (json['footwearIds'] as List<dynamic>? ?? [])
        .map((e) => e as String)
        .toList(),
    accessoryIds: (json['accessoryIds'] as List<dynamic>? ?? [])
        .map((e) => e as String)
        .toList(),
    styleScore: json['styleScore'] as int? ?? 0,
  );

  Map<String, dynamic> toJson() => {
    'topIds': topIds,
    'bottomIds': bottomIds,
    'outerwearIds': outerwearIds,
    'footwearIds': footwearIds,
    'accessoryIds': accessoryIds,
    'styleScore': styleScore,
  };
}

/// Selected wardrobe item IDs, machine-readable for later lookup/highlight.
/// Remains a list of strings — NOT converted to display-only concatenated strings.
class OutfitSelectedItemIds {
  const OutfitSelectedItemIds({
    required this.itemIds,
  });

  final List<String> itemIds;

  factory OutfitSelectedItemIds.fromJson(Map<String, dynamic> json) =>
      OutfitSelectedItemIds(
        itemIds: (json['itemIds'] as List<dynamic>? ?? [])
            .map((e) => e as String)
            .toList(),
      );

  Map<String, dynamic> toJson() => {
    'itemIds': itemIds,
  };
}

/// Complete Outfit Intelligence result from the backend.
class OutfitIntelligence {
  const OutfitIntelligence({
    required this.selectedItemIds,
    required this.outfitComposition,
    required this.occasion,
    required this.stylingRationale,
    required this.compatibilityRationale,
    required this.confidence,
    required this.explanation,
    required this.dataAvailability,
  });

  /// Machine-readable selected wardrobe item IDs.
  final List<String> selectedItemIds;

  /// Outfit composition by category with style score.
  final OutfitComposition outfitComposition;

  /// Occasion associated with the outfit (casual, office, date, party, travel).
  final String occasion;

  /// Styling rationale text.
  final String stylingRationale;

  /// Compatibility rationale text.
  final String compatibilityRationale;

  /// Confidence level in [0, 1].
  final double confidence;

  /// Natural language explanation.
  final String explanation;

  /// Data availability: 'full', 'partial', or 'sparse'.
  final String dataAvailability;

  factory OutfitIntelligence.fromJson(Map<String, dynamic> json) => OutfitIntelligence(
    selectedItemIds: (json['selectedItemIds'] as List<dynamic>? ?? [])
        .map((e) => e as String)
        .toList(),
    outfitComposition: OutfitComposition.fromJson(json['outfitComposition'] as Map<String, dynamic>? ?? {}),
    occasion: json['occasion'] as String? ?? '',
    stylingRationale: json['stylingRationale'] as String? ?? '',
    compatibilityRationale: json['compatibilityRationale'] as String? ?? '',
    confidence: (json['confidence'] as num? ?? 0.0).toDouble(),
    explanation: json['explanation'] as String? ?? '',
    dataAvailability: json['dataAvailability'] as String? ?? 'full',
  );

  Map<String, dynamic> toJson() => {
    'selectedItemIds': selectedItemIds,
    'outfitComposition': outfitComposition.toJson(),
    'occasion': occasion,
    'stylingRationale': stylingRationale,
    'compatibilityRationale': compatibilityRationale,
    'confidence': confidence,
    'explanation': explanation,
    'dataAvailability': dataAvailability,
  };
}

/// Backend-UUID shape gate for outbound item identity (P1-1).
///
/// The assistant engine echoes the IDs of the wardrobe snapshot it was
/// given, which are local on-device IDs (`1`–`24`, never backend UUIDs).
/// M7 validates `selectedItemIds` as owned backend UUIDs and fail-closes
/// anything else, so local IDs must never cross the wire: only
/// canonical-UUID-shaped strings survive sanitization. This is a shape
/// gate only — parsing and ownership stay server-authoritative (unknown
/// or foreign UUIDs still 404 there). Kept order-stable; the server
/// canonicalizes (sorts/uniques) before persisting.
bool isBackendUuidShape(String value) {
  if (value.length != 36) return false;
  const hyphens = [8, 13, 18, 23];
  for (var i = 0; i < value.length; i++) {
    final unit = value.codeUnitAt(i);
    final isHex =
        (unit >= 0x30 && unit <= 0x39) ||
        (unit >= 0x61 && unit <= 0x66) ||
        (unit >= 0x41 && unit <= 0x46);
    if (hyphens.contains(i)) {
      if (unit != 0x2D) return false;
    } else if (!isHex) {
      return false;
    }
  }
  return true;
}

/// Save request for the existing backend contract `POST /v1/looks/saved`.
///
/// Outfit saves always use `lookId = null` (no outfit look catalog) and
/// `sourceContext = "outfit"` — the frozen M7 vocabulary
/// (`hairstyle`/`grooming`/`outfit`/`daily`; `"assistant"` is not an
/// accepted value and would 422, so the assistant outfit flow reuses the
/// outfit-family context it snapshots). The title is derived from the
/// occasion; the snapshot preserves the generated [OutfitIntelligence].
class OutfitSaveRequest {
  const OutfitSaveRequest({
    this.lookId,
    required this.title,
    required this.snapshot,
    this.sourceContext = 'outfit',
  });

  /// Always null for Outfit saves (backend has no outfit look catalog).
  final String? lookId;

  /// Derived from the occasion: `"X Outfit"` or `"Saved Outfit"`.
  final String title;

  /// Snapshot built ONLY from existing [OutfitIntelligence] data.
  final Map<String, dynamic> snapshot;

  /// Always "outfit" for this flow.
  final String sourceContext;

  /// Derives `"X Outfit"`, falling back to `"Saved Outfit"`.
  static String titleForOccasion(String occasion) {
    final trimmed = occasion.trim();
    if (trimmed.isEmpty || trimmed.toLowerCase() == 'unknown') {
      return 'Saved Outfit';
    }
    return '${trimmed[0].toUpperCase()}${trimmed.substring(1)} Outfit';
  }

  factory OutfitSaveRequest.fromOutfitIntelligence(
    OutfitIntelligence intelligence,
  ) {
    // P1-1: strip local engine IDs — only backend-UUID-shaped IDs travel.
    // When none survive, the key is omitted and M7 skips item validation
    // (the snapshot still freezes verbatim); ownership of any surviving
    // UUID stays server-enforced (404-not-403).
    final uuidIds = intelligence.selectedItemIds
        .where(isBackendUuidShape)
        .toList();
    return OutfitSaveRequest(
      lookId: null,
      title: titleForOccasion(intelligence.occasion),
      snapshot: {
        if (uuidIds.isNotEmpty) 'selectedItemIds': uuidIds,
        'outfitComposition': intelligence.outfitComposition.toJson(),
        'occasion': intelligence.occasion,
        'stylingRationale': intelligence.stylingRationale,
        'compatibilityRationale': intelligence.compatibilityRationale,
        'confidence': intelligence.confidence,
        'explanation': intelligence.explanation,
        'dataAvailability': intelligence.dataAvailability,
      },
      sourceContext: 'outfit',
    );
  }

  Map<String, dynamic> toJson() => {
    'lookId': lookId,
    'title': title,
    'snapshot': snapshot,
    'sourceContext': sourceContext,
  };
}

/// Minimal saved-look record returned by `POST /v1/looks/saved`.
///
/// Parses leniently (camelCase or snake_case) so only the fields the
/// backend provides are read; the UI only needs the saved identity.
class SavedOutfitLook {
  const SavedOutfitLook({
    required this.id,
    required this.title,
    required this.sourceContext,
    this.snapshot = const {},
  });

  final String id;
  final String title;
  final String sourceContext;
  final Map<String, dynamic> snapshot;

  factory SavedOutfitLook.fromJson(Map<String, dynamic> json) {
    final rawSnapshot = json['snapshot'];
    return SavedOutfitLook(
      id: json['id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      sourceContext:
          json['sourceContext'] as String? ??
          json['source_context'] as String? ??
          'outfit',
      snapshot: rawSnapshot is Map<String, dynamic>
          ? rawSnapshot
          : rawSnapshot is Map
          ? Map<String, dynamic>.from(rawSnapshot)
          : const {},
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'title': title,
    'sourceContext': sourceContext,
    'snapshot': snapshot,
  };
}

class SuggestionCard {
  const SuggestionCard({
    required this.kind,
    required this.title,
    required this.subtitle,
    this.score,
    this.items = const [],
    this.action,
  });

  final String kind;
  final String title;
  final String subtitle;
  final int? score;
  final List<String> items;
  final String? action;

  factory SuggestionCard.fromJson(Map<String, dynamic> json) => SuggestionCard(
    kind: json['kind'] as String? ?? 'tip',
    title: json['title'] as String? ?? '',
    subtitle: json['subtitle'] as String? ?? '',
    score: json['score'] as int?,
    items: (json['items'] as List<dynamic>? ?? [])
        .map((e) => e as String)
        .toList(),
    action: json['action'] as String?,
  );

  Map<String, dynamic> toJson() => {
    'kind': kind,
    'title': title,
    'subtitle': subtitle,
    'score': score,
    'items': items,
    'action': action,
  };
}

class ClarificationOption {
  const ClarificationOption({required this.label, required this.value});

  final String label;
  final String value;

  factory ClarificationOption.fromJson(Map<String, dynamic> json) =>
      ClarificationOption(
        label: json['label'] as String? ?? '',
        value: json['value'] as String? ?? '',
      );

  Map<String, dynamic> toJson() => {'label': label, 'value': value};
}

class NavigationRequest {
  const NavigationRequest({required this.route, required this.label});

  final String route;
  final String label;

  factory NavigationRequest.fromJson(Map<String, dynamic> json) =>
      NavigationRequest(
        route: json['route'] as String? ?? '',
        label: json['label'] as String? ?? '',
      );

  Map<String, dynamic> toJson() => {'route': route, 'label': label};
}

class AssistantReply {
  const AssistantReply({
    required this.intent,
    required this.text,
    this.cards = const [],
    this.clarifications = const [],
    this.navigation,
    this.outfitIntelligence,
  });

  final String intent;
  final String text;
  final List<SuggestionCard> cards;
  final List<ClarificationOption> clarifications;
  final NavigationRequest? navigation;
  final OutfitIntelligence? outfitIntelligence;

  factory AssistantReply.fromJson(Map<String, dynamic> json) => AssistantReply(
    intent: json['intent'] as String? ?? 'unknown',
    text: json['text'] as String? ?? '',
    cards: (json['cards'] as List<dynamic>? ?? [])
        .map((e) => SuggestionCard.fromJson(e as Map<String, dynamic>))
        .toList(),
    clarifications: (json['clarifications'] as List<dynamic>? ?? [])
        .map((e) => ClarificationOption.fromJson(e as Map<String, dynamic>))
        .toList(),
    navigation: json['navigation'] == null
        ? null
        : NavigationRequest.fromJson(
            json['navigation'] as Map<String, dynamic>,
          ),
    outfitIntelligence: json['outfitIntelligence'] == null
        ? null
        : OutfitIntelligence.fromJson(
            json['outfitIntelligence'] as Map<String, dynamic>,
          ),
  );
}

/// Typed outcome of syncing one occasion code (P1-2).
enum PreferenceSyncResult {
  /// Server now holds the code (PATCH 200).
  synced,

  /// The code was already present server-side; no PATCH sent (no dupes).
  alreadySynced,

  /// Empty code (fail-closed, no network) or server 422.
  invalidInput,

  /// Server 401.
  unauthorized,

  /// Server 429.
  rateLimited,

  /// Server state unreadable, transport failure, or unexpected status.
  networkError,

  /// Any other unexpected status.
  unknown,
}

/// A single message in the conversation shown in the chat screen.
class AssistantMessage {
  const AssistantMessage({
    required this.role,
    required this.text,
    this.cards = const [],
    this.clarifications = const [],
    this.navigation,
    this.outfitIntelligence,
    this.pending = false,
    this.isOffline = false,
  });

  final String role;
  final String text;
  final List<SuggestionCard> cards;
  final List<ClarificationOption> clarifications;
  final NavigationRequest? navigation;
  final OutfitIntelligence? outfitIntelligence;

  /// True while waiting for the backend reply (typing indicator).
  final bool pending;

  /// True when this content was produced from offline/local fallback data
  /// rather than live backend intelligence.
  final bool isOffline;

  bool get isUser => role == 'user';

  AssistantMessage copyWith({
    String? text,
    bool? pending,
    OutfitIntelligence? outfitIntelligence,
    bool? isOffline,
  }) => AssistantMessage(
    role: role,
    text: text ?? this.text,
    cards: cards,
    clarifications: clarifications,
    navigation: navigation,
    outfitIntelligence: outfitIntelligence ?? this.outfitIntelligence,
    pending: pending ?? this.pending,
    isOffline: isOffline ?? this.isOffline,
  );
}

/// Snapshot of the user model sent with every assistant request.
class AssistantUserContext {
  const AssistantUserContext({
    this.wardrobe = const [],
    this.face,
    this.savedLooks = const [],
    this.preferredOccasions = const [],
  });

  final List<WardrobeEntry> wardrobe;
  final FaceProfile? face;
  final List<String> savedLooks;
  final List<String> preferredOccasions;

  Map<String, dynamic> toJson() => {
    'wardrobe': wardrobe.map((e) => e.toJson()).toList(),
    'face': face?.toJson(),
    'savedLooks': savedLooks,
    'preferredOccasions': preferredOccasions,
  };
}
