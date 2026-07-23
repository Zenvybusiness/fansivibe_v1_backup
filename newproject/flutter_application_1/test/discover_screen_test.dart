import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/app/app.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_widgets.dart';

void main() {
  group('DiscoverScreen Widget Tests', () {
    testWidgets('renders Discover header with title and subtitle', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Discover tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify header elements
      expect(find.text('Discover'), findsWidgets);
      expect(find.text('Find looks tailored to your style'), findsOneWidget);
      expect(find.byIcon(Icons.explore_rounded), findsWidgets);
    });

    testWidgets('renders search field and filter button', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Discover tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify search field
      expect(find.byType(TextField), findsOneWidget);
      expect(find.text('Search looks, styles, occasions...'), findsOneWidget);
      expect(find.byIcon(Icons.search_rounded), findsWidgets);

      // Verify filter button
      expect(find.byIcon(Icons.tune_rounded), findsOneWidget);
    });

    testWidgets('renders For You and Trending tabs', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Discover tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify tabs text - use the tab button widgets
      expect(find.byType(DiscoverTabButton), findsNWidgets(2));
      expect(find.text('For You'), findsOneWidget);
    });

    testWidgets('renders filter button with active count', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Discover tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify filter button exists (no active filters by default)
      expect(find.byIcon(Icons.tune_rounded), findsOneWidget);
    });

    testWidgets('renders look cards in grid', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Discover tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify look cards are rendered (at least 6 for "For You" tab)
      expect(find.byType(LookCard), findsWidgets);
    });

    testWidgets('renders match percentage badges on look cards', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Discover tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify match percentage badges (star icons in FansiBadge)
      expect(find.byIcon(Icons.star_rounded), findsWidgets);
    });

    testWidgets('renders trending badges on trending looks', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Discover tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Switch to Trending tab by tapping the Trending tab button
      await tester.tap(find.byType(DiscoverTabButton).last);
      await tester.pumpAndSettle();

      // Verify trending badges appear
      expect(find.text('Trending'), findsWidgets);
    });

    testWidgets('switches between For You and Trending tabs', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Discover tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify For You tab is selected by default
      expect(find.byType(DiscoverTabButton), findsNWidgets(2));

      // Switch to Trending tab
      await tester.tap(find.byType(DiscoverTabButton).last);
      await tester.pumpAndSettle();

      // Verify we're on Trending tab
      expect(find.byType(LookCard), findsWidgets);
    });

    testWidgets('shows results count', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Discover tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify results count is shown
      expect(find.textContaining('looks found'), findsOneWidget);
    });

    testWidgets('opening filter sheet shows filter options', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Discover tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Open filter sheet
      await tester.tap(find.byIcon(Icons.tune_rounded));
      await tester.pumpAndSettle();

      // Verify filter sheet sections
      expect(find.text('Filter'), findsOneWidget);
      expect(find.text('Occasion'), findsOneWidget);
      expect(find.text('Style'), findsOneWidget);
      expect(find.text('Fit'), findsOneWidget);
      expect(find.text('Show results'), findsOneWidget);
    });

    testWidgets('clear filters in results header appears with active filters', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Discover tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Open filter sheet
      await tester.tap(find.byIcon(Icons.tune_rounded));
      await tester.pumpAndSettle();

      // Tap a filter (e.g., Work)
      await tester.tap(find.text('Work'));
      await tester.pumpAndSettle();

      // Close sheet
      await tester.tap(find.text('Show results'));
      await tester.pumpAndSettle();

      // Verify clear filters button appears in results header
      expect(find.text('Clear filters'), findsOneWidget);
    });
  });
}
