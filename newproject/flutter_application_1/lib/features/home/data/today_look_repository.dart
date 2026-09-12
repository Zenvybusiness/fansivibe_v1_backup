import 'package:fansivibe/features/home/data/today_look_client.dart';
import 'package:fansivibe/features/home/data/today_look_models.dart';

/// Abstract contract for M9 Today's Look data operations (STEP 19.25).
///
/// The [TodayLookRepository] is the single source consumed by the Home /
/// Daily Outfit surfaces: the backend `/v1/looks/today` collection is
/// authoritative. There is deliberately no local-service merge and no mock
/// fallback — a fabricated look would corrupt the UUID-addressed save
/// surface. 404 means truthfully none available; any [TodayLookFailure]
/// means the request failed and is safe to retry.
abstract class TodayLookRepository {
  /// Derives today's look (#31 `GET /v1/looks/today`).
  Future<TodayLookResult> getTodayLook();

  /// Derives a fresh today's look (#32 `POST /v1/looks/today`).
  ///
  /// [seed] is an opaque selector passed through verbatim (absent → the
  /// winner). Never randomized in this layer.
  Future<TodayLookResult> regenerateTodayLook({String? seed});

  /// Saves a derived TodayLook (#33 `POST /v1/looks/today/save`).
  ///
  /// `sourceContext` is always `"daily"` (enforced by the client, never a
  /// parameter); [snapshot] is the TodayLook response body verbatim.
  /// [idempotencyKey] is required — one fresh key per save attempt.
  /// Returns the saved record, or null when the save did not land (safe
  /// to retry with the same key). Never logs a wear event.
  Future<SavedTodayLook?> saveTodayLook({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  });
}

/// Backend implementation of [TodayLookRepository].
class TodayLookRepositoryImpl implements TodayLookRepository {
  /// Creates a [TodayLookRepositoryImpl] with an optional client for
  /// testing. Without a client, uses the default [TodayLookClient].
  TodayLookRepositoryImpl({TodayLookClient? client})
    : _client = client ?? TodayLookClient();

  final TodayLookClient _client;

  @override
  Future<TodayLookResult> getTodayLook() {
    // Verbatim passthrough: derivation, determinism, and envelope
    // semantics stay server-authoritative. Null is never fabricated —
    // failures travel as typed [TodayLookResult.failure].
    return _client.getTodayLook();
  }

  @override
  Future<TodayLookResult> regenerateTodayLook({String? seed}) {
    // Verbatim passthrough of the opaque seed: no ID translation, no
    // local numeric IDs, no randomness introduced here.
    return _client.regenerateTodayLook(seed: seed);
  }

  @override
  Future<SavedTodayLook?> saveTodayLook({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) {
    // Verbatim passthrough: the snapshot (with its backend-UUID
    // `selectedItemIds`) is sent as-is under `sourceContext: "daily"`.
    // Null means unsaved — safe to retry with the same key.
    return _client.saveTodayLook(
      lookId: lookId,
      title: title,
      snapshot: snapshot,
      idempotencyKey: idempotencyKey,
    );
  }
}
