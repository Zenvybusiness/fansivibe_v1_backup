import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/auth/data/auth_models.dart';
import 'package:fansivibe/features/auth/data/auth_repository.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/profile/data/saved_looks_models.dart';
import 'package:fansivibe/features/profile/data/saved_looks_repository.dart';
import 'package:fansivibe/features/profile/presentation/profile_screen.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeSummaryRepo implements LearningSummaryRepository {
  @override
  Future<LearningSummary?> getSummary() async =>
      const LearningSummary(
        styleScore: 86,
        breakdown: LearningSummaryBreakdown(
          base: 60,
          wardrobePoints: 14,
          savedPoints: 12,
          total: 86,
        ),
        streak: 12,
        recentSignals: ['Tailored', 'Neutral'],
      );
}

class _FakeSavedLooksRepo implements SavedLooksRepository {
  @override
  Future<SavedLookListPage?> listSavedLooks({int page = 1, int pageSize = 20}) async {
    return SavedLookListPage(
      items: [
        SavedLookItem(
          id: 'sl1',
          title: 'Modern Minimal Evening',
          createdAt: DateTime(2026, 9, 20),
        ),
        SavedLookItem(
          id: 'sl2',
          title: 'Structured Autumn Layer',
          createdAt: DateTime(2026, 9, 22),
        ),
      ],
      page: 1,
      pageSize: 20,
      total: 2,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeWardrobeRepo implements WardrobeRepository {
  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async {
    return const [
      WardrobeItemData(
        id: 'w1',
        name: 'Textured Wool Blazer',
        category: 'outerwear',
        color: 'Charcoal',
        material: 'Wool',
        isFavorite: true,
      ),
      WardrobeItemData(
        id: 'w2',
        name: 'Pure Silk Shirt',
        category: 'tops',
        color: 'Ivory',
        material: 'Silk',
        isFavorite: false,
      ),
      WardrobeItemData(
        id: 'w3',
        name: 'Pleated Trousers',
        category: 'bottoms',
        color: 'Obsidian',
        material: 'Wool Blend',
        isFavorite: false,
      ),
    ];
  }

  @override
  Future<WardrobeInsightData?> getInsight() async {
    return const WardrobeInsightData(
      title: 'Atelier Synthesis',
      insight: 'Your wardrobe is strongest in neutral tailoring, with opportunities to expand texture and accent color.',
      iconName: 'lightbulb_outline_rounded',
      accentColor: 0xFFC5A059,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeAuthRepo implements AuthRepository {
  bool signOutCalled = false;

  @override
  Future<AuthStatus> logout() async {
    signOutCalled = true;
    return AuthStatus.signedOut;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Widget _establishedApp({
  LearningSummaryRepository? summaryRepo,
  SavedLooksRepository? savedLooksRepo,
  WardrobeRepository? wardrobeRepo,
  AuthRepository? authRepo,
}) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: ProfileScreen(
      isEstablishedUser: true,
      summaryRepository: summaryRepo ?? _FakeSummaryRepo(),
      savedLooksRepository: savedLooksRepo ?? _FakeSavedLooksRepo(),
      wardrobeRepository: wardrobeRepo ?? _FakeWardrobeRepo(),
      authRepository: authRepo ?? _FakeAuthRepo(),
    ),
  );
}

void main() {
  group('Established User Profile Redesign Tests', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStorage.init(prefs: await SharedPreferences.getInstance());
      UserSession.displayName = 'Alex Rivera';
      UserSession.isReturningUser = true;
      AuthSession.resetForTest();
      // Auth boundary: the established account UI requires a session.
      await AuthSession.saveSession('established-test-token');
    });

    tearDown(() async {
      AuthSession.resetForTest();
      await AuthSession.clearSession();
    });

    testWidgets('1. Renders all 15 visual reference sections for established user', (
      WidgetTester tester,
    ) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(_establishedApp());
      await tester.pumpAndSettle();

      // Top brand bar
      expect(find.text('FANSIVIBE'), findsOneWidget);

      // Profile hero
      expect(find.text('Alex Rivera'), findsOneWidget);
      expect(find.text('@alexrivera'), findsOneWidget);
      expect(find.textContaining('STYLE LEVEL: ADVANCED'), findsOneWidget);
      expect(find.textContaining('TOP 8% GLOBAL'), findsWidgets);
      expect(find.text('MODERN MINIMAL'), findsWidgets);
      expect(find.text('SMART CASUAL'), findsWidgets);
      expect(find.text('QUIET LUXURY'), findsWidgets);
      expect(find.text('Edit Profile'), findsOneWidget);
      expect(find.text('Share'), findsOneWidget);

      // Primary archetype
      expect(find.text('PRIMARY ARCHETYPE'), findsOneWidget);
      expect(find.text('Modern Minimal'), findsWidgets);
      expect(find.textContaining('Structured Tailoring'), findsOneWidget);

      // Style intelligence
      expect(find.text('STYLE INTELLIGENCE'), findsOneWidget);
      expect(find.text('STYLE SCORE'), findsOneWidget);
      expect(find.text('86'), findsWidgets);
      expect(find.text('/ 100'), findsOneWidget);
      expect(find.text('GLOBAL RANK'), findsOneWidget);
      expect(find.text('#2,481'), findsOneWidget);

      // Trajectory
      expect(find.text('TRAJECTORY'), findsOneWidget);
      expect(find.text('30-Day Evolution'), findsOneWidget);
      expect(find.text('Consistency: 94%'), findsOneWidget);

      // Curated Wardrobe
      expect(find.text('Curated Wardrobe'), findsOneWidget);
      expect(find.text('VIEW ALL →'), findsOneWidget);
      expect(find.text('Textured Wool Blazer'), findsOneWidget);

      // Category summary counts
      expect(find.textContaining('TOPS 1'), findsOneWidget);
      expect(find.textContaining('BOTTOMS 1'), findsOneWidget);
      expect(find.textContaining('OUTERWEAR 1'), findsOneWidget);

      // Wardrobe synthesis
      expect(find.text('ATELIER SYNTHESIS'), findsOneWidget);
      expect(find.text('DISCOVER COMPLEMENTARY PIECES →'), findsOneWidget);

      // Saved looks
      expect(find.text('Saved Looks'), findsOneWidget);
      expect(find.text('Archived Ensembles →'), findsOneWidget);
      expect(find.text('Modern Minimal Evening'), findsOneWidget);
      expect(find.text('Structured Autumn Layer'), findsOneWidget);

      // Curated wishlist
      expect(find.text('Curated Wishlist'), findsOneWidget);
      expect(find.text('Entire Acquisition →'), findsOneWidget);
      expect(find.text('STUDIO NICHOLSON'), findsOneWidget);
      expect(find.text('LEMAIRE'), findsOneWidget);

      // Style DNA Profile
      expect(find.text('Style DNA Profile'), findsOneWidget);
      expect(find.text('Signature Dimensions →'), findsOneWidget);
      expect(find.text('COLOR PALETTE'), findsOneWidget);
      expect(find.text('SILHOUETTE'), findsOneWidget);
      expect(find.text('KEY OCCASIONS'), findsOneWidget);
      expect(find.text('AESTHETIC ANCHOR'), findsOneWidget);

      // AI style observation
      expect(find.text('✦ ATELIER ENGINE OBSERVATION'), findsOneWidget);
      expect(find.text('EXPLORE CURATED EDITIONS →'), findsOneWidget);

      // Curatorial milestones & streak
      expect(find.text('Curatorial Milestones'), findsOneWidget);
      expect(find.text('6 of 12 Unlocked'), findsOneWidget);
      expect(find.textContaining('STYLE'), findsWidgets);
      expect(find.text('12-Day Streak'), findsOneWidget);

      // Personalized Recommendations
      expect(find.text('PERSONALIZED RECOMMENDATIONS'), findsOneWidget);
      expect(find.text('Shop Your Style Signature'), findsOneWidget);
      expect(find.text('DISCOVER FOR YOU →'), findsOneWidget);

      // Atelier Governance
      expect(find.text('Atelier Governance'), findsOneWidget);
      expect(find.text('Settings & Membership'), findsOneWidget);
      expect(find.text('MEMBERSHIP'), findsOneWidget);
      expect(find.text('MANAGE →'), findsOneWidget);
      expect(find.text('Preferences'), findsOneWidget);
      expect(find.text('Style Profile & Measurements'), findsOneWidget);
      expect(find.text('Wardrobe Sync'), findsOneWidget);
      expect(find.text('Notifications & Drops'), findsOneWidget);
      expect(find.text('Privacy & Atelier Lookbook'), findsOneWidget);

      // Support and Sign out
      expect(find.text('Help & Concierge'), findsOneWidget);
      expect(find.text('Provide Feedback'), findsOneWidget);
      expect(find.text('SIGN OUT'), findsOneWidget);
    });

    testWidgets('2. Dynamic user name and handle propagate correctly', (
      WidgetTester tester,
    ) async {
      UserSession.displayName = 'Elena Rostova';

      await tester.pumpWidget(_establishedApp());
      await tester.pumpAndSettle();

      expect(find.text('Elena Rostova'), findsOneWidget);
      expect(find.text('@elenarostova'), findsOneWidget);
    });

    testWidgets('3. Sign out button executes auth repository sign out', (
      WidgetTester tester,
    ) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      final authRepo = _FakeAuthRepo();
      await tester.pumpWidget(_establishedApp(authRepo: authRepo));
      await tester.pumpAndSettle();

      final signOutFinder = find.text('SIGN OUT');
      await tester.ensureVisible(signOutFinder);
      await tester.tap(signOutFinder);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));

      expect(authRepo.signOutCalled, isTrue);
    });
  });
}
