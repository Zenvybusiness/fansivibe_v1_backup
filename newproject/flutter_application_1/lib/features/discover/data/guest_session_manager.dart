import 'package:fansivibe/features/discover/data/discover_client.dart';

/// Manages ephemeral client-side guest session identifiers (DISCOVERY-10A).
///
/// Invariants:
/// - Pure client-generated UUIDv4.
/// - Rotates automatically after 30 days of inactivity.
/// - Never collects hardware IDs, GAID, IDFA, IP, or location.
/// - Never merges or stitches guest telemetry into authenticated accounts upon sign-in.
class GuestSessionManager {
  GuestSessionManager._();

  static const int _inactivityThresholdMs = 30 * 24 * 60 * 60 * 1000; // 30 days

  static String? _cachedSessionId;
  static int? _cachedLastActiveMs;

  /// Returns the current active guest session ID, rotating it if inactive for > 30 days.
  static String getSessionId() {
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    if (_cachedSessionId != null && _cachedLastActiveMs != null) {
      if (nowMs - _cachedLastActiveMs! <= _inactivityThresholdMs) {
        _cachedLastActiveMs = nowMs;
        return _cachedSessionId!;
      }
    }

    // Generate new guest session ID
    _cachedSessionId = newDiscoveryEventId();
    _cachedLastActiveMs = nowMs;
    return _cachedSessionId!;
  }

  /// Manually rotate the guest session (e.g. on logout or cache clear).
  static void rotateSession() {
    _cachedSessionId = newDiscoveryEventId();
    _cachedLastActiveMs = DateTime.now().millisecondsSinceEpoch;
  }

  /// Reset state for deterministic tests.
  static void resetForTest({String? initialSessionId, int? initialLastActiveMs}) {
    _cachedSessionId = initialSessionId;
    _cachedLastActiveMs = initialLastActiveMs;
  }
}
