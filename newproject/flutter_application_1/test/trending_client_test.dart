import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/trending/data/trending_client.dart';
import 'package:fansivibe/features/trending/data/trending_models.dart';
import 'package:fansivibe/features/trending/data/trending_repository.dart';

/// Exact M14 trending feed wire shape (backend contract, camelCase).
Map<String, dynamic> wireFeed() {
  return {
    'region': 'IN',
    'generatedAt': '2026-09-23T02:15:30Z',
    'isStale': false,
    'items': [wireItem()],
  };
}

/// Exact M14 trending item wire shape (score + provenance + products).
Map<String, dynamic> wireItem({String trendId = 'trend-oversized_denim_jacket'}) {
  return {
    'trendId': trendId,
    'displayName': 'oversized denim jacket',
    'category': 'outerwear',
    'region': 'IN',
    'velocity': 0.5,
    'confidence': 0.72,
    'freshnessHours': 1.0,
    'supportingSignals': 2,
    'sources': ['google_trends_in', 'youtube_in'],
    'provenance': [
      {
        'source': 'youtube_in',
        'source_identifier': 'yt-test-1',
        'observed_at': '2026-09-23T02:00:00+00:00',
      },
      {
        'source': 'google_trends_in',
        'source_identifier': 'gt-test-1',
        'observed_at': '2026-09-23T02:00:00+00:00',
      },
    ],
    'matchedProducts': [
      {
        'provider': 'test_commerce',
        'externalId': 'TEST-001',
        'title': 'oversized denim jacket',
        'brand': 'Test Brand',
        'priceInr': 1299.0,
        'imageUrl': null,
        'productUrl': null,
        'inStock': true,
      },
    ],
  };
}

TrendingClient clientFor(http.Response response, {List<Uri>? log}) {
  return TrendingClient(
    client: MockClient((request) async {
      log?.add(request.url);
      return response;
    }),
  );
}

void main() {
  group('TrendingItem model', () {
    test('parses the exact wire shape, nulls stay null', () {
      final item = TrendingItem.fromJson(wireItem());
      expect(item.trendId, 'trend-oversized_denim_jacket');
      expect(item.confidence, 0.72);
      expect(item.sources, ['google_trends_in', 'youtube_in']);
      expect(item.provenance.length, 2);
      expect(item.matchedProducts.single.priceInr, 1299.0);
      // Unprovided fields stay null — never defaulted or faked.
      expect(item.matchedProducts.single.imageUrl, isNull);
      expect(item.matchedProducts.single.productUrl, isNull);
    });

    test('malformed types throw into the client failure path', () {
      expect(
        () => TrendingItem.fromJson({...wireItem(), 'confidence': 'high'}),
        throwsA(isA<TypeError>()),
      );
    });
  });

  group('TrendingClient', () {
    test('feed 200 parses verbatim', () async {
      final client = clientFor(http.Response(jsonEncode(wireFeed()), 200));
      final result = await client.getTrendingFeed();
      expect(result.failure, isNull);
      expect(result.feed!.region, 'IN');
      expect(result.feed!.isStale, isFalse);
      expect(result.feed!.items.single.trendId, 'trend-oversized_denim_jacket');
    });

    test('feed passes region and limit as query params', () async {
      final log = <Uri>[];
      final client = clientFor(http.Response(jsonEncode(wireFeed()), 200), log: log);
      await client.getTrendingFeed(region: 'IN', limit: 10);
      expect(log.single.queryParameters['region'], 'IN');
      expect(log.single.queryParameters['limit'], '10');
    });

    test('feed 401 maps to unauthorized, never throws', () async {
      final client = clientFor(http.Response('unauthorized', 401));
      final result = await client.getTrendingFeed();
      expect(result.feed, isNull);
      expect(result.failure, TrendingFailure.unauthorized);
    });

    test('feed malformed 200 maps to networkError, never mock data', () async {
      final client = clientFor(http.Response('not-json', 200));
      final result = await client.getTrendingFeed();
      expect(result.feed, isNull);
      expect(result.failure, TrendingFailure.networkError);
    });

    test('detail 200 parses, 404 maps to notFound', () async {
      final ok = clientFor(http.Response(jsonEncode(wireItem()), 200));
      final detail = await ok.getTrendDetail(trendId: 'trend-oversized_denim_jacket');
      expect(detail.item!.trendId, 'trend-oversized_denim_jacket');
      expect(detail.notFound, isFalse);

      final missing = clientFor(http.Response('nope', 404));
      final gone = await missing.getTrendDetail(trendId: 'trend-nope');
      expect(gone.item, isNull);
      expect(gone.notFound, isTrue);
    });
  });

  group('TrendingRepository', () {
    test('passes through feed and detail verbatim', () async {
      final repo = TrendingRepositoryImpl(
        client: clientFor(http.Response(jsonEncode(wireFeed()), 200)),
      );
      final feed = await repo.getTrendingFeed();
      expect(feed.feed!.items.single.displayName, 'oversized denim jacket');

      final repoDetail = TrendingRepositoryImpl(
        client: clientFor(http.Response(jsonEncode(wireItem()), 200)),
      );
      final detail = await repoDetail.getTrendDetail(trendId: 'trend-oversized_denim_jacket');
      expect(detail.item!.confidence, 0.72);
    });
  });
}
