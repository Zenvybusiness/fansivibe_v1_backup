import 'package:fansivibe/features/events/data/event_models.dart';
import 'package:fansivibe/features/events/data/events_client.dart';

/// Abstract contract for M8 event calendar data operations.
///
/// The [EventsRepository] is the single source consumed by the Events
/// screens: the backend `/v1/events` collection is authoritative. There
/// is deliberately no local-service merge and no mock fallback — a
/// fabricated row would corrupt the UUID-addressed update/delete/outfit
/// surface. Null means unavailable/failed: the caller keeps its rows
/// and allows a retry.
abstract class EventsRepository {
  /// Returns one page of the owner's events (upcoming-first).
  Future<EventListPage?> listEvents({int page, int pageSize});

  /// Creates one owned event; the backend UUID comes back in the item.
  Future<EventItem?> createEvent(EventCreateRequest request);

  /// Fully replaces one owned event by its backend UUID.
  Future<EventItem?> updateEvent({
    required String id,
    required EventUpdateRequest request,
  });

  /// Deletes one owned event by its backend UUID.
  Future<EventDeleteOutcome?> deleteEvent({required String id});

  /// Derives one outfit for an owned event by its backend UUID.
  Future<EventOutfitResult?> generateEventOutfit({required String id});
}

/// Backend implementation of [EventsRepository].
class EventsRepositoryImpl implements EventsRepository {
  /// Creates an [EventsRepositoryImpl] with an optional client for testing.
  /// Without a client, uses the default [EventsClient].
  EventsRepositoryImpl({EventsClient? client})
    : _client = client ?? EventsClient();

  final EventsClient _client;

  @override
  Future<EventListPage?> listEvents({int page = 1, int pageSize = 20}) {
    // Verbatim passthrough: ordering, pagination, and envelope semantics
    // stay server-authoritative. Null means the list is unavailable.
    return _client.listEvents(page: page, pageSize: pageSize);
  }

  @override
  Future<EventItem?> createEvent(EventCreateRequest request) {
    // Verbatim passthrough: the backend UUID in the 201 body is the only
    // event identity. Null means unlogged — safe to retry (retries append
    // server-side, never overwrite).
    return _client.createEvent(request);
  }

  @override
  Future<EventItem?> updateEvent({
    required String id,
    required EventUpdateRequest request,
  }) {
    // Verbatim passthrough of the backend UUID: no ID translation, no
    // local numeric IDs, no position-derived IDs.
    return _client.updateEvent(id: id, request: request);
  }

  @override
  Future<EventDeleteOutcome?> deleteEvent({required String id}) {
    // Verbatim passthrough of the backend UUID. Null means unlogged —
    // safe to retry.
    return _client.deleteEvent(id: id);
  }

  @override
  Future<EventOutfitResult?> generateEventOutfit({required String id}) {
    // Verbatim passthrough of the backend UUID. The result is rendered
    // as-is: never persisted, worn, or signaled from this layer.
    return _client.generateEventOutfit(id: id);
  }
}
