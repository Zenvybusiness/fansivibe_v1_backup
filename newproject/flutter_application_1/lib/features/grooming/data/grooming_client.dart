import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/features/grooming/data/grooming_models.dart';

/// HTTP client for the grooming recommendation API.
///
/// Override the endpoint with dart-define ASSISTANT_BASE_URL=... .
/// On failure it returns null so the caller can fall back to the offline
/// result — the flow never breaks when the server is unreachable.
class GroomingClient {
  GroomingClient({http.Client? client, Duration? pollInterval})
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

  /// Submits a grooming analysis for the given face profile reference.
  ///
  /// Returns the submitted run id, or null when the backend is unreachable.
  Future<String?> submitGroomingAnalysis({
    required String faceProfileRef,
  }) async {
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/v1/analysis/grooming'),
      )
        ..headers['Authorization'] = 'Bearer $_devToken'
        ..fields['faceProfileRef'] = faceProfileRef;

      final streamed = await _client.send(request).timeout(_timeout);
      final response = await http.Response.fromStream(
        streamed,
      ).timeout(_timeout);

      if (response.statusCode == 202) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return decoded['run_id'] as String?;
      }
      debugPrint(
        'Grooming submit responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Grooming backend unreachable during submit: $error');
    }
    return null;
  }

  /// Fetches an analysis run and polls until it is completed, failed, or times out.
  ///
  /// A terminal `failed` run is returned promptly (never polled to exhaustion)
  /// so the caller can surface the error instead of waiting. Returns the
  /// completed/failed run, or null when unreachable.
  Future<GroomingRun?> pollGroomingRun({required String runId}) async {
    try {
      for (var attempt = 0; attempt < 30; attempt++) {
        final run = await getGroomingRun(runId: runId);
        if (run == null) {
          return null;
        }
        if (run.isCompleted || run.isFailed) {
          return run;
        }
        await Future<void>.delayed(_pollInterval);
      }
    } catch (error) {
      debugPrint('Grooming polling failed: $error');
    }
    return null;
  }

  Future<GroomingRun?> getGroomingRun({required String runId}) async {
    try {
      final response = await _client
          .get(
            Uri.parse('$baseUrl/v1/analysis/runs/$runId'),
            headers: {'Authorization': 'Bearer $_devToken'},
          )
          .timeout(_timeout);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return GroomingRun(
          runId: decoded['run_id'] as String? ?? '',
          runType: decoded['run_type'] as String? ?? '',
          status: decoded['status'] as String? ?? 'pending',
          createdAt: decoded['created_at'] != null
              ? DateTime.tryParse(decoded['created_at'] as String)
              : null,
          completedAt:
              decoded['completed_at'] != null
                  ? DateTime.tryParse(decoded['completed_at'] as String)
                  : null,
          result: decoded['result'] as Map<String, dynamic>?,
          error: decoded['error'] as Map<String, dynamic>?,
        );
      }
      debugPrint(
        'Grooming fetch responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Grooming backend unreachable during fetch: $error');
    }
    return null;
  }

  /// Lists completed analysis runs (summary rows — no `result`).
  ///
  /// Returns null when the backend is unreachable.
  Future<List<dynamic>?> listRuns() async {
    try {
      final response = await _client
          .get(
            Uri.parse('$baseUrl/v1/analysis/runs'),
            headers: {'Authorization': 'Bearer $_devToken'},
          )
          .timeout(_timeout);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return decoded['items'] as List<dynamic>?;
      }
      debugPrint(
        'Grooming list responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Grooming backend unreachable during list: $error');
    }
    return null;
  }

  /// Saves a grooming recommendation to the user's saved looks.
  ///
  /// Returns true when the save succeeded.
  Future<bool> saveGroomingLook({
    required String lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async {
    try {
      final payload = {
        'lookId': lookId,
        'title': title,
        'sourceContext': 'grooming',
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
        'Grooming save responded ${response.statusCode}: ${response.body}',
      );
    }
    catch (error) {
      debugPrint('Grooming backend unreachable during save: $error');
    }
    return false;
  }

  void dispose() => _client.close();
}