import 'package:shared_preferences/shared_preferences.dart';

/// Local storage for persisting user journey state across app launches.
/// Wraps shared_preferences with typed getters/setters using only supported APIs.
class LocalStorage {
  LocalStorage._();

  static SharedPreferences? _prefs;

  /// Whether LocalStorage has been initialized with a SharedPreferences instance.
  static bool get isInitialized => _prefs != null;

  /// Initialize storage with [prefs] instance (typically in app startup).
  static void init({required SharedPreferences prefs}) {
    _prefs = prefs;
  }

  /// Test-only reset: drops the prefs reference so tests can simulate
  /// a fresh cold start. Production always initializes once in main().
  static void resetForTest() {
    _prefs = null;
  }

  /// ----- Onboarding & Session -----

  static bool get onboardingComplete =>
      _prefs?.getBool('onboarding_complete') ?? false;
  static set onboardingComplete(bool value) {
    _prefs?.setBool('onboarding_complete', value);
  }

  static String? get displayName =>
      _prefs?.getString('display_name');
  static set displayName(String? value) {
    if (_prefs == null) return;
    if (value != null) {
      _prefs!.setString('display_name', value);
    } else {
      _prefs!.remove('display_name');
    }
  }

  static String? get vibe =>
      _prefs?.getString('vibe');
  static set vibe(String? value) {
    if (_prefs == null) return;
    if (value != null) {
      _prefs!.setString('vibe', value);
    } else {
      _prefs!.remove('vibe');
    }
  }

  static bool get savedLocally =>
      _prefs?.getBool('saved_locally') ?? false;
  static set savedLocally(bool value) {
    _prefs?.setBool('saved_locally', value);
  }

  static bool get analysisCached =>
      _prefs?.getBool('analysis_cached') ?? false;
  static set analysisCached(bool value) {
    _prefs?.setBool('analysis_cached', value);
  }

  /// ----- Analysis Results Cache -----

  static Map<String, dynamic>? get analysisResult {
    if (_prefs == null) return null;
    final raw = _prefs!.getStringList('analysis_result');
    if (raw == null || raw.isEmpty) return null;
    return _decodeStringList(raw);
  }
  static set analysisResult(Map<String, dynamic>? value) {
    if (_prefs == null) return;
    if (value == null) {
      _prefs!.setStringList('analysis_result', []);
    } else {
      _prefs!.setStringList('analysis_result', _encodeMap(value));
    }
  }

  static List<String> get savedLookIds =>
      _prefs?.getStringList('saved_look_ids') ?? [];
  static set savedLookIds(List<String> value) {
    _prefs?.setStringList('saved_look_ids', value);
  }

  /// ----- Capability State -----

  static Map<String, bool> get capabilityState {
    if (_prefs == null) return {};
    final raw = _prefs!.getStringList('capability_state');
    if (raw == null || raw.isEmpty) return {};
    return _decodeCapabilityState(raw);
  }
  static set capabilityState(Map<String, bool> value) {
    if (_prefs == null) return;
    _prefs!.setStringList('capability_state', _encodeCapabilityState(value));
  }

  /// ----- User Profile -----

  static Map<String, dynamic> get userProfile {
    if (_prefs == null) return {};
    final raw = _prefs!.getStringList('user_profile');
    if (raw == null || raw.isEmpty) return {};
    return _decodeStringList(raw);
  }
  static set userProfile(Map<String, dynamic> value) {
    if (_prefs == null) return;
    _prefs!.setStringList('user_profile', _encodeMap(value));
  }

  /// ----- Helper methods -----

  static List<String> _encodeMap(Map<String, dynamic> map) {
    return map.entries
        .map((e) => '${e.key}:${_encodeValue(e.value)}')
        .toList();
  }

  static String _encodeValue(dynamic value) {
    if (value is String) return value;
    if (value is int) return value.toString();
    if (value is double) return value.toString();
    if (value is bool) return value.toString();
    return value.toString();
  }

  static Map<String, dynamic> _decodeStringList(List<String> list) {
    final result = <String, dynamic>{};
    for (final item in list) {
      final colonIndex = item.indexOf(':');
      if (colonIndex < 0) continue;
      final key = item.substring(0, colonIndex);
      final valueStr = item.substring(colonIndex + 1);
      // Try to parse as int
      if (int.tryParse(valueStr) != null) {
        result[key] = int.parse(valueStr);
      }
      // Try to parse as double
      else if (double.tryParse(valueStr) != null) {
        result[key] = double.parse(valueStr);
      }
      // Try to parse as bool
      else if (valueStr.toLowerCase() == 'true') {
        result[key] = true;
      } else if (valueStr.toLowerCase() == 'false') {
        result[key] = false;
      }
      // Keep as string
      else {
        result[key] = valueStr;
      }
    }
    return result;
  }

  static Map<String, bool> _decodeCapabilityState(List<String> raw) {
    final result = <String, bool>{};
    for (final item in raw) {
      final colonIndex = item.indexOf(':');
      if (colonIndex < 0) continue;
      final key = item.substring(0, colonIndex);
      final valueStr = item.substring(colonIndex + 1);
      result[key] = valueStr.toLowerCase() == 'true';
    }
    return result;
  }

  static List<String> _encodeCapabilityState(Map<String, bool> state) {
    return state.entries
        .map((e) => '${e.key}:${e.value.toString()}')
        .toList();
  }

  /// ----- Auth Session (D-AUTH-1) -----
  ///
  /// Persists the current access token using the project's supported
  /// platform mechanism (shared_preferences). Null-safe: reads are null
  /// without init, writes are dropped without init — callers fall back
  /// to the per-client dart-define token (existing test convention).
  /// Tokens are never logged anywhere (ER-4).
  static String? get authToken => _prefs?.getString('auth_token');
  static set authToken(String? value) {
    if (_prefs == null) return;
    if (value != null) {
      _prefs!.setString('auth_token', value);
    } else {
      _prefs!.remove('auth_token');
    }
  }

  /// Clear all persisted journey state (for onboarding reset or logout)
  static void clear() {
    _prefs?.clear();
  }
}