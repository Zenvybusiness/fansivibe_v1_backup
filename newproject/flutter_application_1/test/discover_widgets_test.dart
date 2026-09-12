import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/discover/data/discover_mock_data.dart';
import 'package:fansivibe/features/discover/discover.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_widgets.dart';
import 'package:fansivibe/shared/components/fansi_badge.dart';

void _emptyCallback() {}

Widget wrapWithTheme(Widget widget) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(body: widget),
  );
}

LookSummary backendSummary() {
  return const LookSummary(
    id: 'textured_quiff',
    title: 'Textured Quiff',
    description: 'A modern take on the classic quiff.',
    matchScore: 94,
    reasons: ['Volume on top suits oval faces'],
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

    testWidgets('LookCard renders a backend row with match badge', (
      WidgetTester tester,
    ) async {
      final look = backendSummary();
      await tester.pumpWidget(
        wrapWithTheme(
          SizedBox(
            width: 200,
            height: 300,
            child: LookCard(
              data: look,
              onTap: _emptyCallback,
              showMatchBadge: true,
            ),
          ),
        ),
      );

      expect(find.text(look.title), findsOneWidget);
      expect(find.text(look.description), findsOneWidget);
      expect(find.byType(FansiBadge), findsOneWidget);
    });

    testWidgets('LookCard hides the badge and trending chrome', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        wrapWithTheme(
          SizedBox(
            width: 200,
            height: 300,
            child: LookCard(
              data: backendSummary(),
              onTap: _emptyCallback,
              showMatchBadge: false,
            ),
          ),
        ),
      );

      expect(find.byType(FansiBadge), findsNothing);
      expect(find.text('Trending'), findsNothing);
    });
  });
}
