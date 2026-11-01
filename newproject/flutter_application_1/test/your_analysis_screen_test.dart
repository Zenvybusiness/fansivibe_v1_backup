import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/photo_capture_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/your_analysis_screen.dart';
import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/auth/data/guest_data_migration.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Regression tests for the Analyze My Style result handoff (guest).
///
/// 1. The screen must never render fabricated analysis data (no mock
///    score, palette, or insights posing as a real result).
/// 2. "Retake Photo" must open a fresh capture screen — never the
///    AiAnalysis processing timer (the old pop() loop).
/// 3. "Sign In to Continue" and "Continue Without Account" keep working:
///    conversion still routes to account creation, while continuing lands
///    on the Home experience (Today's Look via the persisted vibe).
Object? _seenExtra;

GoRouter _router({Widget? resultScreen}) {
  return GoRouter(
    initialLocation: '/your-analysis',
    routes: [
      GoRoute(
        path: '/your-analysis',
        builder: (context, state) => resultScreen ?? const YourAnalysisScreen(),
      ),
      GoRoute(
        path: '/photo-capture',
        name: RouteNames.photoCapture,
        builder: (context, state) => const PhotoCaptureScreen(),
      ),
      GoRoute(
        path: '/analysis',
        name: RouteNames.aiAnalysis,
        builder: (context, state) =>
            const Scaffold(body: Text('analysis-marker')),
      ),
      GoRoute(
        path: '/create-account',
        name: RouteNames.createAccount,
        builder: (context, state) =>
            const Scaffold(body: Text('create-account-marker')),
      ),
      GoRoute(
        path: '/home',
        name: RouteNames.home,
        builder: (context, state) {
          _seenExtra = state.extra;
          return const Scaffold(body: Text('home-marker'));
        },
      ),
    ],
  );
}

