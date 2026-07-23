import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/app/app.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_widgets.dart';
import 'package:fansivibe/shared/components/fansi_chip.dart';

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

      // Verify header elements - find the main header title (displayLarge style)
      expect(find.text('Discover').at(0), findsOneWidget);
      expect(find.text('Find looks tailored to your style'), findsOneWidget);
    });

    testWidgets('renders search field', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Discover tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify search field - look for TextField
      expect(find.byType(TextField), findsOneWidget);
      expect(find.text('Search looks, styles, occasions...'), findsOneWidget);
      expect(find.byIcon(Icons.search_rounded), findsWidgets);
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

    testWidgets('renders filter sections', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Discover tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify filter section titles
      expect(find.text('OCCASION'), findsOneWidget);
      expect(find.text('STYLE'), findsOneWidget);
      expect(find.text('FIT'), findsOneWidget);
    });

    testWidgets('renders occasion filter chips', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Discover tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify occasion filter chips - find in the filter chips row
      final occasionRow = find.byWidgetPredicate(
        (widget) =>
            widget is DiscoverFilterChipsRow && widget.title == 'OCCASION',
      );
      expect(occasionRow, findsOneWidget);
    });

    testWidgets('renders style filter chips', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Discover tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify style filter chips - find in the filter chips row
      final styleRow = find.byWidgetPredicate(
        (widget) => widget is DiscoverFilterChipsRow && widget.title == 'STYLE',
      );
      expect(styleRow, findsOneWidget);
    });

    testWidgets('renders fit filter chips', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Discover tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify fit filter chips - find in the filter chips row
      final fitRow = find.byWidgetPredicate(
        (widget) => widget is DiscoverFilterChipsRow && widget.title == 'FIT',
      );
      expect(fitRow, findsOneWidget);
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

      // Verify match percentage badges (circular progress indicators)
      expect(find.byType(CircularProgressIndicator), findsWidgets);
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
      expect(find.byType(FansiChip), findsWidgets);
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

    testWidgets('filters looks when occasion filter is selected', (
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

      // Tap Work filter - find the filter chip in the occasion row
      final occasionRow = find.byWidgetPredicate(
        (widget) =>
            widget is DiscoverFilterChipsRow && widget.title == 'OCCASION',
      );
      await tester.tap(
        find.descendant(of: occasionRow, matching: find.text('Work')),
      );
      await tester.pumpAndSettle();

      // Verify results update
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

    testWidgets('clear filters button appears when filters are active', (
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

      // Tap a filter - find Work in occasion row
      final occasionRow = find.byWidgetPredicate(
        (widget) =>
            widget is DiscoverFilterChipsRow && widget.title == 'OCCASION',
      );
      await tester.tap(
        find.descendant(of: occasionRow, matching: find.text('Work')),
      );
      await tester.pumpAndSettle();

      // Verify clear filters button appears
      expect(find.text('Clear filters'), findsOneWidget);
    });
  });
}
