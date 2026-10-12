import 'dart:typed_data';

import 'package:fansivibe/features/try_on/data/try_on_client.dart';
import 'package:fansivibe/features/try_on/data/try_on_models.dart';

/// Feature-first repository for the Stage F0 mock try-on surface.
///
/// Nullable passthrough over [TryOnClient] (TodayLook precedent): no
/// mock merge, no local fabrication. Mock outputs stay labelled test
/// data end to end and must never enter saved-look, export, or sharing
/// flows as genuine results.
abstract class TryOnRepository {
  Future<TryOnSubmitResult> submitMockTryOn({
    required Uint8List personBytes,
    String personFilename,
    required String outfitSource,
    required List<String> garmentIds,
    required bool consentAccepted,
    required String idempotencyKey,
  });

  Future<TryOnJobStatus?> getJobStatus(String jobId);

  Future<Uint8List?> getJobImage(String jobId);
}

class TryOnRepositoryImpl implements TryOnRepository {
  TryOnRepositoryImpl({TryOnClient? client}) : _client = client ?? TryOnClient();

  final TryOnClient _client;

  @override
  Future<TryOnSubmitResult> submitMockTryOn({
    required Uint8List personBytes,
    String personFilename = 'tryon_person.jpg',
    required String outfitSource,
    required List<String> garmentIds,
    required bool consentAccepted,
    required String idempotencyKey,
  }) {
    return _client.submitMockTryOn(
      personBytes: personBytes,
      personFilename: personFilename,
      outfitSource: outfitSource,
      garmentIds: garmentIds,
      consentAccepted: consentAccepted,
      idempotencyKey: idempotencyKey,
    );
  }

  @override
  Future<TryOnJobStatus?> getJobStatus(String jobId) {
    return _client.getJobStatus(jobId);
  }

  @override
  Future<Uint8List?> getJobImage(String jobId) {
    return _client.getJobImage(jobId);
  }
}
