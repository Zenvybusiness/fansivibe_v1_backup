import 'package:fansivibe/features/learning/data/models.dart';

/// Typed contract DTOs mirroring `backend/app/models/schemas.py`.
///
/// Keep these in sync with the backend so the JSON contract stays stable.

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
  });

  final String intent;
  final String text;
  final List<SuggestionCard> cards;
  final List<ClarificationOption> clarifications;
  final NavigationRequest? navigation;

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
  );
}

/// A single message in the conversation shown in the chat screen.
class AssistantMessage {
  const AssistantMessage({
    required this.role,
    required this.text,
    this.cards = const [],
    this.clarifications = const [],
    this.navigation,
    this.pending = false,
  });

  final String role;
  final String text;
  final List<SuggestionCard> cards;
  final List<ClarificationOption> clarifications;
  final NavigationRequest? navigation;

  /// True while waiting for the backend reply (typing indicator).
  final bool pending;

  bool get isUser => role == 'user';

  AssistantMessage copyWith({String? text, bool? pending}) => AssistantMessage(
    role: role,
    text: text ?? this.text,
    cards: cards,
    clarifications: clarifications,
    navigation: navigation,
    pending: pending ?? this.pending,
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
