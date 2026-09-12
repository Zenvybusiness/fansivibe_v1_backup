import 'dart:typed_data';

/// Sanitizer for error messages, stack traces, and metadata.
///
/// Ensures no secrets, tokens, passwords, image bytes, wardrobe photos,
/// or sensitive personal user data are leaked into error reports or logs.
abstract final class ErrorSanitizer {
  ErrorSanitizer._();

  static final Set<String> _sensitiveKeyExact = {
    'authorization',
    'auth',
    'token',
    'access_token',
    'refresh_token',
    'password',
    'secret',
    'auth_secret',
    'api_key',
    'apikey',
    'key',
    'cookie',
    'cookies',
    'session',
    'session_id',
    'sessionid',
    'image',
    'photo',
    'bytes',
    'file',
    'wardrobe_photo',
    'wardrobe_image',
    'face_profile',
    'face_data',
    'user_data',
    'email',
    'credit_card',
    'pin',
  };

  static final RegExp _bearerRegex = RegExp(
    r'Bearer\s+[A-Za-z0-9_\-\.]+',
    caseSensitive: false,
  );

  static final RegExp _jwtRegex = RegExp(
    r'eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+',
  );

  static final RegExp _paramSecretRegex = RegExp(
    r'(password|secret|token|access_token|refresh_token|api_key)=([^&\s]+)',
    caseSensitive: false,
  );

  static final RegExp _jsonSecretRegex = RegExp(
    r'"(password|secret|token|access_token|refresh_token|auth_secret|api_key)":\s*"[^"]*"',
    caseSensitive: false,
  );

  /// Checks whether a key name represents sensitive information.
  static bool isSensitiveKey(String key) {
    final lower = key.trim().toLowerCase();
    if (_sensitiveKeyExact.contains(lower)) {
      return true;
    }
    return lower.contains('password') ||
        lower.contains('token') ||
        lower.contains('secret') ||
        lower.contains('auth_') ||
        lower.contains('_auth') ||
        lower.contains('apikey') ||
        lower.contains('api_key') ||
        lower.contains('wardrobe_photo') ||
        lower.contains('wardrobe_image') ||
        lower.contains('image_bytes') ||
        lower.contains('face_profile');
  }

  /// Sanitizes an arbitrary string, redacting tokens, JWTs, and passwords.
  static String sanitizeString(String input) {
    if (input.isEmpty) return input;

    var result = input;
    result = result.replaceAllMapped(_bearerRegex, (match) => 'Bearer [REDACTED]');
    result = result.replaceAllMapped(_jwtRegex, (match) => '[REDACTED_JWT]');
    result = result.replaceAllMapped(_paramSecretRegex, (match) => '${match.group(1)}=[REDACTED]');
    result = result.replaceAllMapped(_jsonSecretRegex, (match) => '"${match.group(1)}": "[REDACTED]"');

    if (result.length > 2048) {
      result = '${result.substring(0, 2048)}... [truncated]';
    }

    return result;
  }

  /// Sanitizes an arbitrary value (map, list, bytes, string, or primitive).
  static dynamic sanitizeValue(dynamic value) {
    if (value == null) return null;

    if (value is Uint8List) {
      return '[BINARY_DATA: ${value.length} bytes]';
    }
    if (value is List<int>) {
      return '[BYTES: ${value.length} items]';
    }
    if (value is Map<String, dynamic>) {
      return sanitizeMap(value);
    }
    if (value is Map) {
      final stringMap = <String, dynamic>{};
      for (final entry in value.entries) {
        stringMap[entry.key.toString()] = entry.value;
      }
      return sanitizeMap(stringMap);
    }
    if (value is Iterable) {
      return value.map((item) => sanitizeValue(item)).toList();
    }
    if (value is String) {
      return sanitizeString(value);
    }

    return value;
  }

  /// Recursively sanitizes a metadata map, redacting sensitive keys and values.
  static Map<String, dynamic> sanitizeMap(Map<String, dynamic>? data) {
    if (data == null || data.isEmpty) {
      return <String, dynamic>{};
    }

    final sanitized = <String, dynamic>{};
    for (final entry in data.entries) {
      final key = entry.key;
      final val = entry.value;

      if (isSensitiveKey(key)) {
        sanitized[key] = '[REDACTED]';
      } else {
        sanitized[key] = sanitizeValue(val);
      }
    }
    return sanitized;
  }
}
