import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/app.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/home/data/home_mock_data.dart';
import 'package:fansivibe/features/home/data/today_look_models.dart';
import 'package:fansivibe/features/home/data/today_look_repository.dart';
import 'package:fansivibe/features/home/presentation/daily_outfit_screen.dart';
import 'package:fansivibe/features/home/presentation/home_screen.dart';
import 'package:fansivibe/features/home/presentation/widgets/home_widgets.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Creates a [FansivibeApp] with an isolated router to prevent state
/// leaking across navigation tests.
Widget _freshApp() {
  return FansivibeApp(
    router: GoRouter(initialLocation: '/home', routes: appRoutes),
  );
}

/// Fixed backend look for the M9 Home tests (STEP 19.25).
TodayLookResult _backendLookResult() => TodayLookResult.available(
  TodayLook.fromJson({
    'title': 'City Layers',
    'occasion': 'work',
    'description': 'Layered neutrals built from owned staples.',
    'matchScore': 84,
    'styleScore': 84,
    'components': [
      {
        'id': '78ff3686-c950-4cd6-84c3-7e18d6634dfa',
        'name': 'Camel Overcoat',
        'category': 'outerwear',
        'color': 'Camel',
      },
      {
        'id': '4412f646-56a9-4afa-8717-b330da03b3d0',
        'name': 'Grey Knit',
        'category': 'tops',
        'color': 'Grey',
      },
    ],
    'reasons': ['Picked for a work occasion'],
    'wardrobeContext': {'totalItems': 2, 'matchingItems': 2},
    'alternatives': <Map<String, dynamic>>[],
    'selectedItemIds': [
      '4412f646-56a9-4afa-8717-b330da03b3d0',
      '78ff3686-c950-4cd6-84c3-7e18d6634dfa',
    ],
  }),
);

class _FakeTodayLookRepository implements TodayLookRepository {
  _FakeTodayLookRepository(this.result);

  final TodayLookResult result;

  @override
  Future<TodayLookResult> getTodayLook() async => result;

  @override
  Future<TodayLookResult> regenerateTodayLook({String? seed}) async => result;

  @override
  Future<SavedTodayLook?> saveTodayLook({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async => null;
}

class _ZeroSummaryRepository implements LearningSummaryRepository {
  @override
  Future<LearningSummary?> getSummary() async => const LearningSummary(
    styleScore: 60,
    breakdown: LearningSummaryBreakdown(
      base: 60,
      wardrobePoints: 0,
      savedPoints: 0,
      total: 60,
    ),
    streak: 0,
    recentSignals: [],
  );
}

class _FakeInsightRepository implements WardrobeRepository {
  _FakeInsightRepository(this.insight);

  final WardrobeInsightData? insight;

  @override
  Future<WardrobeInsightData?> getInsight() async => insight;

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async =>
      const [];

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) =>
      throw UnimplementedError();

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
  }) =>
      throw UnimplementedError();

  @override
  Future<WardrobeItemData?> updateItem({
    required String itemId,
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
  }) =>
      throw UnimplementedError();

  @override
  Future<bool?> deleteItem({required String itemId}) =>
      throw UnimplementedError();

  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) =>
      throw UnimplementedError();

  @override
  Future<WearSummary?> getWearSummary() => throw UnimplementedError();
}

/// App with the backend-fed Home slot (M9, STEP 19.25): the same fake feeds
/// both Home and the Daily Outfit detail surface.
Widget _backendApp({WardrobeRepository? wardrobeRepository}) {
  final todayRepo = _FakeTodayLookRepository(_backendLookResult());
  return FansivibeApp(
    router: GoRouter(
      initialLocation: '/home',
      routes: [
        GoRoute(
          path: '/home',
          builder: (context, state) => HomeScreen(
            todayLookRepository: todayRepo,
            summaryRepository: _ZeroSummaryRepository(),
            wardrobeRepository: wardrobeRepository,
          ),
          routes: [
            GoRoute(
              path: 'daily-outfit',
              name: RouteNames.dailyOutfit,
              builder: (context, state) =>
                  DailyOutfitScreen(todayLookRepository: todayRepo),
            ),
            GoRoute(
              path: 'build-outfit',
              name: RouteNames.buildOutfit,
              builder: (context, state) =>
                  const Scaffold(body: Center(child: Text('Build Outfit'))),
            ),
          ],
        ),
      ],
    ),
  );
}

