import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/discover/presentation/discover_screen.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'saved_locally': true});
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
  });

  Widget createHarness() {
    return const MaterialApp(
      home: DiscoverScreen(),
    );
  }

  group('DiscoverScreen Final New-User Flow Tests', () {
    testWidgets('TEST 1: New user default state is Trending (Trending active, For You inactive)', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(createHarness());
      await tester.pumpAndSettle();

      // Top Header & Monograph
      expect(find.text('FANSIVIBE'), findsOneWidget);
      expect(find.text('EDITORIAL MONOGRAPH'), findsOneWidget);
      expect(find.text('Discover'), findsOneWidget);
      expect(find.text('Fashion inspiration for your next chapter.'), findsOneWidget);

      // Search Bar
      expect(find.text('Search outfits, styles, brands...'), findsOneWidget);

      // Tab bar: Trending is present and active, For You is present
      expect(find.text('Trending'), findsOneWidget);
      expect(find.text('For You'), findsOneWidget);

      // Trending section 1 is immediately visible
      expect(find.text('Trending Now'), findsOneWidget);
      expect(find.text('SPOTLIGHT EDIT'), findsOneWidget);
      expect(find.text('Quiet Luxury'), findsOneWidget);

      // For You empty state sections must NOT be visible initially
      expect(find.text('Your personal style feed starts here.'), findsNothing);
      expect(find.text('How to unlock your feed'), findsNothing);
      expect(find.text('CALIBRATION PATH'), findsNothing);
      expect(find.text('PREVIEW ARCHIVE'), findsNothing);
    });

    testWidgets('TEST 2: Trending tab contains all 5 required sections', (
      WidgetTester tester,
    ) async {
      // Set larger viewport to avoid excessive scrolling during validation
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(createHarness());
      await tester.pumpAndSettle();

      // Section 1: Spotlight Edit
      expect(find.text('SPOTLIGHT EDIT'), findsOneWidget);
      expect(find.text('Trending Now'), findsOneWidget);
      expect(find.text('Quiet Luxury'), findsOneWidget);

      // Section 2: Explore by Category
      expect(find.text('Explore by Category'), findsOneWidget);
      expect(find.text('ATELIER RAIL'), findsOneWidget);
      expect(find.text('Clothing'), findsOneWidget);
      expect(find.text('Sneakers'), findsOneWidget);
      expect(find.text('Accessories'), findsOneWidget);

      // Section 3: Stylist Ensembles
      expect(find.text('STYLIST ENSEMBLES'), findsOneWidget);
      expect(find.text('Trending Looks'), findsOneWidget);
      expect(find.text('Urban Minimal'), findsOneWidget);
      expect(find.text('Modern Classics'), findsOneWidget);

      // Section 4: Acquisition Watch
      expect(find.text('ACQUISITION WATCH'), findsOneWidget);
      expect(find.text('Trending Items'), findsOneWidget);
      expect(find.text('Tailored Wool Coat'), findsOneWidget);
      expect(find.text('Samba OG Archive'), findsOneWidget);

      // Section 5: Style Inspiration
      expect(find.text('EDITORIAL MOODBOARD'), findsOneWidget);
      expect(find.text('Style Inspiration'), findsOneWidget);
      expect(find.text('Texture & Drape'), findsOneWidget);
    });

    testWidgets('TEST 3 & 4: Tap For You switches to ForYou.jpg experience', (
      WidgetTester tester,
    ) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(createHarness());
      await tester.pumpAndSettle();

      // Explicitly tap For You tab
      await tester.tap(find.text('For You'));
      await tester.pumpAndSettle();

      // Trending sections must disappear
      expect(find.text('Trending Now'), findsNothing);
      expect(find.text('Trending Looks'), findsNothing);
      expect(find.text('Trending Items'), findsNothing);
      expect(find.text('Style Inspiration'), findsNothing);

      // For You sections must appear
      expect(find.textContaining('Your personal'), findsOneWidget);
      expect(find.text('EXPLORE TRENDING LOOKS →'), findsOneWidget);
      expect(find.text('SET YOUR STYLE PREFERENCES'), findsOneWidget);

      // Calibration Path
      expect(find.text('CALIBRATION PATH'), findsOneWidget);
      expect(find.text('How to unlock your feed'), findsOneWidget);
      expect(find.text('01'), findsOneWidget);
      expect(find.text('Explore Curations'), findsOneWidget);
      expect(find.text('02'), findsOneWidget);
      expect(find.text('Save What Resonates'), findsOneWidget);
      expect(find.text('03'), findsOneWidget);
      expect(find.text('Catalog Wardrobe Pieces'), findsOneWidget);
      expect(find.text('04'), findsOneWidget);
      expect(find.text('Receive AI Directives'), findsOneWidget);

      // Preview Archive
      expect(find.text('PREVIEW ARCHIVE'), findsOneWidget);
      expect(find.text('Personalized Daily Directives'), findsOneWidget);
    });

    testWidgets('TEST 5: Tap EXPLORE TRENDING LOOKS returns to Trending tab', (
      WidgetTester tester,
    ) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(createHarness());
      await tester.pumpAndSettle();

      // Tap For You
      await tester.tap(find.text('For You'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Your personal'), findsOneWidget);

      // Tap Primary CTA: EXPLORE TRENDING LOOKS →
      await tester.tap(find.text('EXPLORE TRENDING LOOKS →'));
      await tester.pumpAndSettle();

      // Should return to Trending
      expect(find.text('Trending Now'), findsOneWidget);
      expect(find.textContaining('Your personal'), findsNothing);
    });

    testWidgets('TEST 6: Tap Trending tab returns from For You to Trending', (
      WidgetTester tester,
    ) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(createHarness());
      await tester.pumpAndSettle();

      // Tap For You
      await tester.tap(find.text('For You'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Your personal'), findsOneWidget);

      // Tap Trending Tab
      await tester.tap(find.text('Trending'));
      await tester.pumpAndSettle();

      // Should return to Trending
      expect(find.text('Trending Now'), findsOneWidget);
      expect(find.textContaining('Your personal'), findsNothing);
    });
  });
}
