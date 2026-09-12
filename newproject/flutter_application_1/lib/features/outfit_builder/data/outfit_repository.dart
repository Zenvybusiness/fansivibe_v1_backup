import 'package:fansivibe/features/outfit_builder/data/outfit_client.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_models.dart';

/// Abstract contract for M13 outfit builder data operations (PHASE 2).
///
/// The [OutfitBuilderRepository] is the single source consumed by the
/// builder screens: the backend `/v1/outfits` collection is
/// authoritative. There is deliberately no local-service merge and no
/// mock fallback — a fabricated outfit would corrupt the UUID-addressed
/// save surface. 204 means truthfully none available; any
/// [OutfitFailure] means the request failed and is safe to retry.
abstract class OutfitBuilderRepository {
  /// Derives one outfit (#41 `POST /v1/outfits/generate`).
  ///
  /// [seed] is the opaque UC-29 variety selector passed through verbatim
  /// (absent → the winner). Never randomized in this layer.
  Future<OutfitResult> generateOutfit({
    required String occasion,
    required String mood,
    required String fit,
    required String colorPalette,
    String? seed,
  });

  /// Freezes one derived outfit (#42 `POST /v1/outfits/saved`).
  ///
  /// `sourceContext` is always `"outfit"` (enforced by the client, never
  /// a parameter); [snapshot] is the outfit response body verbatim.
  /// [idempotencyKey] is required — one fresh key per save attempt.
  /// Returns the saved record, or null when the save did not land (safe
  /// to retry with the same key). Never logs a wear event.
  Future<SavedOutfit?> saveOutfit({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  });
}

/// Backend implementation of [OutfitBuilderRepository].
class OutfitBuilderRepositoryImpl implements OutfitBuilderRepository {
  /// Creates an [OutfitBuilderRepositoryImpl] with an optional client for
  /// testing. Without a client, uses the default [OutfitBuilderClient].
  OutfitBuilderRepositoryImpl({OutfitBuilderClient? client})
    : _client = client ?? OutfitBuilderClient();

  final OutfitBuilderClient _client;

  @override
  Future<OutfitResult> generateOutfit({
    required String occasion,
    required String mood,
    required String fit,
    required String colorPalette,
    String? seed,
  }) {
    // Verbatim passthrough: derivation, determinism, and envelope
    // semantics stay server-authoritative. Null is never fabricated —
    // failures travel as typed [OutfitResult.failure].
    return _client.generateOutfit(
      occasion: occasion,
      mood: mood,
      fit: fit,
      colorPalette: colorPalette,
      seed: seed,
    );
  }

  @override
  Future<SavedOutfit?> saveOutfit({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) {
    // Verbatim passthrough: the snapshot (with its backend-UUID
    // component IDs) is sent as-is under `sourceContext: "outfit"`.
    // Null means unsaved — safe to retry with the same key.
    return _client.saveOutfit(
      lookId: lookId,
      title: title,
      snapshot: snapshot,
      idempotencyKey: idempotencyKey,
    );
  }
}
