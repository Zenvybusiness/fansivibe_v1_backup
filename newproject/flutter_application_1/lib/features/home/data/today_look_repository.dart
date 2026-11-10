import 'package:fansivibe/features/home/data/today_look_client.dart';
import 'package:fansivibe/features/home/data/today_look_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

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
  Future<TodayLookResult> getTodayLook({
    String? city,
    double? latitude,
    double? longitude,
  });

  /// Derives a fresh today's look (#32 `POST /v1/looks/today`).
  ///
  /// [seed] is an opaque selector passed through verbatim (absent → the
  /// winner). Never randomized in this layer.
  Future<TodayLookResult> regenerateTodayLook({
    String? seed,
    String? city,
    double? latitude,
    double? longitude,
  });

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

  /// Guest city only: an authenticated request must rely on the user's
  /// backend settings (priority 2) so a device-local guest city can never
  /// override another account's saved location.
  static String? _resolveStoredCity() {
    if (AuthSession.isAuthenticated && !isGuestUser) return null;
    return LocalStorage.weatherCity;
  }

  @override
  Future<TodayLookResult> getTodayLook({
    String? city,
    double? latitude,
    double? longitude,
  }) {
    // Verbatim passthrough: derivation, determinism, and envelope
    // semantics stay server-authoritative. Null is never fabricated —
    // failures travel as typed [TodayLookResult.failure].
    final effectiveCity = city ?? _resolveStoredCity();
    return _client.getTodayLook(
      city: effectiveCity,
      latitude: latitude,
      longitude: longitude,
    );
  }

  @override
  Future<TodayLookResult> regenerateTodayLook({
    String? seed,
    String? city,
    double? latitude,
    double? longitude,
  }) {
    // Verbatim passthrough of the opaque seed: no ID translation, no
    // local numeric IDs, no randomness introduced here. Guest city only
    // (same account-isolation rule as [getTodayLook]).
    final effectiveCity = city ?? _resolveStoredCity();
    return _client.regenerateTodayLook(
      seed: seed,
      city: effectiveCity,
      latitude: latitude,
      longitude: longitude,
    );
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
