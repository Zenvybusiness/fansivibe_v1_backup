import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_client.dart';
import 'package:fansivibe/features/outfit_builder/presentation/build_outfit_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/auth/secure_token_storage.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

Widget _buildTestApp({
  String? eventId,
  String? eventTitle,
  String? initialOccasion,
  String? preferredItemId,
  GoRouter? router,
}) {
  if (router != null) {
    return MaterialApp.router(routerConfig: router);
  }
  return MaterialApp(
    home: BuildOutfitScreen(
      eventId: eventId,
      eventTitle: eventTitle,
      initialOccasion: initialOccasion,
      preferredItemId: preferredItemId,
    ),
  );
}

void main() {
  const explanationCopy =
      'Your outfit recommendations are tailored to the occasion you select. '
      'Date and location are not automatically considered.';

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
    AuthSession.resetForTest();
    await AuthSession.saveSession('test-token-authenticated');
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    LocalStorage.resetForTest();
  });

  group('Occasion Context Transparency — Visibility & Display', () {
    testWidgets('1. Occasion transparency explanation is visible on initial render', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());

      // Find by key
      expect(
        find.byKey(const Key('occasion_context_transparency_notice')),
        findsOneWidget,
      );

      // Find by exact text
      expect(find.text(explanationCopy), findsOneWidget);

      // Verify information icon is present
      expect(find.byIcon(Icons.info_outline_rounded), findsOneWidget);
    });

    testWidgets('Occasion transparency explanation is visible when opened from an event', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _buildTestApp(
          eventId: 'evt-12345',
          eventTitle: 'Annual Gala Dinner',
          initialOccasion: 'office',
        ),
      );

      // Event chip is visible
      expect(find.text('Styling for: Annual Gala Dinner'), findsOneWidget);

      // Transparency notice is visible
      expect(find.text(explanationCopy), findsOneWidget);

      // The office option is preselected from event type
      expect(find.byIcon(Icons.check_circle_rounded), findsOneWidget);
    });
  });

  group('Occasion Context Transparency — State & Selection Resilience', () {
    testWidgets('2. Explanation remains visible when the occasion changes', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());

      expect(find.text(explanationCopy), findsOneWidget);

      // Tap 'Casual'
      await tester.tap(find.text('Casual'));
      await tester.pumpAndSettle();
      expect(find.text(explanationCopy), findsOneWidget);

      // Change to 'Office'
      await tester.tap(find.text('Office'));
      await tester.pumpAndSettle();
      expect(find.text(explanationCopy), findsOneWidget);

      // Change to 'Date'
      await tester.tap(find.text('Date'));
      await tester.pumpAndSettle();
      expect(find.text(explanationCopy), findsOneWidget);

      // Change to 'Travel' (with scroll)
      await tester.scrollUntilVisible(find.text('Travel'), 100);
      await tester.tap(find.text('Travel'));
      await tester.pumpAndSettle();
      expect(find.text(explanationCopy), findsOneWidget);
    });

    testWidgets('3. Existing occasion selection continues to work correctly', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());

      // Initially no check icons
      expect(find.byIcon(Icons.check_circle_rounded), findsNothing);

      // Select 'Casual'
      await tester.tap(find.text('Casual'));
      await tester.pumpAndSettle();
      expect(find.byIcon(Icons.check_circle_rounded), findsOneWidget);

      // Select 'Office' — previous selection replaced
      await tester.tap(find.text('Office'));
      await tester.pumpAndSettle();
      expect(find.byIcon(Icons.check_circle_rounded), findsOneWidget);

      // Other sections can still be selected independently with scrolling
      await tester.scrollUntilVisible(find.text('Minimal'), 200);
      await tester.tap(find.text('Minimal')); // Mood
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Slim'), 200);
      await tester.tap(find.text('Slim')); // Fit
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Monochrome'), 200);
      await tester.tap(find.text('Monochrome')); // Palette
      await tester.pump();

      // Four options selected in total
      expect(find.byIcon(Icons.check_circle_rounded), findsNWidgets(4));
    });
  });

  group('Occasion Context Transparency — Navigation & Guest Flow', () {
    testWidgets('4. Existing Outfit Builder navigation remains fully functional', (
      WidgetTester tester,
    ) async {
      Map<String, dynamic>? pushedExtra;

      final router = GoRouter(
        initialLocation: '/build',
        routes: [
          GoRoute(
            path: '/build',
            name: RouteNames.buildOutfit,
            builder: (context, state) => const BuildOutfitScreen(
              eventId: 'evt-999',
              eventTitle: 'Product Launch',
              initialOccasion: 'office',
            ),
          ),
          GoRoute(
            path: '/generation',
            name: RouteNames.outfitGeneration,
            builder: (context, state) {
              pushedExtra = state.extra as Map<String, dynamic>?;
              return const Scaffold(body: Text('Generation Screen'));
            },
          ),
        ],
      );

      await tester.pumpWidget(_buildTestApp(router: router));

      // Notice is visible
      expect(find.text(explanationCopy), findsOneWidget);

      // Office preselected; select the remaining 3 preferences with scroll
      await tester.scrollUntilVisible(find.text('Bold'), 200);
      await tester.tap(find.text('Bold'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Tailored'), 200);
      await tester.tap(find.text('Tailored'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Warm'), 200);
      await tester.tap(find.text('Warm'));
      await tester.pump();

      // Tap Build Outfit
      final buildBtn = find.ancestor(
        of: find.text('Build Outfit'),
        matching: find.byWidgetPredicate((w) => w is ButtonStyleButton),
      );
      await tester.scrollUntilVisible(buildBtn, 200);
      await tester.tap(buildBtn);
      await tester.pumpAndSettle();

      // Verified navigated to generation screen
      expect(find.text('Generation Screen'), findsOneWidget);
      expect(pushedExtra, isNotNull);
      expect(pushedExtra!['occasion'], 'office');
      expect(pushedExtra!['mood'], 'bold');
      expect(pushedExtra!['fit'], 'tailored');
      expect(pushedExtra!['colorPalette'], 'warm');
      expect(pushedExtra!['eventId'], 'evt-999');
      expect(pushedExtra!['eventTitle'], 'Product Launch');
    });

    testWidgets('Guest user tapping Build Outfit triggers sign-in prompt', (
      WidgetTester tester,
    ) async {
      AuthSession.resetForTest();
      SecureTokenStorage.clearSync();
      LocalStorage.savedLocally = true; // Guest mode
      addTearDown(() {
        SecureTokenStorage.clearSync();
        LocalStorage.savedLocally = false;
      });

      final router = GoRouter(
        initialLocation: '/build',
        routes: [
          GoRoute(
            path: '/build',
            name: RouteNames.buildOutfit,
            builder: (context, state) => const BuildOutfitScreen(),
          ),
          GoRoute(
            path: '/sign-in',
            name: RouteNames.signIn,
            builder: (context, state) =>
                const Scaffold(body: Text('Sign In Screen')),
          ),
        ],
      );

      await tester.pumpWidget(_buildTestApp(router: router));

      // Select all 4 preferences with scroll
      await tester.tap(find.text('Casual'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Minimal'), 200);
      await tester.tap(find.text('Minimal'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Slim'), 200);
      await tester.tap(find.text('Slim'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Monochrome'), 200);
      await tester.tap(find.text('Monochrome'));
      await tester.pump();

      // Tap Build Outfit as guest
      final buildBtn = find.ancestor(
        of: find.text('Build Outfit'),
        matching: find.byWidgetPredicate((w) => w is ButtonStyleButton),
      );
      await tester.scrollUntilVisible(buildBtn, 200);
      await tester.tap(buildBtn);
      await tester.pumpAndSettle();

      // Verify guest dialog prompt appears and pushes sign-in route
      expect(find.text('Sign in to build outfits. Browsing stays free.'), findsOneWidget);
      expect(find.text('Sign In Screen'), findsOneWidget);
    });
  });

  group('Occasion Context Transparency — Factual Accuracy & Negative Checks', () {
    testWidgets('5. UI does not claim automatic date, time, location, or weather awareness', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _buildTestApp(
          eventId: 'evt-101',
          eventTitle: 'Weekend Trip',
          initialOccasion: 'travel',
        ),
      );

      // Explicit statement that date and location are NOT automatically considered
      expect(
        find.textContaining('Date and location are not automatically considered.'),
        findsOneWidget,
      );

      // Negative checks: verify no false claims exist in the UI
      expect(find.textContaining('considering your location'), findsNothing);
      expect(find.textContaining('tailored to your location'), findsNothing);
      expect(find.textContaining('weather-aware'), findsNothing);
      expect(find.textContaining('considering weather'), findsNothing);
      expect(find.textContaining('calendar synchronized'), findsNothing);
      expect(find.textContaining('considering current time'), findsNothing);
    });
  });

  group('Occasion Context Transparency — Wire Contract & Request Preservation', () {
    testWidgets('6. Existing recommendation request behavior is unchanged (no date/location on wire)', (
      WidgetTester tester,
    ) async {
      http.Request? capturedRequest;

      final mockClient = MockClient((request) async {
        if (request.url.path == '/v1/outfits/generate') {
          capturedRequest = request;
          return http.Response(
            jsonEncode({
              'title': 'Casual Outfit',
              'matchScore': 0.85,
              'components': <Map<String, dynamic>>[],
              'reasons': ['Picked for a Casual occasion'],
              'colorHarmony': 'Monochrome palette across 2 pieces.',
              'bodyFit': 'Assembled for a Slim fit.',
              'occasionMatch': 'Matched for Casual.',
              'styleScoreImpact': '85% ensemble match.',
              'improvementSuggestion': 'Full coverage.',
              'selectedOccasion': 'casual',
              'selectedMood': 'minimal',
              'selectedColorPalette': 'monochrome',
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('{}', 404);
      });

      final outfitClient = OutfitBuilderClient(
        client: mockClient,
      );

      final result = await outfitClient.generateOutfit(
        occasion: 'casual',
        mood: 'minimal',
        fit: 'slim',
        colorPalette: 'monochrome',
      );

      expect(result.available, isTrue);
      expect(capturedRequest, isNotNull);

      final decoded = jsonDecode(capturedRequest!.body) as Map<String, dynamic>;

      // Only the 4 frozen preferences are sent
      expect(decoded['occasion'], 'casual');
      expect(decoded['mood'], 'minimal');
      expect(decoded['fit'], 'slim');
      expect(decoded['colorPalette'], 'monochrome');

      // Date, location, weather, eventId are strictly absent from HTTP wire payload
      expect(decoded.containsKey('date'), isFalse);
      expect(decoded.containsKey('time'), isFalse);
      expect(decoded.containsKey('location'), isFalse);
      expect(decoded.containsKey('weather'), isFalse);
      expect(decoded.containsKey('eventId'), isFalse);
      expect(decoded.containsKey('eventTitle'), isFalse);
    });
  });

  group('Occasion Context Transparency — Accessibility & Responsive Layout', () {
    testWidgets('Adapts to narrow mobile screen (320px width) without layout overflow', (
      WidgetTester tester,
    ) async {
      tester.view.physicalSize = const Size(320, 640);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });

      await tester.pumpWidget(_buildTestApp());

      // No overflow errors
      expect(tester.takeException(), isNull);

      // Transparency notice is fully visible and rendered
      expect(find.byKey(const Key('occasion_context_transparency_notice')), findsOneWidget);
      expect(find.text(explanationCopy), findsOneWidget);
    });

    testWidgets('Notice contains accessible semantics', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());

      final semanticsFinder = find.ancestor(
        of: find.byKey(const Key('occasion_context_transparency_notice')),
        matching: find.byType(Semantics),
      ).first;

      final semanticsWidget = tester.widget<Semantics>(semanticsFinder);
      expect(semanticsWidget.container, isTrue);
      expect(semanticsWidget.properties.label, explanationCopy);
    });
  });
}
