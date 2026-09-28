import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/auth/data/guest_data_migration.dart';
import 'package:fansivibe/features/auth/presentation/post_auth_flow.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Minimal throwing backend: every operation fails. Merge must report
/// failures honestly and never throw into the login flow.
class _ThrowingWardrobeRepo implements WardrobeRepository {
  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async => throw Exception('offline');

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async =>
      throw Exception('offline');

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
    String? fit,
    double? fitConfidence,
  }) async => throw Exception('offline');

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
  }) async => throw Exception('offline');

  @override
  Future<bool?> deleteItem({required String itemId}) async =>
      throw Exception('offline');

  @override
  Future<WardrobeInsightData?> getInsight() async =>
      throw Exception('offline');

  @override
  Future<WearSummary?> getWearSummary() async => throw Exception('offline');

  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async => throw Exception('offline');
}

class _BoxLearning implements LearningRepository {
  _BoxLearning({List<WardrobeEntry>? wardrobe, List<String>? prefs})
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

const _localTee = WardrobeEntry(
  id: 'local-step3-1',
  name: 'Step3 Tee',
  category: 'tops',
  color: 'black',
);

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    AuthSession.resetForTest();
    LearningService.instance.resetForTest();
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    LocalStorage.resetForTest();
    LearningService.instance.resetForTest();
  });

  group('Step 3 req 5 — guest data survives restart', () {
    test('wardrobe, prefs, and guest flag persist across reload', () async {
      final service = LearningService.instance;
      await service.load();
      service.addItem(_localTee);
      service.addPreferredOccasion('casual');
      LocalStorage.savedLocally = true;
      // Mutations persist fire-and-forget; flush before killing memory.
      await Future<void>.delayed(const Duration(milliseconds: 250));

      // Simulate process death: drop memory, keep the prefs store.
      service.resetForTest();
      await service.load();

      expect(
        service.wardrobe.any((e) => e.id == 'local-step3-1'),
        isTrue,
      );
      expect(service.preferredOccasions, contains('casual'));
      expect(LocalStorage.savedLocally, isTrue);
    });
  });

  group('Step 3 req 9 — merge never blocks login', () {
    test('all-throwing collaborators report failures without throwing',
        () async {
      final learning = _BoxLearning(
        wardrobe: [_localTee],
        prefs: ['casual'],
      );
      Future<PreferenceSyncResult> sync({required String code}) async =>
          throw Exception('down');
      final result = await GuestDataMigration(
        wardrobeRepo: _ThrowingWardrobeRepo(),
        syncPreference: sync,
        learning: learning,
      ).migrate();

      expect(result.failedItemNames, ['Step3 Tee']);
      expect(result.prefsFailed, ['casual']);
      expect(result.movedAnything, isFalse);
      // Locals preserved for retry; ledgers untouched.
      expect(learning.wardrobe, hasLength(1));
      expect(LocalStorage.migratedGuestIds, isEmpty);
      expect(LocalStorage.migratedGuestPrefs, isEmpty);
    });
  });

  group('Step 3 req 13 — completed merge is not repeated', () {
    test('synced prefs are ledgered and skipped on the next run', () async {
      var calls = 0;
      Future<PreferenceSyncResult> sync({required String code}) async {
        calls++;
        return PreferenceSyncResult.synced;
      }

      GuestDataMigration make() => GuestDataMigration(
        wardrobeRepo: _ThrowingWardrobeRepo(),
        syncPreference: sync,
        learning: _BoxLearning(prefs: ['casual']),
      );

      final first = await make().migrate();
      expect(first.prefsSynced, ['casual']);
      expect(LocalStorage.migratedGuestPrefs, ['casual']);

      final second = await make().migrate();
      expect(second.prefsSynced, isEmpty);
      expect(second.prefsFailed, isEmpty);
      expect(calls, 1);
    });

    test('failed prefs stay unledgered and are retried', () async {
      var calls = 0;
      Future<PreferenceSyncResult> sync({required String code}) async {
        calls++;
        return calls == 1
            ? PreferenceSyncResult.networkError
            : PreferenceSyncResult.synced;
      }

      GuestDataMigration make() => GuestDataMigration(
        wardrobeRepo: _ThrowingWardrobeRepo(),
        syncPreference: sync,
        learning: _BoxLearning(prefs: ['formal']),
      );

      final first = await make().migrate();
      expect(first.prefsFailed, ['formal']);
      expect(LocalStorage.migratedGuestPrefs, isEmpty);

      final second = await make().migrate();
      expect(second.prefsSynced, ['formal']);
      expect(calls, 2);
    });
  });

  group('Step 3 req 4 — account-only action opens sign-in', () {
    testWidgets('guest prompt routes to the sign-in screen', (
      WidgetTester tester,
    ) async {
      LocalStorage.savedLocally = true;
      final router = GoRouter(
        initialLocation: '/start',
        routes: [
          GoRoute(
            path: '/start',
            builder: (context, state) => Scaffold(
              body: TextButton(
                onPressed: () => promptGuestSignIn(context),
                child: const Text('locked-action'),
              ),
            ),
          ),
          GoRoute(
            path: '/sign-in',
            name: RouteNames.signIn,
            builder: (context, state) =>
                const Scaffold(body: Text('sign-in-marker')),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();
      await tester.tap(find.text('locked-action'));
      await tester.pumpAndSettle();
      expect(find.text('sign-in-marker'), findsOneWidget);
    });
  });

  group('Step 3 req 10/11/12 — keep and discard flow', () {
    Future<void> seedGuest() async {
      final service = LearningService.instance;
      await service.load();
      service.addItem(
        const WardrobeEntry(
          id: 'local-keep-1',
          name: 'Keep Tee',
          category: 'tops',
          color: 'black',
        ),
      );
      service.addPreferredOccasion('casual');
    }

    Widget harness() {
      return MaterialApp.router(
        routerConfig: GoRouter(
          initialLocation: '/start',
          routes: [
            GoRoute(
              path: '/start',
              builder: (context, state) => Scaffold(
                body: TextButton(
                  key: const Key('convert'),
                  onPressed: () => handlePostAuthConversion(context),
                  child: const Text('convert'),
                ),
              ),
            ),
            GoRoute(
              path: '/home',
              builder: (context, state) =>
                  const Scaffold(body: Text('home-marker')),
            ),
          ],
        ),
      );
    }

    testWidgets('keep uploads nothing, lands home, data intact', (
      WidgetTester tester,
    ) async {
      await seedGuest();
      await tester.pumpWidget(harness());
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('convert')));
      await tester.pumpAndSettle();

      expect(find.textContaining('saved on this device'), findsOneWidget);
      await tester.tap(find.text('Keep on this device'));
      await tester.pumpAndSettle();

      expect(find.text('home-marker'), findsOneWidget);
      final service = LearningService.instance;
      expect(service.wardrobe.any((e) => e.id == 'local-keep-1'), isTrue);
      expect(service.preferredOccasions, contains('casual'));
    });

    testWidgets('discard confirms, then clears only guest data', (
      WidgetTester tester,
    ) async {
      await seedGuest();
      LocalStorage.migratedGuestPrefs = ['casual'];
      await tester.pumpWidget(harness());
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('convert')));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Discard from this device'));
      await tester.pumpAndSettle();
      expect(find.text('Discard device data?'), findsOneWidget);
      await tester.tap(find.text('Discard'));
      await tester.pumpAndSettle();

      expect(find.text('home-marker'), findsOneWidget);
      final service = LearningService.instance;
      expect(
        service.wardrobe.any((e) => e.id.startsWith('local-')),
        isFalse,
      );
      expect(service.preferredOccasions, isEmpty);
      // Seeded on-device catalog untouched; prefs ledger reset.
      expect(service.wardrobe, isNotEmpty);
      expect(LocalStorage.migratedGuestPrefs, isEmpty);
    });
  });
}
