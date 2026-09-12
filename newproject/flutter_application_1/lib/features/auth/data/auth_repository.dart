import 'package:fansivibe/features/auth/data/auth_client.dart';
import 'package:fansivibe/features/auth/data/auth_models.dart';

/// Abstract contract for authentication operations (D-AUTH-1).
///
/// The single seam consumed by the entry/account/profile surfaces:
/// register/login persist the session through [AuthClient] (backed by
/// the canonical [AuthSession]), logout clears it, and
/// [validateSession] probes restoration. No fake identity is ever
/// produced — without a backend-issued token there is no user.
abstract class AuthRepository {
  /// Registers a new account (O-1 `POST /v1/auth/register`).
  ///
  /// [idempotencyKey] is required — one fresh key per attempt (see
  /// [newAuthIdempotencyKey]); an empty key fails closed.
  Future<AuthResult> register({
    required String email,
    required String password,
    String? displayName,
    required String idempotencyKey,
  });

  /// Signs in (O-3 `POST /v1/auth/login`).
  Future<AuthResult> login({
    required String email,
    required String password,
  });

  /// Exchanges a social provider token (O-2 `POST /v1/auth/social`).
  ///
  /// Honestly unavailable while no external identity provider is
  /// configured — always [AuthStatus.providerUnavailable], never a
  /// fabricated session.
  Future<AuthResult> socialSignIn({
    required String provider,
    required String providerToken,
  });

  /// Signs out (O-4 `POST /v1/auth/logout` + local clear).
  Future<AuthStatus> logout();

  /// True only when the persisted session still authenticates.
  Future<bool> validateSession();
}

/// Backend implementation of [AuthRepository].
class AuthRepositoryImpl implements AuthRepository {
  /// Creates an [AuthRepositoryImpl] with an optional client for
  /// testing. Without a client, uses the default [AuthClient].
  AuthRepositoryImpl({AuthClient? client})
    : _client = client ?? AuthClient();

  final AuthClient _client;

  @override
  Future<AuthResult> register({
    required String email,
    required String password,
    String? displayName,
    required String idempotencyKey,
  }) {
    // Verbatim passthrough: account creation, replay semantics, and
    // session persistence stay server-authoritative inside the client.
    return _client.register(
      email: email,
      password: password,
      displayName: displayName,
      idempotencyKey: idempotencyKey,
    );
  }

  @override
  Future<AuthResult> login({
    required String email,
    required String password,
  }) {
    return _client.login(email: email, password: password);
  }

  @override
  Future<AuthResult> socialSignIn({
    required String provider,
    required String providerToken,
  }) {
    return _client.socialSignIn(
      provider: provider,
      providerToken: providerToken,
    );
  }

  @override
  Future<AuthStatus> logout() => _client.logout();

  @override
  Future<bool> validateSession() => _client.validateSession();
}
