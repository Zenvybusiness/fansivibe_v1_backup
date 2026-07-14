import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/discover/data/discover_mock_data.dart';
import 'package:fansivibe/features/discover/presentation/look_details_screen.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_widgets.dart';
import 'package:fansivibe/features/discover/presentation/widgets/look_details_widgets.dart';

Widget _wrapScreen(DiscoverLookData look) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: LookDetailsScreen(look: look),
  );
}

void main() {
  group('LookDetailsScreen Widget Tests', () {
    testWidgets('renders hero section with title and description', (
      WidgetTester tester,
    ) async {
      final look = DiscoverLookData.forYouMock.first;
      await tester.pumpWidget(_wrapScreen(look));

      expect(find.text(look.title), findsWidgets);
      expect(find.text(look.description), findsOneWidget);
      expect(find.byType(MatchPercentageBadge), findsOneWidget);
    });

    testWidgets('renders match score breakdown section', (
      WidgetTester tester,
    ) async {
      final look = DiscoverLookData.forYouMock.first;
      await tester.pumpWidget(_wrapScreen(look));

      expect(find.text('Match Score'), findsOneWidget);
      expect(find.text('How well this look fits your style'), findsOneWidget);
      expect(find.byType(ScoreCategoryRow), findsNWidgets(4));
    });

    testWidgets('renders recommendation reasons', (WidgetTester tester) async {
      final look = DiscoverLookData.forYouMock.first;
      await tester.pumpWidget(_wrapScreen(look));

      expect(find.text('Why We Recommend This'), findsOneWidget);
      expect(find.byType(ReasonRow), findsWidgets);
    });

    testWidgets('renders style and fit tags', (WidgetTester tester) async {
      final look = DiscoverLookData.forYouMock.first;
      await tester.pumpWidget(_wrapScreen(look));

      expect(find.text('STYLE & FIT'), findsOneWidget);
      expect(find.byType(LookTag), findsWidgets);
    });

    testWidgets('renders ensemble components section', (
      WidgetTester tester,
    ) async {
      final look = DiscoverLookData.forYouMock.first;
      await tester.pumpWidget(_wrapScreen(look));

      expect(find.text('Complete The Look'), findsOneWidget);
      expect(find.text('Pieces in this ensemble'), findsOneWidget);
      expect(find.byType(ComponentRow), findsWidgets);
    });

    testWidgets('renders wardrobe alternatives section', (
      WidgetTester tester,
    ) async {
      final look = DiscoverLookData.forYouMock.first;
      await tester.pumpWidget(_wrapScreen(look));

      expect(find.text('Wardrobe Alternatives'), findsOneWidget);
      expect(find.byType(AlternativeSection), findsWidgets);
    });

    testWidgets('renders Save and Share action buttons', (
      WidgetTester tester,
    ) async {
      final look = DiscoverLookData.forYouMock.first;
      await tester.pumpWidget(_wrapScreen(look));

      expect(find.text('Save Look'), findsOneWidget);
      expect(find.text('Share'), findsOneWidget);
    });

    testWidgets('shows Save snackbar on save tap', (WidgetTester tester) async {
      final look = DiscoverLookData.forYouMock.first;
      await tester.pumpWidget(_wrapScreen(look));

      await tester.scrollUntilVisible(find.text('Save Look'), 200);
      await tester.tap(find.text('Save Look'));
      await tester.pump();

      expect(find.textContaining('saved to your looks'), findsOneWidget);
    });

    testWidgets('shows Share snackbar on share tap', (
      WidgetTester tester,
    ) async {
      final look = DiscoverLookData.forYouMock.first;
      await tester.pumpWidget(_wrapScreen(look));

      await tester.scrollUntilVisible(find.text('Share'), 200);
      await tester.tap(find.text('Share'));
      await tester.pump();

      expect(find.textContaining('Sharing'), findsOneWidget);
    });

    testWidgets('navigates back on back button tap', (
      WidgetTester tester,
    ) async {
      final look = DiscoverLookData.forYouMock.first;
      await tester.pumpWidget(_wrapScreen(look));

      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();

      expect(find.byType(LookDetailsScreen), findsNothing);
    });

    testWidgets('renders occasion from the look data', (
      WidgetTester tester,
    ) async {
      final look = DiscoverLookData.forYouMock.first;
      await tester.pumpWidget(_wrapScreen(look));

      expect(find.text(look.occasion), findsOneWidget);
    });

    testWidgets('renders trending look without details sections gracefully', (
      WidgetTester tester,
    ) async {
      final look = DiscoverLookData.trendingMock.first;
      await tester.pumpWidget(_wrapScreen(look));

      expect(find.text(look.title), findsWidgets);
      expect(find.text(look.description), findsOneWidget);
      expect(find.text('Match Score'), findsNothing);
      expect(find.text('Why We Recommend This'), findsNothing);
      expect(find.text('Complete The Look'), findsNothing);
      expect(find.text('Wardrobe Alternatives'), findsNothing);
    });

    testWidgets('share and save icons in app bar', (WidgetTester tester) async {
      final look = DiscoverLookData.forYouMock.first;
      await tester.pumpWidget(_wrapScreen(look));

      expect(find.byIcon(Icons.share_rounded), findsWidgets);
      expect(find.byIcon(Icons.favorite_border_rounded), findsOneWidget);
    });
  });
}
