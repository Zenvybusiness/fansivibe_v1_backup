import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/features/profile/data/user_profile_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// HTTP client for the user profile surface (endpoint #06 `GET /v1/users/me`).
///
/// Follows the same pattern as [SavedLooksClient] and other repository clients:
/// connects to the canonical backend, checks session authentication, and
/// safely handles network timeouts or errors without fabricating fake profiles.
class UserProfileClient {
  UserProfileClient({http.Client? client}) : _client = client ?? http.Client();

  /// Canonical base URL from [AppConfig.apiBaseUrl].
  static const String baseUrl = AppConfig.apiBaseUrl;

  static const String _devTokenDefault = String.fromEnvironment(
    'FANSIVIBE_DEV_TOKEN',
    defaultValue: 'dev',
  );

  /// Session-first Bearer token: persisted session wins; default covers
  /// tests or unconfigured environments.
  static String get _devToken => AuthSession.effectiveToken(_devTokenDefault);

  final http.Client _client;
  static const Duration _timeout = Duration(seconds: 10);

  /// Fetches the authenticated user's authoritative profile from `GET /v1/users/me`.
  ///
  /// Returns [UserProfile] on 200, or `null` when the backend is unreachable,
  /// token is expired/invalid (401), or profile does not exist (404).
  Future<UserProfile?> getProfile() async {
    try {
      final uri = Uri.parse('$baseUrl/v1/users/me');
      final response = await _client
          .get(
            uri,
            headers: {
              'Authorization': 'Bearer $_devToken',
              'Accept': 'application/json',
            },
          )
          .timeout(_timeout);

      AuthSession.noteStatus(response.statusCode);

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return UserProfile.fromJson(decoded);
      }
      debugPrint(
        'User profile API GET /v1/users/me responded ${response.statusCode}: ${response.body}',
      );
      return null;
    } catch (error) {
      debugPrint('User profile backend unreachable during getProfile: $error');
      return null;
    }
  }

  /// Updates the authenticated user's preferences, style archetype, or settings
  /// via `PATCH /v1/users/me`.
  ///
  /// Returns the fresh [UserProfile] on 200, or `null` on failure.
  Future<UserProfile?> updateProfile({
    List<String>? preferredOccasions,
    String? styleType,
    Map<String, dynamic>? settings,
  }) async {
    try {
      final uri = Uri.parse('$baseUrl/v1/users/me');
      final Map<String, dynamic> body = {};
      if (preferredOccasions != null) {
        body['preferredOccasions'] = preferredOccasions;
      }
      if (styleType != null && styleType.trim().isNotEmpty) {
        body['styleType'] = styleType.trim();
      }
      if (settings != null && settings.isNotEmpty) {
        body['settings'] = settings;
      }

      final response = await _client
          .patch(
            uri,
            headers: {
              'Authorization': 'Bearer $_devToken',
              'Content-Type': 'application/json',
              'Accept': 'application/json',
            },
            body: jsonEncode(body),
          )
          .timeout(_timeout);

      AuthSession.noteStatus(response.statusCode);

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return UserProfile.fromJson(decoded);
      }
      debugPrint(
        'User profile API PATCH /v1/users/me responded ${response.statusCode}: ${response.body}',
      );
      return null;
    } catch (error) {
      debugPrint('User profile backend unreachable during updateProfile: $error');
      return null;
    }
  }
}
