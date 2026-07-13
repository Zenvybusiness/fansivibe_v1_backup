import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/discover/data/discover_mock_data.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_widgets.dart';

void _emptyCallback() {}
void _emptyTabCallback(DiscoverTab tab) {}
void _emptyFilterCallback(FilterOption option) {}

/// Helper to wrap a widget with the Fansivibe theme for testing.
Widget wrapWithTheme(Widget widget) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(body: widget),
  );
}

void main() {
  group('Discover Feature Widgets Tests', () {
    testWidgets('DiscoverCard renders correctly', (WidgetTester tester) async {
      await tester.pumpWidget(
        wrapWithTheme(const DiscoverCard(child: Text('Test Content'))),
      );

      expect(find.text('Test Content'), findsOneWidget);
      expect(find.byType(Container), findsWidgets);
    });

    testWidgets('DiscoverCard handles tap callback', (
      WidgetTester tester,
    ) async {
      bool tapped = false;
      await tester.pumpWidget(
        wrapWithTheme(
          DiscoverCard(
            child: const Text('Test Content'),
            onTap: () => tapped = true,
          ),
        ),
      );

      await tester.tap(find.byType(DiscoverCard));
      await tester.pump();

      expect(tapped, true);
    });

    testWidgets('DiscoverSectionTitle renders correctly', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        wrapWithTheme(
          DiscoverSectionTitle(
            title: 'Test Title',
            subtitle: 'Test Subtitle',
            actionLabel: 'View All',
            onActionPressed: _emptyCallback,
          ),
        ),
      );

      expect(find.text('Test Title'), findsOneWidget);
      expect(find.text('Test Subtitle'), findsOneWidget);
      expect(find.text('View All'), findsOneWidget);
    });

    testWidgets('DiscoverTabButton renders selected and unselected states', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        wrapWithTheme(
          Row(
            children: [
              DiscoverTabButton(
                data: DiscoverTabData.all.first,
                isSelected: true,
                onTap: _emptyCallback,
              ),
              DiscoverTabButton(
                data: DiscoverTabData.all.last,
                isSelected: false,
                onTap: _emptyCallback,
              ),
            ],
          ),
        ),
      );

      expect(find.text('For You'), findsOneWidget);
      expect(find.text('Trending'), findsOneWidget);
      expect(find.byIcon(Icons.person_outline_rounded), findsOneWidget);
      expect(find.byIcon(Icons.trending_up_rounded), findsOneWidget);
    });

    testWidgets('DiscoverFilterChip renders selected and unselected states', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        wrapWithTheme(
          Row(
            children: [
              DiscoverFilterChip(
                option: const FilterOption(
                  id: 'test1',
                  label: 'Test 1',
                  icon: Icons.star_rounded,
                  isSelected: true,
                ),
                onTap: _emptyCallback,
              ),
              DiscoverFilterChip(
                option: const FilterOption(
                  id: 'test2',
                  label: 'Test 2',
                  icon: Icons.favorite_rounded,
                  isSelected: false,
                ),
                onTap: _emptyCallback,
              ),
            ],
          ),
        ),
      );

      expect(find.text('Test 1'), findsOneWidget);
      expect(find.text('Test 2'), findsOneWidget);
      expect(find.byIcon(Icons.star_rounded), findsOneWidget);
      expect(find.byIcon(Icons.favorite_rounded), findsOneWidget);
    });

    testWidgets('DiscoverFilterChipsRow renders correctly', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        wrapWithTheme(
          DiscoverFilterChipsRow(
            options: [
              const FilterOption(
                id: '1',
                label: 'Option 1',
                icon: Icons.star_rounded,
              ),
              const FilterOption(
                id: '2',
                label: 'Option 2',
                icon: Icons.favorite_rounded,
              ),
            ],
            onOptionChanged: _emptyFilterCallback,
            title: 'TEST',
          ),
        ),
      );

      expect(find.text('TEST'), findsOneWidget);
      expect(find.text('Option 1'), findsOneWidget);
      expect(find.text('Option 2'), findsOneWidget);
    });

    testWidgets('MatchPercentageBadge renders correctly', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        wrapWithTheme(const MatchPercentageBadge(percentage: 85, size: 48)),
      );

      expect(find.text('85%'), findsOneWidget);
      expect(find.text('Match'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('TrendingBadge renders correctly', (WidgetTester tester) async {
      await tester.pumpWidget(
        wrapWithTheme(const TrendingBadge(label: 'Trending')),
      );

      expect(find.text('Trending'), findsOneWidget);
      expect(find.byIcon(Icons.trending_up_rounded), findsOneWidget);
    });

    testWidgets('DiscoverSearchField renders correctly', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        wrapWithTheme(const DiscoverSearchField(onTap: _emptyCallback)),
      );

      expect(find.byType(TextField), findsOneWidget);
      expect(find.text('Search looks, styles, occasions...'), findsOneWidget);
      expect(find.byIcon(Icons.search_rounded), findsOneWidget);
      expect(find.byIcon(Icons.tune_rounded), findsOneWidget);
    });

    testWidgets('DiscoverHeader renders correctly', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        wrapWithTheme(
          const DiscoverHeader(
            onSearchTap: _emptyCallback,
            activeFilterCount: 0,
          ),
        ),
      );

      expect(find.text('Discover'), findsOneWidget);
      expect(find.text('Find your next signature look'), findsOneWidget);
      expect(find.byType(TextField), findsOneWidget);
    });

    testWidgets('DiscoverTabs renders correctly', (WidgetTester tester) async {
      await tester.pumpWidget(
        wrapWithTheme(
          const DiscoverTabs(
            selectedTab: DiscoverTab.forYou,
            onTabChanged: _emptyTabCallback,
          ),
        ),
      );

      expect(find.text('For You'), findsOneWidget);
      expect(find.text('Trending'), findsOneWidget);
    });

    testWidgets('DiscoverEmptyState renders correctly', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        wrapWithTheme(
          const DiscoverEmptyState(
            message: 'No looks found',
            subtitle: 'Try adjusting your filters',
          ),
        ),
      );

      expect(find.text('No looks found'), findsOneWidget);
      expect(find.text('Try adjusting your filters'), findsOneWidget);
      expect(find.byIcon(Icons.search_off_rounded), findsOneWidget);
    });

    testWidgets('LookCard renders with constraints', (
      WidgetTester tester,
    ) async {
      final look = DiscoverLookData.forYouMock.first;
      await tester.pumpWidget(
        wrapWithTheme(
          SizedBox(
            width: 200,
            height: 300,
            child: LookCard(
              data: look,
              onTap: _emptyCallback,
              showMatchBadge: true,
              showTrendingBadge: false,
            ),
          ),
        ),
      );

      expect(find.text(look.title), findsOneWidget);
      expect(find.text(look.occasion), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });
  });
}
