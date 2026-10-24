import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/discover/data/discover_models.dart';
import 'package:fansivibe/features/discover/data/discover_repository.dart';
import 'package:fansivibe/features/discover/presentation/widgets/existing_user_for_you_widgets.dart';
import 'package:fansivibe/features/discover/presentation/widgets/product_offer_comparison_sheet.dart';

class FakeOffersDiscoverRepository implements DiscoverRepository {
  FakeOffersDiscoverRepository({
    this.offersResponse,
    this.shouldFail = false,
  });

  ProductOffersResponse? offersResponse;
  bool shouldFail;
  final List<DiscoveryEventItem> recordedEvents = [];
  String? lastGuestSessionId;

  @override
  Future<ProductOffersResult> getProductOffers(String productId) async {
    if (shouldFail) {
      return const ProductOffersResult.failure(DiscoverFailure.networkError);
    }
    return ProductOffersResult.success(
      offersResponse ??
          ProductOffersResponse(
            productId: productId,
            title: 'Test Product',
            brand: 'Test Brand',
            isSyntheticFixture: false,
            offersCount: 0,
            offers: const [],
          ),
    );
  }

  @override
  Uri getOfferRedirectUri({
    required String offerId,
    String? guestSessionId,
    String surface = 'product_offers',
    int? position,
  }) {
    final queryParams = <String, String>{
      'surface': surface,
      if (guestSessionId != null) 'guest_session_id': guestSessionId,
      if (position != null) 'position': position.toString(),
    };
    return Uri.parse(
      'http://localhost:8000/v1/discovery/offers/$offerId/redirect',
    ).replace(queryParameters: queryParams);
  }

  @override
  Future<DiscoveryEventsResult> recordEvents(
    List<DiscoveryEventItem> events, {
    String? guestSessionId,
  }) async {
    recordedEvents.addAll(events);
    lastGuestSessionId = guestSessionId;
    return DiscoveryEventsResult.success(
      DiscoveryEventsBatchResponse(
        acceptedCount: events.length,
        events: events
            .map((e) => DiscoveryEventAck(
                  eventId: e.eventId,
                  status: 'persisted',
                  replayed: false,
                ))
            .toList(),
      ),
    );
  }

