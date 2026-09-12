import 'package:fansivibe/shared/auth/auth_session.dart';

/// Typed outcome of an auth operation (D-AUTH-1).
///
/// Mirrors the `PreferenceSyncResult`/`OutfitResult` convention: the UI
/// renders truthful per-outcome copy from this — never a fake login
/// success. No tokens, passwords, or emails travel inside failures.
enum AuthStatus {
  /// Authenticated — [AuthSession.token] now holds the access token.
  authenticated,

  /// Register/login rejected: unknown email or wrong password (the
  /// backend answers a uniform 401 by contract, never distinguishing).
  invalidCredentials,

  /// Register rejected: the email is already registered (409).
  emailTaken,

  /// The request was malformed (422) or a required key was missing.
  invalidInput,

  /// Social sign-in is not available: no external identity provider is
  /// configured in this instantiation (honest 502, never a bypass).
  providerUnavailable,

  /// Backend unreachable or unexpected shape/status.
  networkError,

  /// Signed out and the session cleared.
  signedOut,
}

/// An authenticated session issued by the backend (#02/#04).
class AuthResult {
  const AuthResult._(this.status, {this.displayName, this.expiresIn});

  const AuthResult.authenticated({String? displayName, int? expiresIn})
    : this._(
        AuthStatus.authenticated,
        displayName: displayName,
        expiresIn: expiresIn,
      );

  const AuthResult.failure(AuthStatus status) : this._(status);

  final AuthStatus status;

  /// Caller display name echoed by the backend profile (may be null).
  final String? displayName;

  /// Token lifetime in seconds as issued (`expiresIn`).
  final int? expiresIn;

  bool get isAuthenticated => status == AuthStatus.authenticated;
}
