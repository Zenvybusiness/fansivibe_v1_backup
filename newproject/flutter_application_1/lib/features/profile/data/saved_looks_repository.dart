import 'package:fansivibe/features/profile/data/saved_looks_client.dart';
import 'package:fansivibe/features/profile/data/saved_looks_models.dart';

/// Abstract contract for saved-looks data operations.
///
/// The [SavedLooksRepository] is the single source consumed by
/// `SavedLooksScreen`: the backend `GET /v1/looks/saved` collection is
/// authoritative. There is deliberately no local-service merge and no mock
/// fallback — a fabricated row would corrupt the delete surface (DEC-013).
/// Null means unavailable/failed: the caller keeps its rows and allows a
/// retry.
abstract class SavedLooksRepository {
  /// Returns one page of the owner's saved looks (`createdAt` desc).
  Future<SavedLookListPage?> listSavedLooks({int page, int pageSize});

  /// Deletes one owned saved look by its backend UUID.
  Future<SavedLookDeleteOutcome?> deleteSavedLook({required String id});
}

/// Backend implementation of [SavedLooksRepository].
class SavedLooksRepositoryImpl implements SavedLooksRepository {
  /// Creates a [SavedLooksRepositoryImpl] with an optional client for testing.
  /// Without a client, uses the default [SavedLooksClient].
  SavedLooksRepositoryImpl({SavedLooksClient? client})
    : _client = client ?? SavedLooksClient();

  final SavedLooksClient _client;

  @override
  Future<SavedLookListPage?> listSavedLooks({int page = 1, int pageSize = 20}) {
    // Verbatim passthrough: ordering, pagination, and envelope semantics
    // stay server-authoritative. Null means the list is unavailable.
    return _client.listSavedLooks(page: page, pageSize: pageSize);
  }

  @override
  Future<SavedLookDeleteOutcome?> deleteSavedLook({required String id}) {
    // Verbatim passthrough of the backend UUID: no ID translation, no
    // local numeric IDs, no position-derived IDs. Null means unlogged —
    // safe to retry.
    return _client.deleteSavedLook(id: id);
  }
}
