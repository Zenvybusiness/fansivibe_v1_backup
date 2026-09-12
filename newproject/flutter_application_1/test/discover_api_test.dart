import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/discover/data/discover_client.dart';
import 'package:fansivibe/features/discover/data/discover_models.dart';
import 'package:fansivibe/features/discover/data/discover_repository.dart';

/// Exact M14 feed envelope wire shape (cursor envelope — no `total`).
Map<String, dynamic> wireFeedPage({
  List<Map<String, dynamic>>? items,
  Object? nextCursor = 'CURSOR-1',
  bool hasMore = true,
}) {
  return {
    'items': items ?? [wireSummary(), wireSummary(id: 'classic_pompadour')],
    'next_cursor': nextCursor,
    'has_more': hasMore,
  };
}

/// Exact M14 summary row wire shape (grounded catalog fields only).
Map<String, dynamic> wireSummary({
  String id = 'textured_quiff',
  int matchScore = 94,
}) {
  return {
    'id': id,
    'title': 'Textured Quiff',
    'description': 'A modern take on the classic quiff.',
    'matchScore': matchScore,
    'reasons': ['Volume on top suits oval faces'],
  };
}

/// Exact M14 detail wire shape (summary core + grounded content).
Map<String, dynamic> wireDetail({String id = 'textured_quiff'}) {
  return {
    ...wireSummary(id: id),
    'stylingTips': 'Apply mousse to damp hair.',
    'maintenance': 'Medium. Trim every 4-5 weeks',
    'bestFor': 'Oval, Heart, and Rectangle face shapes',
  };
}

DiscoverClient clientFor(http.Response response, {List<Uri>? log}) {
  return DiscoverClient(
    client: MockClient((request) async {
      log?.add(request.url);
      return response;
    }),
  );
}

