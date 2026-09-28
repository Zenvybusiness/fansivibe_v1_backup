import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/auth/data/auth_client.dart';
import 'package:fansivibe/features/auth/data/guest_data_migration.dart';
import 'package:fansivibe/features/auth/presentation/post_auth_flow.dart';
import 'package:fansivibe/features/grooming/data/grooming_client.dart';
import 'package:fansivibe/features/grooming/data/grooming_models.dart';
import 'package:fansivibe/features/grooming/data/grooming_service.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_input_screen.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_processing_screen.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_result_screen.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/your_analysis_screen.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/pending_auth_intent.dart';

/// Fake backend wardrobe: records creates, mints server UUIDs.
class _FakeWardrobeRepo implements WardrobeRepository {
  final List<WardrobeItemData> server = [];
  final List<String> createdNames = [];
  final List<String> favoritedIds = [];
  final Set<String> failNames;
  bool throwOnList = false;

  _FakeWardrobeRepo({this.failNames = const {}});

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
    if (failNames.contains(name)) return null;
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
  }) async {
    if (isFavorite == true) favoritedIds.add(itemId);
    return null;
  }

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
  }) async =>
      null;
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

WardrobeEntry _local(String id, String name, {bool fav = false}) =>
    WardrobeEntry(
      id: id,
      name: name,
      category: 'tops',
      color: 'black',
      isFavorite: fav,
    );

