import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/app/app.dart';

void main() {
  testWidgets('Fansivibe App renders main shell with bottom navigation', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const FansivibeApp());

    // Verify the home screen is shown by default.
    expect(find.text('Good morning, Alex'), findsOneWidget);

    // Verify all 5 navigation destinations are present in the bottom nav bar.
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.text('Discover'), findsWidgets);
    expect(find.text('Stylist'), findsWidgets);
    expect(find.text('Wardrobe'), findsWidgets);
    expect(find.text('Profile'), findsWidgets);
  });

  testWidgets('Bottom navigation switches between tabs', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const FansivibeApp());

    // Tap Discover tab.
    await tester.tap(
      find.descendant(
        of: find.byType(NavigationBar),
        matching: find.text('Discover'),
      ),
    );
    await tester.pumpAndSettle();

    // Verify Discover screen is shown.
    expect(find.text('Find looks tailored to your style'), findsOneWidget);
    expect(find.text('For You'), findsOneWidget);
    expect(find.text('OCCASION'), findsOneWidget);

    // Tap Stylist tab.
    await tester.tap(
      find.descendant(
        of: find.byType(NavigationBar),
        matching: find.text('Stylist'),
      ),
    );
    await tester.pumpAndSettle();

    // Verify Stylist screen is shown with actions.
    expect(find.text('Stylist'), findsAtLeast(1));
    expect(find.text('Scan My Outfit'), findsOneWidget);
    expect(find.text('Build Outfit'), findsOneWidget);

    // Tap Wardrobe tab.
    await tester.tap(
      find.descendant(
        of: find.byType(NavigationBar),
        matching: find.text('Wardrobe'),
      ),
    );
    await tester.pumpAndSettle();

    // Verify Wardrobe screen is shown.
    expect(find.text('My Wardrobe'), findsOneWidget);
    expect(find.text('24 items'), findsWidgets);

    // Tap Profile tab.
    await tester.tap(
      find.descendant(
        of: find.byType(NavigationBar),
        matching: find.text('Profile'),
      ),
    );
    await tester.pumpAndSettle();

    // Verify Profile screen is shown.
    expect(find.text('Alex'), findsOneWidget);
    expect(find.text('@alex_styles'), findsOneWidget);

    // Tap Home tab to return.
    await tester.tap(
      find.descendant(
        of: find.byType(NavigationBar),
        matching: find.text('Home'),
      ),
    );
    await tester.pumpAndSettle();

    // Verify Home screen is shown again.
    expect(find.text('Good morning, Alex'), findsOneWidget);
  });

  testWidgets('Build Outfit card navigates to BuildOutfitScreen', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const FansivibeApp());

    // Navigate to Stylist tab.
    await tester.tap(
      find.descendant(
        of: find.byType(NavigationBar),
        matching: find.text('Stylist'),
      ),
    );
    await tester.pumpAndSettle();

    // Tap the Build Outfit card.
    await tester.tap(find.text('Build Outfit'));
    await tester.pumpAndSettle();

    // Verify BuildOutfitScreen is shown.
    expect(find.text('Create Your Look'), findsOneWidget);
    expect(find.text('Occasion'), findsOneWidget);

    // Go back.
    await tester.tap(find.byIcon(Icons.arrow_back_rounded));
    await tester.pumpAndSettle();

    // Verify we are back on the Stylist screen.
    expect(find.text('Build Outfit'), findsAtLeast(1));
  });

  testWidgets('Hairstyle card navigates to FaceScanScreen', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const FansivibeApp());

    // Navigate to Stylist tab.
    await tester.tap(
      find.descendant(
        of: find.byType(NavigationBar),
        matching: find.text('Stylist'),
      ),
    );
    await tester.pumpAndSettle();

    // Tap the Hairstyle card.
    await tester.tap(find.text('Hairstyle'));
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    // Verify FaceScanScreen is shown.
    expect(find.text('Face Scan'), findsOneWidget);
    expect(find.text('Start Scan'), findsOneWidget);

    // Go back.
    await tester.tap(find.byIcon(Icons.arrow_back_rounded));
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    // Verify we are back on the Stylist screen.
    expect(find.text('Hairstyle'), findsAtLeast(1));
  });

  testWidgets('Event Planning card navigates to EventListScreen', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const FansivibeApp());

    // Navigate to Stylist tab.
    await tester.tap(
      find.descendant(
        of: find.byType(NavigationBar),
        matching: find.text('Stylist'),
      ),
    );
    await tester.pumpAndSettle();

    // Scroll to make Event Planning card visible.
    await tester.drag(
      find.byType(SingleChildScrollView),
      const Offset(0, -200),
    );
    await tester.pump();
    await tester.pump();

    // Tap the Event Planning card.
    await tester.tap(find.text('Event Planning'));
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    // Verify EventListScreen is shown.
    expect(find.text('My Events'), findsOneWidget);
    expect(find.text('Upcoming Events'), findsOneWidget);

    // Go back.
    await tester.tap(find.byIcon(Icons.arrow_back_rounded));
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    // Verify we are back on the Stylist screen.
    await tester.drag(find.byType(SingleChildScrollView), const Offset(0, 200));
    await tester.pump();
    await tester.pump();
    expect(find.text('Event Planning'), findsAtLeast(1));
  });

  testWidgets('Beard / Glasses card navigates to GroomingInputScreen', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const FansivibeApp());

    // Navigate to Stylist tab.
    await tester.tap(
      find.descendant(
        of: find.byType(NavigationBar),
        matching: find.text('Stylist'),
      ),
    );
    await tester.pumpAndSettle();

    // Tap the Beard / Glasses card.
    await tester.tap(find.text('Beard / Glasses'));
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    // Verify GroomingInputScreen is shown.
    expect(find.text('Grooming Profile'), findsOneWidget);
    expect(find.text('Face Shape'), findsOneWidget);

    // Go back.
    await tester.tap(find.byIcon(Icons.arrow_back_rounded));
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    // Verify we are back on the Stylist screen.
    expect(find.text('Beard / Glasses'), findsAtLeast(1));
  });

  testWidgets('Tab state is preserved when switching tabs', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const FansivibeApp());

    // Switch to Discover tab.
    await tester.tap(
      find.descendant(
        of: find.byType(NavigationBar),
        matching: find.text('Discover'),
      ),
    );
    await tester.pumpAndSettle();

    // Switch to Stylist tab.
    await tester.tap(
      find.descendant(
        of: find.byType(NavigationBar),
        matching: find.text('Stylist'),
      ),
    );
    await tester.pumpAndSettle();

    // Switch back to Discover tab.
    await tester.tap(
      find.descendant(
        of: find.byType(NavigationBar),
        matching: find.text('Discover'),
      ),
    );
    await tester.pumpAndSettle();

    // Verify Discover screen is still showing (state preserved via IndexedStack).
    expect(find.text('Find looks tailored to your style'), findsOneWidget);
    expect(find.text('For You'), findsOneWidget);
    expect(find.text('OCCASION'), findsOneWidget);
  });
}
