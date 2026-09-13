import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Secure persistence for the auth session token (21.2, H2).
///
/// The JWT no longer lives in plaintext `SharedPreferences` on devices
/// that provide platform secure storage (Android EncryptedSharedPreferences
/// via Keystore, iOS Keychain, and the respective desktop backends; Web
/// falls back to the platform's origin storage — see below).
///
/// Design (why it cannot break existing behavior):
/// - All platform I/O is guarded: any secure-storage failure (missing
///   plugin in unit tests, unsupported platform, device error) falls
///   back to the historical `LocalStorage.authToken` path, so tests and
///   development environments keep working with zero setup.
/// - Reads are synchronous-safe: an in-memory cache warmed by [init]
///   (called from `main()` before `runApp()`); when the cache was never
///   warmed (unit/widget tests), reads fall through to `LocalStorage`.
/// - No plaintext duplication: a successful secure write deletes the
///   legacy preferences copy; [migrateIfNeeded] moves a pre-existing
///   preferences token into secure storage once, then deletes the copy.
/// - Tokens are never logged anywhere.
class SecureTokenStorage {
  SecureTokenStorage._();

  static const String _tokenKey = 'fansivibe_auth_token';

  static FlutterSecureStorage? _secure;
  static bool _initialized = false;
  static String? _cachedToken;

  /// Whether [init] has warmed the cache (false in unit tests by design).
  @visibleForTesting
  static bool get isInitialized => _initialized;

  /// Warms the cache; migrates a legacy preferences token when present.
  ///
  /// Called once from `main()` after `LocalStorage.init`. Never throws:
  /// platform failures leave the cache empty and the `LocalStorage`
  /// fallback path active.
  static Future<void> init({FlutterSecureStorage? secure}) async {
    _secure = secure ?? const FlutterSecureStorage();
    String? secured;
    try {
      secured = await _secure!.read(key: _tokenKey);
    } catch (error) {
      debugPrint('Secure token storage unavailable; using app storage.');
      _initialized = false;
      _cachedToken = null;
      return;
    }
    _initialized = true;
    if (secured != null && secured.isNotEmpty) {
      _cachedToken = secured;
      // A secured token wins: drop any stale plaintext copy.
      LocalStorage.authToken = null;
      return;
    }
    await migrateIfNeeded();
  }

  /// Moves a legacy preferences token into secure storage (once).
  ///
  /// No-op when secure storage is unreachable, when no legacy token
  /// exists, or when a secured token already exists. Never throws.
  static Future<void> migrateIfNeeded() async {
    final secure = _secure;
    if (secure == null) return;
    try {
      final existing = await secure.read(key: _tokenKey);
      if (existing != null && existing.isNotEmpty) {
        _cachedToken = existing;
        LocalStorage.authToken = null;
        return;
      }
      final legacy = LocalStorage.authToken;
      if (legacy == null || legacy.isEmpty) {
        _cachedToken = null;
        return;
      }
      await secure.write(key: _tokenKey, value: legacy);
      LocalStorage.authToken = null;
      _cachedToken = legacy;
    } catch (_) {
      // Stay on the legacy path; retry on next launch.
      _cachedToken = null;
    }
  }

  /// Synchronous token read for [AuthSession].
  ///
  /// Warmed cache wins; otherwise the legacy preferences value (unit
  /// tests and pre-init callers). Never throws.
  static String? get currentToken {
    if (_initialized) return _cachedToken;
    return LocalStorage.authToken;
  }

  /// Persists [token]; prefers secure storage, falls back to preferences.
  ///
  /// On secure success the preferences copy is removed (no duplication).
  /// Never throws, never logs the token.
  static Future<void> writeToken(String token) async {
    _cachedToken = token;
    final secure = _secure;
    if (secure != null) {
      try {
        await secure.write(key: _tokenKey, value: token);
        LocalStorage.authToken = null;
        return;
      } catch (_) {
        // Fall through to the legacy path below.
      }
    }
    LocalStorage.authToken = token;
  }

  /// Removes the token from every backing store. Never throws.
  static Future<void> deleteToken() async {
    _cachedToken = null;
    LocalStorage.authToken = null;
    final secure = _secure;
    if (secure == null) return;
    try {
      await secure.delete(key: _tokenKey);
    } catch (_) {
      // Preferences copy is already gone; nothing left to do.
    }
  }

  /// Synchronous clear for 401 handling ([AuthSession.notifyUnauthorized]).
  ///
  /// Drops the cache and the preferences copy immediately; schedules the
  /// secure delete without awaiting (callers are synchronous).
  static void clearSync() {
    _cachedToken = null;
    LocalStorage.authToken = null;
    final secure = _secure;
    if (secure == null) return;
    // Fire-and-forget: failures leave no plaintext behind (the prefs
    // copy is already removed) and retry on next write/delete.
    unawaited(
      () async {
        try {
          await secure.delete(key: _tokenKey);
        } catch (_) {
          // Intentionally ignored (see above).
        }
      }(),
    );
  }

  /// Test-only reset: drops the cache/init state between tests.
  /// (Called from [AuthSession.resetForTest]; matches the
  /// `LocalStorage.resetForTest` convention.)
  static void resetForTest() {
    _secure = null;
    _initialized = false;
    _cachedToken = null;
  }
}
