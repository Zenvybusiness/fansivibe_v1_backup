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

    // Verify Stylist screen is shown.
    expect(find.text('Temporary Stylist Screen'), findsOneWidget);

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
    expect(find.text('Temporary Profile Screen'), findsOneWidget);

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
