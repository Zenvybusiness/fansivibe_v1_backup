import 'dart:async';
import 'dart:convert';

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

  void dispose() => _client.close();
}