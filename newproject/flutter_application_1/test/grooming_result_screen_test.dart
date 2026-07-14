import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/grooming/data/grooming_mock_data.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_details_screen.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_input_screen.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_result_screen.dart';

GoRouter _groomingResultRouter({
  String faceShape = 'Oval',
  String beardStyle = 'Full Beard',
  String beardDensity = 'Medium',
  String beardColor = 'Dark Brown',
}) {
  return GoRouter(
    initialLocation: '/',
    routes: [
      GoRoute(
        path: '/',
        name: RouteNames.groomingResult,
        builder: (_, __) => GroomingResultScreen(
          faceShape: faceShape,
          beardStyle: beardStyle,
          beardDensity: beardDensity,
          beardColor: beardColor,
        ),
        routes: [
          GoRoute(
            path: 'details',
            name: RouteNames.groomingDetails,
            builder: (_, state) {
              final rec = state.extra as GroomingRecommendation?;
              return rec != null
                  ? GroomingDetailsScreen(recommendation: rec)
                  : const SizedBox();
            },
          ),
        ],
      ),
      GoRoute(
        path: '/input',
        name: RouteNames.grooming,
        builder: (_, __) => const GroomingInputScreen(),
      ),
    ],
  );
}

void main() {
  testWidgets('renders app bar with title', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: const GroomingResultScreen(
          faceShape: 'Oval',
          beardStyle: 'Full Beard',
          beardDensity: 'Medium',
          beardColor: 'Dark Brown',
        ),
      ),
    );

    expect(find.text('Grooming Results'), findsOneWidget);
    expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
  });

  testWidgets('renders header', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: const GroomingResultScreen(
          faceShape: 'Oval',
          beardStyle: 'Full Beard',
          beardDensity: 'Medium',
          beardColor: 'Dark Brown',
        ),
      ),
    );

    expect(find.text('Your Grooming Profile'), findsOneWidget);
  });

  testWidgets('renders feature profile section', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: const GroomingResultScreen(
          faceShape: 'Oval',
          beardStyle: 'Full Beard',
          beardDensity: 'Medium',
          beardColor: 'Dark Brown',
        ),
      ),
    );

    expect(find.text('Feature Profile'), findsOneWidget);
    expect(find.text('Oval'), findsOneWidget);
    expect(find.text('Full Beard'), findsOneWidget);
    expect(find.text('Medium'), findsOneWidget);
    expect(find.text('Dark Brown'), findsOneWidget);
  });

  testWidgets('renders match score section', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: const GroomingResultScreen(
          faceShape: 'Oval',
          beardStyle: 'Full Beard',
          beardDensity: 'Medium',
          beardColor: 'Dark Brown',
        ),
      ),
    );

    expect(find.text('Match Score'), findsOneWidget);
    expect(find.text('Structured Goatee is your top match'), findsOneWidget);
  });

  testWidgets('renders primary beard recommendation', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: const GroomingResultScreen(
          faceShape: 'Oval',
          beardStyle: 'Full Beard',
          beardDensity: 'Medium',
          beardColor: 'Dark Brown',
        ),
      ),
    );

    expect(find.text('Primary Beard Recommendation'), findsOneWidget);
    expect(find.text('Structured Goatee'), findsOneWidget);
  });

  testWidgets('renders eyewear suggestion section', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: const GroomingResultScreen(
          faceShape: 'Oval',
          beardStyle: 'Full Beard',
          beardDensity: 'Medium',
          beardColor: 'Dark Brown',
        ),
      ),
    );

    expect(find.text('Eyewear Suggestion'), findsOneWidget);
    expect(find.textContaining('Rectangular Frames'), findsOneWidget);
  });

  testWidgets('renders why it works', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: const GroomingResultScreen(
          faceShape: 'Oval',
          beardStyle: 'Full Beard',
          beardDensity: 'Medium',
          beardColor: 'Dark Brown',
        ),
      ),
    );

    expect(find.text('Why It Works'), findsOneWidget);
  });

  testWidgets('renders grooming specifications', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: const GroomingResultScreen(
          faceShape: 'Oval',
          beardStyle: 'Full Beard',
          beardDensity: 'Medium',
          beardColor: 'Dark Brown',
        ),
      ),
    );

    expect(find.text('Grooming Specifications'), findsOneWidget);
    expect(find.text('Beard Length'), findsOneWidget);
    expect(find.text('Cheek Line'), findsOneWidget);
    expect(find.text('Eyewear Frame'), findsOneWidget);
  });

  testWidgets('renders alternatives section', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: const GroomingResultScreen(
          faceShape: 'Oval',
          beardStyle: 'Full Beard',
          beardDensity: 'Medium',
          beardColor: 'Dark Brown',
        ),
      ),
    );

    expect(find.text('Alternatives'), findsOneWidget);
    expect(find.text('3 curated alternatives for you'), findsOneWidget);
    expect(find.text('Classic Stubble'), findsOneWidget);
    expect(find.text('Cropped Full Beard'), findsOneWidget);
    expect(find.text('Sleek Moustache'), findsOneWidget);
  });

  testWidgets('renders action buttons', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: const GroomingResultScreen(
          faceShape: 'Oval',
          beardStyle: 'Full Beard',
          beardDensity: 'Medium',
          beardColor: 'Dark Brown',
        ),
      ),
    );

    expect(find.text('Start Over'), findsOneWidget);
    expect(find.text('Save Recommendation'), findsOneWidget);
  });

  testWidgets('tapping top recommendation navigates to details', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp.router(routerConfig: _groomingResultRouter()),
    );

    await tester.ensureVisible(find.text('Structured Goatee'));
    await tester.pump();
    await tester.tap(find.text('Structured Goatee'));
    for (var i = 0; i < 60; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    expect(find.text('Styling Tips'), findsOneWidget);
  });

  testWidgets('tapping alternative navigates to details', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp.router(routerConfig: _groomingResultRouter()),
    );

    await tester.ensureVisible(find.text('Classic Stubble'));
    await tester.pump();
    await tester.tap(find.text('Classic Stubble'));
    for (var i = 0; i < 60; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    expect(find.text('Styling Tips'), findsOneWidget);
  });

  testWidgets('Start Over navigates back to input screen', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp.router(routerConfig: _groomingResultRouter()),
    );

    await tester.ensureVisible(find.text('Start Over'));
    await tester.pump();
    await tester.tap(find.text('Start Over'));
    for (var i = 0; i < 60; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    expect(find.text('Grooming Profile'), findsOneWidget);
  });
}
