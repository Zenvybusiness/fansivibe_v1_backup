import 'package:flutter/foundation.dart';

/// Central application configuration for Fansivibe (P0-4).
///
/// Single authoritative API base URL for all backend clients.
///
/// - Local development / tests: default `http://localhost:8000`, or
///   override with `--dart-define=ASSISTANT_BASE_URL=...`.
/// - Production: build with BOTH
///   `--dart-define=PRODUCTION=true` and
///   `--dart-define=ASSISTANT_BASE_URL=https://<your-backend-host>`.
///   No production domain is hardcoded here (none exists yet).
///
/// Production never silently falls back to localhost and never uses
/// cleartext HTTP: [validateOrThrow] fails fast with a clear [StateError]
/// instead of issuing unusable network requests. `main()` calls it at
/// startup before `runApp()`.
abstract final class AppConfig {
  AppConfig._();

  /// Authoritative API base URL (dart-define configurable).
  static const String apiBaseUrl = String.fromEnvironment(
    'ASSISTANT_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  /// True for production builds (`--dart-define=PRODUCTION=true`).
  /// Development and tests default to false so localhost keeps working.
  static const bool isProduction = bool.fromEnvironment(
    'PRODUCTION',
    defaultValue: false,
  );

  /// Production reasoning request deadline (Phase 3AL timeout hierarchy).
  ///
  /// Ollama runs with a 60s inference limit, backend handler has a 65s deadline,
  /// and the Flutter client waits 75s to allow truthful backend 504 responses to arrive.
  static const Duration reasoningTimeout = Duration(
    seconds: int.fromEnvironment('REASONING_TIMEOUT_S', defaultValue: 75),
  );

  /// Standard knowledge catalog read timeout (default 12 seconds).
  static const Duration defaultApiTimeout = Duration(
    seconds: int.fromEnvironment('API_TIMEOUT_S', defaultValue: 12),
  );

  /// Whether [url] targets a loopback host.
  static bool isLocalhostUrl(String url) =>
      url.contains('localhost') || url.contains('127.0.0.1');

  /// Whether the configured base URL targets a loopback host.
  static bool get isLocalhost => isLocalhostUrl(apiBaseUrl);

  /// Android emulator loopback alias for the dev-machine host.
  ///
  /// Inside an Android emulator, `localhost`/`127.0.0.1` points at the
  /// emulated device itself — never the Windows/macOS host running the
  /// backend. The emulator's virtual router exposes the host loopback as
  /// `10.0.2.2`.
  static const String androidEmulatorHost = '10.0.2.2';

  /// Resolves the API base URL for the current runtime platform.
  ///
  /// - Android (non-web) + loopback `apiBaseUrl` → host rewritten to
  ///   [androidEmulatorHost], preserving scheme/port/path. Any port works
  ///   (`:8000`, `:18000`, ...), so no port is hardcoded here.
  /// - Everywhere else (web, desktop, physical device with a LAN IP,
  ///   production HTTPS) → [apiBaseUrl] unchanged.
  ///
  /// The optional parameters exist so tests can exercise the mapping
  /// without running on a device.
  static String resolveApiBaseUrl({
    String? baseUrl,
    TargetPlatform? platform,
    bool? isWeb,
  }) {
    final String url = baseUrl ?? apiBaseUrl;
    final bool web = isWeb ?? kIsWeb;
    if (web) return url;
    final TargetPlatform current = platform ?? defaultTargetPlatform;
    if (current != TargetPlatform.android) return url;
    if (!isLocalhostUrl(url)) return url;
    final Uri? uri = Uri.tryParse(url);
    if (uri == null || !uri.hasAuthority) return url;
    return uri.replace(host: androidEmulatorHost).toString();
  }

  /// Platform-resolved API base URL (see [resolveApiBaseUrl]).
  static String get resolvedApiBaseUrl => resolveApiBaseUrl();

  /// Whether [url] uses HTTPS.
  static bool isHttpsUrl(String url) => url.startsWith('https://');

  /// Whether the configured base URL uses HTTPS.
  static bool get isHttps => isHttpsUrl(apiBaseUrl);

  /// Validates the API configuration, failing clearly in production.
  ///
  /// - Non-production: always passes (localhost + HTTP allowed for dev).
  /// - Production: throws [StateError] when the URL is missing, targets
  ///   localhost, is not HTTPS, or is otherwise unparsable — never a
  ///   silent fallback to an unusable endpoint.
  ///
  /// The optional parameters exist so tests can exercise the production
  /// rules without recompiling with different dart-defines.
  static void validateOrThrow({String? baseUrl, bool? production}) {
    final String url = baseUrl ?? apiBaseUrl;
    final bool prod = production ?? isProduction;
    if (!prod) return;
    if (url.isEmpty) {
      throw StateError(
        'PRODUCTION build requires '
        '--dart-define=ASSISTANT_BASE_URL=https://<your-backend-host> '
        '(missing or empty). Refusing to start with an unusable endpoint.',
      );
    }
    if (isLocalhostUrl(url)) {
      throw StateError(
        'PRODUCTION build must not use localhost ($url). Supply '
        '--dart-define=ASSISTANT_BASE_URL=https://<your-backend-host>.',
      );
    }
    if (!isHttpsUrl(url)) {
      throw StateError(
        'PRODUCTION API base URL must use HTTPS ($url). Supply '
        '--dart-define=ASSISTANT_BASE_URL=https://<your-backend-host>.',
      );
    }
    final Uri? uri = Uri.tryParse(url);
    if (uri == null || !uri.hasScheme || !uri.hasAuthority) {
      throw StateError(
        'PRODUCTION API base URL is invalid ($url). Supply '
        '--dart-define=ASSISTANT_BASE_URL=https://<your-backend-host>.',
      );
    }
  }

  /// Returns the validated API base URL (throws in production when
  /// misconfigured — see [validateOrThrow]).
  static String requireApiBaseUrl() {
    validateOrThrow();
    return apiBaseUrl;
  }

  /// Truthful connection hint for error surfaces (Phase 22, Step 2).
  ///
  /// Never changes routing — purely diagnostic copy so a failed API
  /// connection tells the user what was attempted and how to fix the
  /// development address. `localhost` reaches the dev machine from
  /// Chrome, but from an Android emulator/device it points at the
  /// device itself: use `10.0.2.2` (emulator loopback) or the dev
  /// machine LAN IP via
  /// `--dart-define=ASSISTANT_BASE_URL=http://<host>:8000`.
  static String get connectionHint {
    if (isLocalhost) {
      final int? port = Uri.tryParse(apiBaseUrl)?.port;
      final String emulatorUrl = (port != null && port > 0)
          ? 'http://$androidEmulatorHost:$port'
          : 'http://$androidEmulatorHost:8000';
      return 'Could not reach $apiBaseUrl. '
          'On an Android emulator use $emulatorUrl, '
          'on a physical device use your computer\u2019s LAN IP '
          '(--dart-define=ASSISTANT_BASE_URL=http://<host>:${(port != null && port > 0) ? port : 8000}).';
    }
    return 'Could not reach $apiBaseUrl. Check your connection and try again.';
  }
}