  @override
  Future<CompleteLooksDiscoveryResult> getCompleteLooks({
    int limit = 10,
    double? maxBudget,
    String? targetOccasion,
    String? targetAesthetic,
    String? anchorProductId,
    String? anchorWardrobeItemId,
    bool allowWardrobe = true,
    bool includeSynthetic = true,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<ForYouFeedResult> getForYouFeed({String? cursor, int? limit}) {
    throw UnimplementedError();
  }

  @override
  Future<ForYouDiscoveryResult> getForYouRecommendations({
    int page = 1,
    int pageSize = 20,
    String? q,
    List<String>? categories,
    List<String>? excludeCategories,
    List<String>? brands,
    List<String>? excludeBrands,
    double? minPrice,
    double? maxPrice,
    String? currency,
    List<String>? colors,
    List<String>? materials,
    List<String>? fits,
    List<String>? silhouettes,
    bool? inStockOnly,
    bool includeSynthetic = true,
    bool isGuest = false,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<LookDetailResult> getLookDetail({required String lookId}) {
    throw UnimplementedError();
  }

  @override
  Future<DiscoverFeedResult> getLookFeed({
    String? occasion,
    String? style,
    String? fit,
    String? cursor,
    int? limit,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<DiscoveryTrendingResult> getTrending({
    DateTime? windowStart,
    DateTime? windowEnd,
    int limit = 20,
    String? category,
  }) {
    throw UnimplementedError();
  }
}

void main() {
  group('DISCOVERY-10B-3: Product Offers Model Serialization', () {
    test('ProductOffersResponse parses valid multi-retailer JSON', () {
      final jsonRaw = {
        'productId': '11111111-1111-4111-8111-111111111111',
        'title': 'Tailored Wool Coat',
        'brand': 'Atelier Minimalist',
        'isSyntheticFixture': false,
        'offersCount': 2,
        'offers': [
          {
            'id': '22222222-2222-4222-8222-222222222222',
            'retailer': {
              'id': '33333333-3333-4333-8333-333333333333',
              'name': 'Nordstrom Atelier',
              'slug': 'nordstrom-atelier',
              'domain': 'nordstrom.com',
            },
            'price': 18500.0,
            'originalPrice': 22000.0,
            'currency': 'INR',
            'inStock': true,
            'productUrl': 'https://nordstrom.com/items/wool-coat-123',
            'redirectUrl': '/v1/discovery/offers/22222222-2222-4222-8222-222222222222/redirect',
            'lastCheckedAt': DateTime.now().subtract(const Duration(hours: 2)).toIso8601String(),
            'isPriceFresh': true,
            'freshnessStatus': 'Price verified recently',
            'variant': {
              'id': '44444444-4444-4444-8444-444444444444',
              'sku': 'WOOL-COAT-BLK-M',
              'color': 'Black',
              'size': 'M',
              'attributes': {'material': 'Wool'},
            },
          },
          {
            'id': '55555555-5555-4555-8555-555555555555',
            'retailer': {
              'id': '66666666-6666-4666-8666-666666666666',
              'name': 'Farfetch Luxury',
              'slug': 'farfetch-luxury',
              'domain': 'farfetch.com',
            },
            'price': 19200.0,
            'currency': 'INR',
            'inStock': false,
            'productUrl': 'https://farfetch.com/items/wool-coat-999',
            'redirectUrl': '/v1/discovery/offers/55555555-5555-4555-8555-555555555555/redirect',
            'lastCheckedAt': DateTime.now().subtract(const Duration(hours: 48)).toIso8601String(),
            'isPriceFresh': false,
            'freshnessStatus': 'Verified 2 days ago',
            'variant': null,
          },
        ],
      };

      final response = ProductOffersResponse.fromJson(jsonRaw);

      expect(response.productId, '11111111-1111-4111-8111-111111111111');
      expect(response.title, 'Tailored Wool Coat');
      expect(response.brand, 'Atelier Minimalist');
      expect(response.isSyntheticFixture, isFalse);
      expect(response.offersCount, 2);
      expect(response.offers.length, 2);

      final offer1 = response.offers[0];
      expect(offer1.id, '22222222-2222-4222-8222-222222222222');
      expect(offer1.retailer.name, 'Nordstrom Atelier');
      expect(offer1.retailer.domain, 'nordstrom.com');
      expect(offer1.price, 18500.0);
      expect(offer1.originalPrice, 22000.0);
      expect(offer1.inStock, isTrue);
      expect(offer1.isPriceFresh, isTrue);
      expect(offer1.variant?.sku, 'WOOL-COAT-BLK-M');
      expect(offer1.variant?.size, 'M');

      final offer2 = response.offers[1];
      expect(offer2.retailer.name, 'Farfetch Luxury');
      expect(offer2.inStock, isFalse);
      expect(offer2.isPriceFresh, isFalse);
      expect(offer2.variant, isNull);
    });

    test('ProductOffersResponse parses empty synthetic fixture response', () {
      final jsonRaw = {
        'productId': 'fixture-product-01',
        'title': 'Demo Fixture Blazer',
        'brand': 'Fansivibe Atelier',
        'isSyntheticFixture': true,
        'offersCount': 0,
        'offers': <Map<String, dynamic>>[],
      };

      final response = ProductOffersResponse.fromJson(jsonRaw);
      expect(response.productId, 'fixture-product-01');
      expect(response.title, 'Demo Fixture Blazer');
      expect(response.isSyntheticFixture, isTrue);
      expect(response.offersCount, 0);
      expect(response.offers, isEmpty);
    });
  });

  group('DISCOVERY-10B-3: ProductOfferComparisonSheet UI & Telemetry', () {
    testWidgets('Renders verified retailer offers with price, freshness, and attribution tap', (tester) async {
      tester.view.physicalSize = const Size(800, 1200);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      final product = const ForYouProductItem(
        id: '11111111-1111-4111-8111-111111111111',
        brand: 'Atelier Minimalist',
        title: 'Tailored Wool Coat',
        price: '₹18,500',
        imageAsset: 'assets/images/discover_hero_quiet_luxury.jpg',
        isSyntheticFixture: false,
      );

      final List<ProductOfferItem> offers = [
        const ProductOfferItem(
          id: '22222222-2222-4222-8222-222222222222',
          retailer: RetailerSummary(
            id: '33333333-3333-4333-8333-333333333333',
            name: 'Nordstrom Atelier',
            slug: 'nordstrom-atelier',
            domain: 'nordstrom.com',
          ),
          price: 18500.0,
          originalPrice: 22000.0,
          currency: 'INR',
          inStock: true,
          productUrl: 'https://nordstrom.com/items/wool-coat-123',
          redirectUrl: '/v1/discovery/offers/22222222-2222-4222-8222-222222222222/redirect',
          lastCheckedAt: '2026-10-14T12:00:00Z',
          isPriceFresh: true,
          freshnessStatus: 'Price verified recently',
          variant: ProductVariantSummary(
            id: '44444444-4444-4444-8444-444444444444',
            sku: 'WOOL-COAT-BLK-M',
            color: 'Black',
            size: 'M',
            attributes: {'material': 'Wool'},
          ),
        ),
      ];

      final fakeRepo = FakeOffersDiscoverRepository(
        offersResponse: ProductOffersResponse(
          productId: product.id,
          title: product.title,
          brand: product.brand,
          isSyntheticFixture: false,
          offersCount: 1,
          offers: offers,
        ),
      );

      ProductOfferItem? tappedOffer;
      Uri? tappedUri;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ProductOfferComparisonSheet(
              product: product,
              repository: fakeRepo,
              initialOffers: offers,
              onPurchaseTap: (offer, redirectUri) {
                tappedOffer = offer;
                tappedUri = redirectUri;
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Header checks
      expect(find.text('AVAILABLE OFFERS'), findsOneWidget);
      expect(find.text('Tailored Wool Coat'), findsOneWidget);
      expect(find.text('ATELIER MINIMALIST'), findsOneWidget);

      // Offer card checks
      expect(find.text('Nordstrom Atelier'), findsOneWidget);
      expect(find.text('₹18500'), findsOneWidget);
      expect(find.text('IN STOCK'), findsOneWidget);
      expect(find.text('✓ Price Verified (<24h)'), findsOneWidget);
      expect(find.text('Size: M'), findsOneWidget);
      expect(find.text('Color: Black'), findsOneWidget);

      // Purchase button
      final buyButton = find.text('BUY AT NORDSTROM ATELIER →');
      expect(buyButton, findsOneWidget);

      // Tap purchase action
      await tester.tap(buyButton);
      await tester.pumpAndSettle();

      // Attribution telemetry and redirect verification
      expect(tappedOffer, isNotNull);
      expect(tappedOffer!.id, '22222222-2222-4222-8222-222222222222');
      expect(tappedUri, isNotNull);
      expect(tappedUri.toString(), contains('/v1/discovery/offers/22222222-2222-4222-8222-222222222222/redirect'));

      // Event recorded in fake repo
      expect(fakeRepo.recordedEvents.length, 1);
      final event = fakeRepo.recordedEvents.first;
      expect(event.eventType, 'offer_click');
      expect(event.targetType, 'product');
      expect(event.targetId, product.id);
      expect(event.surface, 'product_offer_sheet');
      expect(event.metadata['offerId'], '22222222-2222-4222-8222-222222222222');
      expect(event.metadata['retailer'], 'Nordstrom Atelier');
      expect(event.metadata['retailerSlug'], 'nordstrom-atelier');
    });

    testWidgets('Synthetic fixture displays development disclosure and zero merchant buttons', (tester) async {
      tester.view.physicalSize = const Size(800, 1200);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      final fixtureProduct = const ForYouProductItem(
        id: 'fixture-product-999',
        brand: 'Fansivibe Atelier',
        title: 'Demo Tailored Coat',
        price: '₹12,000',
        imageAsset: 'assets/images/discover_hero_quiet_luxury.jpg',
        isSyntheticFixture: true,
      );

      final fakeRepo = FakeOffersDiscoverRepository(
        offersResponse: ProductOffersResponse(
          productId: fixtureProduct.id,
          title: fixtureProduct.title,
          brand: fixtureProduct.brand,
          isSyntheticFixture: true,
          offersCount: 0,
          offers: const [],
        ),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ProductOfferComparisonSheet(
              product: fixtureProduct,
              repository: fakeRepo,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verifies synthetic fixture badge
      expect(find.text('DEVELOPMENT FIXTURE'), findsOneWidget);

      // Verifies Digital Atelier disclosure
      expect(find.text('Synthetic Demo Product'), findsOneWidget);
      expect(
        find.textContaining('is a development fixture catalog item created for style harmonization'),
        findsOneWidget,
      );
      expect(find.text('Understood'), findsOneWidget);

      // ZERO merchant buttons must exist
      expect(find.textContaining('BUY AT'), findsNothing);
    });

    testWidgets('Out of stock offer displays disabled action', (tester) async {
      tester.view.physicalSize = const Size(800, 1200);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      final product = const ForYouProductItem(
        id: '11111111-1111-4111-8111-111111111111',
        brand: 'Studio Atelier',
        title: 'Silk Evening Gown',
        price: '₹25,000',
        imageAsset: 'assets/images/discover_hero_quiet_luxury.jpg',
        isSyntheticFixture: false,
      );

      final List<ProductOfferItem> offers = [
        const ProductOfferItem(
          id: 'offer-out-of-stock',
          retailer: RetailerSummary(
            id: 'ret-1',
            name: 'Farfetch Luxury',
            slug: 'farfetch-luxury',
            domain: 'farfetch.com',
          ),
          price: 25000.0,
          currency: 'INR',
          inStock: false,
          productUrl: 'https://farfetch.com/gown',
          redirectUrl: '/v1/discovery/offers/offer-out-of-stock/redirect',
          isPriceFresh: false,
          freshnessStatus: 'Price verification pending',
        ),
      ];

      final fakeRepo = FakeOffersDiscoverRepository(
        offersResponse: ProductOffersResponse(
          productId: product.id,
          title: product.title,
          brand: product.brand,
          isSyntheticFixture: false,
          offersCount: 1,
          offers: offers,
        ),
      );

      bool tapped = false;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ProductOfferComparisonSheet(
              product: product,
              repository: fakeRepo,
              initialOffers: offers,
              onPurchaseTap: (_, __) => tapped = true,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('OUT OF STOCK'), findsOneWidget);
      final disabledButton = find.text('OUT OF STOCK AT FARFETCH LUXURY');
      expect(disabledButton, findsOneWidget);

      await tester.tap(disabledButton);
      await tester.pumpAndSettle();

      // Disabled button must not trigger tap callback or telemetry
      expect(tapped, isFalse);
      expect(fakeRepo.recordedEvents, isEmpty);
    });

    testWidgets('API error displays user-friendly recovery message', (tester) async {
      tester.view.physicalSize = const Size(800, 1200);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      final product = const ForYouProductItem(
        id: '11111111-1111-4111-8111-111111111111',
        brand: 'Studio Atelier',
        title: 'Silk Evening Gown',
        price: '₹25,000',
        imageAsset: 'assets/images/discover_hero_quiet_luxury.jpg',
        isSyntheticFixture: false,
      );

      final fakeRepo = FakeOffersDiscoverRepository(shouldFail: true);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ProductOfferComparisonSheet(
              product: product,
              repository: fakeRepo,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Unable to load verified merchant offers. Please try again.'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);
    });
  });
}
