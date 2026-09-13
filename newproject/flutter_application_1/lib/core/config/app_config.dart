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

  /// Whether [url] targets a loopback host.
  static bool isLocalhostUrl(String url) =>
      url.contains('localhost') || url.contains('127.0.0.1');

  /// Whether the configured base URL targets a loopback host.
  static bool get isLocalhost => isLocalhostUrl(apiBaseUrl);

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
      return 'Could not reach $apiBaseUrl. '
          'On an Android emulator use http://10.0.2.2:8000, '
          'on a physical device use your computer\u2019s LAN IP '
          '(--dart-define=ASSISTANT_BASE_URL=http://<host>:8000).';
    }
    return 'Could not reach $apiBaseUrl. Check your connection and try again.';
  }
}
