
/// Signature for analytics event callbacks.
typedef AnalyticsEventHandler = void Function(Map<String, dynamic> event);

/// Analytics service that emits the six approved experiment events.
///
/// This service is deliberately non-blocking. Calls should never await or
/// block critical business operations. Events are dispatched fire-and-forget.
class AnalyticsService {
  AnalyticsService._internal();

  static final AnalyticsService _instance = AnalyticsService._internal();
  static AnalyticsService get instance => _instance;

  factory AnalyticsService() => _instance;

  /// Whether experiment event dispatching is enabled.
  ///
  /// When [isExperimentMode] is false, experiment events are no-ops.
  /// This flag allows the client to disable experiment tracking when using
  /// mock data, preventing contamination of experimental observations.
  bool _experimentMode = true;

  set experimentMode(bool value) {
    _experimentMode = value;
  }

  bool get experimentMode => _experimentMode;

  /// Subscription handlers for each event type.
  ///
  /// Listeners can observe events if they wish; the service itself does not
  /// enforce any particular listening behavior. Handlers are optional and
  /// fire-and-forget by design.
  final List<AnalyticsEventHandler> _handlers = [];

  /// Add an event handler (optional, for observability).
  void addHandler(AnalyticsEventHandler handler) {
    _handlers.add(handler);
  }

  /// Emit an experiment event only when experiment mode is enabled and the
  /// source is real (not mock). This is the primary gate for mock
  /// contamination protection.
  ///
  /// If [fromMock] is true, the event is suppressed unless [force] is true.
  /// Typically [force] should remain false to respect the real/mock boundary.
  void _emitExperimentEvent(Map<String, dynamic> event, {bool fromMock = false, bool force = false}) {
    if (!force && fromMock) {
      // Mock contamination protection: suppress experiment events when
      // the result came from offline mock data.
      return;
    }
    if (!_experimentMode) {
      return;
    }
    for (final handler in _handlers) {
      try {
        handler(event);
      } catch (_) {
        // Never let a handler failure break the product flow.
      }
    }
  }

  /// Emit any event (experiment or not). Experiment-gated events should
  /// use [_emitExperimentEvent]; this is a general-purpose emit.
  void _emitEvent(Map<String, dynamic> event) {
    for (final handler in _handlers) {
      try {
        handler(event);
      } catch (_) {
        // Never let a handler failure break the product flow.
      }
    }
  }

  /// Fire-and-forget: emit an [appearance_scan_started] event.
  ///
  /// Includes [camera_source] and [image_quality] per the approved contract.
  /// Image quality uses the safest supported value when the current code
  /// cannot reliably determine lighting/resolution; uses null if unavailable.
  void emitAppearanceScanStarted({
    required String cameraSource,
    required String? imageQuality,
  }) {
    final event = <String, dynamic>{
      'name': 'appearance_scan_started',
      'camera_source': cameraSource,
      'image_quality': imageQuality,
    };
    _emitExperimentEvent(event, fromMock: false);
  }

  /// Fire-and-forget: emit an [appearance_scan_completed] event.
  ///
  /// Includes [runStatus], [errorCode] when applicable, and [pollAttempts].
  /// Only emitted once per analysis run when the run reaches a terminal state.
  void emitAppearanceScanCompleted({
    required String runStatus,
    String? errorCode,
    int pollAttempts = 0,
  }) {
    // Validate run_status is one of the allowed values
    final validStatuses = {'completed', 'failed', 'timeout'};
    final safeStatus = validStatuses.contains(runStatus) ? runStatus : 'completed';

    final event = <String, dynamic>{
      'name': 'appearance_scan_completed',
      'run_status': safeStatus,
      'error_code': errorCode,
      'poll_attempts': pollAttempts,
    };
    _emitExperimentEvent(event, fromMock: false);
  }

