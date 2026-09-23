import 'package:fansivibe/features/knowledge/data/knowledge_api_models.dart';

/// Distinct presentation lifecycle and error states for fashion reasoning.
enum FashionReasoningStatus {
  /// Initial idle state before a query is submitted.
  idle,

  /// Query is actively being processed by the reasoning service.
  loading,

  /// Successfully received grounded reasoning conclusions.
  success,

  /// Query has insufficient evidence in the knowledge corpus (empty conclusions with missing evidence).
  insufficientEvidence,

  /// Query is out-of-scope / unsupported by the fashion ontology (unsupported == true).
  unsupported,

  /// Network or transport failure (unreachable backend or client socket error).
  apiNetworkError,

  /// AI service temporarily unavailable (HTTP 503).
  aiUnavailable,

  /// AI reasoning request timed out (HTTP 504).
  timeout,

  /// AI response could not be validated against the contract (HTTP 502).
  malformedInvalidResponse,

  /// Request violated contract constraints (HTTP 422).
  contractViolation,

  /// Unexpected server or internal failure (HTTP 500).
  unexpectedError,
}

/// Immutable state snapshot for fashion reasoning presentation.
class FashionReasoningState {
  const FashionReasoningState({
    this.status = FashionReasoningStatus.idle,
    this.response,
    this.failure,
    this.errorMessage,
    this.query = '',
  });

  /// Factory for the initial idle state.
  const FashionReasoningState.idle() : this(status: FashionReasoningStatus.idle);

  /// Factory for the active loading state.
  const FashionReasoningState.loading({required String query})
    : this(status: FashionReasoningStatus.loading, query: query);

  /// Current lifecycle / outcome status.
  final FashionReasoningStatus status;

  /// Validated response payload when available.
  final FashionReasoningResponse? response;

  /// Technical failure type when in an error state.
  final ReasoningFailure? failure;

  /// User-friendly error message (never raw stack traces or internal JSON).
  final String? errorMessage;

  /// The active or last executed user query.
  final String query;

  bool get isIdle => status == FashionReasoningStatus.idle;
  bool get isLoading => status == FashionReasoningStatus.loading;
  bool get isSuccess => status == FashionReasoningStatus.success;
  bool get isInsufficient => status == FashionReasoningStatus.insufficientEvidence;
  bool get isUnsupported => status == FashionReasoningStatus.unsupported;

  bool get isError =>
      status == FashionReasoningStatus.apiNetworkError ||
      status == FashionReasoningStatus.aiUnavailable ||
      status == FashionReasoningStatus.timeout ||
      status == FashionReasoningStatus.malformedInvalidResponse ||
      status == FashionReasoningStatus.contractViolation ||
      status == FashionReasoningStatus.unexpectedError;

  List<ReasoningConclusion> get conclusions =>
      response?.conclusions ?? const [];

  List<String> get uncertainties => response?.uncertainties ?? const [];

  List<String> get missingEvidence => response?.missingEvidence ?? const [];

  List<String> get contradictions => response?.contradictions ?? const [];

  String get confidence => response?.confidence ?? 'unknown';

  ReasoningVersions? get versions => response?.versions;

  FashionReasoningState copyWith({
    FashionReasoningStatus? status,
    FashionReasoningResponse? response,
    ReasoningFailure? failure,
    String? errorMessage,
    String? query,
  }) {
    return FashionReasoningState(
      status: status ?? this.status,
      response: response ?? this.response,
      failure: failure ?? this.failure,
      errorMessage: errorMessage ?? this.errorMessage,
      query: query ?? this.query,
    );
  }
}
