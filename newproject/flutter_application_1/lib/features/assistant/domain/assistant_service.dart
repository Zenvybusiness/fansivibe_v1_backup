import 'package:flutter/foundation.dart';

import 'package:fansivibe/features/assistant/data/assistant_client.dart';
import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/assistant/data/offline_assistant.dart';
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

  /// Record that the user opened a suggestion so the model can learn from it.
  void onCardOpened(SuggestionCard card) {
    _learning?.recordSignal('suggestion_opened', card.title);
  }

  void onNavigated(NavigationRequest request) {
    _learning?.recordSignal('assistant_navigation', request.route);
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
