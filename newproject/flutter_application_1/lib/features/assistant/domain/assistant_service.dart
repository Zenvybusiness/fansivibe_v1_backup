import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';

import 'package:fansivibe/features/assistant/data/assistant_client.dart';
import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/assistant/data/offline_assistant.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';

/// Conversation state + orchestration for the assistant.
///
/// Sends the message history and a snapshot of the user model to the backend,
/// falling back to [OfflineAssistant] when the server is unreachable. Every
/// exchange records learning signals so the app adapts over time.
class AssistantService extends ChangeNotifier {
  AssistantService({
    AssistantClient? client,
    OfflineAssistant? offline,
    LearningRepository? learning,
  }) : _client = client ?? AssistantClient(),
       _offline = offline ?? OfflineAssistant(),
       _learning = learning;

  LearningRepository? _learning;

  final AssistantClient _client;
  final OfflineAssistant _offline;

  final List<AssistantMessage> _messages = [];
  List<AssistantMessage> get messages => List.unmodifiable(_messages);

  bool _isSending = false;
  bool get isSending => _isSending;

  bool _disposed = false;

  /// Read-only snapshot of the already-loaded learning wardrobe.
  ///
  /// Presentation uses this to resolve outfit selections into displayable
  /// items without new network requests. Empty when no learning repository
  /// is attached. The returned list is a copy; mutating it never affects
  /// the underlying user model.
  List<WardrobeEntry> get wardrobe =>
      List.unmodifiable(_learning?.wardrobe ?? const []);

  /// Wire the learning repository so assistant answers are grounded in the
  /// user's own data (wardrobe, face analysis, saved looks).
  void attachLearning(LearningRepository learning) {
    _learning = learning;
  }

  AssistantUserContext _buildContext() {
    final learning = _learning;
    return AssistantUserContext(
      wardrobe: learning?.wardrobe ?? const [],
      face: learning?.face,
      savedLooks: learning?.savedLooks ?? const [],
      preferredOccasions: learning?.preferredOccasions ?? const [],
    );
  }

  Future<void> send(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty || _isSending) return;

    _learning?.recordSignal('assistant_message', trimmed);

    _messages.add(AssistantMessage(role: 'user', text: trimmed));
    _messages.add(
      const AssistantMessage(role: 'assistant', text: '', pending: true),
    );
    _isSending = true;
    _safeNotify();

    final reply = await _client.chat(
      history: _messages.where((m) => !m.pending).toList(),
      context: _buildContext(),
    );

    if (_disposed) return;

    final result = reply ?? _offline.replyFor(trimmed, _buildContext());

    final index = _messages.length - 1;
    _messages[index] = AssistantMessage(
      role: 'assistant',
      text: result.text,
      cards: result.cards,
      clarifications: result.clarifications,
      navigation: result.navigation,
      outfitIntelligence: result.outfitIntelligence,
    );
    _isSending = false;
    _safeNotify();
  }

  /// Send a clarification option (e.g. tapping an occasion chip).
  Future<void> selectClarification(ClarificationOption option) =>
      send(option.value);

  /// Save the current [OutfitIntelligence] via `POST /v1/looks/saved`.
  ///
  /// Builds the request (lookId = null, sourceContext = "outfit",
  /// snapshot from the intelligence), generates a fresh Idempotency-Key
  /// for each new save attempt (pass [idempotencyKey] to keep the key
  /// stable across retries of the SAME attempt), and returns true only
  /// when the backend confirms the save.
  ///
  /// Never emits local learning signals: `look_saved` / `outfit_selected`
  /// are backend-owned and committed atomically with the saved look.
  Future<bool> saveOutfit(
    OutfitIntelligence intelligence, {
    String? idempotencyKey,
  }) async {
    final request = OutfitSaveRequest.fromOutfitIntelligence(intelligence);
    final key = idempotencyKey ?? newOutfitIdempotencyKey();
    final saved = await _client.saveOutfitLook(
      request: request,
      idempotencyKey: key,
    );
    return saved != null;
  }

  /// Record that the user opened a suggestion so the model can learn from it.
  ///
  /// Reports `interactionType: "opened"` to the backend first. A confirmed
  /// backend write is authoritative, so no local signal is recorded then
  /// (never double-count — same convention as [saveOutfit]). Only when the
  /// backend write fails does the existing local recording run, preserving
  /// offline behavior without ever faking a synced success. Never blocks
  /// the interaction. No card ids exist on [SuggestionCard], so only the
  /// title travels — ids are never fabricated.
  void onCardOpened(SuggestionCard card) {
    _reportCardInteraction(
      cardTitle: card.title,
      interactionType: 'opened',
      localType: 'suggestion_opened',
      localLabel: card.title,
    );
  }

  /// Record that the user navigated from a suggestion card.
  ///
  /// Same backend-first convention as [onCardOpened]. Cards carry no id and
  /// navigation carries no title, so the route string travels as the card
  /// reference — identical to the local label convention, keeping online
  /// and offline labels equivalent.
  void onNavigated(NavigationRequest request) {
    _reportCardInteraction(
      cardTitle: request.route,
      interactionType: 'navigated',
      localType: 'assistant_navigation',
      localLabel: request.route,
    );
  }

  void _reportCardInteraction({
    required String cardTitle,
    required String interactionType,
    required String localType,
    required String localLabel,
  }) {
    final learning = _learning;
    unawaited(
      _client
          .submitCardFeedback(
            cardTitle: cardTitle,
            interactionType: interactionType,
          )
          .then((confirmed) {
            if (!confirmed) learning?.recordSignal(localType, localLabel);
          }),
    );
  }

  void clear() {
    if (_disposed) return;
    _messages.clear();
    _safeNotify();
  }

  void _safeNotify() {
    if (_disposed) return;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _client.dispose();
    super.dispose();
  }
}

/// Generates a fresh v4-style client idempotency key for one save attempt.
///
/// No new dependency: 122 random bits formatted as UUID text. The backend
/// remains authoritative for idempotency; Flutter only guarantees a fresh
/// key per new attempt.
@visibleForTesting
String newOutfitIdempotencyKey() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 0x0F) | 0x40;
  bytes[8] = (bytes[8] & 0x3F) | 0x80;
  String hex(int v) => v.toRadixString(16).padLeft(2, '0');
  final h = bytes.map(hex).join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-'
      '${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}
