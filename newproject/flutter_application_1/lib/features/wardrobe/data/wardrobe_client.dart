import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';

/// HTTP client for the wardrobe API.
///
/// Override the endpoint with `--dart-define=ASSISTANT_BASE_URL=...`.
/// On failure it returns null so the caller can fall back to the offline
/// result — the flow never breaks when the server is unreachable.
class WardrobeClient {
  WardrobeClient({http.Client? client})
    : _client = client ?? http.Client();

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

  /// Fetches the list of wardrobe items for the current user.
  ///
  /// Returns the [ListEnvelope] on 200, or null when the backend is unreachable.
  Future<ListEnvelope?> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async {
    try {
      final queryParams = <String, String>{};
      if (category != null) queryParams['category'] = category;
      if (color != null) queryParams['color'] = color;
      if (sortBy != null) queryParams['sort'] = sortBy;
      if (order != null) queryParams['order'] = order;
      if (page > 1) queryParams['page'] = page.toString();
      if (pageSize > 20) queryParams['page_size'] = pageSize.toString();

      final uri = Uri.parse('$baseUrl/v1/wardrobe/items')
          .resolveUri(Uri(queryParameters: queryParams));

      final response = await _client
          .get(
            uri,
            headers: {'Authorization': 'Bearer $_devToken'},
          )
          .timeout(_timeout);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return ListEnvelope.fromJson(decoded);
      }
      debugPrint(
        'Wardrobe list responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Wardrobe backend unreachable during list: $error');
    }
    return null;
  }

  /// Fetches a single wardrobe item by ID.
  ///
  /// Returns the [WardrobeItem] on 200, or null when unreachable / not owned.
  Future<WardrobeItem?> getItem({required String itemId}) async {
    try {
      final response = await _client
          .get(
            Uri.parse('$baseUrl/v1/wardrobe/items/$itemId'),
            headers: {'Authorization': 'Bearer $_devToken'},
          )
          .timeout(_timeout);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return WardrobeItem.fromJson(decoded);
      }
      if (response.statusCode == 404) {
        debugPrint(
          'Wardrobe item not found (404): ${response.body}',
        );
      } else {
        debugPrint(
          'Wardrobe fetch responded ${response.statusCode}: ${response.body}',
        );
      }
    } catch (error) {
      debugPrint('Wardrobe backend unreachable during fetch: $error');
    }
    return null;
  }

  /// Creates a new wardrobe item.
  ///
  /// Returns the created [WardrobeItem] on 201, or null when unreachable.
  Future<WardrobeItem?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
  }) async {
    try {
      final payload = {
        'name': name,
        'category': category,
        'color': color,
        if (material != null) 'material': material,
        if (imageRef != null) 'imageRef': imageRef.toJson(),
      };
      final response = await _client
          .post(
            Uri.parse('$baseUrl/v1/wardrobe/items'),
            headers: {
              'Content-Type': 'application/json; charset=UTF-8',
              'Authorization': 'Bearer $_devToken',
            },
            body: jsonEncode(payload),
          )
          .timeout(_timeout);
      if (response.statusCode == 201) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return WardrobeItem.fromJson(decoded);
      }
      debugPrint(
        'Wardrobe create responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Wardrobe backend unreachable during create: $error');
    }
    return null;
  }

  /// Partially updates a wardrobe item.
  ///
  /// Returns the updated [WardrobeItem] on 200, or null when unreachable.
  Future<WardrobeItem?> updateItem({
    required String itemId,
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
  }) async {
    try {
      final payload = <String, dynamic>{};
      if (name != null) payload['name'] = name;
      if (category != null) payload['category'] = category;
      if (color != null) payload['color'] = color;
      if (material != null) payload['material'] = material;
      if (isFavorite != null) payload['isFavorite'] = isFavorite;

      final response = await _client
          .patch(
            Uri.parse('$baseUrl/v1/wardrobe/items/$itemId'),
            headers: {
              'Content-Type': 'application/json; charset=UTF-8',
              'Authorization': 'Bearer $_devToken',
            },
            body: jsonEncode(payload),
          )
          .timeout(_timeout);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return WardrobeItem.fromJson(decoded);
      }
      debugPrint(
        'Wardrobe update responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Wardrobe backend unreachable during update: $error');
    }
    return null;
  }

  /// Deletes a wardrobe item.
  ///
  /// Returns `true` on 204, or null when unreachable.
  Future<bool?> deleteItem({required String itemId}) async {
    try {
      final response = await _client
          .delete(
            Uri.parse('$baseUrl/v1/wardrobe/items/$itemId'),
            headers: {'Authorization': 'Bearer $_devToken'},
          )
          .timeout(_timeout);
      if (response.statusCode == 204) {
        return true;
      }
      debugPrint(
        'Wardrobe delete responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Wardrobe backend unreachable during delete: $error');
    }
    return null;
  }

  /// Fetches the derived wardrobe insight for the current user.
  ///
  /// Returns the [WardrobeInsight] on 200, or null when there is no insight
  /// to show: 204 (empty wardrobe — not an error), any other non-200
  /// status, or an unreachable backend. The backend-provided title/insight
  /// are rendered verbatim by the caller.
  Future<WardrobeInsight?> getInsight() async {
    try {
      final response = await _client
          .get(
            Uri.parse('$baseUrl/v1/wardrobe/insight'),
            headers: {'Authorization': 'Bearer $_devToken'},
          )
          .timeout(_timeout);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return WardrobeInsight.fromJson(decoded);
      }
      if (response.statusCode == 204) {
        debugPrint('Wardrobe insight: empty wardrobe (204), no insight.');
      } else {
        debugPrint(
          'Wardrobe insight responded ${response.statusCode}: ${response.body}',
        );
      }
    } catch (error) {
      debugPrint('Wardrobe backend unreachable during insight: $error');
    }
    return null;
  }

  /// Logs a wear event for backend wardrobe items.
  ///
  /// POSTs `{itemIds, wornAt?}` to `/v1/wardrobe/wears` with a fresh
  /// `Idempotency-Key` per logical action (pass [idempotencyKey] to keep
  /// the key stable across retries of the SAME action).
  ///
  /// [itemIds] are backend wardrobe UUIDs sent verbatim — this method
  /// never translates local mock IDs ("1"–"24") into backend UUIDs, so
  /// callers must pass real backend IDs. [wornAt] is omitted when null
  /// and the server defaults it to now.
  ///
  /// Returns the [WearEventLogResponse] on 201 (`created` distinguishes a
  /// fresh log from an idempotent replay), or null on 404/409/422/401,
  /// 5xx, malformed bodies, or network failure — an error is never turned
  /// into a fake success, and there is deliberately NO mock fallback.
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async {
    try {
      final request = WearEventLogRequest(itemIds: itemIds, wornAt: wornAt);
      final response = await _client
          .post(
            Uri.parse('$baseUrl/v1/wardrobe/wears'),
            headers: {
              'Content-Type': 'application/json; charset=UTF-8',
              'Authorization': 'Bearer $_devToken',
              'Idempotency-Key': idempotencyKey ?? newWearIdempotencyKey(),
            },
            body: jsonEncode(request.toJson()),
          )
          .timeout(_timeout);
      if (response.statusCode == 201) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return WearEventLogResponse.fromJson(decoded);
      }
      debugPrint(
        'Wear log responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Wardrobe backend unreachable during wear log: $error');
    }
    return null;
  }

  void dispose() => _client.close();
}

/// Generates a fresh v4-style client idempotency key for one wear-logging
/// action.
///
/// Mirrors `newOutfitIdempotencyKey()` in the assistant feature without
/// importing across features (feature-first boundary): 122 random bits
/// formatted as UUID text, no new dependency. The backend remains
/// authoritative for idempotency; Flutter only guarantees a fresh key per
/// new action — pass [idempotencyKey] explicitly to keep the key stable
/// across retries of the SAME action.
@visibleForTesting
String newWearIdempotencyKey() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 0x0F) | 0x40;
  bytes[8] = (bytes[8] & 0x3F) | 0x80;
  String hex(int v) => v.toRadixString(16).padLeft(2, '0');
  final h = bytes.map(hex).join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-'
      '${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}