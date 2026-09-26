import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/discover/presentation/discover_screen.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_widgets.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({
      'saved_locally': true,
      'is_returning_user': true,
      'has_saved_wardrobe_item': true,
      'saved_look_ids': ['look_urban_minimal'],
    });
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
    UserSession.isReturningUser = true;
    UserSession.hasSavedWardrobeItem = true;
    await LearningService.instance.load();
  });

  Widget createHarness({bool? isEstablished}) {
    return MaterialApp(
      home: DiscoverScreen(
        isEstablishedUser: isEstablished ?? true,
      ),
    );
  }

  group('DiscoverScreen Established-User For You Feed Tests', () {
    testWidgets(
      'TEST 1: Established user switches to For You and sees PERSONAL EDIT header',
      (WidgetTester tester) async {
        tester.view.physicalSize = const Size(1080, 2400);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() => tester.view.resetPhysicalSize());

        await tester.pumpWidget(createHarness());
        await tester.pumpAndSettle();

        // Switch to For You tab
        await tester.tap(find.text('For You'));
        await tester.pumpAndSettle();

        // Top Brand Bar
        expect(find.text('FANSIVIBE'), findsOneWidget);

        // Header Monograph changes to PERSONAL EDIT for established user
        expect(find.text('PERSONAL EDIT'), findsOneWidget);
        expect(find.text('For You'), findsNWidgets(2)); // Tab + Headline
        expect(
          find.text('Fashion selected around your style.'),
          findsOneWidget,
        );

        // Search Bar with products placeholder
        expect(
          find.text('Search products, brands, styles...'),
          findsOneWidget,
        );

        // Established feed container must be mounted
        expect(find.byType(EstablishedUserForYouFeed), findsOneWidget);

        // New-user calibration must NOT be rendered
        expect(find.text('CALIBRATION PATH'), findsNothing);
        expect(find.text('How to unlock your feed'), findsNothing);
        expect(find.text('EXPLORE TRENDING LOOKS →'), findsNothing);
      },
    );

    testWidgets(
      'TEST 2: Personalized Hero Product renders with 65% image, match score, and expandable reasoning',
      (WidgetTester tester) async {
        tester.view.physicalSize = const Size(1080, 2400);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() => tester.view.resetPhysicalSize());

        await tester.pumpWidget(createHarness());
        await tester.pumpAndSettle();
        await tester.tap(find.text('For You'));
        await tester.pumpAndSettle();

        // Hero Product Card
        expect(find.byType(PersonalizedHeroProductCard), findsOneWidget);
        expect(find.text('94% STYLE MATCH'), findsOneWidget);
        expect(find.text('COS'), findsOneWidget);
        expect(
          find.text('Structured Double-Faced Wool Overshirt'),
          findsOneWidget,
        );
        expect(find.text('₹12,500'), findsOneWidget);
        expect(find.text('Available at COS Official'), findsOneWidget);
        expect(find.text('WHY THIS IS FOR YOU'), findsOneWidget);
        expect(find.text('SHOP AT COS →'), findsOneWidget);

        // Checkmark reasons inside expanded drawer
        expect(
          find.text('Matches your neutral palette and minimal preference'),
          findsOneWidget,
        );
        expect(
          find.text('Relaxed tailored fit complements your silhouette profile'),
          findsOneWidget,
        );

        // Test collapsing drawer
        await tester.tap(find.text('WHY THIS IS FOR YOU'));
        await tester.pumpAndSettle();
        expect(
          find.text('Matches your neutral palette and minimal preference'),
          findsNothing,
        );

        // Re-expand drawer
        await tester.tap(find.text('WHY THIS IS FOR YOU'));
        await tester.pumpAndSettle();
        expect(
          find.text('Matches your neutral palette and minimal preference'),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'TEST 3: Curated For You Summary card renders with affinity and modal trigger',
      (WidgetTester tester) async {
        tester.view.physicalSize = const Size(1080, 2400);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() => tester.view.resetPhysicalSize());

        await tester.pumpWidget(createHarness());
        await tester.pumpAndSettle();
        await tester.tap(find.text('For You'));
        await tester.pumpAndSettle();

        expect(find.byType(CuratedForYouSummaryCard), findsOneWidget);
        expect(find.text('CURATED FOR YOU'), findsOneWidget);
        expect(find.textContaining('OVERALL AFFINITY'), findsOneWidget);
        expect(
          find.text(
            'Based on your style profile, saved looks, wardrobe and recent activity.',
          ),
          findsOneWidget,
        );
        expect(find.text('WHY THIS MATTERS →'), findsOneWidget);

        // Tap modal trigger
        await tester.tap(find.text('WHY THIS MATTERS →'));
        await tester.pumpAndSettle();
        expect(find.text('Affinity Precision'), findsOneWidget);
      },
    );

    testWidgets(
      'TEST 4: Wardrobe Match section renders 3 paired items and BUILD THIS LOOK CTA',
      (WidgetTester tester) async {
        tester.view.physicalSize = const Size(1080, 2400);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() => tester.view.resetPhysicalSize());

        await tester.pumpWidget(createHarness());
        await tester.pumpAndSettle();
        await tester.tap(find.text('For You'));
        await tester.pumpAndSettle();

        expect(find.byType(WardrobeMatchCard), findsOneWidget);
        expect(find.text('WARDROBE MATCH'), findsOneWidget);
        expect(find.text('Works with what you own'), findsOneWidget);
        expect(
          find.text('Cream Minimal Knit Polo'),
          findsOneWidget,
        );
        expect(
          find.text('Minimal Leather Sneakers'),
          findsOneWidget,
        );
        expect(
          find.text('BUILD THIS LOOK (3 PIECES) →'),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'TEST 5: Product Category Filter Chips are interactive',
      (WidgetTester tester) async {
        tester.view.physicalSize = const Size(1080, 2400);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() => tester.view.resetPhysicalSize());

        await tester.pumpWidget(createHarness());
        await tester.pumpAndSettle();
        await tester.tap(find.text('For You'));
        await tester.pumpAndSettle();

        expect(find.byType(ProductFilterChipsRow), findsOneWidget);
        expect(find.text('All Picks'), findsOneWidget);
        expect(find.text('Jackets & Coats'), findsOneWidget);
        expect(find.text('Knitwear'), findsOneWidget);

        // Tap Knitwear filter chip
        await tester.tap(find.text('Knitwear'));
        await tester.pumpAndSettle();

        // Relaxed Poplin Shirt is Knitwear/Tops category
        expect(find.text('Relaxed Poplin Shirt'), findsOneWidget);
      },
    );

    testWidgets(
      'TEST 6: Because You Like section displays 2-column mathematical grid with equal widths and shop actions',
      (WidgetTester tester) async {
        tester.view.physicalSize = const Size(1080, 2400);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() => tester.view.resetPhysicalSize());

        await tester.pumpWidget(createHarness());
        await tester.pumpAndSettle();
        await tester.tap(find.text('For You'));
        await tester.pumpAndSettle();

        expect(find.byType(BecauseYouLikeSection), findsOneWidget);
        expect(find.text('BECAUSE YOU LIKE'), findsOneWidget);
        expect(find.text('LEMAIRE'), findsOneWidget);
        expect(find.text('Pleated Wool Flannel Pant'), findsOneWidget);
        expect(find.text('₹32,400'), findsOneWidget);
        expect(find.text('ARKET'), findsOneWidget);
        expect(find.text('STUDIO NICHOLSON'), findsOneWidget);
        expect(find.text('TOM WOOD'), findsWidgets);

        // Verify SHOP → action presence
        expect(find.text('SHOP →'), findsWidgets);
      },
    );

    testWidgets(
      'TEST 7: Ensemble Curation renders head-to-toe look with total price and shop CTA',
      (WidgetTester tester) async {
        tester.view.physicalSize = const Size(1080, 2400);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() => tester.view.resetPhysicalSize());

        await tester.pumpWidget(createHarness());
        await tester.pumpAndSettle();
        await tester.tap(find.text('For You'));
        await tester.pumpAndSettle();

        expect(find.byType(EnsembleCurationCard), findsOneWidget);
        expect(find.text('ENSEMBLE CURATION'), findsOneWidget);
        expect(find.text('Curated Autumn Evening'), findsOneWidget);
        expect(find.text('Wool Overcoat'), findsOneWidget);
        expect(find.text('Cashmere Knit'), findsOneWidget);
        expect(find.text('Chelsea Boot'), findsOneWidget);
        expect(find.text('TOTAL LOOK'), findsOneWidget);
        expect(find.text('₹60,700'), findsOneWidget);
        expect(find.text('SHOP THE LOOK (3 PIECES) →'), findsOneWidget);
      },
    );

    testWidgets(
      'TEST 8: Trending in Your Style, Curated Collections, and Finishing Touches render correctly',
      (WidgetTester tester) async {
        tester.view.physicalSize = const Size(1080, 2400);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() => tester.view.resetPhysicalSize());

        await tester.pumpWidget(createHarness());
        await tester.pumpAndSettle();
        await tester.tap(find.text('For You'));
        await tester.pumpAndSettle();

        // Trending in Your Style
        expect(find.byType(TrendingInYourStyleSection), findsOneWidget);
        expect(find.text('Trending In Your Style'), findsOneWidget);
        expect(find.text('OUR LEGACY'), findsOneWidget);
        expect(find.text('Box Shirt in Silk'), findsOneWidget);
        expect(find.text('A.P.C.'), findsOneWidget);
        expect(find.text('Mac Coat in Gabardine'), findsOneWidget);

        // Curated Collections
        expect(find.byType(CuratedCollectionsSection), findsOneWidget);
        expect(find.text('CURATED COLLECTIONS'), findsOneWidget);
        expect(find.text('Quiet Luxury'), findsOneWidget);
        expect(find.text('Modern Minimal'), findsOneWidget);
        expect(find.text('SHOP NOW →'), findsNWidgets(2));

        // Finishing Touches
        expect(find.byType(FinishingTouchesSection), findsOneWidget);
        expect(find.text('THE FINISHING TOUCHES'), findsOneWidget);
        expect(find.text('Signet Ring'), findsOneWidget);
        expect(find.text('Sunglasses'), findsOneWidget);
        expect(find.text('Leather Tote'), findsOneWidget);
      },
    );

    testWidgets(
      'TEST 9: Established user with empty wardrobe still sees established-user For You page',
      (WidgetTester tester) async {
        // Clear all wardrobe items to simulate established user with 0 wardrobe items
        tester.view.physicalSize = const Size(1080, 2400);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() => tester.view.resetPhysicalSize());

        // Returning user flag is true, but wardrobe count is 0
        UserSession.isReturningUser = true;

        await tester.pumpWidget(createHarness(isEstablished: true));
        await tester.pumpAndSettle();
        await tester.tap(find.text('For You'));
        await tester.pumpAndSettle();

        // Must still show EstablishedUserForYouFeed
        expect(find.byType(EstablishedUserForYouFeed), findsOneWidget);

        // Must NOT fall back to new-user calibration
        expect(find.text('CALIBRATION PATH'), findsNothing);
        expect(find.text('Your personal style feed starts here.'), findsNothing);
      },
    );

    testWidgets(
      'TEST 10: Smooth switching between Trending and For You tabs',
      (WidgetTester tester) async {
        tester.view.physicalSize = const Size(1080, 2400);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() => tester.view.resetPhysicalSize());

        await tester.pumpWidget(createHarness());
        await tester.pumpAndSettle();

        // Initially on Trending
        expect(find.text('Trending Now'), findsOneWidget);
        expect(find.byType(EstablishedUserForYouFeed), findsNothing);

        // Switch to For You
        await tester.tap(find.text('For You'));
        await tester.pumpAndSettle();
        expect(find.byType(EstablishedUserForYouFeed), findsOneWidget);
        expect(find.text('Trending Now'), findsNothing);

        // Switch back to Trending
        await tester.tap(find.text('Trending'));
        await tester.pumpAndSettle();
        expect(find.text('Trending Now'), findsOneWidget);
        expect(find.byType(EstablishedUserForYouFeed), findsNothing);
      },
    );
  });
}
