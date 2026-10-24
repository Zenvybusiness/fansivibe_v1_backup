import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/discover/data/discover_client.dart';
import 'package:fansivibe/features/discover/data/discover_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/auth/secure_token_storage.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
    SecureTokenStorage.resetForTest();
    AuthSession.resetForTest();
    await AuthSession.clearSession();
  });

  group('ForYouDiscoveryResponse deserialization', () {
    test('parses full response payload correctly', () {
      final json = {
        'items': [
          {
            'id': 'rec-1',
            'title': 'Indigo Linen Shirt',
            'brand': 'Kutch Indigo',
            'category': 'tops',
            'subcategory': 'shirt',
            'price': 2499.0,
            'currency': 'INR',
            'availability': true,
            'imageUrls': ['https://cdn.fixture.test/shirt.jpg'],
            'attributes': {'color': 'indigo', 'material': 'linen', 'synthetic': true, 'fixture': true},
            'ffoConcepts': ['cotton', 'indigo'],
            'isSynthetic': true,
            'isFixture': true,
            'score': 85.5,
            'rank': 1,
            'scoreBreakdown': {
              'preferenceMatch': 40.0,
              'styleProfileMatch': 20.0,
              'wardrobeComplementarity': 15.0,
              'budgetAvailability': 10.5,
              'totalScore': 85.5,
              'matchReasons': ['Matches linen preference'],
              'neutralDimensions': ['brand_preference'],
            },
            'explanation': {
              'summary': 'Selected based on fabric preferences.',
              'reasons': ['Breathable linen'],
              'positiveEvidence': ['Linen confirmed'],
              'neutralDimensions': ['brand_preference'],
              'isSyntheticFixture': true,
              'provenance': 'synthetic_fixture_catalog',
            },
          }
        ],
        'totalCount': 42,
        'page': 1,
        'pageSize': 1,
        'totalPages': 42,
        'hasNext': true,
        'hasPrev': false,
        'isPersonalized': true,
        'appliedContext': {
          'isGuest': false,
          'userId': 'usr-001',
          'displayName': 'Test User',
          'hasWardrobe': true,
          'styleType': 'Minimalist',
        },
      };

      final response = ForYouDiscoveryResponse.fromJson(json);
      expect(response.totalCount, 42);
      expect(response.page, 1);
      expect(response.pageSize, 1);
      expect(response.totalPages, 42);
      expect(response.hasNext, isTrue);
      expect(response.hasPrev, isFalse);
      expect(response.isPersonalized, isTrue);
      expect(response.appliedContext.isGuest, isFalse);
      expect(response.appliedContext.userId, 'usr-001');
      expect(response.appliedContext.displayName, 'Test User');
      expect(response.appliedContext.hasWardrobe, isTrue);
      expect(response.appliedContext.styleType, 'Minimalist');

      expect(response.items.length, 1);
      final item = response.items.first;
      expect(item.id, 'rec-1');
      expect(item.title, 'Indigo Linen Shirt');
      expect(item.brand, 'Kutch Indigo');
      expect(item.price, 2499.0);
      expect(item.currency, 'INR');
      expect(item.availability, isTrue);
      expect(item.imageUrls, ['https://cdn.fixture.test/shirt.jpg']);
      expect(item.isSynthetic, isTrue);
      expect(item.isFixture, isTrue);
      expect(item.isSyntheticFixture, isTrue);
      expect(item.score, 85.5);
      expect(item.rank, 1);
      expect(item.scoreBreakdown.matchReasons, ['Matches linen preference']);
      expect(item.explanation.provenance, 'synthetic_fixture_catalog');
      expect(item.explanation.isSyntheticFixture, isTrue);
    });

    test('handles absent and nullable fields gracefully', () {
      final json = {
        'items': [
          {
            'id': 'rec-2',
            'title': 'Generic Tee',
            'category': 'tops',
            'isSynthetic': false,
            'isFixture': false,
            'score': 10.0,
            'rank': 1,
          }
        ],
        'totalCount': 1,
        'page': 1,
        'pageSize': 10,
        'totalPages': 1,
      };

      final response = ForYouDiscoveryResponse.fromJson(json);
      expect(response.items.length, 1);
      final item = response.items.first;
      expect(item.id, 'rec-2');
      expect(item.brand, isNull);
      expect(item.subcategory, isNull);
      expect(item.price, isNull);
      expect(item.currency, 'INR');
      expect(item.availability, isNull);
      expect(item.imageUrls, isEmpty);
      expect(item.attributes, isEmpty);
      expect(item.ffoConcepts, isEmpty);
      expect(item.isSynthetic, isFalse);
      expect(item.isFixture, isFalse);
      expect(item.isSyntheticFixture, isFalse);
      expect(item.scoreBreakdown.totalScore, 0.0);
      expect(item.explanation.summary, isEmpty);

      expect(response.hasNext, isFalse);
      expect(response.hasPrev, isFalse);
      expect(response.isPersonalized, isFalse);
      expect(response.appliedContext.isGuest, isTrue);
      expect(response.appliedContext.userId, isNull);
    });
  });

  group('CompleteLooksDiscoveryResponse deserialization', () {
    test('parses full ensemble with catalog and wardrobe pieces', () {
      final json = {
        'looks': [
          {
            'lookId': 'look-abc',
            'slots': {
              'top': {
                'itemId': 'cat-top-1',
                'source': 'catalog',
                'title': 'Knit Overshirt',
                'category': 'tops',
                'brand': 'Studio Atelier',
                'price': 3499.0,
                'currency': 'INR',
                'imageUrl': 'https://cdn.fixture.test/knit.jpg',
                'isSynthetic': true,
                'isFixture': true,
                'ffoConcepts': ['cotton', 'regular-fit'],
              },
              'bottom': {
                'itemId': 'wardrobe-bot-1',
                'source': 'wardrobe',
                'title': 'Owned Pleated Trousers',
                'category': 'bottoms',
                'price': null,
                'imageUrl': null,
                'isSynthetic': false,
                'isFixture': false,
              },
            },
            'totalCatalogPrice': 3499.0,
            'currency': 'INR',
            'compatibilityScore': 92.0,
            'compatibilityBreakdown': {
              'categoryCompleteness': 25.0,
              'colorHarmony': 25.0,
              'materialConsistency': 22.0,
              'styleConceptMatch': 20.0,
              'totalScore': 92.0,
              'reasons': ['Complementary neutrals'],
              'warnings': <String>[],
            },
            'compatibilityReasons': ['Complementary neutrals'],
            'unresolvedConstraints': <String>[],
            'explanation': {
              'summary': 'Cohesive ensemble utilizing your wardrobe bottoms.',
              'reasons': ['Color harmony verified'],
              'positiveEvidence': ['Neutral baseline'],
              'isSyntheticFixture': true,
              'isWardrobeAware': true,
            },
            'isWardrobeAware': true,
            'wardrobeItemCount': 1,
            'catalogItemCount': 1,
            'containsSyntheticFixtures': true,
            'bundlePurchasable': false,
          }
        ],
        'totalLooks': 1,
        'targetOccasion': 'smart_casual',
        'targetAesthetic': 'atelier_minimal',
        'maxBudget': 5000.0,
        'isWardrobeAware': true,
        'containsSyntheticFixtures': true,
      };

      final response = CompleteLooksDiscoveryResponse.fromJson(json);
      expect(response.totalLooks, 1);
      expect(response.targetOccasion, 'smart_casual');
      expect(response.targetAesthetic, 'atelier_minimal');
      expect(response.maxBudget, 5000.0);
      expect(response.isWardrobeAware, isTrue);
      expect(response.containsSyntheticFixtures, isTrue);

      final look = response.looks.first;
      expect(look.lookId, 'look-abc');
      expect(look.totalCatalogPrice, 3499.0);
      expect(look.currency, 'INR');
      expect(look.compatibilityScore, 92.0);
      expect(look.bundlePurchasable, isFalse);
      expect(look.isWardrobeAware, isTrue);
      expect(look.wardrobeItemCount, 1);
      expect(look.catalogItemCount, 1);
      expect(look.containsSyntheticFixtures, isTrue);

      final top = look.slots['top']!;
      expect(top.isCatalog, isTrue);
      expect(top.isWardrobe, isFalse);
      expect(top.title, 'Knit Overshirt');
      expect(top.price, 3499.0);
      expect(top.isSynthetic, isTrue);

      final bottom = look.slots['bottom']!;
      expect(bottom.isCatalog, isFalse);
      expect(bottom.isWardrobe, isTrue);
      expect(bottom.title, 'Owned Pleated Trousers');
      expect(bottom.price, isNull);
    });

    test('handles partial slot assignments and null breakdowns', () {
      final json = {
        'looks': [
          {
            'lookId': 'look-partial',
            'slots': <String, dynamic>{},
            'totalCatalogPrice': 0.0,
            'compatibilityScore': 50.0,
            'bundlePurchasable': false,
          }
        ],
        'totalLooks': 1,
      };

      final response = CompleteLooksDiscoveryResponse.fromJson(json);
      final look = response.looks.first;
      expect(look.slots, isEmpty);
      expect(look.totalCatalogPrice, 0.0);
      expect(look.currency, 'INR');
      expect(look.compatibilityBreakdown.totalScore, 0.0);
      expect(look.compatibilityReasons, isEmpty);
      expect(look.unresolvedConstraints, isEmpty);
      expect(look.explanation.summary, isEmpty);
      expect(look.isWardrobeAware, isFalse);
      expect(look.wardrobeItemCount, 0);
      expect(look.catalogItemCount, 0);
      expect(look.containsSyntheticFixtures, isFalse);
      expect(look.bundlePurchasable, isFalse);
    });
  });

  group('DiscoveryTrendingResponse deserialization', () {
    test('parses catalog activity with demand unavailable semantics', () {
      final json = {
        'windowStart': '2026-10-01T00:00:00Z',
        'windowEnd': '2026-10-14T00:00:00Z',
        'generatedAt': '2026-10-14T12:00:00Z',
        'demandTrendStatus': 'insufficient_evidence',
        'evidenceType': 'catalog_activity',
        'catalogActivityStatus': 'active',
        'directDemandAvailable': false,
        'sourceCoverage': 5,
        'observationCount': 1,
        'insufficientEvidenceReason': 'Direct consumer-demand signals are unavailable in this environment.',
        'confidenceInterpretation': 'Signals reflect internal catalog additions only.',
        'limitations': [
          'No direct consumer search or purchase telemetry',
          'Ranking reflects catalog frequency rather than verified consumer demand',
        ],
        'items': [
          {
            'concept': 'carpenter-pant',
            'canonicalName': 'Carpenter Workwear Pants',
            'category': 'bottoms',
            'evidenceType': 'catalog_activity',
            'catalogActivityStatus': 'active',
            'observationCount': 4,
            'distinctProducts': 3,
            'distinctSources': 2,
            'firstObservedAt': '2026-10-01T00:00:00Z',
            'lastObservedAt': '2026-10-14T00:00:00Z',
            'catalogGrowth': 0.15,
            'confidence': 0.85,
            'fixtureDerived': true,
            'publishable': true,
            'directDemandAvailable': false,
            'signals': [
              {
                'metric': 'catalog_frequency',
                'kind': 'catalog',
                'available': true,
                'value': 4,
                'unit': 'items',
              }
            ],
            'explanation': {
              'summary': 'Observed catalog frequency in bottoms category.',
              'evidenceType': 'catalog_activity',
              'demandSignalAvailable': false,
              'reasons': ['Catalog additions observed'],
            },
          }
        ],
      };

      final response = DiscoveryTrendingResponse.fromJson(json);
      expect(response.demandTrendStatus, 'insufficient_evidence');
      expect(response.directDemandAvailable, isFalse);
      expect(response.evidenceType, 'catalog_activity');
      expect(response.insufficientEvidenceReason, contains('Direct consumer-demand signals are unavailable'));
      expect(response.limitations.length, 2);
      expect(response.observationCount, 1);
      expect(response.windowStart, '2026-10-01T00:00:00Z');

      final item = response.items.first;
      expect(item.concept, 'carpenter-pant');
      expect(item.canonicalName, 'Carpenter Workwear Pants');
      expect(item.category, 'bottoms');
      expect(item.catalogActivityStatus, 'active');
      expect(item.observationCount, 4);
      expect(item.distinctProducts, 3);
      expect(item.fixtureDerived, isTrue);
      expect(item.publishable, isTrue);
      expect(item.directDemandAvailable, isFalse);
      expect(item.signals.length, 1);
      expect(item.signals.first.metric, 'catalog_frequency');
      expect(item.signals.first.available, isTrue);
      expect(item.explanation.summary, 'Observed catalog frequency in bottoms category.');
      expect(item.explanation.demandSignalAvailable, isFalse);
    });

    test('does not invent metrics when nullable values are omitted', () {
      final json = {
        'windowStart': '2026-10-01T00:00:00Z',
        'windowEnd': '2026-10-14T00:00:00Z',
        'generatedAt': '2026-10-14T12:00:00Z',
        'demandTrendStatus': 'insufficient_evidence',
        'catalogActivityStatus': 'active',
        'directDemandAvailable': false,
        'sourceCoverage': 0,
        'observationCount': 1,
        'confidenceInterpretation': 'None',
        'items': [
          {
            'concept': 'linen-vest',
            'canonicalName': 'Linen Vest',
            'category': 'outerwear',
            'catalogActivityStatus': 'active',
            'observationCount': 1,
            'distinctProducts': 1,
            'distinctSources': 1,
            'firstObservedAt': '',
            'lastObservedAt': '',
            'confidence': 0.5,
            'fixtureDerived': true,
            'publishable': false,
          }
        ],
      };

      final response = DiscoveryTrendingResponse.fromJson(json);
      expect(response.insufficientEvidenceReason, isNull);
      expect(response.limitations, isEmpty);
      expect(response.observationCount, 1);

      final item = response.items.first;
      expect(item.catalogGrowth, isNull);
      expect(item.priceChangeRatio, isNull);
      expect(item.inStockRatio, isNull);
      expect(item.strength, isNull);
      expect(item.signals, isEmpty);
      expect(item.reasons, isEmpty);
      expect(item.explanation.summary, isEmpty);
      expect(item.explanation.demandSignalAvailable, isFalse);
    });
  });

  group('DiscoverClient networking & security behavior', () {
    test('guest requests NEVER send Authorization header', () async {
      await AuthSession.saveSession('leaked-token');
      expect(AuthSession.isAuthenticated, isTrue);

      final capturedHeaders = <Map<String, String>>[];
      final mock = MockClient((request) async {
        capturedHeaders.add(request.headers);
        return http.Response(
          jsonEncode({
            'items': <dynamic>[],
            'totalCount': 0,
            'page': 1,
            'pageSize': 20,
            'totalPages': 0,
            'hasNext': false,
            'hasPrev': false,
            'isPersonalized': false,
            'appliedContext': {'isGuest': true},
          }),
          200,
        );
      });

      final client = DiscoverClient(client: mock);
      final result = await client.getForYouRecommendations(isGuest: true);

      expect(result.isSuccess, isTrue);
      expect(capturedHeaders.length, 1);
      expect(capturedHeaders.first.containsKey('Authorization'), isFalse);
    });

    test('authenticated requests attach Bearer token when present', () async {
      await AuthSession.saveSession('valid-secret-token');

      final capturedHeaders = <Map<String, String>>[];
      final mock = MockClient((request) async {
        capturedHeaders.add(request.headers);
        return http.Response(
          jsonEncode({
            'windowStart': '2026-10-01T00:00:00Z',
            'windowEnd': '2026-10-14T00:00:00Z',
            'generatedAt': '2026-10-14T12:00:00Z',
            'demandTrendStatus': 'insufficient_evidence',
            'catalogActivityStatus': 'active',
            'directDemandAvailable': false,
            'sourceCoverage': 1,
            'observationCount': 0,
            'confidenceInterpretation': 'None',
            'items': <dynamic>[],
          }),
          200,
        );
      });

      final client = DiscoverClient(client: mock);
      final result = await client.getTrending();

      expect(result.isSuccess, isTrue);
      expect(capturedHeaders.length, 1);
      expect(capturedHeaders.first['Authorization'], 'Bearer valid-secret-token');
    });

    test('maps 401 response to DiscoverFailure.unauthorized', () async {
      final mock = MockClient((_) async => http.Response('{"error": "Unauthorized"}', 401));
      final client = DiscoverClient(client: mock);

      final result = await client.getTrending();
      expect(result.isSuccess, isFalse);
      expect(result.failure, DiscoverFailure.unauthorized);
    });

    test('maps 422 response to DiscoverFailure.invalidInput', () async {
      final mock = MockClient((_) async => http.Response('{"error": "Invalid Input"}', 422));
      final client = DiscoverClient(client: mock);

      final result = await client.getForYouRecommendations();
      expect(result.isSuccess, isFalse);
      expect(result.failure, DiscoverFailure.invalidInput);
    });

    test('maps network exceptions to DiscoverFailure.networkError', () async {
      final mock = MockClient((_) async => throw Exception('Connection reset by peer'));
      final client = DiscoverClient(client: mock);

      final result = await client.getCompleteLooks();
      expect(result.isSuccess, isFalse);
      expect(result.failure, DiscoverFailure.networkError);
    });

    test('serializes complete looks parameters accurately', () async {
      final capturedUris = <Uri>[];
      final mock = MockClient((request) async {
        capturedUris.add(request.url);
        return http.Response(
          jsonEncode({'looks': <dynamic>[], 'totalLooks': 0}),
          200,
        );
      });

      final client = DiscoverClient(client: mock);
      await client.getCompleteLooks(
        limit: 5,
        maxBudget: 15000.0,
        targetOccasion: 'evening',
        targetAesthetic: 'minimal',
        anchorProductId: 'prod-99',
        allowWardrobe: false,
        includeSynthetic: true,
      );

      expect(capturedUris.length, 1);
      final uri = capturedUris.first;
      expect(uri.path, '/v1/discovery/looks/complete');
      expect(uri.queryParameters['limit'], '5');
      expect(uri.queryParameters['max_budget'], '15000.0');
      expect(uri.queryParameters['target_occasion'], 'evening');
      expect(uri.queryParameters['target_aesthetic'], 'minimal');
      expect(uri.queryParameters['anchor_product_id'], 'prod-99');
      expect(uri.queryParameters['allow_wardrobe'], 'false');
      expect(uri.queryParameters['include_synthetic'], 'true');
    });

    test('serializes trending date window and category parameters', () async {
      final capturedUris = <Uri>[];
      final mock = MockClient((request) async {
        capturedUris.add(request.url);
        return http.Response(
          jsonEncode({
            'windowStart': '2026-10-01T00:00:00Z',
            'windowEnd': '2026-10-14T00:00:00Z',
            'generatedAt': '2026-10-14T12:00:00Z',
            'demandTrendStatus': 'insufficient_evidence',
            'catalogActivityStatus': 'active',
            'directDemandAvailable': false,
            'sourceCoverage': 1,
            'observationCount': 0,
            'confidenceInterpretation': 'None',
            'items': <dynamic>[],
          }),
          200,
        );
      });

      final client = DiscoverClient(client: mock);
      await client.getTrending(
        limit: 10,
        category: 'accessories',
        windowStart: DateTime.utc(2026, 10, 1),
        windowEnd: DateTime.utc(2026, 10, 14),
      );

      expect(capturedUris.length, 1);
      final uri = capturedUris.first;
      expect(uri.path, '/v1/discovery/trending');
      expect(uri.queryParameters['limit'], '10');
      expect(uri.queryParameters['category'], 'accessories');
      expect(uri.queryParameters['window_start'], contains('2026-10-01'));
      expect(uri.queryParameters['window_end'], contains('2026-10-14'));
    });
  });
}