PendingAuthIntent _intent(String route, {String action = 'save'}) =>
    PendingAuthIntent(
      action: action,
      route: route,
      createdAt: DateTime.now(),
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

  group('guest detection', () {
    test('guest = no session + savedLocally; auth flips it false', () async {
      LocalStorage.savedLocally = true;
      expect(isGuestUser, isTrue);
      await AuthSession.saveSession('token-1');
      expect(isGuestUser, isFalse);
      await AuthSession.clearSession();
      expect(isGuestUser, isTrue);
    });

    test('no token and no guest flag is neither guest nor authed', () {
      expect(isGuestUser, isFalse);
      expect(AuthSession.isAuthenticated, isFalse);
    });
  });

  group('PendingAuthIntent', () {
    test('round-trips through JSON', () {
      final intent = PendingAuthIntent(
        action: 'save',
        route: '/stylist',
        params: const {'a': 'b'},
        createdAt: DateTime(2026, 1, 2, 3, 4, 5),
      );
      final back = PendingAuthIntent.fromJson(
        jsonDecode(jsonEncode(intent.toJson())) as Map<String, dynamic>,
      );
      expect(back, isNotNull);
      expect(back!.action, 'save');
      expect(back.route, '/stylist');
      expect(back.params, {'a': 'b'});
    });

    test('persists and consumes exactly once', () {
      recordPendingAuthIntent(_intent('/wardrobe'));
      expect(takePendingAuthIntent()?.route, '/wardrobe');
      expect(takePendingAuthIntent(), isNull);
    });

    test('malformed slot fails closed and is cleared', () {
      LocalStorage.pendingAuthIntent = '(((not-json';
      expect(takePendingAuthIntent(), isNull);
      expect(LocalStorage.pendingAuthIntent, isNull);
      LocalStorage.pendingAuthIntent = jsonEncode({'route': '/x'});
      expect(takePendingAuthIntent(), isNull);
    });

    test('expired intent is treated as absent', () {
      recordPendingAuthIntent(
        PendingAuthIntent(
          action: 'save',
          route: '/stylist',
          createdAt: DateTime.now().subtract(const Duration(hours: 25)),
        ),
      );
      expect(takePendingAuthIntent(), isNull);
    });
  });

  group('resolvePostAuthDestination', () {
    test('null intent falls back to /home', () {
      expect(resolvePostAuthDestination(null), '/home');
    });

    test('safe roots pass through', () {
      expect(resolvePostAuthDestination(_intent('/stylist')), '/stylist');
      expect(
        resolvePostAuthDestination(_intent('/wardrobe')),
        '/wardrobe',
      );
    });

    test('extra-dependent routes walk up to the safe parent', () {
      expect(
        resolvePostAuthDestination(_intent('/discover/look-details')),
        '/discover',
      );
      expect(
        resolvePostAuthDestination(
          _intent('/stylist/build-outfit/generation'),
        ),
        '/stylist/build-outfit',
      );
      expect(
        resolvePostAuthDestination(_intent('/wardrobe/add-item')),
        '/wardrobe',
      );
      expect(
        resolvePostAuthDestination(_intent('/stylist/hairstyle/processing')),
        '/stylist/hairstyle',
      );
    });

    test('auth screens and garbage fall back to /home', () {
      expect(resolvePostAuthDestination(_intent('/sign-in')), '/home');
      expect(
        resolvePostAuthDestination(_intent('/create-account')),
        '/home',
      );
      expect(resolvePostAuthDestination(_intent('http://evil')), '/home');
      expect(resolvePostAuthDestination(_intent('nope')), '/home');
    });
  });

  group('GuestDataMigration', () {
    test('uploads local-* items with server-minted ids, never local ids',
        () async {
      final repo = _FakeWardrobeRepo();
      final learning = _FakeLearning(
        wardrobe: [_local('local-1', 'Tee'), _local('local-2', 'Jeans')],
      );
      final migration = GuestDataMigration(
        wardrobeRepo: repo,
        syncPreference: ({required String code}) async =>
            PreferenceSyncResult.synced,
        learning: learning,
      );
      final result = await migration.migrate();
      expect(result.failedItemNames, isEmpty);
      expect(result.migratedLocalIds, ['local-1', 'local-2']);
      expect(repo.createdNames, ['Tee', 'Jeans']);
      // Server ids minted; local ids only in the ledger.
      expect(
        repo.server.every((e) => !e.id.startsWith('local-')),
        isTrue,
      );
      expect(LocalStorage.migratedGuestIds, ['local-1', 'local-2']);
      // Migration never mutates local state (caller removes on choice).
      expect(learning.wardrobe, hasLength(2));
    });

    test('skips already-present content and backend-owned ids', () async {
      final repo = _FakeWardrobeRepo();
      repo.server.add(
        const WardrobeItemData(
          id: 'server-0',
          name: 'Tee',
          category: 'tops',
          color: 'black',
        ),
      );
      final learning = _FakeLearning(
        wardrobe: [
          _local('local-1', 'Tee'),
          const WardrobeEntry(
            id: 'server-0',
            name: 'Tee',
            category: 'tops',
            color: 'black',
          ),
        ],
      );
      final result = await GuestDataMigration(
        wardrobeRepo: repo,
        syncPreference: ({required String code}) async =>
            PreferenceSyncResult.synced,
        learning: learning,
      ).migrate();
      expect(result.migratedItemNames, isEmpty);
      expect(result.skippedItemNames, ['Tee']);
      expect(repo.createdNames, isEmpty);
    });

    test('favorite rides updateItem; failure records honestly', () async {
      final repo = _FakeWardrobeRepo(failNames: {'Bad'});
      final learning = _FakeLearning(
        wardrobe: [_local('local-1', 'Good', fav: true), _local('local-2', 'Bad')],
        prefs: ['casual', 'formal'],
      );
      Future<PreferenceSyncResult> sync({required String code}) async =>
          code == 'casual'
              ? PreferenceSyncResult.alreadySynced
              : PreferenceSyncResult.networkError;
      final result = await GuestDataMigration(
        wardrobeRepo: repo,
        syncPreference: sync,
        learning: learning,
      ).migrate();
      expect(result.migratedItemNames, ['Good']);
      expect(result.failedItemNames, ['Bad']);
      expect(result.hasFailures, isTrue);
      expect(repo.favoritedIds, hasLength(1));
      expect(result.prefsSynced, ['casual']);
      expect(result.prefsFailed, ['formal']);
      // Ledger holds only the success: retry duplicates nothing.
      expect(LocalStorage.migratedGuestIds, ['local-1']);
      final again = await GuestDataMigration(
        wardrobeRepo: repo,
        syncPreference: sync,
        learning: learning,
      ).migrate();
      expect(
        repo.createdNames.where((n) => n == 'Good'),
        hasLength(1),
      );
      expect(again.failedItemNames, ['Bad']);
    });

    test('list failure still attempts creates (ledger guards retries)',
        () async {
      final repo = _FakeWardrobeRepo()..throwOnList = true;
      final learning = _FakeLearning(
        wardrobe: [_local('local-9', 'Hat')],
      );
      final result = await GuestDataMigration(
        wardrobeRepo: repo,
        syncPreference: ({required String code}) async =>
            PreferenceSyncResult.synced,
        learning: learning,
      ).migrate();
      expect(result.migratedItemNames, ['Hat']);
    });
  });

  group('LearningService local cleanup', () {
    test('removeLocalItems drops only device ids; clears prefs', () async {
      final service = LearningService.instance;
      await service.load();
      service.addItem(_local('local-x', 'Temp'));
      service.addPreferredOccasion('casual');
      expect(
        service.wardrobe.any((e) => e.id == 'local-x'),
        isTrue,
      );
      service.removeLocalItems({'local-x', 'server-zzz'});
      expect(service.wardrobe.any((e) => e.id == 'local-x'), isFalse);
      service.clearPreferredOccasions();
      expect(service.preferredOccasions, isEmpty);
      service.removeLocalItems(const {});
    });
  });

  group('merge dialog', () {
    testWidgets('shows counts and returns the tapped choice', (
      WidgetTester tester,
    ) async {
      GuestDataChoice? tapped;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => TextButton(
              onPressed: () async {
                tapped = await showGuestMergeDialog(
                  context,
                  itemCount: 2,
                  prefCount: 1,
                );
              },
              child: const Text('open'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      expect(find.textContaining('2 wardrobe items'), findsOneWidget);
      expect(find.textContaining('1 preference'), findsOneWidget);
      await tester.tap(find.text('Keep on this device'));
      await tester.pumpAndSettle();
      expect(tapped, GuestDataChoice.keep);
    });

    testWidgets('discard requires explicit confirmation', (
      WidgetTester tester,
    ) async {
      GuestDataChoice? tapped;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => TextButton(
              onPressed: () async {
                tapped = await showGuestMergeDialog(
                  context,
                  itemCount: 1,
                  prefCount: 0,
                );
                if (tapped == GuestDataChoice.discard && context.mounted) {
                  final confirmed = await showGuestDiscardConfirm(
                    context,
                    itemCount: 1,
                    prefCount: 0,
                  );
                  if (!confirmed) tapped = GuestDataChoice.keep;
                }
              },
              child: const Text('open'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Discard from this device'));
      await tester.pumpAndSettle();
      // Confirm step appears; cancel keeps data.
      expect(find.text('Discard device data?'), findsOneWidget);
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(tapped, GuestDataChoice.keep);
    });
  });

  group('grooming guest gate', () {
    // D-01: guests analyze first (ephemeral, no sign-in); authentication
    // is required only at the account-owned Save point on the result.
    testWidgets('guest Analyze reaches the result; Save prompts sign-in', (
      WidgetTester tester,
    ) async {
      LocalStorage.savedLocally = true;
      final snapshot = {
        'appearance': {
          'faceShape': 'oval',
          'skinTone': '',
          'bodyType': '',
          'styleType': '',
          'sourceRunId': 'ephemeral-test-id',
        },
        'confidence': 0.88,
        'needs_more_data': true,
        'recommendations': {
          'top': {
            'id': 'structured_goatee',
            'name': 'Structured Goatee',
            'description': 'A test recommendation.',
            'matchScore': 0.92,
            'reasons': ['Grounded reason'],
            'stylingTips': 'Tips',
            'maintenance': 'Medium',
            'bestFor': 'Oval',
          },
          'alternatives': [],
        },
      };
      final service = GroomingService(
        client: GroomingClient(
          client: MockClient((request) async {
            expect(request.url.path, '/v1/analysis/grooming/ephemeral');
            expect(request.headers['Authorization'], isNull);
            return http.Response(jsonEncode(snapshot), 200);
          }),
        ),
      );
      final router = GoRouter(
        initialLocation: '/grooming',
        routes: [
          GoRoute(
            path: '/grooming',
            builder: (context, state) => const GroomingInputScreen(),
            routes: [
              GoRoute(
                path: 'processing',
                name: RouteNames.groomingProcessing,
                builder: (context, state) {
                  final data = state.extra as Map<String, String>;
                  return GroomingProcessingScreen(
                    service: service,
                    faceShape: data['faceShape']!,
                    beardStyle: data['beardStyle']!,
                    beardDensity: data['beardDensity']!,
                    beardColor: data['beardColor']!,
                  );
                },
                routes: [
                  GoRoute(
                    path: 'result',
                    name: RouteNames.groomingResult,
                    builder: (context, state) {
                      final extra = state.extra;
                      final result = extra is GroomingAnalysisResult
                          ? extra
                          : null;
                      return GroomingResultScreen(
                        faceShape: result?.faceShape ?? '',
                        beardStyle: result?.beardStyle ?? '',
                        beardDensity: result?.beardDensity ?? '',
                        beardColor: result?.beardColor ?? '',
                        result: result,
                      );
                    },
                  ),
                ],
              ),
            ],
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
      for (final label in ['Oval', 'Full Beard', 'Light', 'Dark Brown']) {
        await tester.scrollUntilVisible(find.text(label), 300);
        await tester.pumpAndSettle();
        await tester.tap(find.text(label));
        await tester.pump();
      }
      await tester.scrollUntilVisible(find.text('Analyze Style'), 300);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Analyze Style'));
      await tester.pumpAndSettle();
      // 1+2. Guest reaches the analysis result without a sign-in gate.
      expect(find.text('Structured Goatee'), findsOneWidget);
      expect(find.text('sign-in-marker'), findsNothing);
      // 3. The account-owned Save point still requires authentication.
      await tester.scrollUntilVisible(find.text('Save Look'), 300);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save Look'));
      await tester.pumpAndSettle();
      expect(find.text('sign-in-marker'), findsOneWidget);
      expect(takePendingAuthIntent(), isNotNull);
    });
  });

  group('Save My Progress conversion', () {
    testWidgets('records a save_progress intent before account creation', (
      WidgetTester tester,
    ) async {
      final router = GoRouter(
        initialLocation: '/your-analysis',
        routes: [
          GoRoute(
            path: '/your-analysis',
            builder: (context, state) => const YourAnalysisScreen(),
          ),
          GoRoute(
            path: '/create-account',
            name: RouteNames.createAccount,
            builder: (context, state) =>
                const Scaffold(body: Text('create-account-marker')),
          ),
          GoRoute(
            path: '/photo-capture',
            name: RouteNames.photoCapture,
            builder: (context, state) =>
                const Scaffold(body: Text('capture-marker')),
          ),
          GoRoute(
            path: '/stylist',
            name: RouteNames.stylist,
            builder: (context, state) =>
                const Scaffold(body: Text('stylist-marker')),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();
      final finder = find.text('Save My Progress');
      await tester.scrollUntilVisible(finder, 300);
      await tester.pumpAndSettle();
      await tester.tap(finder);
      await tester.pumpAndSettle();
      expect(find.text('create-account-marker'), findsOneWidget);
      final intent = takePendingAuthIntent();
      expect(intent?.action, 'save_progress');
      expect(intent?.route, '/home');
    });
  });

  group('logout hygiene (unchanged)', () {
    test('logout clears the session even when the server is gone', () async {
      final client = AuthClient(
        client: MockClient((request) async => http.Response('x', 401)),
      );
      await AuthSession.saveSession('dead-token');
      LocalStorage.savedLocally = true;
      final status = await client.logout();
      expect(status.name, 'signedOut');
      expect(AuthSession.isAuthenticated, isFalse);
      // Guest flags intentionally untouched (reported, not changed).
      expect(LocalStorage.savedLocally, isTrue);
    });
  });
}
