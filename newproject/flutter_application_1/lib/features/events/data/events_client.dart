import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/features/events/data/event_models.dart';

/// HTTP client for the M8 event calendar surface (#26–30, STEP 19.22).
///
/// Override the endpoint with `--dart-define=ASSISTANT_BASE_URL=...`.
/// On failure it returns null so the caller keeps its rows and allows a
/// retry — the flow never fabricates success when the server is
/// unreachable, and failures are never posed as backend data (no mock
/// success, no local fallback, no local-ID echo). IDs pass through
/// verbatim; local numeric IDs are never submitted.
class EventsClient {
  /// Creates an [EventsClient] with an optional client for testing.
  EventsClient({http.Client? client}) : _client = client ?? http.Client();

  /// Backend base URL.
  static const String baseUrl = String.fromEnvironment(
    'ASSISTANT_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  static const String _devToken = String.fromEnvironment(
    'FANSIVIBE_DEV_TOKEN',
    defaultValue: 'dev',
  );

  final http.Client _client;
  static const Duration _timeout = Duration(seconds: 12);

  Map<String, String> get _headers => {'Authorization': 'Bearer $_devToken'};

  Map<String, String> get _jsonHeaders => {
    'Authorization': 'Bearer $_devToken',
    'Content-Type': 'application/json; charset=UTF-8',
  };

  /// Lists the owner's events (#27 `GET /v1/events`, upcoming-first).
  ///
  /// Returns the decoded page on 200 (including an empty page), or null
  /// when the backend is unreachable or rejects the request.
  Future<EventListPage?> listEvents({int page = 1, int pageSize = 20}) async {
    try {
      final uri = Uri.parse(
        '$baseUrl/v1/events?page=$page&page_size=$pageSize',
      );
      final response = await _client
          .get(uri, headers: _headers)
          .timeout(_timeout);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return EventListPage.fromJson(decoded);
      }
      debugPrint(
        'Events list responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Events backend unreachable during list: $error');
    }
    return null;
  }

  /// Creates one owned event (#26 `POST /v1/events`, never idempotent).
  ///
  /// Returns the backend-created [EventItem] (server UUID) on 201, or
  /// null when the backend is unreachable or rejects the request (401 /
  /// 404 / 422 / 429 all map to null — never a fabricated event).
  Future<EventItem?> createEvent(EventCreateRequest request) async {
    try {
      final response = await _client
          .post(
            Uri.parse('$baseUrl/v1/events'),
            headers: _jsonHeaders,
            body: jsonEncode(request.toJson()),
          )
          .timeout(_timeout);
      if (response.statusCode == 201) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return EventItem.fromJson(decoded);
      }
      debugPrint(
        'Events create responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Events backend unreachable during create: $error');
    }
    return null;
  }

  /// Fully replaces one owned event (#28 `PUT /v1/events/{event_id}`).
  ///
  /// Returns the updated [EventItem] on 200, or null when the backend
  /// is unreachable or rejects the request. [id] is the backend event
  /// UUID, sent verbatim.
  Future<EventItem?> updateEvent({
    required String id,
    required EventUpdateRequest request,
  }) async {
    try {
      final response = await _client
          .put(
            Uri.parse('$baseUrl/v1/events/$id'),
            headers: _jsonHeaders,
            body: jsonEncode(request.toJson()),
          )
          .timeout(_timeout);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return EventItem.fromJson(decoded);
      }
      debugPrint(
        'Events update responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Events backend unreachable during update: $error');
    }
    return null;
  }

  /// Deletes one owned event (#29 `DELETE /v1/events/{event_id}`).
  ///
  /// Returns [EventDeleteOutcome.deleted] on 204 and
  /// [EventDeleteOutcome.alreadyGone] on 404. Returns null on any
  /// other status or when unreachable, so the caller retains the row.
  /// [id] is the backend event UUID, sent verbatim.
  Future<EventDeleteOutcome?> deleteEvent({required String id}) async {
    try {
      final response = await _client
          .delete(Uri.parse('$baseUrl/v1/events/$id'), headers: _headers)
          .timeout(_timeout);
      if (response.statusCode == 204) {
        return EventDeleteOutcome.deleted;
      }
      if (response.statusCode == 404) {
        return EventDeleteOutcome.alreadyGone;
      }
      debugPrint(
        'Events delete responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Events backend unreachable during delete: $error');
    }
    return null;
  }

  /// Derives one outfit for an owned event (#30
  /// `POST /v1/events/{event_id}/outfit`, no body).
  ///
  /// Returns [EventOutfitResult.available] on 200 and
  /// [EventOutfitResult.noneAvailable] on 204 (empty wardrobe / no
  /// legal candidate — a truthful empty state, never a failure).
  /// Returns null on any other status or when unreachable, so the
  /// caller shows an error instead of a fabricated outfit. [id] is the
  /// backend event UUID, sent verbatim. Nothing is persisted, worn, or
  /// signaled by this call.
  Future<EventOutfitResult?> generateEventOutfit({required String id}) async {
    try {
      final response = await _client
          .post(Uri.parse('$baseUrl/v1/events/$id/outfit'), headers: _headers)
          .timeout(_timeout);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return EventOutfitResult.available(EventOutfit.fromJson(decoded));
      }
      if (response.statusCode == 204) {
        return const EventOutfitResult.noneAvailable();
      }
      debugPrint(
        'Event outfit responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Events backend unreachable during outfit: $error');
    }
    return null;
  }

  /// Closes the underlying HTTP client.
  void dispose() => _client.close();
}
