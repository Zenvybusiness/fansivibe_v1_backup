import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/app.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/profile/data/profile_mock_data.dart';
import 'package:fansivibe/features/profile/presentation/profile_screen.dart';
import 'package:fansivibe/features/profile/presentation/widgets/profile_widgets.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _TestSummaryRepo implements LearningSummaryRepository {
  final LearningSummary? _summary;
  _TestSummaryRepo({LearningSummary? summary}) : _summary = summary;

  @override
  Future<LearningSummary?> getSummary() async => _summary;
}

Widget _freshApp() {
  return FansivibeApp(
    router: GoRouter(initialLocation: '/home', routes: appRoutes),
  );
}

void main() {
  group('ProfileScreen Redesign & Dynamic Behavior Tests', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStorage.init(prefs: await SharedPreferences.getInstance());
      UserSession.displayName = null;
      UserSession.hasSavedWardrobeItem = false;
      LocalStorage.savedLookIds = [];
      LearningService.instance.resetForTest();
    });

    testWidgets('1. New-user Profile renders all reference sections', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Profile'),
        ),
      );
      await tester.pumpAndSettle();

      // Top level badge & neutral profile header
      expect(find.text('NOVICE'), findsOneWidget);
      expect(find.text('Style Profile'), findsOneWidget);
      expect(find.textContaining('NEW STYLE JOURNEY'), findsOneWidget);
      expect(find.text('Edit Profile'), findsOneWidget);
      expect(find.text('Share'), findsOneWidget);

      // Current style score & global rank
      expect(find.text('CURRENT STYLE SCORE'), findsOneWidget);
      expect(find.text('--'), findsOneWidget);
      expect(find.text('Uncalibrated'), findsOneWidget);
      expect(find.text('+ Scan Outfit  →'), findsOneWidget);
      expect(find.text('GLOBAL RANK'), findsOneWidget);
      expect(find.text('Not Ranked'), findsOneWidget);

      // Style progress
      expect(find.text('Style Progress'), findsOneWidget);
      expect(find.text('30-DAY OVERVIEW'), findsOneWidget);
      expect(find.text('Now'), findsOneWidget);

      // Achievements
      expect(find.text('Achievements'), findsOneWidget);
      expect(find.text('0 OF 4 UNLOCKED'), findsOneWidget);

      // Saved looks
      expect(find.text('Saved Looks'), findsWidgets);
      expect(find.text('No saved looks yet'), findsOneWidget);
      expect(find.text('Curate First Outfit'), findsOneWidget);

      // Style DNA
      expect(find.text('Style DNA'), findsOneWidget);
      expect(find.text('PENDING ASSESSMENT'), findsOneWidget);
      expect(find.text('DISCOVER MY STYLE DNA'), findsOneWidget);

      // Lower menu
      expect(find.text('PREFERENCES'), findsOneWidget);
      expect(find.text('SAVED LOOKS'), findsOneWidget);
      expect(find.text('SUBSCRIPTION'), findsOneWidget);
      expect(find.text('SUPPORT'), findsOneWidget);
      expect(find.text('SIGN OUT'), findsOneWidget);
    });

    testWidgets('2. Real user name appears and fake data is never hardcoded', (
      WidgetTester tester,
    ) async {
      UserSession.displayName = 'Jordan Lee';
      await tester.pumpWidget(_freshApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Profile'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Jordan Lee'), findsOneWidget);
      expect(find.text('J'), findsOneWidget);
      expect(find.text('@jordan_lee'), findsOneWidget);
      expect(find.textContaining('@JORDANLEE'), findsOneWidget);

      // Strictly verify fake "Alex" profile data is never hardcoded
      expect(find.text('Alex'), findsNothing);
      expect(find.text('@alex_styles'), findsNothing);
      expect(find.text('Style Seeker'), findsNothing);
      expect(find.text('Lvl 4'), findsNothing);
      expect(find.text('#128'), findsNothing);
    });

    testWidgets('3. Empty Style Score state appears correctly for new users', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const ProfileScreen(),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('CURRENT STYLE SCORE'), findsOneWidget);
      expect(find.text('--'), findsOneWidget);
      expect(find.text('Uncalibrated'), findsOneWidget);
      expect(find.text('+ Scan Outfit  →'), findsOneWidget);
    });

    testWidgets('4. Empty Global Rank state appears correctly for new users', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const ProfileScreen(),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('GLOBAL RANK'), findsOneWidget);
      expect(find.text('Not Ranked'), findsOneWidget);
      expect(
        find.text('Complete style profile to\nunlock ranking'),
        findsOneWidget,
      );
    });

    testWidgets('5. Achievement locked state appears with 0 OF 4 UNLOCKED', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const ProfileScreen(),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('0 OF 4 UNLOCKED'), findsOneWidget);
      expect(find.text('COLOR'), findsOneWidget);
      expect(find.text('FIT'), findsOneWidget);
      expect(find.text('OCCASION'), findsOneWidget);
      expect(find.text('TREND'), findsOneWidget);
      expect(find.text('LOCKED'), findsNWidgets(4));
    });

    testWidgets('6. Empty Saved Looks state appears with curation CTA', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const ProfileScreen(),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('No saved looks yet'), findsOneWidget);
      expect(find.text('Curate First Outfit'), findsOneWidget);
      expect(find.text('EXPLORE LOOKS'), findsOneWidget);
    });

    testWidgets('7. Pending Style DNA state appears with all 4 attribute cells', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const ProfileScreen(),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('PENDING ASSESSMENT'), findsOneWidget);
      expect(find.text('BIOMETRIC & PALETTE ARCHETYPE'), findsOneWidget);
      expect(find.text('SKIN TONE'), findsOneWidget);
      expect(find.text('FACE SHAPE'), findsOneWidget);
      expect(find.text('BODY TYPE'), findsOneWidget);
      expect(find.text('STYLE TYPE'), findsOneWidget);
      expect(find.text('Not analyzed yet'), findsNWidgets(2));
      expect(find.text('Pending setup'), findsOneWidget);
      expect(find.text('In progress'), findsOneWidget);
      expect(find.text('DISCOVER MY STYLE DNA'), findsOneWidget);
    });

    testWidgets('8. Preferences empty state appears', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const ProfileScreen(),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('PREFERENCES'), findsOneWidget);
      expect(find.text('Not configured yet'), findsOneWidget);
    });

    testWidgets('9. Subscription uses real state showing FREE', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const ProfileScreen(),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('SUBSCRIPTION'), findsOneWidget);
      expect(find.text('FREE'), findsOneWidget);
    });

    testWidgets('10. Wardrobe state changes propagate and unlock FIT achievement', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const ProfileScreen(),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('0 OF 4 UNLOCKED'), findsOneWidget);

      // Simulate adding a wardrobe item
      UserSession.hasSavedWardrobeItem = true;
      LearningService.instance.addItem(
        const WardrobeEntry(
          id: 'item-101',
          name: 'Navy Cashmere Knit',
          category: 'tops',
          color: 'Navy',
        ),
      );
      await tester.pumpAndSettle();

      // FIT and COLOR achievements should now unlock reactively
      expect(find.text('2 OF 4 UNLOCKED'), findsOneWidget);
      expect(find.text('UNLOCKED'), findsNWidgets(2));
    });

    testWidgets('11. Saved Looks changes propagate reactively', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const ProfileScreen(),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('0 items'), findsOneWidget);
      expect(find.text('No saved looks yet'), findsOneWidget);

      // Simulate saving a look in LearningService
      LearningService.instance.addSavedLook('look-abc');
      await tester.pumpAndSettle();

      expect(find.text('1 items'), findsOneWidget);
    });

    testWidgets('12. Profile remains correct after navigation across tabs', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      // Navigate to Profile
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Profile'),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('NOVICE'), findsOneWidget);

      // Navigate to Discover
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Discover'),
        ),
      );
      await tester.pumpAndSettle();

      // Return to Profile
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Profile'),
        ),
      );
      await tester.pumpAndSettle();

      // Everything remains intact and rendered
      expect(find.text('NOVICE'), findsOneWidget);
      expect(find.text('Style Progress'), findsOneWidget);
      expect(find.text('Achievements'), findsOneWidget);
    });

    testWidgets('13. Profile remains correct after restart with stored name', (
      WidgetTester tester,
    ) async {
      LocalStorage.displayName = 'Morgan Blake';

      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const ProfileScreen(),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Morgan Blake'), findsOneWidget);
      expect(find.text('MB'), findsOneWidget);
    });

    testWidgets('14. Existing users with calibrated summary render real score', (
      WidgetTester tester,
    ) async {
      final fakeRepo = _TestSummaryRepo(
        summary: const LearningSummary(
          styleScore: 82,
          streak: 4,
          recentSignals: ['Excellent balance'],
          breakdown: LearningSummaryBreakdown(
            base: 60,
            wardrobePoints: 12,
            savedPoints: 10,
            total: 82,
          ),
        ),
      );

      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: ProfileScreen(
            displayName: 'Alexandre',
            summaryRepository: fakeRepo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Alexandre'), findsOneWidget);
      expect(find.text('82'), findsWidgets);
      expect(find.text('+4.2% this week'), findsOneWidget);
      expect(find.text('--'), findsNothing);
    });

    testWidgets('15. Menu actions navigate to Preferences, SavedLooks, Subscription', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Profile'),
        ),
      );
      await tester.pumpAndSettle();

      // Test Preferences navigation
      final prefFinder = find.text('PREFERENCES');
      await tester.scrollUntilVisible(prefFinder, 200, scrollable: find.byType(Scrollable).first);
      await tester.tap(prefFinder);
      await tester.pumpAndSettle();
      expect(find.text('Style Preferences'), findsOneWidget);

      // Return to Profile
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Profile'),
        ),
      );
      await tester.pumpAndSettle();

      // Test Subscription navigation
      final subFinder = find.text('SUBSCRIPTION');
      await tester.scrollUntilVisible(subFinder, 200, scrollable: find.byType(Scrollable).first);
      await tester.tap(subFinder);
      await tester.pumpAndSettle();
      expect(find.text('Choose Your Plan'), findsOneWidget);
    });

    testWidgets('16. Uses correct dark theme', (WidgetTester tester) async {
      await tester.pumpWidget(_freshApp());

      final materialApp = tester.widget<MaterialApp>(find.byType(MaterialApp));
      expect(materialApp.theme?.brightness, Brightness.dark);
    });
  });

  group('Profile Feature Widgets Tests', () {
    testWidgets('ProfileHeader renders correctly', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const Scaffold(
            body: SingleChildScrollView(
              child: ProfileHeader(data: ProfileData.mock),
            ),
          ),
        ),
      );

      expect(find.text('Alex'), findsOneWidget);
      expect(find.text('@alex_styles'), findsOneWidget);
      expect(find.text('Member since Jan 2026'), findsOneWidget);
    });

    testWidgets('StylistLevelBadge renders with progress', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: StylistLevelBadge(data: ProfileData.mock.stylistLevel),
          ),
        ),
      );

      expect(find.text('Style Seeker'), findsOneWidget);
      expect(find.text('Lvl 4'), findsOneWidget);
    });

    testWidgets('ProfileStatRow renders score and rank', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: ProfileStatRow(score: 84, rank: ProfileData.mock.globalRank),
          ),
        ),
      );

      expect(find.text('84'), findsOneWidget);
      expect(find.text('#128'), findsOneWidget);
      expect(find.text('Style Score'), findsOneWidget);
      expect(find.text('Global Rank'), findsOneWidget);
    });

    testWidgets('StyleProgressIndicator renders correctly', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: StyleProgressIndicator(data: ProfileData.mock.styleProgress),
          ),
        ),
      );

      expect(find.text('XP to next level'), findsOneWidget);
      expect(find.text('3200 / 5000'), findsOneWidget);
    });

    testWidgets('AchievementGrid shows locked and unlocked', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: AchievementGrid(achievements: ProfileData.mock.achievements),
          ),
        ),
      );

      expect(find.text('7-Day Streak'), findsOneWidget);
      expect(find.text('Style Guru'), findsOneWidget);
      expect(find.text('Score 90+'), findsOneWidget);
      expect(find.text('20 Looks'), findsOneWidget);
      expect(find.text('Explorer'), findsOneWidget);
      expect(find.text('Trendsetter'), findsOneWidget);
    });

    testWidgets('SavedLooksRow renders looks', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: SavedLooksRow(looks: ProfileData.mock.savedLooks),
          ),
        ),
      );

      expect(find.text('Modern Minimalist'), findsOneWidget);
      expect(find.text('Weekend Casual'), findsOneWidget);
      expect(find.text('Smart Business'), findsOneWidget);
      expect(find.text('Date Night'), findsOneWidget);
    });

    testWidgets('StyleDnaCard renders all attributes', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(body: StyleDnaCard(data: ProfileData.mock.styleDna)),
        ),
      );

      expect(find.text('Skin Tone'), findsOneWidget);
      expect(find.text('Warm Medium'), findsOneWidget);
      expect(find.text('Face Shape'), findsOneWidget);
      expect(find.text('Oval'), findsOneWidget);
      expect(find.text('Body Type'), findsOneWidget);
      expect(find.text('Athletic'), findsOneWidget);
      expect(find.text('Style Type'), findsOneWidget);
      expect(find.text('Modern Minimalist'), findsOneWidget);
    });

    testWidgets('ProfileMenuCard renders and handles tap', (
      WidgetTester tester,
    ) async {
      bool tapped = false;
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: ProfileMenuCard(
              action: ProfileData.mock.menuActions.first,
              onTap: () => tapped = true,
            ),
          ),
        ),
      );

      expect(find.text('Preferences'), findsOneWidget);

      await tester.tap(find.text('Preferences'));
      await tester.pump();

      expect(tapped, true);
    });

    testWidgets('ProfileMenuCard destructive action uses the error token', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: ProfileMenuCard(
              action: ProfileData.mock.menuActions.firstWhere(
                (action) => action.id == 'sign_out',
              ),
            ),
          ),
        ),
      );

      expect(find.text('Sign Out'), findsOneWidget);
      final icon = tester.widget<Icon>(find.byIcon(Icons.logout_rounded));
      expect(icon.color, FansivibeColors.error);
    });
  });
}
