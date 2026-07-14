import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/app/app.dart';
import 'package:fansivibe/features/profile/data/profile_mock_data.dart';
import 'package:fansivibe/features/profile/presentation/widgets/profile_widgets.dart';

void main() {
  group('ProfileScreen Widget Tests', () {
    testWidgets('renders profile header with avatar and name', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Profile tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Profile'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify header
      expect(find.text('Alex'), findsOneWidget);
      expect(find.text('@alex_styles'), findsOneWidget);
      expect(find.text('Member since Jan 2026'), findsOneWidget);
    });

    testWidgets('renders stylist level badge', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Profile'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Style Seeker'), findsOneWidget);
      expect(find.text('Lvl 4'), findsOneWidget);
    });

    testWidgets('renders style score and global rank', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Profile'),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text('Style Score'),
        findsWidgets,
      ); // section title + stat label
      expect(find.text('Global Rank'), findsOneWidget);
      expect(find.text('#128'), findsOneWidget);
    });

    testWidgets('renders style progress section', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Profile'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('XP to next level'), findsOneWidget);
      expect(find.text('3200 / 5000'), findsOneWidget);
    });

    testWidgets('renders achievements section', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Profile'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Achievements'), findsOneWidget);
      expect(find.text('4 of 6 unlocked'), findsOneWidget);
      expect(find.text('7-Day Streak'), findsOneWidget);
      expect(find.text('Style Guru'), findsOneWidget);
      expect(find.text('Score 90+'), findsOneWidget);
      expect(find.text('20 Looks'), findsOneWidget);
      expect(find.text('Explorer'), findsOneWidget);
      expect(find.text('Trendsetter'), findsOneWidget);
    });

    testWidgets('renders saved looks preview', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Profile'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Saved Looks'), findsWidgets);
      expect(find.text('View All'), findsOneWidget);
      expect(find.text('Modern Minimalist'), findsAtLeast(1));
      expect(find.text('Weekend Casual'), findsOneWidget);
    });

    testWidgets('renders Style DNA section', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Profile'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Style DNA'), findsOneWidget);
      expect(find.text('Skin Tone'), findsOneWidget);
      expect(find.text('Warm Medium'), findsOneWidget);
      expect(find.text('Face Shape'), findsOneWidget);
      expect(find.text('Oval'), findsOneWidget);
      expect(find.text('Body Type'), findsOneWidget);
      expect(find.text('Athletic'), findsOneWidget);
      expect(find.text('Style Type'), findsOneWidget);
      expect(find.text('Modern Minimalist'), findsAtLeast(1));
    });

    testWidgets('renders account menu actions', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

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

    testWidgets('menu actions show snackbar on tap', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Profile'),
        ),
      );
      await tester.pumpAndSettle();

      final scrollable = find.byType(SingleChildScrollView);
      await tester.drag(scrollable, const Offset(0, -1000));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Preferences'));
      await tester.pumpAndSettle();
      expect(find.text('Opening Preferences...'), findsOneWidget);
    });

    testWidgets('ProfileScreen is scrollable with all sections', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

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
      expect(find.text('Alex'), findsOneWidget);
      expect(find.text('Style Seeker'), findsOneWidget);
      expect(find.text('Achievements'), findsOneWidget);
      expect(find.text('Saved Looks'), findsWidgets);
      expect(find.text('Style DNA'), findsOneWidget);
      expect(find.text('Account'), findsOneWidget);
      expect(find.text('Sign Out'), findsOneWidget);
    });

    testWidgets('uses correct dark theme', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

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
          home: Scaffold(
            body: StyleDnaCard(data: ProfileData.mock.styleDna),
          ),
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
  });
}
