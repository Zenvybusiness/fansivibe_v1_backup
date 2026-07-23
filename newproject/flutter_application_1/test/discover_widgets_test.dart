import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/discover/data/discover_mock_data.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_widgets.dart';

void _emptyCallback() {}
void _emptyFilterCallback(FilterOption option) {}

Widget wrapWithTheme(Widget widget) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(body: widget),
  );
}

void main() {
  group('Discover Feature Widgets Tests', () {
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