Future<void> _tapVisible(WidgetTester tester, String label) async {
  final finder = find.text(label);
  await tester.scrollUntilVisible(finder, 300.0);
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    AuthSession.resetForTest();
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    LocalStorage.resetForTest();
  });

  group('YourAnalysisScreen (guest handoff)', () {
    testWidgets('shows honest handoff state, never mock analysis data', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      // Honest state.
      expect(find.text('Photo ready'), findsOneWidget);
      expect(find.text('Continue Without Account'), findsOneWidget);
      expect(find.text('Sign In to Continue'), findsOneWidget);
      expect(find.text('Retake Photo'), findsOneWidget);
      // Mock analysis data must be gone.
      expect(find.text('Style Score'), findsNothing);
      expect(find.text('Strong Silhouette'), findsNothing);
      expect(find.text('Color Harmony'), findsNothing);
      expect(find.text('Refinement Tip'), findsNothing);
      expect(find.text('AI Insights'), findsNothing);
      expect(find.text('Appearance Intelligence'), findsNothing);
    });

    testWidgets('Retake Photo opens capture, not processing', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Retake Photo');

      expect(tester.takeException(), isNull);
      // Fresh capture screen (idle Take Photo), not the timer.
      expect(find.byType(PhotoCaptureScreen), findsOneWidget);
      expect(find.text('Take Photo'), findsOneWidget);
      expect(find.text('analysis-marker'), findsNothing);
    });

    testWidgets('Sign In to Continue routes to account creation', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Sign In to Continue');

      expect(tester.takeException(), isNull);
      expect(find.text('create-account-marker'), findsOneWidget);
    });

    testWidgets('Continue Without Account reaches Home with the vibe', (
      WidgetTester tester,
    ) async {
      _seenExtra = null;
      LocalStorage.vibe = 'minimalist';
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('home-marker'), findsOneWidget);
      expect(LocalStorage.savedLocally, isTrue);
      expect(LocalStorage.onboardingComplete, isTrue);
      expect((_seenExtra as Map<String, dynamic>?)?['vibe'], 'minimalist');
    });

    testWidgets('Continue Without Account reports no cache without a preview', (
      WidgetTester tester,
    ) async {
      _seenExtra = null;
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('home-marker'), findsOneWidget);
      expect(
        (_seenExtra as Map<String, dynamic>?)?['analysis_cached'],
        isFalse,
      );
    });

    testWidgets('Continue Without Account reports no cache after a failure', (
      WidgetTester tester,
    ) async {
      _seenExtra = null;
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: const YourAnalysisScreen(
              outfitFailure: 'no_face_detected',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Preview unavailable'), findsOneWidget);
      await _tapVisible(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('home-marker'), findsOneWidget);
      expect(
        (_seenExtra as Map<String, dynamic>?)?['analysis_cached'],
        isFalse,
      );
    });

    testWidgets(
      'Continue Without Account reports a cache when the preview is stashed',
      (WidgetTester tester) async {
        _seenExtra = null;
        stashPendingEphemeralResult(
          feature: EphemeralFeature.outfit,
          snapshot: <String, dynamic>{
            'appearance': <String, dynamic>{'faceShape': 'oval'},
          },
        );
        await tester.pumpWidget(
          MaterialApp.router(
            routerConfig: _router(
              resultScreen: YourAnalysisScreen(
                outfitSnapshot: <String, dynamic>{
                  'appearance': <String, dynamic>{'faceShape': 'oval'},
                },
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('Your Style Preview'), findsOneWidget);
        await _tapVisible(tester, 'Continue Without Account');

        expect(tester.takeException(), isNull);
        expect(find.text('home-marker'), findsOneWidget);
        expect(
          (_seenExtra as Map<String, dynamic>?)?['analysis_cached'],
          isTrue,
        );
      },
    );

    testWidgets('Continue Without Account ignores a malformed outfit stash', (
      WidgetTester tester,
    ) async {
      _seenExtra = null;
      stashPendingEphemeralResult(
        feature: EphemeralFeature.outfit,
        snapshot: <String, dynamic>{
          'appearance': 'not-a-map',
          'garment': <String, dynamic>{},
        },
      );
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: YourAnalysisScreen(
              outfitSnapshot: <String, dynamic>{
                'appearance': <String, dynamic>{'faceShape': 'oval'},
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(peekPendingEphemeralResult(), isNotNull);
      await _tapVisible(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('home-marker'), findsOneWidget);
      expect(
        (_seenExtra as Map<String, dynamic>?)?['analysis_cached'],
        isFalse,
      );
    });

    testWidgets('no-photo handoff clears an older outfit stash', (
      WidgetTester tester,
    ) async {
      _seenExtra = null;
      stashPendingEphemeralResult(
        feature: EphemeralFeature.outfit,
        snapshot: <String, dynamic>{
          'appearance': <String, dynamic>{'faceShape': 'oval'},
        },
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();

      expect(peekPendingEphemeralResult(), isNull);
      expect(
        find.textContaining('Nothing has been analyzed yet'),
        findsOneWidget,
      );
      await _tapVisible(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('home-marker'), findsOneWidget);
      expect(
        (_seenExtra as Map<String, dynamic>?)?['analysis_cached'],
        isFalse,
      );
    });

    testWidgets('no-photo handoff preserves an unrelated stashed result', (
      WidgetTester tester,
    ) async {
      _seenExtra = null;
      stashPendingEphemeralResult(
        feature: EphemeralFeature.hairstyle,
        snapshot: <String, dynamic>{'style': 'curtain'},
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();

      expect(peekPendingEphemeralResult()?.feature, EphemeralFeature.hairstyle);
      await _tapVisible(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('home-marker'), findsOneWidget);
      expect(
        (_seenExtra as Map<String, dynamic>?)?['analysis_cached'],
        isFalse,
      );
    });

    testWidgets('route preview without a stash does not claim a cache', (
      WidgetTester tester,
    ) async {
      _seenExtra = null;
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: YourAnalysisScreen(
              outfitSnapshot: <String, dynamic>{
                'appearance': <String, dynamic>{'faceShape': 'oval'},
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Your Style Preview'), findsOneWidget);
      await _tapVisible(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('home-marker'), findsOneWidget);
      expect(
        (_seenExtra as Map<String, dynamic>?)?['analysis_cached'],
        isFalse,
      );
    });

    testWidgets('malformed appearance branch does not crash the preview', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: YourAnalysisScreen(
              outfitSnapshot: <String, dynamic>{
                'appearance': 'not-a-map',
                'garment': <String, dynamic>{'category': 'tops', 'color': 7},
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('Your Style Preview'), findsOneWidget);
      expect(find.text('Garment: Tops'), findsOneWidget);
      expect(find.textContaining('Color:'), findsNothing);
      expect(
        find.text("Face shape wasn't measurable in this photo."),
        findsOneWidget,
      );
    });

    testWidgets('malformed optional snapshot fields are ignored', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: YourAnalysisScreen(
              outfitSnapshot: <String, dynamic>{
                'appearance': <String, dynamic>{'faceShape': 42},
                'garment': 'not-a-map',
                'appearance_error': 'not-a-map',
                'garment_error': <String, dynamic>{'reason': 7},
                'recommendations': 'not-a-map',
                'confidence': 'high',
                'needs_more_data': 'yes',
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('Your Style Preview'), findsOneWidget);
      expect(find.textContaining('Face shape:'), findsNothing);
      expect(find.textContaining('Garment:'), findsNothing);
      expect(
        find.text('No clear outfit details in this photo.'),
        findsOneWidget,
      );
      expect(
        find.text("Face shape wasn't measurable in this photo."),
        findsOneWidget,
      );
    });

    testWidgets('snapshot without a renderable branch shows the empty state', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: YourAnalysisScreen(
              outfitSnapshot: <String, dynamic>{
                'appearance': 'not-a-map',
                'garment': <String, dynamic>{},
                'appearance_error': 'not-a-map',
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('Your Style Preview'), findsNothing);
      expect(
        find.textContaining('Nothing has been analyzed yet'),
        findsOneWidget,
      );
    });
  });

  group('D10 Guest Preview Disclosure', () {
    testWidgets('1 & 2 & 3. guest preview disclosure is visible with required temporary preview copy', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: YourAnalysisScreen(
              outfitSnapshot: <String, dynamic>{
                'appearance': <String, dynamic>{'faceShape': 'oval'},
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final disclosureFinder = find.text('Your style preview is temporary');
      await tester.scrollUntilVisible(disclosureFinder, 300.0);
      await tester.pumpAndSettle();

      // 1. Guest preview disclosure is visible
      expect(disclosureFinder, findsOneWidget);

      // 2. Temporary-preview meaning is displayed
      expect(
        find.textContaining(
          'Your guest scan gives you a preview of your style analysis. '
          'It is not saved as your personal profile.',
        ),
        findsOneWidget,
      );

      // 3. User is told to complete an authenticated scan for profile personalization
      expect(
        find.textContaining(
          'complete an authenticated scan to personalize your Fansivibe profile',
        ),
        findsOneWidget,
      );

      // Option to continue without an account is preserved
      expect(
        find.textContaining('You can also continue exploring without an account'),
        findsOneWidget,
      );
    });

    testWidgets('4. Create Account navigation still works', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: YourAnalysisScreen(
              outfitSnapshot: <String, dynamic>{
                'appearance': <String, dynamic>{'faceShape': 'oval'},
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Create Account');

      expect(tester.takeException(), isNull);
      expect(find.text('create-account-marker'), findsOneWidget);
    });

    testWidgets('5. Sign In navigation still works from disclosure screen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: YourAnalysisScreen(
              outfitSnapshot: <String, dynamic>{
                'appearance': <String, dynamic>{'faceShape': 'oval'},
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Sign In to Continue');

      expect(tester.takeException(), isNull);
      expect(find.text('create-account-marker'), findsOneWidget);
    });

    testWidgets('6. Continue Without Account still works from disclosure screen', (
      WidgetTester tester,
    ) async {
      _seenExtra = null;
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: YourAnalysisScreen(
              outfitSnapshot: <String, dynamic>{
                'appearance': <String, dynamic>{'faceShape': 'oval'},
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('home-marker'), findsOneWidget);
      expect(LocalStorage.savedLocally, isTrue);
      expect(LocalStorage.onboardingComplete, isTrue);
    });

    testWidgets('7. disclosure is not incorrectly shown to authenticated users', (
      WidgetTester tester,
    ) async {
      await AuthSession.saveSession('auth-jwt-token-xyz');

      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: YourAnalysisScreen(
              outfitSnapshot: <String, dynamic>{
                'appearance': <String, dynamic>{'faceShape': 'oval'},
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Your style preview is temporary'), findsNothing);
      expect(
        find.textContaining('Your guest scan gives you a preview'),
        findsNothing,
      );
    });

    testWidgets(
      '8. guest-to-authenticated transition does not imply appearance data migration',
      (WidgetTester tester) async {
        // Stash an ephemeral outfit appearance snapshot
        stashPendingEphemeralResult(
          feature: EphemeralFeature.outfit,
          snapshot: <String, dynamic>{
            'appearance': <String, dynamic>{'faceShape': 'square'},
          },
        );

        // Verify that stashed result is in local storage only
        final stashed = peekPendingEphemeralResult();
        expect(stashed, isNotNull);
        expect(stashed?.snapshot['appearance']?['faceShape'], 'square');

        // Migrate guest data (wardrobe and prefs only)
        final repo = _FakeWardrobeRepo();
        final learning = _FakeLearning(
          wardrobe: [
            const WardrobeEntry(
              id: 'local-1',
              name: 'Jacket',
              category: 'outerwear',
              color: 'navy',
            ),
          ],
          prefs: ['smart_casual'],
        );

        final migration = GuestDataMigration(
          wardrobeRepo: repo,
          syncPreference: ({required String code}) async =>
              PreferenceSyncResult.synced,
          learning: learning,
        );
        final result = await migration.migrate();

        // Wardrobe and prefs migrated cleanly
        expect(result.migratedItemNames, ['Jacket']);
        expect(result.prefsSynced, ['smart_casual']);

        // Verify appearance data was NOT migrated into server wardrobe or preferences
        expect(repo.createdNames, ['Jacket']);
        expect(repo.server.any((i) => i.name.contains('square')), isFalse);
        expect(result.migratedLocalIds, ['local-1']);

        // Ephemeral result remains untransferred and device-local
        final afterMigration = peekPendingEphemeralResult();
        expect(afterMigration?.snapshot['appearance']?['faceShape'], 'square');
      },
    );
  });
}

class _FakeWardrobeRepo implements WardrobeRepository {
  final List<WardrobeItemData> server = [];
  final List<String> createdNames = [];
  bool throwOnList = false;

  _FakeWardrobeRepo();

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async {
    if (throwOnList) throw Exception('offline');
    return List.of(server);
  }

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async => null;

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
    String? fit,
    double? fitConfidence,
  }) async {
    createdNames.add(name);
    final item = WardrobeItemData(
      id: 'server-${createdNames.length}',
      name: name,
      category: category,
      color: color,
      material: material,
    );
    server.add(item);
    return item;
  }

  @override
  Future<WardrobeItemData?> updateItem({
    required String itemId,
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
    String? fit,
    double? fitConfidence,
  }) async => null;

  @override
  Future<bool?> deleteItem({required String itemId}) async => null;

  @override
  Future<WardrobeInsightData?> getInsight() async => null;

  @override
  Future<WearSummary?> getWearSummary() async => null;

  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async => null;

  @override
  Future<WearEventLogResponse?> logEnsembleWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) =>
      logWear(
        itemIds: itemIds,
        wornAt: wornAt,
        idempotencyKey: idempotencyKey,
      );

}

class _FakeLearning implements LearningRepository {
  _FakeLearning({List<WardrobeEntry>? wardrobe, List<String>? prefs})
      : wardrobe = wardrobe ?? const [],
        preferredOccasions = prefs ?? const [];

  @override
  List<WardrobeEntry> wardrobe;

  @override
  List<String> preferredOccasions;

  @override
  FaceProfile? get face => null;

  @override
  String? get styleType => null;

  @override
  List<String> get savedLooks => const [];

  @override
  List<LearningSignal> get signals => const [];

  @override
  int get styleScore => 60;

  @override
  Future<void> load() async {}

  @override
  void addItem(WardrobeEntry item) {}

  @override
  void setFace(FaceProfile face) {}

  @override
  void setStyleType(String styleType) {}

  @override
  void addSavedLook(String title) {}

  @override
  void addPreferredOccasion(String occasion) {}

  @override
  void recordSignal(String type, String label) {}

  @override
  void updateItem(String itemId, WardrobeEntry item) {}
}