  /// Fire-and-forget: emit a [recommendations_viewed] event.
  ///
  /// Only emitted when a REAL backend recommendation is displayed, not mock/
  /// fallback. The [isMock] parameter allows the caller to tag the source;
  /// the service suppresses the event when [isMock] is true and experiment
  /// mode is on (mock contamination protection).
  ///
  /// Properties per approved contract:
  /// - recommendation_id: the unique ID of the recommended look
  /// - confidence_score: confidence score in [0,1] from the backend
  /// - has_explanation: whether an explanation was included with the recommendation
  /// - top_style_name: the name of the top recommended style
  void emitRecommendationsViewed({
    required String recommendationId,
    required double confidenceScore,
    required bool hasExplanation,
    required String topStyleName,
    bool isMock = false,
  }) {
    final event = <String, dynamic>{
      'name': 'recommendations_viewed',
      'recommendation_id': recommendationId,
      'confidence_score': confidenceScore,
      'has_explanation': hasExplanation,
      'top_style_name': topStyleName,
    };
    _emitExperimentEvent(event, fromMock: isMock);
  }

  /// Fire-and-forget: emit an [explanation_viewed] event.
  ///
  /// Emitted when the explanation is genuinely considered visible to the user.
  /// If reliable visibility detection already exists, reuse it. If not,
  /// implement the smallest reliable visibility mechanism.
  ///
  /// Includes [explanationText] and [timeInView] if reliably trackable.
  /// If time_in_view cannot be reliably measured, uses null and documents
  /// the limitation per the approved contract.
  void emitExplanationViewed({
    required String explanationText,
    Duration? timeInView,
  }) {
    final event = <String, dynamic>{
      'name': 'explanation_viewed',
      'explanation_text': explanationText,
      'time_in_view': timeInView?.inMilliseconds,
    };
    _emitEvent(event);
  }

  /// Fire-and-forget: emit a [recommendation_selected] event.
  ///
  /// Emits when the user makes the decision: [action] = save or dismiss.
  /// Do NOT classify arbitrary navigation as dismiss unless the existing
  /// contract explicitly supports it.
  ///
  /// Properties per approved contract:
  /// - action: either 'save' or 'dismiss' (KEEP AS ONE EVENT, do NOT split)
  /// - recommendation_id: the ID of the recommendation being acted upon
  /// - confidence_at_selection: the confidence score at the moment of selection
  void emitRecommendationSelected({
    required String action, // 'save' or 'dismiss'
    required String recommendationId,
    required double confidenceAtSelection,
  }) {
    final event = <String, dynamic>{
      'name': 'recommendation_selected',
      'action': action,
      'recommendation_id': recommendationId,
      'confidence_at_selection': confidenceAtSelection,
    };
    _emitExperimentEvent(event, fromMock: false);
  }

  /// Fire-and-forget: emit a [recommendation_saved] event.
  ///
   /// This event must observe the authoritative save result. Success means
  /// POST /v1/looks/saved returned 201 AND TRX-3 was committed AND look_saved
  /// signal was committed. Failure means the save operation did not succeed.
  ///
  /// Must NOT report success because a button was tapped, a snackbar was
  /// displayed, or a request was started. Analytics must reflect actual
  /// save outcome.
  ///
  /// Properties per approved contract:
  /// - save_success: true when save succeeded, false when it failed
  /// - idempotency_key: the key used for the save operation
  /// - look_saved_signal_committed: whether the look_saved signal was committed
  /// - snackbar_shown: whether the save snackbar was displayed to the user
  void emitRecommendationSaved({
    required bool saveSuccess,
    required String idempotencyKey,
    required bool lookSavedSignalCommitted,
    required bool snackbarShown,
  }) {
    final event = <String, dynamic>{
      'name': 'recommendation_saved',
      'save_success': saveSuccess,
      'idempotency_key': idempotencyKey,
      'look_saved_signal_committed': lookSavedSignalCommitted,
      'snackbar_shown': snackbarShown,
    };
    _emitExperimentEvent(event, fromMock: false);
  }

  /// Disable experiment event dispatching. Used when operating in mock-only
  /// mode to prevent mock data from contaminating experimental observations.
  void disableExperimentMode() {
    _experimentMode = false;
  }

  /// Re-enable experiment event dispatching.
  void enableExperimentMode() {
    _experimentMode = true;
  }
}