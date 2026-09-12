import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import 'package:fansivibe/shared/auth/auth_session.dart';

/// Response payload from an analysis run query.
class OutfitAnalysisRunResult {
  const OutfitAnalysisRunResult({
    required this.statusCode,
    this.data,
  });

  final int statusCode;
  final Map<String, dynamic>? data;

  bool get isCompleted => data?['status'] == 'completed';
  bool get isFailed => data?['status'] == 'failed';
  String? get error => data?['error'] as String?;
}

/// Canonical API client for Outfit Scan operations.
class OutfitScanClient {
  OutfitScanClient({http.Client? client}) : _client = client ?? http.Client();

  static const String baseUrl = String.fromEnvironment(
    'ASSISTANT_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  static const String _devTokenDefault = String.fromEnvironment(
    'FANSIVIBE_DEV_TOKEN',
    defaultValue: 'dev',
  );

  /// Session-first Bearer token (D-AUTH-1): the persisted session wins;
  /// the dart-define default covers logged-out/test behavior.
  static String get devToken => AuthSession.effectiveToken(_devTokenDefault);

  final http.Client _client;
  static const Duration _timeout = Duration(seconds: 12);

  /// Submits an outfit image file for analysis (`POST /v1/analysis/outfit`).
  ///
  /// Returns the accepted [run_id] on 202, or null when the backend rejects
  /// or is unreachable.
  Future<String?> submitOutfitAnalysis(File imageFile) async {
    try {
      final uri = Uri.parse('$baseUrl/v1/analysis/outfit');
      final request = http.MultipartRequest('POST', uri)
        ..headers['Authorization'] = 'Bearer $devToken';

      final filename = imageFile.path.split(Platform.pathSeparator).last;
      final contentType = _contentTypeForFilename(filename);

      request.files.add(
        await http.MultipartFile.fromPath(
          'image',
          imageFile.path,
          contentType: MediaType.parse(contentType),
        ),
      );

      final streamed = await _client.send(request).timeout(_timeout);
      final response =
          await http.Response.fromStream(streamed).timeout(_timeout);

      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 202) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return decoded['run_id'] as String?;
      }
      debugPrint(
        'Outfit scan submit responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Outfit scan backend unreachable during submit: $error');
    }
    return null;
  }

  /// Polls the analysis run status (`GET /v1/analysis/runs/{run_id}`).
  ///
  /// Returns an [OutfitAnalysisRunResult] with the status code and decoded data.
  Future<OutfitAnalysisRunResult> getAnalysisRun(String runId) async {
    try {
      final uri = Uri.parse('$baseUrl/v1/analysis/runs/$runId');
      final response = await _client
          .get(
            uri,
            headers: {'Authorization': 'Bearer $devToken'},
          )
          .timeout(_timeout);

      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>?;
        return OutfitAnalysisRunResult(
          statusCode: 200,
          data: decoded,
        );
      }
      return OutfitAnalysisRunResult(statusCode: response.statusCode);
    } catch (error) {
      debugPrint('Outfit scan backend unreachable during poll: $error');
      return const OutfitAnalysisRunResult(statusCode: 0);
    }
  }

  static String _contentTypeForFilename(String filename) {
    final lower = filename.toLowerCase();
    if (lower.endsWith('.png')) return 'image/png';
    if (lower.endsWith('.webp')) return 'image/webp';
    return 'image/jpeg';
  }
}
