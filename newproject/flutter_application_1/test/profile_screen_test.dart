import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/app.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/profile/data/profile_mock_data.dart';
import 'package:fansivibe/features/profile/presentation/profile_screen.dart';
import 'package:fansivibe/features/profile/presentation/widgets/profile_widgets.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/utils/user_session.dart';

class _TestSummaryRepo implements LearningSummaryRepository {
  final LearningSummary? _summary;
  _TestSummaryRepo({LearningSummary? summary}) : _summary = summary;

  @override
  Future<LearningSummary?> getSummary() async => _summary;
}

/// Creates a [FansivibeApp] booted directly into the main shell so tab
/// navigation can be exercised without re-running the onboarding Entry flow.
Widget _freshApp() {
  return FansivibeApp(
    router: GoRouter(initialLocation: '/home', routes: appRoutes),
  );
}

void main() {
  group('ProfileScreen Widget Tests', () {
    testWidgets(
      'renders neutral empty profile state when unauthenticated or no display name',
      (WidgetTester tester) async {
        UserSession.displayName = null;
        await tester.pumpWidget(_freshApp());

        // Navigate to Profile tab
        await tester.tap(
          find.descendant(
            of: find.byType(NavigationBar),
            matching: find.text('Profile'),
          ),
        );
        await tester.pumpAndSettle();

        // Neutral empty profile state
        expect(find.text('Style Profile'), findsOneWidget);
        expect(find.byIcon(Icons.person_outline_rounded), findsOneWidget);

        // Verifies fake "Alex" data is never rendered
        expect(find.text('Alex'), findsNothing);
        expect(find.text('@alex_styles'), findsNothing);
        expect(find.text('Member since Jan 2026'), findsNothing);
        expect(find.text('March 2026'), findsNothing);
        expect(find.text('Style Seeker'), findsNothing);
        expect(find.text('Lvl 4'), findsNothing);
        expect(find.text('#128'), findsNothing);
      },
    );

    testWidgets(
      'renders real user display name and initials when authenticated',
      (WidgetTester tester) async {
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

        // Verifies fake "Alex" data is never rendered
        expect(find.text('Alex'), findsNothing);
        expect(find.text('@alex_styles'), findsNothing);
        UserSession.displayName = null;
      },
    );

    testWidgets(
      'renders real display name from widget property override',
      (WidgetTester tester) async {
        await tester.pumpWidget(
          MaterialApp(
            theme: ThemeData.dark(),
            home: const ProfileScreen(displayName: 'Taylor Swift'),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('Taylor Swift'), findsOneWidget);
        expect(find.text('T'), findsOneWidget);
        expect(find.text('@taylor_swift'), findsOneWidget);

        // Verifies fake "Alex" data is never rendered
        expect(find.text('Alex'), findsNothing);
        expect(find.text('@alex_styles'), findsNothing);
      },
    );

    testWidgets(
      'renders real style score and streak from summary repository',
      (WidgetTester tester) async {
        final fakeRepo = _TestSummaryRepo(
          summary: const LearningSummary(
            styleScore: 92,
            streak: 5,
            recentSignals: ['Great contrast today'],
            breakdown: LearningSummaryBreakdown(
              base: 60,
              wardrobePoints: 16,
              savedPoints: 16,
              total: 92,
            ),
          ),
        );

        await tester.pumpWidget(
          MaterialApp(
            theme: ThemeData.dark(),
            home: ProfileScreen(
              displayName: 'Sam Stylist',
              summaryRepository: fakeRepo,
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('Sam Stylist'), findsOneWidget);
        expect(find.text('92'), findsOneWidget);
        expect(find.text('5d streak'), findsOneWidget);

        // Verifies fake "Alex" / fake stats are never rendered
        expect(find.text('Alex'), findsNothing);
        expect(find.text('@alex_styles'), findsNothing);
        expect(find.text('#128'), findsNothing);
        expect(find.text('Style Seeker'), findsNothing);
        expect(find.text('Lvl 4'), findsNothing);
      },
    );

    testWidgets(
      'never renders fabricated Alex or mock stats for real users',
      (WidgetTester tester) async {
        await tester.pumpWidget(_freshApp());

        await tester.tap(
          find.descendant(
            of: find.byType(NavigationBar),
            matching: find.text('Profile'),
          ),
        );
        await tester.pumpAndSettle();

        // Strictly verify that none of the prohibited fake "Alex" items appear
        expect(find.text('Alex'), findsNothing);
        expect(find.text('@alex_styles'), findsNothing);
        expect(find.text('Member since Jan 2026'), findsNothing);
        expect(find.text('March 2026'), findsNothing);
        expect(find.text('Style Seeker'), findsNothing);
        expect(find.text('Lvl 4'), findsNothing);
        expect(find.text('#128'), findsNothing);
      },
    );

    testWidgets('renders account menu actions', (WidgetTester tester) async {
      await tester.pumpWidget(_freshApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Profile'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Account'), findsOneWidget);
      expect(find.text('Preferences'), findsOneWidget);
      expect(find.text('Subscription'), findsOneWidget);
      expect(find.text('Support'), findsOneWidget);
      expect(find.text('Settings'), findsOneWidget);
      expect(find.text('Sign Out'), findsOneWidget);
    });

    testWidgets('menu actions navigate to PreferencesScreen', (
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

      final preferencesFinder = find.text('Preferences');
      await tester.scrollUntilVisible(
        preferencesFinder,
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(preferencesFinder);
      await tester.pumpAndSettle();
      expect(find.text('Style Preferences'), findsOneWidget);
    });

    testWidgets('menu actions navigate to SavedLooksScreen', (
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

      final savedLooksFinder = find.text('Saved Looks').last;
      await tester.scrollUntilVisible(
        savedLooksFinder,
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(savedLooksFinder);
      await tester.pumpAndSettle();
      // Backend is unreachable under the test binding, so the backend-truth
      // screen lands on its honest error state (DEC-013, STEP 18.4).
      expect(
        find.text('Couldn\'t load saved looks. Please check your connection.'),
        findsOneWidget,
      );
    });

    testWidgets('menu actions navigate to SubscriptionScreen', (
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

      final subscriptionFinder = find.text('Subscription');
      await tester.scrollUntilVisible(
        subscriptionFinder,
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(subscriptionFinder);
      await tester.pumpAndSettle();
      expect(find.text('Choose Your Plan'), findsOneWidget);
    });

    testWidgets('ProfileScreen is scrollable with all sections', (
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

      // Scroll to bottom
      await tester.drag(
        find.byType(SingleChildScrollView),
        const Offset(0, -1000),
      );
      await tester.pumpAndSettle();

      // All sections should still exist
      expect(find.text('Style Profile'), findsOneWidget);
      expect(find.text('Saved Looks'), findsWidgets);
      expect(find.text('Account'), findsOneWidget);
      expect(find.text('Sign Out'), findsOneWidget);

      // Verifies fake "Alex" data is never rendered
      expect(find.text('Alex'), findsNothing);
      expect(find.text('Style Seeker'), findsNothing);
    });

    testWidgets('uses correct dark theme', (WidgetTester tester) async {
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

      // Destructive semantics are unchanged; only the raw-red accent moved
      // to the Fansivibe error token.
      expect(find.text('Sign Out'), findsOneWidget);
      final icon = tester.widget<Icon>(find.byIcon(Icons.logout_rounded));
      expect(icon.color, FansivibeColors.error);
    });
  });
}
