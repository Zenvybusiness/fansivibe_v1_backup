/// Central application configuration for Fansivibe.
///
/// In production, builds targeting physical devices must supply:
/// `--dart-define=ASSISTANT_BASE_URL=https://<your-backend-host>`
///
/// If omitted, defaults to `http://localhost:8000` for local dev/testing.
abstract final class AppConfig {
  AppConfig._();

  static const String apiBaseUrl = String.fromEnvironment(
    'ASSISTANT_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  static bool get isLocalhost =>
      apiBaseUrl.contains('localhost') || apiBaseUrl.contains('127.0.0.1');

  static bool get isHttps => apiBaseUrl.startsWith('https://');
}
