import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/features/home/presentation/first_time_home_screen.dart';
import 'package:fansivibe/features/home/presentation/daily_outfit_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/vibe_select_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/face_scan_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

GoRouter _testRouter(Widget home) {
  return GoRouter(
    initialLocation: '/test',
    routes: [
      GoRoute(path: '/test', builder: (context, state) => home),
      ...appRoutes,
    ],
  );
}

Widget _wrap(Widget home) {
  return MaterialApp.router(
    theme: FansivibeTheme.darkTheme,
    routerConfig: _testRouter(home),
  );
}

/// Pumps the single canonical New User Home. The curated look follows the
/// persisted vibe ([LocalStorage.vibe]); the greeting follows [displayName].
Widget _wrapNewHome({String? vibe, String? displayName}) {
  LocalStorage.vibe = vibe;
  return _wrap(FirstTimeHomeScreen(displayName: displayName));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
  });

  group('FirstTimeHomeScreen — New User Home (Homes.pdf architecture)', () {
    testWidgets('renders all core sections according to Homes.pdf', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapNewHome(vibe: 'minimalist'),
      );
      await tester.pumpAndSettle();

      // 1. Branding & Greeting
      expect(find.text('F A N S I V I B E'), findsOneWidget);
      expect(find.text("Let's build your style\nprofile."), findsOneWidget);

      // 2. Today's Look card
      expect(find.text("TODAY'S LOOK"), findsOneWidget);
      expect(find.text('INITIAL LOOK'), findsOneWidget);
      expect(find.text('CURATED RECOMMENDATION'), findsOneWidget);
      expect(find.text('Modern Minimalist'), findsOneWidget);
      expect(find.text('TRY THIS LOOK'), findsOneWidget);
      expect(find.text('CHANGE STYLE'), findsOneWidget);

      // 3. Scan My Outfit banner
      expect(find.text('SCAN MY OUTFIT'), findsAtLeastNWidgets(1));
      expect(
        find.text('GET INSTANT AI FEEDBACK IN UNDER 2 SECONDS'),
        findsOneWidget,
      );

      // 4. Style Score card
      expect(find.text('STYLE SCORE'), findsOneWidget);
      expect(find.text('Baseline'), findsOneWidget);
      expect(find.text('Uncalibrated'), findsOneWidget);
      expect(find.text('0'), findsOneWidget);
      expect(find.text('Your score starts here'), findsOneWidget);
      expect(
        find.text('0 days (First scan activates streak)'),
        findsOneWidget,
      );
      expect(find.text('READY'), findsOneWidget);

      // 5. AI Stylist Discovery
      expect(
        find.text('Want to discover more about your style?'),
        findsOneWidget,
      );
      expect(find.text('Find My Hairstyle'), findsOneWidget);
      expect(find.text('Build My Wardrobe'), findsOneWidget);

      // 6. Style Journey & AI Insight
      expect(find.text('AI INSIGHT'), findsOneWidget);
      expect(find.text('Your Style Journey'), findsOneWidget);
      expect(find.text('Style preferences selected'), findsOneWidget);
      expect(find.text('First outfit scan'), findsOneWidget);
      expect(find.text('First wardrobe item added'), findsOneWidget);
      expect(
        find.text('Unlock dynamic score & trend radar'),
        findsOneWidget,
      );
    });

    testWidgets('reflects the selected style direction (classic)', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapNewHome(vibe: 'classic'),
      );
      await tester.pumpAndSettle();

      expect(find.text('Timeless Tailored'), findsOneWidget);
      expect(find.text('Navy Wool Overcoat'), findsOneWidget);
    });

    testWidgets('shows default streetwear look when no vibe was chosen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_wrapNewHome());
      await tester.pumpAndSettle();

      // Defaults to Relaxed Streetwear look from Homes.pdf
      expect(find.text('Relaxed Streetwear'), findsOneWidget);
      expect(find.text('Oversized Denim Jacket'), findsOneWidget);
    });

    testWidgets('Scan My Outfit navigates to scan outfit flow', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapNewHome(vibe: 'trendy'),
      );
      await tester.pumpAndSettle();

      final scanBanner = find.text('SCAN MY OUTFIT').first;
      final scrollable = find.byType(SingleChildScrollView).first;
      await tester.dragUntilVisible(
        scanBanner,
        scrollable,
        const Offset(0, -200),
        maxIteration: 20,
      );

      await tester.tap(scanBanner);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('Camera Preview'), findsOneWidget);
    });

    testWidgets('TRY THIS LOOK navigates to daily outfit', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapNewHome(vibe: 'minimalist'),
      );
      await tester.pumpAndSettle();

      final tryButton = find.text('TRY THIS LOOK');
      final scrollable = find.byType(SingleChildScrollView).first;
      await tester.dragUntilVisible(
        tryButton,
        scrollable,
        const Offset(0, -200),
        maxIteration: 20,
      );

      await tester.tap(tryButton);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(DailyOutfitScreen), findsOneWidget);
    });

    testWidgets('CHANGE STYLE navigates to vibe selection', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapNewHome(vibe: 'minimalist'),
      );
      await tester.pumpAndSettle();

      final changeButton = find.text('CHANGE STYLE');
      final scrollable = find.byType(SingleChildScrollView).first;
      await tester.dragUntilVisible(
        changeButton,
        scrollable,
        const Offset(0, -200),
        maxIteration: 20,
      );

      await tester.tap(changeButton);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(VibeSelectScreen), findsOneWidget);
    });

    testWidgets('Find My Hairstyle navigates to hairstyle scan', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapNewHome(vibe: 'minimalist'),
      );
      await tester.pumpAndSettle();

      final hairstyleTile = find.text('Find My Hairstyle');
      final scrollable = find.byType(SingleChildScrollView).first;
      await tester.dragUntilVisible(
        hairstyleTile,
        scrollable,
        const Offset(0, -200),
        maxIteration: 20,
      );

      await tester.tap(hairstyleTile);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(FaceScanScreen), findsOneWidget);
    });

    testWidgets('Build My Wardrobe navigates to wardrobe flow', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapNewHome(vibe: 'minimalist'),
      );
      await tester.pumpAndSettle();

      final wardrobeTile = find.text('Build My Wardrobe');
      final scrollable = find.byType(SingleChildScrollView).first;
      await tester.dragUntilVisible(
        wardrobeTile,
        scrollable,
        const Offset(0, -200),
        maxIteration: 20,
      );

      await tester.tap(wardrobeTile);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(WardrobeScreen), findsOneWidget);
    });

    testWidgets('renders cleanly on phone-sized viewport without overflow', (
      WidgetTester tester,
    ) async {
      tester.view.physicalSize = const Size(360, 640);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _wrapNewHome(vibe: 'bold'),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
    });
  });

  group('FirstTimeHomeScreen greeting (Homes.pdf architecture)', () {
    // Display names are account identity: the named greeting renders
    // while signed in; signed-out Homes show the generic greeting.
    setUp(() async {
      AuthSession.resetForTest();
      await AuthSession.saveSession('new-user-greeting-token');
    });
    tearDown(() async {
      AuthSession.resetForTest();
      await AuthSession.clearSession();
    });

    testWidgets('renders user name in greeting and completed preference step', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapNewHome(displayName: 'Alex'),
      );
      await tester.pumpAndSettle();

      // Greeting with name
      expect(find.textContaining('Alex'), findsOneWidget);
      expect(find.text("TODAY'S LOOK"), findsOneWidget);
      expect(find.text('INITIAL LOOK'), findsOneWidget);

      // Score starts at 0 uncalibrated
      expect(find.text('0'), findsOneWidget);
      expect(find.text('Baseline'), findsOneWidget);
      expect(find.text('Uncalibrated'), findsOneWidget);

      // Preferences are selected
      expect(find.text('Style preferences selected'), findsOneWidget);
    });

    testWidgets('renders on phone-sized viewport without overflow', (
      WidgetTester tester,
    ) async {
      tester.view.physicalSize = const Size(360, 640);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _wrapNewHome(displayName: 'Alex'),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
    });

    testWidgets('signed out with stale local name shows generic greeting', (
      WidgetTester tester,
    ) async {
      await AuthSession.clearSession();
      LocalStorage.displayName = 'StaleName';

      await tester.pumpWidget(
        _wrap(const FirstTimeHomeScreen(displayName: null)),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('StaleName'), findsNothing);
    });
  });
}
