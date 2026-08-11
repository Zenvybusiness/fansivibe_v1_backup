import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/features/hairstyle/data/hairstyle_models.dart';

/// HTTP client for the hairstyle recommendation API.
///
/// Override the endpoint with `--dart-define=ASSISTANT_BASE_URL=...`.
/// On failure it returns null so the caller can fall back to the offline
/// result — the flow never breaks when the server is unreachable.
class HairstyleClient {
  HairstyleClient({http.Client? client, Duration? pollInterval})
      : _client = client ?? http.Client(),
        _pollInterval = pollInterval ?? const Duration(milliseconds: 600);

  static const String baseUrl = String.fromEnvironment(
    'ASSISTANT_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  static const String _devToken = String.fromEnvironment(
    'FANSIVIBE_DEV_TOKEN',
    defaultValue: 'dev',
  );

  final http.Client _client;
  static const Duration _timeout = Duration(seconds: 12);
  final Duration _pollInterval;

  /// Submits a hairstyle analysis for the given face profile reference.
  ///
  /// Returns the submitted run id, or null when the backend is unreachable.
  Future<String?> submitHairstyleAnalysis({required String faceProfileRef}) async {
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/v1/analysis/hairstyle'),
      )
        ..headers['Authorization'] = 'Bearer $_devToken'
        ..fields['faceProfileRef'] = faceProfileRef;

      final streamed =
          await _client.send(request).timeout(_timeout);
      final response = await http.Response.fromStream(streamed).timeout(_timeout);

      if (response.statusCode == 202) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return decoded['run_id'] as String?;
      }
      debugPrint(
        'Hairstyle submit responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Hairstyle backend unreachable during submit: $error');
    }
    return null;
  }

  /// Fetches an analysis run and polls until it is completed or failed.
  ///
  /// Returns the completed run, or null when unreachable / failed.
  Future<AnalysisRun?> pollAnalysisRun({required String runId}) async {
    try {
      for (var attempt = 0; attempt < 30; attempt++) {
        final run = await getAnalysisRun(runId: runId);
        if (run == null) {
          return null;
        }
        if (run.isCompleted) {
          return run;
        }
        await Future<void>.delayed(_pollInterval);
      }
    } catch (error) {
      debugPrint('Hairstyle polling failed: $error');
    }
    return null;
  }

  Future<AnalysisRun?> getAnalysisRun({required String runId}) async {
    try {
      final response = await _client
          .get(
            Uri.parse('$baseUrl/v1/analysis/$runId'),
            headers: {'Authorization': 'Bearer $_devToken'},
          )
          .timeout(_timeout);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return AnalysisRun.fromJson(decoded);
      }
      debugPrint(
        'Hairstyle fetch responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Hairstyle backend unreachable during fetch: $error');
    }
    return null;
  }

  /// Saves a look with an idempotency key so retries never duplicate.
  ///
  /// Returns true when the save succeeded.
  Future<bool> saveLook({
    required String lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async {
    try {
      final payload = {
        'lookId': lookId,
        'title': title,
        'sourceContext': 'hairstyle',
        'snapshot': snapshot,
      };
      final response = await _client
          .post(
            Uri.parse('$baseUrl/v1/looks/saved'),
            headers: {
              'Content-Type': 'application/json; charset=UTF-8',
              'Authorization': 'Bearer $_devToken',
              'Idempotency-Key': idempotencyKey,
            },
            body: jsonEncode(payload),
          )
          .timeout(_timeout);
      if (response.statusCode == 201) {
        return true;
      }
      debugPrint(
        'Hairstyle save responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Hairstyle backend unreachable during save: $error');
    }
    return false;
  }

  void dispose() => _client.close();
}
