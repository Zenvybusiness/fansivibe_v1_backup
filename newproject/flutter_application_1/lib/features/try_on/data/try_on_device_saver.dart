import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'package:fansivibe/features/media/domain/image_pipeline.dart';

enum TryOnSaveStatus { saved, permissionDenied, unsupported, failed }

class TryOnSaveOutcome {
  const TryOnSaveOutcome({
    required this.status,
    this.location,
    this.message,
    this.permanentlyDenied = false,
  });

  final TryOnSaveStatus status;
  final String? location;
  final String? message;
  final bool permanentlyDenied;
}

/// Platform-aware saver for genuine (non-mock) AI try-on results.
///
/// - Android: uses `MethodChannel('com.fansivibe.fansivibe/media_save')` to
///   write to MediaStore (`Pictures/Fansivibe`), handling legacy storage
///   permission prompts cleanly when required (`SDK < 29`).
/// - Desktop: writes to `~/Pictures/Fansivibe` (or `~/Downloads`).
/// - Tests can inject an override directly into `TryOnScreen.saveResultImage`.
class TryOnDeviceSaver {
  TryOnDeviceSaver._();

  static const MethodChannel _channel = MethodChannel(
    'com.fansivibe.fansivibe/media_save',
  );

  static Future<TryOnSaveOutcome> saveImage(
    Uint8List bytes, {
    required String jobId,
  }) async {
    if (bytes.isEmpty) {
      return const TryOnSaveOutcome(
        status: TryOnSaveStatus.failed,
        message: 'No image data available to save.',
      );
    }

    final mime = detectImageMimeType(bytes);
    if (mime == null) {
      return const TryOnSaveOutcome(
        status: TryOnSaveStatus.unsupported,
        message: 'Only JPEG, PNG, and WebP results can be saved to your device.',
      );
    }

    final ext = switch (mime) {
      'image/png' => 'png',
      'image/webp' => 'webp',
      _ => 'jpg',
    };
    final safeId = jobId.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
    final filename = 'fansivibe_tryon_$safeId.$ext';

    if (kIsWeb) {
      return const TryOnSaveOutcome(
        status: TryOnSaveStatus.unsupported,
        message: 'Saving directly to gallery is available on mobile and desktop apps.',
      );
    }

    if (Platform.isAndroid || Platform.isIOS) {
      try {
        final raw = await _channel.invokeMapMethod<String, dynamic>(
          'saveImageToGallery',
          <String, dynamic>{
            'bytes': bytes,
            'filename': filename,
            'mimeType': mime,
          },
        );
        final status = raw?['status'] as String?;
        final location = raw?['location'] as String?;
        final message = raw?['message'] as String?;
        final permanentlyDenied = raw?['permanentlyDenied'] == true;
        if (status == 'saved') {
          return TryOnSaveOutcome(
            status: TryOnSaveStatus.saved,
            location: location,
            message: message ?? 'Saved to your device gallery.',
          );
        }
        if (status == 'permission_denied') {
          return TryOnSaveOutcome(
            status: TryOnSaveStatus.permissionDenied,
            permanentlyDenied: permanentlyDenied,
            message: message ??
                (permanentlyDenied
                    ? 'Photo storage permission is permanently denied. Enable photo access in device Settings to save.'
                    : 'Photo storage permission was denied. Enable storage access in settings to save.'),
          );
        }
        return TryOnSaveOutcome(
          status: TryOnSaveStatus.failed,
          message: message ?? 'Could not save image to your device.',
        );
      } on MissingPluginException {
        return const TryOnSaveOutcome(
          status: TryOnSaveStatus.unsupported,
          message: 'Gallery saving is not configured on this platform.',
        );
      } on PlatformException catch (e) {
        final codeLower = e.code.toLowerCase();
        if (codeLower.contains('permission') ||
            codeLower.contains('denied')) {
          final isPerm = codeLower.contains('permanent') ||
              codeLower.contains('access_denied');
          return TryOnSaveOutcome(
            status: TryOnSaveStatus.permissionDenied,
            permanentlyDenied: isPerm,
            message: e.message ??
                (isPerm
                    ? 'Photo access is permanently denied. Enable it in device Settings to save.'
                    : 'Permission denied. Allow photo access to save try-on results.'),
          );
        }
        return TryOnSaveOutcome(
          status: TryOnSaveStatus.failed,
          message: e.message ?? 'Could not save image to your device.',
        );
      } catch (_) {
        return const TryOnSaveOutcome(
          status: TryOnSaveStatus.failed,
          message: 'Could not save image to your device.',
        );
      }
    }

    try {
      final home = Platform.environment['HOME'];
      if (home == null || home.isEmpty) {
        return const TryOnSaveOutcome(
          status: TryOnSaveStatus.failed,
          message: 'Could not resolve user Pictures directory.',
        );
      }
      final picturesDir = Directory('$home/Pictures/Fansivibe');
      if (!picturesDir.existsSync()) {
        picturesDir.createSync(recursive: true);
      }
      final outFile = File('${picturesDir.path}/$filename');
      await outFile.writeAsBytes(bytes, flush: true);
      return TryOnSaveOutcome(
        status: TryOnSaveStatus.saved,
        location: outFile.path,
        message: 'Saved to ${outFile.path}',
      );
    } catch (_) {
      return const TryOnSaveOutcome(
        status: TryOnSaveStatus.failed,
        message: 'Could not save image to disk.',
      );
    }
  }
}

