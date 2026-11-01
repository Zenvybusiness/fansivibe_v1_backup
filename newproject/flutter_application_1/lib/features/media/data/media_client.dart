import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

class UploadAuthorizationResponse {
  const UploadAuthorizationResponse({
    required this.uploadId,
    required this.stagingKey,
    required this.presignedPutUrl,
    required this.expiresAt,
  });

  final String uploadId;
  final String stagingKey;
  final String presignedPutUrl;
  final DateTime expiresAt;

  factory UploadAuthorizationResponse.fromJson(Map<String, dynamic> json) =>
      UploadAuthorizationResponse(
        uploadId: (json['uploadId'] ?? json['upload_id']) as String,
        stagingKey: (json['stagingKey'] ?? json['staging_key']) as String,
        presignedPutUrl: (json['uploadUrl'] ??
            json['upload_url'] ??
            json['presignedPutUrl'] ??
            json['presigned_put_url']) as String,
        expiresAt: DateTime.parse(
          (json['expiresAt'] ?? json['expires_at']) as String,
        ),
      );
}

class PublishedMediaRefResponse {
  const PublishedMediaRefResponse({
    required this.uploadId,
    required this.canonicalKey,
    required this.mediaType,
    required this.sizeBytes,
    required this.width,
    required this.height,
    required this.sha256,
    required this.completedAt,
    required this.status,
  });

  final String uploadId;
  final String canonicalKey;
  final String mediaType;
  final int sizeBytes;
  final int width;
  final int height;
  final String sha256;
  final DateTime completedAt;
  final String status;

  factory PublishedMediaRefResponse.fromJson(Map<String, dynamic> json) =>
      PublishedMediaRefResponse(
        uploadId: (json['uploadId'] ?? json['upload_id']) as String,
        canonicalKey: (json['objectKey'] ??
            json['object_key'] ??
            json['canonicalKey'] ??
            json['canonical_key']) as String,
        mediaType:
            (json['mediaType'] ?? json['media_type']) as String? ?? 'image/webp',
        sizeBytes: (json['sizeBytes'] ?? json['size_bytes']) as int,
        width: (json['width'] as num).toInt(),
        height: (json['height'] as num).toInt(),
        sha256: (json['contentHash'] ??
            json['content_hash'] ??
            json['sha256'] ??
            '') as String,
        completedAt: DateTime.parse(
          (json['uploadedAt'] ??
              json['uploaded_at'] ??
              json['completedAt'] ??
              json['completed_at']) as String,
        ),
        status: (json['status'] as String?) ?? 'ready',
      );
}

class MediaDownloadUrlResponse {
  const MediaDownloadUrlResponse({
    required this.uploadId,
    required this.objectKey,
    required this.downloadUrl,
    required this.expiresAt,
    required this.expiresInSeconds,
  });

  final String uploadId;
  final String objectKey;
  final String downloadUrl;
  final DateTime expiresAt;
  final int expiresInSeconds;

  factory MediaDownloadUrlResponse.fromJson(Map<String, dynamic> json) =>
      MediaDownloadUrlResponse(
        uploadId: (json['uploadId'] ?? json['upload_id']) as String,
        objectKey: (json['objectKey'] ?? json['object_key']) as String,
        downloadUrl: (json['downloadUrl'] ?? json['download_url']) as String,
        expiresAt: DateTime.parse(
          (json['expiresAt'] ?? json['expires_at']) as String,
        ),
        expiresInSeconds:
            (json['expiresInSeconds'] ?? json['expires_in_seconds']) as int? ??
                900,
      );
}

/// Client for Fansivibe authenticated media APIs (Stage 2 P0-4 Phase 4).
class MediaClient {
  MediaClient({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl = baseUrl ?? AppConfig.apiBaseUrl;

  final http.Client _client;
  final String _baseUrl;
  static const Duration _timeout = Duration(seconds: 15);

  static const String _devTokenDefault = String.fromEnvironment(
    'FANSIVIBE_DEV_TOKEN',
    defaultValue: 'dev',
  );

  String get _token => AuthSession.effectiveToken(_devTokenDefault);

  Map<String, String> _headers([Map<String, String>? extra]) => {
        'Authorization': 'Bearer $_token',
        'Accept': 'application/json',
        ...?extra,
      };

  /// Requests upload authorization from the backend (P0-4 Phase 2).
  Future<UploadAuthorizationResponse?> authorizeUpload({
    required int clientSizeBytes,
    required String clientSha256,
    required String idempotencyKey,
    String mimeType = 'image/webp',
    int? clientDeclaredWidth,
    int? clientDeclaredHeight,
  }) async {
    try {
      final uri = Uri.parse('$_baseUrl/v1/media/uploads');
      final body = jsonEncode({
        'purpose': 'wardrobe_item',
        'contentType': mimeType,
        'sizeBytes': clientSizeBytes,
        if (clientSha256.isNotEmpty)
          'clientAssertionSha256': clientSha256,
      });

      final response = await _client
          .post(
            uri,
            headers: _headers({
              'Content-Type': 'application/json',
              'Idempotency-Key': idempotencyKey,
            }),
            body: body,
          )
          .timeout(_timeout);

      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200 || response.statusCode == 201) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return UploadAuthorizationResponse.fromJson(decoded);
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  /// Uploads raw image bytes directly to Cloudflare R2 via presigned PUT URL.
  Future<bool> uploadBytesDirect({
    required String presignedPutUrl,
    required Uint8List bytes,
    String contentType = 'image/webp',
  }) async {
    try {
      final uri = Uri.parse(presignedPutUrl);
      final response = await _client
          .put(
            uri,
            headers: {'Content-Type': contentType},
            body: bytes,
          )
          .timeout(const Duration(seconds: 30));

      return response.statusCode >= 200 && response.statusCode < 300;
    } catch (_) {
      return false;
    }
  }

  /// Completes media upload, triggering server-side verification and canonical publication.
  Future<PublishedMediaRefResponse?> completeUpload({
    required String uploadId,
  }) async {
    try {
      final uri = Uri.parse('$_baseUrl/v1/media/uploads/$uploadId/complete');
      final response = await _client
          .post(uri, headers: _headers())
          .timeout(_timeout);

      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return PublishedMediaRefResponse.fromJson(decoded);
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  /// Fetches a fresh 15-minute presigned GET URL for a published media upload.
  Future<MediaDownloadUrlResponse?> getDownloadUrl({
    required String uploadId,
  }) async {
    try {
      final uri = Uri.parse('$_baseUrl/v1/media/url')
          .replace(queryParameters: {'uploadId': uploadId});
      final response = await _client
          .get(uri, headers: _headers())
          .timeout(_timeout);

      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return MediaDownloadUrlResponse.fromJson(decoded);
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  void dispose() {
    _client.close();
  }
}
