import 'package:fansivibe/shared/utils/local_storage.dart';

/// Canonical auth/session mechanism (D-AUTH-1).
///
/// Every authenticated API client resolves its Bearer token through
/// [effectiveToken] instead of inventing its own token handling: the
/// persisted session token wins when present, otherwise the caller
/// supplies its historical dart-define fallback (so logged-out and
/// test behavior is unchanged).
///
/// - [saveSession]/[clearSession] persist through [LocalStorage]
///   (the project's supported platform mechanism); tokens are never
///   logged.
/// - [notifyUnauthorized] is invoked by clients on HTTP 401: it clears
///   the dead session and fires [onSessionExpired] once so the app
///   layer can redirect to login. No fake identity is ever produced —
///   without a token there is no user.
class AuthSession {
  AuthSession._();

  /// Set by the app layer (app.dart) to navigate to login on expiry.
  /// Null in tests unless a test sets it.
  static void Function()? onSessionExpired;

  static bool _expiryNotified = false;

  /// The persisted session token, or null when signed out.
  static String? get token => LocalStorage.authToken;

  /// True when a session token is persisted.
  static bool get isAuthenticated => token != null && token!.isNotEmpty;

  /// Session-first token resolution for authenticated clients.
  ///
  /// Returns the session token when signed in, else [fallback] (the
  /// client's dart-define default — unchanged logged-out behavior).
  static String effectiveToken(String fallback) {
    final current = token;
    if (current != null && current.isNotEmpty) return current;
    return fallback;
  }

  /// Persists a new session after register/login.
  static Future<void> saveSession(String accessToken) async {
    _expiryNotified = false;
    LocalStorage.authToken = accessToken;
  }

  /// Clears the session (logout). Local journey state is preserved —
  /// only the credential is removed.
  static Future<void> clearSession() async {
    _expiryNotified = false;
    LocalStorage.authToken = null;
  }

  /// Handles an HTTP 401 from any authenticated client: drops the dead
  /// session and notifies once. Safe to call repeatedly and safe
  /// without init (no-op navigation when no handler is set).
  static void notifyUnauthorized() {
    LocalStorage.authToken = null;
    if (_expiryNotified) return;
    _expiryNotified = true;
    onSessionExpired?.call();
  }

  /// Notes an HTTP status from any client: 401 routes through
  /// [notifyUnauthorized]; every other status is ignored. One-line
  /// hook so each client reports unauthorized sessions canonically.
  static void noteStatus(int statusCode) {
    if (statusCode == 401) notifyUnauthorized();
  }

  /// Test-only reset: clears any handler/flag state between tests.
  static void resetForTest() {
    onSessionExpired = null;
    _expiryNotified = false;
  }
}
