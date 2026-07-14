import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/presentation/face_scan_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/hairstyle_details_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/hairstyle_result_screen.dart';

GoRouter _freshHairstyleRouter() => GoRouter(
  initialLocation: '/',
  routes: [
    GoRoute(
      path: '/',
      name: RouteNames.hairstyleResult,
      builder: (_, __) => const HairstyleResultScreen(),
      routes: [
        GoRoute(
          path: 'details',
          name: RouteNames.hairstyleDetails,
          builder: (_, state) {
            final rec = state.extra as HairstyleRecommendation?;
            return rec != null
                ? HairstyleDetailsScreen(recommendation: rec)
                : const SizedBox();
          },
        ),
      ],
    ),
    GoRoute(
      path: '/scan',
      name: RouteNames.hairstyle,
      builder: (_, __) => const FaceScanScreen(),
    ),
  ],
);

void main() {
  group('HairstyleResultScreen Widget Tests', () {
    testWidgets('renders app bar with title', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const HairstyleResultScreen()));

      expect(find.text('Hairstyle Results'), findsOneWidget);
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
    });

    testWidgets('renders header', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const HairstyleResultScreen()));

      expect(find.text('Your Style Profile'), findsOneWidget);
    });

    testWidgets('renders style profile section', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const HairstyleResultScreen()));

      expect(find.text('Style Profile'), findsOneWidget);
      expect(find.text('Oval'), findsOneWidget);
      expect(find.text('Warm Medium'), findsOneWidget);
    });

    testWidgets('renders top recommendation section', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const HairstyleResultScreen()));

      expect(find.text('Top Recommendation'), findsOneWidget);
      expect(find.text('Textured Quiff'), findsOneWidget);
    });

    testWidgets('renders alternative hairstyles', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const HairstyleResultScreen()));

      expect(find.text('Alternative Hairstyles'), findsOneWidget);
      expect(find.text('Classic Pompadour'), findsOneWidget);
      expect(find.text('Side Part'), findsOneWidget);
      expect(find.text('Brushed Up Undercut'), findsOneWidget);
    });

    testWidgets('renders match percentage', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const HairstyleResultScreen()));

      expect(find.text('94%'), findsOneWidget);
    });

    testWidgets('renders action buttons', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const HairstyleResultScreen()));

      expect(find.text('Scan Again'), findsOneWidget);
      expect(find.text('Save to Profile'), findsOneWidget);
    });

    testWidgets('tapping top recommendation navigates to details', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _freshHairstyleRouter()),
      );

      await tester.tap(find.text('Textured Quiff'));
      await tester.pumpAndSettle();

      expect(find.text('Styling Tips'), findsOneWidget);
      expect(find.text('Maintenance'), findsOneWidget);
      expect(find.text('Best For'), findsOneWidget);
    });

    testWidgets('tapping alternative navigates to details', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _freshHairstyleRouter()),
      );

      final scrollable = find.byType(Scrollable).first;
      await tester.drag(scrollable, const Offset(0, -800));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Classic Pompadour'));
      await tester.pumpAndSettle();

      expect(find.text('Styling Tips'), findsOneWidget);
    });

    testWidgets('Scan Again navigates back to scan screen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _freshHairstyleRouter()),
      );

      await tester.drag(find.byType(Scrollable).first, const Offset(0, -1000));
      await tester.pump();
      await tester.tap(find.text('Scan Again'));
      for (var i = 0; i < 30; i++) {
        await tester.pump(const Duration(milliseconds: 16));
      }

      expect(find.text('Face Scan'), findsOneWidget);
    });
  });
}
