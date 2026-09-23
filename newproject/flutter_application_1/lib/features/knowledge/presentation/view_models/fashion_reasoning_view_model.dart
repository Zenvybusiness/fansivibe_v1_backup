import 'package:flutter/foundation.dart';

import 'package:fansivibe/features/knowledge/data/knowledge_api_models.dart';
import 'package:fansivibe/features/knowledge/data/knowledge_repository.dart';
import 'package:fansivibe/features/knowledge/presentation/models/fashion_reasoning_state.dart';

/// ViewModel managing state transitions for fashion ontology reasoning.
///
/// Follows Fansivibe's MVVM convention with [ChangeNotifier].
/// Guarantees that raw model JSON and raw exception strings never reach the UI.
class FashionReasoningViewModel extends ChangeNotifier {
  FashionReasoningViewModel({KnowledgeRepository? repository})
    : _repository = repository ?? KnowledgeRepositoryImpl();

  final KnowledgeRepository _repository;

  FashionReasoningState _state = const FashionReasoningState.idle();
  FashionReasoningState get state => _state;

  bool _disposed = false;

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

  void _notify() {
    if (!_disposed) {
      notifyListeners();
    }
  }

  /// Resets state back to the idle starting condition.
  void reset() {
    _state = const FashionReasoningState.idle();
    _notify();
  }

  /// Retries the most recent query if one exists.
  Future<void> retry() async {
    if (_state.query.trim().isNotEmpty) {
      await queryReasoning(_state.query);
    }
  }

  /// Submits a user query to the fashion reasoning pipeline.
  Future<void> queryReasoning(
    String query, {
    String? intent,
    ReasoningContextDto? context,
    int maxConclusions = 3,
    bool evidenceOnly = true,
  }) async {
    final trimmed = query.trim();
    if (trimmed.isEmpty || _state.isLoading) return;

    _state = FashionReasoningState.loading(query: trimmed);
    _notify();

    final request = FashionReasoningRequest(
      query: trimmed,
      intent: intent,
      context: context,
      maxConclusions: maxConclusions,
      evidenceOnly: evidenceOnly,
    );

    final result = await _repository.reasonQueryDetailed(request);

    if (_disposed) return;

    if (result.isSuccess && result.response != null) {
      final resp = result.response!;
      if (resp.unsupported) {
        _state = FashionReasoningState(
          status: FashionReasoningStatus.unsupported,
          response: resp,
          query: trimmed,
        );
      } else if (resp.conclusions.isEmpty && resp.missingEvidence.isNotEmpty) {
        _state = FashionReasoningState(
          status: FashionReasoningStatus.insufficientEvidence,
          response: resp,
          query: trimmed,
        );
      } else {
        _state = FashionReasoningState(
          status: FashionReasoningStatus.success,
          response: resp,
          query: trimmed,
        );
      }
    } else {
      final failure = result.failure ?? ReasoningFailure.unknown;
      final status = _mapFailureToStatus(failure);
      final message = _mapFailureToMessage(failure, result.errorMessage);

      _state = FashionReasoningState(
        status: status,
        failure: failure,
        errorMessage: message,
        query: trimmed,
      );
    }

    _notify();
  }

  static FashionReasoningStatus _mapFailureToStatus(ReasoningFailure failure) {
    return switch (failure) {
      ReasoningFailure.serviceUnavailable => FashionReasoningStatus.aiUnavailable,
      ReasoningFailure.timeout => FashionReasoningStatus.timeout,
      ReasoningFailure.malformedOutput =>
        FashionReasoningStatus.malformedInvalidResponse,
      ReasoningFailure.contractViolation =>
        FashionReasoningStatus.contractViolation,
      ReasoningFailure.networkError => FashionReasoningStatus.apiNetworkError,
      ReasoningFailure.unexpected => FashionReasoningStatus.unexpectedError,
      ReasoningFailure.unauthorized => FashionReasoningStatus.unexpectedError,
      ReasoningFailure.rateLimited => FashionReasoningStatus.unexpectedError,
      ReasoningFailure.invalidInput => FashionReasoningStatus.contractViolation,
      ReasoningFailure.unknown => FashionReasoningStatus.unexpectedError,
    };
  }

  static String _mapFailureToMessage(
    ReasoningFailure failure,
    String? backendMessage,
  ) {
    return switch (failure) {
      ReasoningFailure.serviceUnavailable =>
        'The fashion reasoning service is temporarily unavailable. Please try again shortly.',
      ReasoningFailure.timeout =>
        'The reasoning request timed out while analyzing fashion sources. Please try again.',
      ReasoningFailure.malformedOutput =>
        'The reasoning response could not be validated against the fashion knowledge contract.',
      ReasoningFailure.contractViolation =>
        backendMessage != null && backendMessage.isNotEmpty
            ? 'The request could not be processed: $backendMessage'
            : 'The request could not be processed due to contract constraints.',
      ReasoningFailure.networkError =>
        'Unable to reach the reasoning service. Please check your network connection.',
      ReasoningFailure.unauthorized =>
        'Authentication required to access reasoning service.',
      ReasoningFailure.rateLimited =>
        'Reasoning service request limit reached. Please wait a moment.',
      ReasoningFailure.unexpected || ReasoningFailure.unknown || ReasoningFailure.invalidInput =>
        'An unexpected reasoning service error occurred. Please try again later.',
    };
  }
}
