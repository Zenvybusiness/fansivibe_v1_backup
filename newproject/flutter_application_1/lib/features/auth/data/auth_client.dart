import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/features/auth/data/auth_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// HTTP client for real authentication (D-AUTH-1, M1, endpoints #02–05).
///
/// - `register` → `POST /v1/auth/register` (requires a fresh
///   `Idempotency-Key` per attempt; empty keys fail closed with zero
///   network calls — the outfit/today key convention).
/// - `login` → `POST /v1/auth/login`.
/// - `logout` → `POST /v1/auth/logout` with the session token, then the
///   local session is cleared regardless (logout is locally complete
///   even when the server answers 401 for an already-dead session).
/// - `validateSession` → `GET /v1/users/me` (true only on 200 — used
///   for session restoration on app launch).
///
/// Successful register/login persist the issued `accessToken` through
/// [AuthSession] and return [AuthStatus.authenticated]. Failures are
/// typed ([AuthResult]) — never a fake success, never throws, never
/// logs credentials or tokens.
class AuthClient {
  AuthClient({http.Client? client}) : _client = client ?? http.Client();

  static const String baseUrl = String.fromEnvironment(
    'ASSISTANT_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  final http.Client _client;
  static const Duration _timeout = Duration(seconds: 12);

  static const Map<String, String> _jsonHeaders = {
    'Content-Type': 'application/json; charset=UTF-8',
  };

  /// Registers a new account and persists the issued session.
  Future<AuthResult> register({
    required String email,
    required String password,
    String? displayName,
    required String idempotencyKey,
  }) async {
    if (idempotencyKey.isEmpty) {
      debugPrint('Auth register refused: Idempotency-Key is required.');
      return const AuthResult.failure(AuthStatus.invalidInput);
    }
    try {
      final response = await _client
          .post(
            Uri.parse('$baseUrl/v1/auth/register'),
            headers: {..._jsonHeaders, 'Idempotency-Key': idempotencyKey},
            body: jsonEncode({
              'email': email,
              'password': password,
              if (displayName != null) 'displayName': displayName,
            }),
          )
          .timeout(_timeout);
      if (response.statusCode == 201) {
        return await _persistSession(response.body);
      }
      return AuthResult.failure(_failureFor(response.statusCode));
    } catch (error) {
      debugPrint('Auth backend unreachable during register: $error');
      return const AuthResult.failure(AuthStatus.networkError);
    }
  }

  /// Signs in with email + password and persists the issued session.
  Future<AuthResult> login({
    required String email,
    required String password,
  }) async {
    try {
      final response = await _client
          .post(
            Uri.parse('$baseUrl/v1/auth/login'),
            headers: _jsonHeaders,
            body: jsonEncode({'email': email, 'password': password}),
          )
          .timeout(_timeout);
      if (response.statusCode == 200) {
        return await _persistSession(response.body);
      }
      return AuthResult.failure(_failureFor(response.statusCode));
    } catch (error) {
      debugPrint('Auth backend unreachable during login: $error');
      return const AuthResult.failure(AuthStatus.networkError);
    }
  }

  /// Signs out: revokes the server session, then clears the local one.
  ///
  /// The local session is cleared even when the server answers 401
  /// (already-dead session) or is unreachable — logout is locally
  /// complete either way, so no signed-out device keeps a token.
  Future<AuthStatus> logout() async {
    final token = AuthSession.token;
    if (token != null && token.isNotEmpty) {
      try {
        await _client
            .post(
              Uri.parse('$baseUrl/v1/auth/logout'),
              headers: {'Authorization': 'Bearer $token'},
            )
            .timeout(_timeout);
      } catch (error) {
        debugPrint('Auth backend unreachable during logout: $error');
      }
    }
    await AuthSession.clearSession();
    return AuthStatus.signedOut;
  }

  /// Returns true only when the persisted session still authenticates
  /// (session restoration probe on app launch). A 401 also routes
  /// through [AuthSession.notifyUnauthorized] so expiry redirects.
  Future<bool> validateSession() async {
    final token = AuthSession.token;
    if (token == null || token.isEmpty) return false;
    try {
      final response = await _client
          .get(
            Uri.parse('$baseUrl/v1/users/me'),
            headers: {'Authorization': 'Bearer $token'},
          )
          .timeout(_timeout);
      if (response.statusCode == 200) return true;
      if (response.statusCode == 401) AuthSession.notifyUnauthorized();
      return false;
    } catch (error) {
      debugPrint('Auth backend unreachable during validation: $error');
      return false;
    }
  }

  /// Exchanges a social provider token (O-2).
  ///
  /// Always answers [AuthStatus.providerUnavailable] while no external
  /// identity provider is configured: the client never fabricates a
  /// session from an unverified provider token.
  Future<AuthResult> socialSignIn({
    required String provider,
    required String providerToken,
  }) async {
    try {
      final response = await _client
          .post(
            Uri.parse('$baseUrl/v1/auth/social'),
            headers: _jsonHeaders,
            body: jsonEncode({
              'provider': provider,
              'providerToken': providerToken,
            }),
          )
          .timeout(_timeout);
      if (response.statusCode == 200 || response.statusCode == 201) {
        return await _persistSession(response.body);
      }
      return AuthResult.failure(_failureFor(response.statusCode));
    } catch (error) {
      debugPrint('Auth backend unreachable during social sign-in: $error');
      return const AuthResult.failure(AuthStatus.networkError);
    }
  }

  Future<AuthResult> _persistSession(String body) async {
    try {
      final decoded = jsonDecode(body) as Map<String, dynamic>;
      final token = decoded['accessToken'];
      if (token is! String || token.isEmpty) {
        debugPrint('Auth response carried no access token.');
        return const AuthResult.failure(AuthStatus.networkError);
      }
      await AuthSession.saveSession(token);
      final profile = decoded['profile'];
      final displayName = profile is Map<String, dynamic>
          ? profile['displayName'] as String?
          : null;
      final expiresIn = decoded['expiresIn'];
      return AuthResult.authenticated(
        displayName: displayName,
        expiresIn: expiresIn is int ? expiresIn : null,
      );
    } catch (error) {
      debugPrint('Auth response unparseable: $error');
      await AuthSession.clearSession();
      return const AuthResult.failure(AuthStatus.networkError);
    }
  }

  AuthStatus _failureFor(int statusCode) {
    switch (statusCode) {
      case 401:
        return AuthStatus.invalidCredentials;
      case 409:
        return AuthStatus.emailTaken;
      case 422:
        return AuthStatus.invalidInput;
      case 502:
        return AuthStatus.providerUnavailable;
      default:
        return AuthStatus.networkError;
    }
  }

  void dispose() => _client.close();
}

/// Generates a fresh v4-style client idempotency key for one register
/// attempt (feature-local, mirroring the outfit/today key helpers
/// without importing across features: 122 random bits as UUID text).
String newAuthIdempotencyKey() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 0x0F) | 0x40;
  bytes[8] = (bytes[8] & 0x3F) | 0x80;
  String hex(int v) => v.toRadixString(16).padLeft(2, '0');
  final h = bytes.map(hex).join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-'
      '${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}
