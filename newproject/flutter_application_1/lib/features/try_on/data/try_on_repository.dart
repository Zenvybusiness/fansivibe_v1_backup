import 'dart:typed_data';

import 'package:fansivibe/features/try_on/data/try_on_client.dart';
import 'package:fansivibe/features/try_on/data/try_on_models.dart';

/// Feature-first repository for the Fansivibe Virtual Try-On surface.
///
/// Nullable/typed passthrough over [TryOnClient]: no mock merge, no local
/// fabrication. Mock outputs stay labelled test data end to end and must
/// never enter saved-look, export, or sharing flows as genuine results.
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

  Future<TryOnSubmitResult> retryJob(String jobId);

  Future<TryOnJobStatus?> cancelJob(String jobId);

  Future<bool> deleteJob(String jobId);
}

/// Optional rich-outcome extensions on [TryOnRepository] that keep existing
/// minimal test doubles compiling without boilerplate overrides.
extension TryOnRepositoryCapabilitiesExtension on TryOnRepository {
  Future<TryOnCapabilities?> getCapabilities() async {
    final self = this;
    if (self is TryOnRepositoryImpl) {
      return self.getCapabilitiesDirect();
    }
    return null;
  }

  Future<TryOnStatusOutcome> getJobStatusOutcome(String jobId) async {
    final self = this;
    if (self is TryOnRepositoryImpl) {
      return self.getJobStatusOutcomeDirect(jobId);
    }
    final status = await getJobStatus(jobId);
    if (status != null) {
      return TryOnStatusOutcome(status: status, statusCode: 200);
    }
    return const TryOnStatusOutcome(failure: TryOnFailure.networkError);
  }

  Future<TryOnImageOutcome> getJobImageOutcome(String jobId) async {
    final self = this;
    if (self is TryOnRepositoryImpl) {
      return self.getJobImageOutcomeDirect(jobId);
    }
    final bytes = await getJobImage(jobId);
    if (bytes != null) {
      return TryOnImageOutcome(bytes: bytes, statusCode: 200);
    }
    return const TryOnImageOutcome(failure: TryOnFailure.networkError);
  }

  Future<TryOnSubmitResult> submitTryOn({
    required Uint8List personBytes,
    String personFilename = 'tryon_person.jpg',
    String? personContentType,
    required String outfitSource,
    required List<String> garmentIds,
    String consentVersion = TryOnConsentVersion.current,
    required bool consentAccepted,
    required String idempotencyKey,
    int maxBytes = TryOnClient.maxImageBytes,
  }) {
    final self = this;
    if (self is TryOnRepositoryImpl) {
      return self.submitTryOnDirect(
        personBytes: personBytes,
        personFilename: personFilename,
        personContentType: personContentType,
        outfitSource: outfitSource,
        garmentIds: garmentIds,
        consentVersion: consentVersion,
        consentAccepted: consentAccepted,
        idempotencyKey: idempotencyKey,
        maxBytes: maxBytes,
      );
    }
    return submitMockTryOn(
      personBytes: personBytes,
      personFilename: personFilename,
      outfitSource: outfitSource,
      garmentIds: garmentIds,
      consentAccepted: consentAccepted,
      idempotencyKey: idempotencyKey,
    );
  }
}

class TryOnRepositoryImpl implements TryOnRepository {
  TryOnRepositoryImpl({TryOnClient? client}) : _client = client ?? TryOnClient();

  final TryOnClient _client;

  Future<TryOnCapabilities?> getCapabilitiesDirect() => _client.getCapabilities();

  Future<TryOnStatusOutcome> getJobStatusOutcomeDirect(String jobId) =>
      _client.getJobStatusOutcome(jobId);

  Future<TryOnImageOutcome> getJobImageOutcomeDirect(String jobId) =>
      _client.getJobImageOutcome(jobId);

  Future<TryOnSubmitResult> submitTryOnDirect({
    required Uint8List personBytes,
    String personFilename = 'tryon_person.jpg',
    String? personContentType,
    required String outfitSource,
    required List<String> garmentIds,
    String consentVersion = TryOnConsentVersion.current,
    required bool consentAccepted,
    required String idempotencyKey,
    int maxBytes = TryOnClient.maxImageBytes,
  }) {
    return _client.submitMockTryOn(
      personBytes: personBytes,
      personFilename: personFilename,
      personContentType: personContentType,
      outfitSource: outfitSource,
      garmentIds: garmentIds,
      consentVersion: consentVersion,
      consentAccepted: consentAccepted,
      idempotencyKey: idempotencyKey,
      maxBytes: maxBytes,
    );
  }

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

  @override
  Future<TryOnSubmitResult> retryJob(String jobId) {
    return _client.retryJob(jobId);
  }

  @override
  Future<TryOnJobStatus?> cancelJob(String jobId) {
    return _client.cancelJob(jobId);
  }

  @override
  Future<bool> deleteJob(String jobId) {
    return _client.deleteJob(jobId);
  }
}