void main() {
  group('LookSummary model', () {
    test('parses the exact wire shape', () {
      final summary = LookSummary.fromJson(wireSummary());
      expect(summary.id, 'textured_quiff');
      expect(summary.title, 'Textured Quiff');
      expect(summary.matchScore, 94);
      expect(summary.reasons, ['Volume on top suits oval faces']);
    });

    test('ids are backend codes, never translated', () {
      final summary = LookSummary.fromJson(wireSummary(id: 'full_beard'));
      expect(summary.id, 'full_beard');
    });

    test('strict parsing rejects wrong types', () {
      expect(
        () => LookSummary.fromJson({...wireSummary(), 'matchScore': '94'}),
        throwsA(isA<TypeError>()),
      );
      expect(
        () => LookSummary.fromJson({...wireSummary(), 'reasons': 'nope'}),
        throwsA(isA<TypeError>()),
      );
    });

    test('round-trips through toJson', () {
      final json = wireSummary();
      expect(LookSummary.fromJson(json).toJson(), json);
    });
  });

  group('LookDetail model', () {
    test('parses the exact wire shape', () {
      final detail = LookDetail.fromJson(wireDetail());
      expect(detail.id, 'textured_quiff');
      expect(detail.stylingTips, 'Apply mousse to damp hair.');
      expect(detail.maintenance, 'Medium. Trim every 4-5 weeks');
      expect(detail.bestFor, 'Oval, Heart, and Rectangle face shapes');
    });

    test('strict parsing rejects wrong types', () {
      expect(
        () => LookDetail.fromJson({...wireDetail(), 'bestFor': 42}),
        throwsA(isA<TypeError>()),
      );
    });
  });

  group('LookFeedPage model', () {
    test('parses cursor envelope keys (snake_case, no total)', () {
      final page = LookFeedPage.fromJson(wireFeedPage());
      expect(page.items, hasLength(2));
      expect(page.nextCursor, 'CURSOR-1');
      expect(page.hasMore, isTrue);
    });

    test('terminal page has null cursor and hasMore false', () {
      final page = LookFeedPage.fromJson(
        wireFeedPage(nextCursor: null, hasMore: false),
      );
      expect(page.nextCursor, isNull);
      expect(page.hasMore, isFalse);
    });

    test('empty items is a valid page (empty is not an error)', () {
      final page = LookFeedPage.fromJson(
        wireFeedPage(items: [], nextCursor: null, hasMore: false),
      );
      expect(page.items, isEmpty);
    });
  });

  group('DiscoverClient.getLookFeed', () {
    test('hits GET /v1/looks with no query when filters are null', () async {
      final log = <Uri>[];
      final client = clientFor(
        http.Response(jsonEncode(wireFeedPage()), 200),
        log: log,
      );
      final result = await client.getLookFeed();
      expect(result.isPage, isTrue);
      expect(log.single.path, '/v1/looks');
      expect(log.single.queryParameters, isEmpty);
    });

    test('passes filters, cursor, and limit verbatim', () async {
      final log = <Uri>[];
      final client = clientFor(
        http.Response(jsonEncode(wireFeedPage()), 200),
        log: log,
      );
      await client.getLookFeed(
        occasion: 'casual',
        style: 'minimalist',
        fit: 'slim',
        cursor: 'ABC',
        limit: 3,
      );
      expect(log.single.queryParameters, {
        'occasion': 'casual',
        'style': 'minimalist',
        'fit': 'slim',
        'cursor': 'ABC',
        'limit': '3',
      });
    });

    test('failure table maps statuses without throwing', () async {
      final cases = {
        401: DiscoverFailure.unauthorized,
        422: DiscoverFailure.invalidInput,
        429: DiscoverFailure.rateLimited,
        500: DiscoverFailure.unknown,
      };
      for (final entry in cases.entries) {
        final client = clientFor(http.Response('{}', entry.key));
        final result = await client.getLookFeed();
        expect(result.isPage, isFalse, reason: 'status ${entry.key}');
        expect(result.failure, entry.value, reason: 'status ${entry.key}');
      }
    });

    test('malformed 200 body is a failure, never a fake page', () async {
      final client = clientFor(http.Response('not-json', 200));
      final result = await client.getLookFeed();
      expect(result.isPage, isFalse);
    });

    test('offline transport is a network failure, never throws', () async {
      final client = DiscoverClient(
        client: MockClient((_) async => throw Exception('offline')),
      );
      final result = await client.getLookFeed();
      expect(result.failure, DiscoverFailure.networkError);
    });
  });

  group('DiscoverClient.getLookDetail', () {
    test('hits GET /v1/looks/{code} with the verbatim code', () async {
      final log = <Uri>[];
      final client = clientFor(
        http.Response(jsonEncode(wireDetail()), 200),
        log: log,
      );
      final result = await client.getLookDetail(lookId: 'textured_quiff');
      expect(result.isAvailable, isTrue);
      expect(result.detail!.id, 'textured_quiff');
      expect(log.single.path, '/v1/looks/textured_quiff');
    });

    test('404 is a truthful not-found', () async {
      final client = clientFor(http.Response('{}', 404));
      final result = await client.getLookDetail(lookId: 'no-such-look');
      expect(result.notFound, isTrue);
      expect(result.isAvailable, isFalse);
    });

    test(
      '422/401 map without throwing; offline is a network failure',
      () async {
        for (final status in [401, 422]) {
          final client = clientFor(http.Response('{}', status));
          final result = await client.getLookDetail(lookId: 'textured_quiff');
          expect(result.isAvailable, isFalse);
          expect(result.notFound, isFalse);
        }
        final offline = DiscoverClient(
          client: MockClient((_) async => throw Exception('offline')),
        );
        final result = await offline.getLookDetail(lookId: 'textured_quiff');
        expect(result.failure, DiscoverFailure.networkError);
      },
    );
  });

  group('DiscoverRepositoryImpl', () {
    test('passes feed args through verbatim', () async {
      final log = <Uri>[];
      final repo = DiscoverRepositoryImpl(
        client: clientFor(
          http.Response(jsonEncode(wireFeedPage()), 200),
          log: log,
        ),
      );
      final result = await repo.getLookFeed(occasion: 'casual', limit: 5);
      expect(result.isPage, isTrue);
      expect(log.single.queryParameters['occasion'], 'casual');
      expect(log.single.queryParameters['limit'], '5');
    });

    test('passes the detail code through verbatim', () async {
      final log = <Uri>[];
      final repo = DiscoverRepositoryImpl(
        client: clientFor(
          http.Response(jsonEncode(wireDetail(id: 'full_beard')), 200),
          log: log,
        ),
      );
      final result = await repo.getLookDetail(lookId: 'full_beard');
      expect(result.detail!.id, 'full_beard');
      expect(log.single.path, '/v1/looks/full_beard');
    });
  });

  group('no fabrication proof', () {
    test('no numeric or mock ids cross the client', () async {
      final log = <Uri>[];
      final client = clientFor(
        http.Response(jsonEncode(wireFeedPage()), 200),
        log: log,
      );
      final result = await client.getLookFeed();
      for (final item in result.page!.items) {
        expect(int.tryParse(item.id), isNull, reason: 'no numeric id');
        expect(item.id.startsWith('fy_'), isFalse);
        expect(item.id.startsWith('tr_'), isFalse);
      }
      expect(log.single.toString().contains('fy_'), isFalse);
    });

    test('feed and detail carry no invented keys', () async {
      const banned = {
        'imageUrl',
        'occasion',
        'styleTags',
        'fitTags',
        'wardrobeMatchCount',
        'matchScoreDetails',
        'isTrending',
        'isOwned',
        'total',
      };
      final feedClient = clientFor(
        http.Response(jsonEncode(wireFeedPage()), 200),
      );
      final page = (await feedClient.getLookFeed()).page!;
      for (final item in page.items) {
        expect((item.toJson().keys.toSet()).intersection(banned), isEmpty);
      }
    });
  });
}