void main() {
  group('HomeScreen Widget Tests', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStorage.init(prefs: await SharedPreferences.getInstance());
      LearningService.instance.resetForTest();
      LocalStorage.displayName = null;
      LocalStorage.onboardingComplete = false;
    });

    testWidgets('renders greeting header truthfully without fabricated name', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      // Verify unauthenticated user sees generic greeting without "Alex"
      expect(find.text('Good morning'), findsOneWidget);
      expect(find.text('Good morning, Alex'), findsNothing);
      expect(find.text('Alex'), findsNothing);
    });

    testWidgets('renders greeting header with real display name when available', (
      WidgetTester tester,
    ) async {
      LocalStorage.displayName = 'Taylor';
      await tester.pumpWidget(_freshApp());

      // Verify real stored display name is used
      expect(find.text('Good morning, Taylor'), findsOneWidget);
      expect(find.text('Good morning, Alex'), findsNothing);
    });

    testWidgets('renders Today\'s Look card from the backend', (
      WidgetTester tester,
    ) async {
      // M9 (STEP 19.25): the slot renders the backend derivation verbatim —
      // no mock titles, wardrobe names, or numeric IDs.
      await tester.pumpWidget(_backendApp());
      await tester.pumpAndSettle();

      // Verify Today's Look card elements
      expect(find.text('TODAY\'S LOOK'), findsOneWidget);
      expect(find.text('City Layers'), findsOneWidget);
      expect(find.text('work'), findsOneWidget);
      expect(find.text('84%'), findsWidgets); // Style score badge

      // Verify backend description
      expect(
        find.textContaining('Layered neutrals built from owned staples'),
        findsOneWidget,
      );

      // Verify backend outfit items (UUID-addressed, verbatim names)
      expect(find.text('Camel Overcoat'), findsOneWidget);
      expect(find.text('Grey Knit'), findsOneWidget);

      // No mock leftovers posing as data
      expect(find.text('Your Look'), findsNothing);
      expect(find.text('Modern Minimalist'), findsNothing);
      expect(find.text('Unstructured Blazer'), findsNothing);

      // Verify action buttons
      expect(find.text('Try This Look'), findsOneWidget);
      expect(
        find.text('Change Style'),
        findsWidgets,
      ); // Appears in Today's Look and Quick Actions
    });

    testWidgets('renders backend Style Score slot without mock values', (
      WidgetTester tester,
    ) async {
      // M10-C (STEP 19.16): the mock score card (84/+3 pts, Fit/Color/
      // Occasion/Creativity) is replaced by the backend-fed slot. With no
      // server under the test binding the slot keeps its title and shows
      // the honest error state — never a fabricated score.
      await tester.pumpWidget(_freshApp());

      // Scroll to find Style Score section
      await tester.scrollUntilVisible(find.text('Style Score'), 500.0);
      // Flush the backend future (no server under the test binding).
      await tester.pumpAndSettle();

      expect(find.text('Style Score'), findsWidgets);
      expect(find.text('84'), findsNothing);
      expect(find.text('+3 pts'), findsNothing);
      expect(find.text('Fit'), findsNothing);
      expect(find.text('Occasion'), findsNothing);
      expect(find.text('Creativity'), findsNothing);
      expect(
        find.text(
          'Couldn\'t load style summary. Please check your connection.',
        ),
        findsWidgets,
      );
    });

    testWidgets('renders Quick Actions section', (WidgetTester tester) async {
      await tester.pumpWidget(_freshApp());

      await tester.scrollUntilVisible(find.text('Quick Actions'), 500.0);

      expect(find.text('Quick Actions'), findsOneWidget);
      expect(find.text('Scan My Outfit'), findsOneWidget);
      expect(find.text('Get AI analysis of your current look'), findsOneWidget);
      expect(find.text('Build Outfit'), findsOneWidget);
      expect(find.text('Create a look from your wardrobe'), findsOneWidget);
      expect(
        find.text('Change Style'),
        findsWidgets,
      ); // Appears in both Today's Look and Quick Actions
      expect(find.text('Adjust today\'s recommendation'), findsOneWidget);
    });

    testWidgets('renders backend Style Streak slot without mock values', (
      WidgetTester tester,
    ) async {
      // M10-C (STEP 19.16): the mock streak card (12-day streak, Mon–Sun
      // week path, stat bar) is replaced by the backend-fed slot. With no
      // server under the test binding the slot keeps its title and shows
      // the honest error state — never fabricated week data.
      await tester.pumpWidget(_freshApp());

      await tester.scrollUntilVisible(find.text('Style Streak'), 500.0);
      // Flush the backend future (no server under the test binding).
      await tester.pumpAndSettle();

      expect(find.text('Style Streak'), findsOneWidget);
      expect(find.text('12-day streak'), findsNothing);
      expect(find.text('Mon'), findsNothing);
      expect(find.text('Tue'), findsNothing);
      expect(find.text('Wed'), findsNothing);
      expect(find.text('Thu'), findsNothing);
      expect(find.text('Fri'), findsNothing);
      expect(find.text('Sat'), findsNothing);
      expect(find.text('Sun'), findsNothing);
    });

    testWidgets('omits AI insight card when no backend insight exists (no fabricated content)', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());
      await tester.pumpAndSettle();

      // Verify mock insight is NOT rendered
      expect(find.text('Wardrobe Insight'), findsNothing);
      expect(find.textContaining('outerwear pieces'), findsNothing);
      expect(find.text('Wardrobe Gap Detected'), findsNothing);
      expect(find.text('View Recommendations'), findsNothing);
    });

    testWidgets('renders live backend insight verbatim when returned', (
      WidgetTester tester,
    ) async {
      const liveInsight = WardrobeInsightData(
        title: 'Palette Harmony',
        insight: 'Your neutral layers create 10 versatile combinations.',
        iconName: 'lightbulb_outline_rounded',
        accentColor: 0xFFC5A059,
      );
      await tester.pumpWidget(
        _backendApp(
          wardrobeRepository: _FakeInsightRepository(liveInsight),
        ),
      );
      await tester.pumpAndSettle();

      await tester.drag(
        find.byType(SingleChildScrollView),
        const Offset(0, -1000),
      );
      await tester.pumpAndSettle();

      // Verify backend insight is rendered truthfully
      expect(find.text('Palette Harmony'), findsOneWidget);
      expect(
        find.text('Your neutral layers create 10 versatile combinations.'),
        findsOneWidget,
      );
      expect(find.text('AI Insight'), findsOneWidget);
      // Verify no mock insight text is present
      expect(find.textContaining('outerwear pieces'), findsNothing);
      expect(find.text('Wardrobe Gap Detected'), findsNothing);
    });

    testWidgets('HomeScreen is scrollable with all sections (truthful content)', (
      WidgetTester tester,
    ) async {
      // M9 (STEP 19.25) + P2-8: scrolled through truthful backend slots.
      const liveInsight = WardrobeInsightData(
        title: 'Seasonal Balance',
        insight: 'Neutral layers match well.',
        iconName: 'lightbulb_outline_rounded',
        accentColor: 0xFFC5A059,
      );
      await tester.pumpWidget(
        _backendApp(
          wardrobeRepository: _FakeInsightRepository(liveInsight),
        ),
      );
      await tester.pumpAndSettle();

      await tester.drag(
        find.byType(SingleChildScrollView),
        const Offset(0, -1000),
      );
      await tester.pumpAndSettle();

      expect(find.text('Good morning'), findsOneWidget);
      expect(find.text('Good morning, Alex'), findsNothing);
      expect(find.text("TODAY'S LOOK"), findsOneWidget);
      expect(find.text('Style Score'), findsOneWidget);
      expect(find.text('Quick Actions'), findsOneWidget);
      expect(find.text('Style Streak'), findsOneWidget);
      expect(find.text('Seasonal Balance'), findsOneWidget);
      expect(find.text('AI Insight'), findsOneWidget);
    });

    testWidgets('HomeScreen uses correct theme colors', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      final homeScreen = find.byType(HomeScreen);
      expect(homeScreen, findsOneWidget);

      final materialApp = tester.widget<MaterialApp>(find.byType(MaterialApp));
      expect(materialApp.theme?.brightness, Brightness.dark);
      expect(materialApp.theme?.primaryColor, const Color(0xFFE3C373));
    });

    testWidgets('Try This Look navigates to Daily Outfit screen', (
      WidgetTester tester,
    ) async {
      // M9 (STEP 19.25): navigation runs through the backend-fed slot.
      await tester.pumpWidget(_backendApp());
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(find.text('Try This Look'), 500.0);
      await tester.pumpAndSettle();
      await tester.tap(find.byType(FansiButton).first);
      await tester.pumpAndSettle();

      expect(find.text("TODAY'S LOOK"), findsOneWidget);
      expect(find.text('City Layers'), findsWidgets);
    });

    testWidgets(
      'Change Style button in Today\'s Look navigates to Build Outfit',
      (WidgetTester tester) async {
        await tester.pumpWidget(_backendApp());

        await tester.pumpAndSettle();

        // Tap the on-screen "Change Style" inside the scroll view.
        final changeStyleFinder = find.text('Change Style').first;
        expect(changeStyleFinder, findsOneWidget);

        await tester.scrollUntilVisible(changeStyleFinder, 1000.0);
        await tester.pumpAndSettle();

        await tester.tap(changeStyleFinder);
        await tester.pumpAndSettle();

        expect(find.text('Build Outfit'), findsWidgets);
      },
    );

    testWidgets('Quick action cards navigate to respective screens', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      final scrollable = find.byType(SingleChildScrollView);
      await tester.dragUntilVisible(
        find.text('Scan My Outfit'),
        scrollable,
        const Offset(0, -300),
        maxIteration: 30,
      );

      final scanTitle = find.text('Scan My Outfit');
      expect(scanTitle, findsOneWidget);

      await tester.tap(scanTitle);
      // Use pump() instead of pumpAndSettle() because the scan screen has
      // an indeterminate CircularProgressIndicator that never settles.
      await tester.pump();
      await tester.pump();

      expect(find.text('Capture Photo'), findsOneWidget);
    });

    testWidgets('does not present fabricated recommendations snackbar on Home', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());
      await tester.pumpAndSettle();

      // Fabricated CTA and fake snackbar are completely absent
      expect(find.text('View Recommendations'), findsNothing);
      expect(find.text('Opening Wardrobe Recommendations...'), findsNothing);
    });
  });

  group('Home Feature Widgets Tests', () {
    testWidgets('GreetingHeader renders with name when provided', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const Scaffold(body: GreetingHeader(data: GreetingData.mock)),
        ),
      );

      expect(find.text('Good morning, Alex'), findsOneWidget);
      expect(find.text('Monday, January 13'), findsOneWidget);
    });

    testWidgets('GreetingHeader renders without trailing comma when name is empty', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const Scaffold(
            body: GreetingHeader(
              data: GreetingData(
                greeting: 'Good morning',
                name: '',
                dateLabel: 'Monday, January 13',
              ),
            ),
          ),
        ),
      );

      expect(find.text('Good morning'), findsOneWidget);
      expect(find.text('Good morning, '), findsNothing);
      expect(find.text('Good morning, Alex'), findsNothing);
      expect(find.text('Monday, January 13'), findsOneWidget);
    });

    testWidgets('TodaysLookCard renders all components', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: SingleChildScrollView(
              child: TodaysLookCard(
                data: TodaysLookData.mock,
                onTryThisLook: () {},
                onChangeStyle: () {},
              ),
            ),
          ),
        ),
      );

      expect(find.text('TODAY\'S LOOK'), findsOneWidget);
      expect(find.text('Modern Minimalist'), findsOneWidget);
      expect(find.text('87%'), findsWidgets);
      expect(find.text('Try This Look'), findsOneWidget);
      expect(find.text('Change Style'), findsOneWidget);
    });

    testWidgets('StyleScoreCard renders with breakdown', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(body: StyleScoreCard(data: StyleScoreData.mock)),
        ),
      );

      expect(find.text('Style Score'), findsOneWidget);
      expect(find.text('84'), findsWidgets);
      expect(find.text('Fit'), findsOneWidget);
      expect(find.text('Color'), findsOneWidget);
      expect(find.text('Occasion'), findsOneWidget);
      expect(find.text('Creativity'), findsOneWidget);
    });

    testWidgets('StyleStreakCard renders with progress ring', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(body: StyleStreakCard(data: StyleStreakData.mock)),
        ),
      );

      expect(find.text('Style Streak'), findsOneWidget);
      expect(find.text('Current'), findsOneWidget);
      expect(find.text('Best'), findsOneWidget);
      expect(find.text('Total'), findsOneWidget);
    });

    testWidgets('AIInsightCard renders with action button', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: AIInsightCard(
              data: AIWardrobeInsightData.mock,
              onActionPressed: () {},
            ),
          ),
        ),
      );

      expect(find.text('Wardrobe Gap Detected'), findsOneWidget);
      expect(find.text('AI Insight'), findsOneWidget);
      expect(find.text('View Recommendations'), findsOneWidget);
    });

    testWidgets('QuickActionCard renders and handles tap', (
      WidgetTester tester,
    ) async {
      bool tapped = false;
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: QuickActionCard(
              data: QuickActionData.mockActions.first,
              onTap: () => tapped = true,
            ),
          ),
        ),
      );

      expect(find.text('Scan My Outfit'), findsOneWidget);
      expect(find.text('Get AI analysis of your current look'), findsOneWidget);

      await tester.tap(find.byType(QuickActionCard));
      await tester.pump();

      expect(tapped, true);
    });

    testWidgets('HomeCard renders with proper styling', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(body: HomeCard(child: const Text('Test Content'))),
        ),
      );

      expect(find.text('Test Content'), findsOneWidget);
      expect(find.byType(Container), findsWidgets);
    });

    testWidgets('StreakDayIndicator shows styled and unstyled days', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: Row(
              children: [
                StreakDayIndicator(
                  day: 'Mon',
                  styled: true,
                  score: 87,
                  isToday: true,
                ),
                StreakDayIndicator(day: 'Tue', styled: false, isToday: false),
              ],
            ),
          ),
        ),
      );

      expect(find.text('Mon'), findsOneWidget);
      expect(find.text('Tue'), findsOneWidget);
      expect(find.text('87'), findsOneWidget);
      expect(find.byIcon(Icons.check_rounded), findsOneWidget);
      expect(find.byIcon(Icons.close_rounded), findsOneWidget);
    });
  });
}
