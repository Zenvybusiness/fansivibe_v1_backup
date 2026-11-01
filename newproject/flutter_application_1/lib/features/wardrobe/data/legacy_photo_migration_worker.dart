import 'dart:async';

import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/media/data/media_client.dart';
import 'package:fansivibe/features/media/domain/image_pipeline.dart';
import 'package:fansivibe/features/media/domain/original_file_manager.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_item_photo.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

enum MigrationItemState {
  pending,
  authorized,
  uploaded,
  published,
  associated,
  completed,
  failed,
}

class MigrationProgressSummary {
  const MigrationProgressSummary({
    required this.totalEligible,
    required this.migratedCount,
    required this.failedCount,
    required this.skippedCount,
    required this.isCancelled,
  });

  final int totalEligible;
  final int migratedCount;
  final int failedCount;
  final int skippedCount;
  final bool isCancelled;
}

/// Worker for device-initiated, resumable legacy Base64 wardrobe photo migration (Gate 4).
///
/// Invariants:
/// 1. Migration is device-initiated and bounded in concurrency (max 2 parallel).
/// 2. Preserves the local original in app storage via [OriginalFileManager] (Option B).
/// 3. Never deletes local Base64 until server confirms published media association.
/// 4. Idempotent: repeated runs skip already-associated items.
/// 5. Cancelable immediately on logout or account switch (Gate 5).
class LegacyPhotoMigrationWorker {
  LegacyPhotoMigrationWorker({
    WardrobeRepository? wardrobeRepository,
    MediaClient? mediaClient,
    OriginalFileManager? originalFileManager,
    int maxConcurrency = 2,
  })  : _wardrobeRepo = wardrobeRepository ?? WardrobeRepositoryImpl(),
        _mediaClient = mediaClient ?? MediaClient(),
        _originalFileManager =
            originalFileManager ?? OriginalFileManager.instance,
        _maxConcurrency = maxConcurrency;

  final WardrobeRepository _wardrobeRepo;
  final MediaClient _mediaClient;
  final OriginalFileManager _originalFileManager;
  final int _maxConcurrency;

  bool _isCancelled = false;

  void cancel() {
    _isCancelled = true;
  }

  /// Runs legacy Base64 migration for authenticated accounts.
  Future<MigrationProgressSummary> runMigration({
    List<WardrobeEntry>? explicitEntries,
  }) async {
    if (_isCancelled) {
      final entries = explicitEntries ??
          LearningService.instance.wardrobe
              .where((e) => e.imageBase64 != null && e.imageBase64!.isNotEmpty)
              .toList();
      return MigrationProgressSummary(
        totalEligible: entries.length,
        migratedCount: 0,
        failedCount: 0,
        skippedCount: 0,
        isCancelled: true,
      );
    }
    if (!AuthSession.isAuthenticated) {
      return const MigrationProgressSummary(
        totalEligible: 0,
        migratedCount: 0,
        failedCount: 0,
        skippedCount: 0,
        isCancelled: false,
      );
    }

    final entries = explicitEntries ??
        LearningService.instance.wardrobe
            .where((e) => e.imageBase64 != null && e.imageBase64!.isNotEmpty)
            .toList();

    var migrated = 0;
    var failed = 0;
    var skipped = 0;

    // Process in bounded chunks
    for (var i = 0; i < entries.length; i += _maxConcurrency) {
      if (_isCancelled) break;
      final chunk = entries.skip(i).take(_maxConcurrency).toList();

      final futures = chunk.map((entry) => _migrateSingleEntry(entry));
      final results = await Future.wait(futures);

      for (final result in results) {
        if (result == MigrationItemState.completed) {
          migrated++;
        } else if (result == MigrationItemState.failed) {
          failed++;
        } else {
          skipped++;
        }
      }
    }

    return MigrationProgressSummary(
      totalEligible: entries.length,
      migratedCount: migrated,
      failedCount: failed,
      skippedCount: skipped,
      isCancelled: _isCancelled,
    );
  }

  Future<MigrationItemState> _migrateSingleEntry(WardrobeEntry entry) async {
    if (_isCancelled) return MigrationItemState.failed;

    // 1. Validate Base64
    final rawBase64 = entry.imageBase64;
    if (rawBase64 == null || rawBase64.isEmpty) {
      return MigrationItemState.completed;
    }

    final bytes = decodeWardrobePhoto(rawBase64);
    if (bytes == null || bytes.isEmpty) {
      return MigrationItemState.failed;
    }

    // 2. Retain original photo on local disk (Option B)
    await _originalFileManager.saveOriginal(
      idOrHash: entry.id,
      bytes: bytes,
    );

    // 3. Compute client SHA-256 and dimensions
    final clientSha = sha256Hex(bytes);
    final dims = await getImageDimensions(bytes);
    final width = dims?.$1;
    final height = dims?.$2;

    if (_isCancelled) return MigrationItemState.failed;

    // 4. Request upload authorization
    final idempotencyKey = 'mig_${entry.id}_${clientSha.substring(0, 16)}';
    final authRes = await _mediaClient.authorizeUpload(
      clientSizeBytes: bytes.length,
      clientSha256: clientSha,
      idempotencyKey: idempotencyKey,
      mimeType: 'image/webp',
      clientDeclaredWidth: width,
      clientDeclaredHeight: height,
    );

    if (authRes == null) {
      return MigrationItemState.failed;
    }

    if (_isCancelled) return MigrationItemState.failed;

    // 5. Upload bytes directly to R2
    final uploadSuccess = await _mediaClient.uploadBytesDirect(
      presignedPutUrl: authRes.presignedPutUrl,
      bytes: bytes,
      contentType: 'image/webp',
    );

    if (!uploadSuccess) {
      return MigrationItemState.failed;
    }

    if (_isCancelled) return MigrationItemState.failed;

    // 6. Complete server-side verification and publication
    final completeRes = await _mediaClient.completeUpload(
      uploadId: authRes.uploadId,
    );

    if (completeRes == null ||
        (completeRes.status != 'ready' &&
            completeRes.status != 'published')) {
      return MigrationItemState.failed;
    }

    if (_isCancelled) return MigrationItemState.failed;

    // 7. Associate published reference with wardrobe item on backend
    final mediaRef = MediaRef(
      objectKey: completeRes.canonicalKey,
      mediaType: completeRes.mediaType,
      uploadId: completeRes.uploadId,
      contentHash: completeRes.sha256,
      sizeBytes: completeRes.sizeBytes,
      width: completeRes.width,
      height: completeRes.height,
    );

    final updatedItem = await _wardrobeRepo.updateItemMedia(
      itemId: entry.id,
      imageRef: mediaRef,
    );

    // 8. Confirm backend item has published image reference
    if (updatedItem == null || updatedItem.imageRef == null) {
      // Backend association not confirmed: KEEP local Base64 intact for safety!
      return MigrationItemState.failed;
    }

    // 9. Association verified: now and only now clear Base64 from local record
    final clearedEntry = entry.copyWith(clearImageBase64: true);
    LearningService.instance.updateItem(entry.id, clearedEntry);

    return MigrationItemState.completed;
  }
}
