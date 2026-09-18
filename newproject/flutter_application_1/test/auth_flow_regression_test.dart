import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/router/auth_guard.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_client.dart';
import 'package:fansivibe/features/hairstyle/domain/hairstyle_service.dart';
import 'package:fansivibe/features/home/presentation/home_screen.dart';
import 'package:fansivibe/features/home/data/today_look_models.dart';
import 'package:fansivibe/features/home/data/today_look_repository.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_models.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_repository.dart';
import 'package:fansivibe/features/outfit_builder/presentation/outfit_generation_screen.dart';
import 'package:fansivibe/features/outfit_scan/data/outfit_scan_client.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_analysis_screen.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_processing_screen.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Regression coverage for the authenticated user-flow fixes:
/// login → home → explore without scanning, failed analysis staying
/// inside the shell, real-result rendering, GoRouter-only navigation,
/// scoped 401 expiry, and no mock home for authenticated users.

class _FixedSummaryRepository implements LearningSummaryRepository {
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

class _EmptyTodayLookRepository implements TodayLookRepository {
  @override
  Future<TodayLookResult> getTodayLook() async =>
      const TodayLookResult.failure(TodayLookFailure.unknown);

  @override
  Future<TodayLookResult> regenerateTodayLook({String? seed}) async =>
      const TodayLookResult.failure(TodayLookFailure.unknown);

  @override
  Future<SavedTodayLook?> saveTodayLook({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async => null;
}

class _NullInsightRepository implements WardrobeRepository {
  @override
  Future<WardrobeInsightData?> getInsight() async => null;

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async => const [];

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
  }) => throw UnimplementedError();

  @override
  Future<WardrobeItemData?> updateItem({
    required String itemId,
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
  }) => throw UnimplementedError();

  @override
  Future<bool?> deleteItem({required String itemId}) =>
      throw UnimplementedError();

  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) => throw UnimplementedError();

  @override
  Future<WearSummary?> getWearSummary() => throw UnimplementedError();
}

Future<void> _initStorage() async {
  SharedPreferences.setMockInitialValues({});
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
}

class _NoneAvailableOutfitRepository implements OutfitBuilderRepository {
  @override
  Future<OutfitResult> generateOutfit({
    required String occasion,
    required String mood,
    required String fit,
    required String colorPalette,
    String? seed,
  }) async =>
      const OutfitResult.noneAvailable();

  @override
  Future<SavedOutfit?> saveOutfit({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async =>
      null;
}

void main() {
  setUp(() async {
    await _initStorage();
    AuthSession.resetForTest();
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    LocalStorage.resetForTest();
  });

  group('authenticated navigation needs no scan', () {
    test('login → home → explore/discover/stylist stays in shell', () {
      for (final location in [
        '/home',
        '/discover',
        '/stylist',
        '/stylist/scan-outfit',
        '/wardrobe',
        '/profile',
      ]) {
        expect(
          authRedirect(location, isAuthenticated: true),
          isNull,
          reason: location,
        );
      }
    });

    testWidgets('authenticated home ignores onboarding extra (no mock home)',
        (WidgetTester tester) async {
      await AuthSession.saveSession('regression-session-token');
      await tester.pumpWidget(
        MaterialApp(
          home: HomeScreen(
            onboardingData: const {
              'onboarding_complete': true,
              'display_name': 'Test',
            },
            summaryRepository: _FixedSummaryRepository(),
            todayLookRepository: _EmptyTodayLookRepository(),
            wardrobeRepository: _NullInsightRepository(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Real shell, never the first-time mock branch.
      expect(find.text('Refined Minimalist'), findsNothing);
      expect(find.text('Modern Minimalist'), findsNothing);
      expect(find.text("Today's Look"), findsOneWidget);
    });
  });

  group('outfit processing failures stay in the shell', () {
    testWidgets('failed run shows retry, never entry', (
      WidgetTester tester,
    ) async {
      final client = OutfitScanClient(
        client: MockClient((request) async {
          if (request.url.path.endsWith('/runs/failed-run')) {
            return http.Response(
              '{"status":"failed","error":"analyzer_unavailable"}',
              200,
            );
          }
          return http.Response('{}', 404);
        }),
      );
      final router = GoRouter(
        initialLocation: '/processing',
        routes: [
          GoRoute(
            path: '/entry',
            name: RouteNames.entry,
            builder: (_, __) =>
                const Scaffold(body: Center(child: Text('ENTRY'))),
          ),
          GoRoute(
            path: '/processing',
            builder: (_, __) => OutfitProcessingScreen(
              runId: 'failed-run',
              client: client,
            ),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      expect(find.text('ENTRY'), findsNothing);
      expect(find.text('Back to Scan'), findsWidgets);
    });
  });

  group('outfit analysis shows the real API result', () {
    testWidgets('face-only backend payload renders verbatim', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: const OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {'faceShape': 'oval'},
              'confidence': 0.62,
              'needs_more_data': true,
            },
          ),
        ),
      );

      expect(find.text('Outfit Analysis'), findsOneWidget);
      expect(find.text('Face Shape: oval'), findsOneWidget);
      // Empty vision fields are honest, never invented.
      expect(find.textContaining('Not detected'), findsWidgets);
    });

    testWidgets('See Recommendations uses GoRouter', (
      WidgetTester tester,
    ) async {
      final router = GoRouter(
        initialLocation: '/analysis',
        routes: [
          GoRoute(
            path: '/analysis',
            name: RouteNames.scanAnalysis,
            builder: (_, __) => const OutfitAnalysisScreen(
              analysisResult: {
                'appearance': {'faceShape': 'oval'},
                'confidence': 0.62,
              },
            ),
          ),
          GoRoute(
            path: '/home/daily-outfit',
            name: RouteNames.dailyOutfit,
            builder: (_, __) =>
                const Scaffold(body: Center(child: Text('DAILY OUTFIT'))),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('See Recommendations'));
      await tester.tap(find.text('See Recommendations'));
      await tester.pumpAndSettle();

      expect(find.text('DAILY OUTFIT'), findsOneWidget);
    });
  });

  group('scoped 401 session expiry', () {
    test('no session → no expiry navigation', () {
      var calls = 0;
      AuthSession.onSessionExpired = () => calls++;
      expect(AuthSession.isAuthenticated, isFalse);

      AuthSession.notifyUnauthorized();

      expect(calls, 0);
      expect(AuthSession.isAuthenticated, isFalse);
    });

    test('stale session → clears once and navigates to entry', () async {
      await AuthSession.saveSession('stale-token');
      var calls = 0;
      AuthSession.onSessionExpired = () => calls++;

      AuthSession.notifyUnauthorized();
      AuthSession.notifyUnauthorized();

      expect(AuthSession.token, isNull);
      expect(calls, 1);
    });
  });

  group('completed run envelope resolves to the real snapshot', () {
    testWidgets('analysis shows the backend faceShape, not Not detected', (
      WidgetTester tester,
    ) async {
      final client = OutfitScanClient(
        client: MockClient((request) async {
          return http.Response(
            '{"run_id":"r1","run_type":"outfit","status":"completed",'
            '"result":{"appearance":{"faceShape":"oval","skinTone":"",'
            '"bodyType":"","styleType":""},"confidence":0.62,'
            '"needs_more_data":true,'
            '"recommendations":{"top":{"id":"t","name":"Real Top",'
            '"description":"d","matchScore":0.9,"reasons":[],'
            '"stylingTips":"","maintenance":"","bestFor":""},'
            '"alternatives":[]}}}',
            200,
          );
        }),
      );
      final router = GoRouter(
        initialLocation: '/processing',
        routes: [
          GoRoute(
            path: '/processing',
            builder: (_, __) => OutfitProcessingScreen(
              runId: 'r1',
              client: client,
            ),
            routes: [
              GoRoute(
                path: 'analysis',
                name: RouteNames.scanAnalysis,
                builder: (_, state) => OutfitAnalysisScreen(
                  analysisResult: state.extra as Map<String, dynamic>?,
                ),
              ),
            ],
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      expect(find.text('Face Shape: oval'), findsOneWidget);
      expect(find.text('Confidence: 62%'), findsOneWidget);
      expect(find.text('Real Top'), findsOneWidget);
      expect(find.text('Face Shape: Not detected'), findsNothing);
    });
  });

  group('recommendation empty state is actionable', () {
    testWidgets('no candidate offers wardrobe, prefs, and retry', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitGenerationScreen(
            occasion: 'office',
            mood: 'classic',
            fit: 'tailored',
            colorPalette: 'warm',
            outfitRepository: _NoneAvailableOutfitRepository(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('No matching outfit'), findsOneWidget);
      expect(find.text('Add wardrobe items'), findsOneWidget);
      expect(find.text('Change preferences'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);
    });
  });

  group('multi-angle analysis aggregates real backend votes', () {
    test('majority faceShape wins from three real runs', () async {
      var submits = 0;
      String shapeFor(String runId) =>
          runId == 'run-3' ? 'round' : 'oval';
      final client = HairstyleClient(
        client: MockClient((request) async {
          if (request.method == 'POST') {
            submits++;
            return http.Response('{"run_id":"run-$submits"}', 202);
          }
          final runId = request.url.pathSegments.last;
          final shape = shapeFor(runId);
          return http.Response(
            '{"run_id":"$runId","run_type":"hairstyle","status":"completed",'
            '"result":{"appearance":{"faceShape":"$shape"},'
            '"confidence":0.8,"needs_more_data":true,'
            '"recommendations":{"top":{"id":"t","name":"$shape top",'
            '"description":"d","matchScore":0.9,"reasons":[],'
            '"stylingTips":"","maintenance":"","bestFor":""},'
            '"alternatives":[]}}}',
            200,
          );
        }),
        pollInterval: const Duration(milliseconds: 1),
      );
      final service = HairstyleService(client: client);
      addTearDown(service.dispose);

      final result = await service.runMultiAngleAnalysis(
        frontBytes: Uint8List.fromList(const [1]),
        leftBytes: Uint8List.fromList(const [2]),
        rightBytes: Uint8List.fromList(const [3]),
      );

      expect(submits, 3);
      expect(result, isNotNull);
      expect(result!.faceShape, 'oval');
      expect(service.isMockResult, isFalse);
      expect(service.analysisError, isNull);
    });

    test('disagreeing views are an explicit failure, never a guess',
        () async {
      var submits = 0;
      const shapes = ['oval', 'round', 'square'];
      final client = HairstyleClient(
        client: MockClient((request) async {
          if (request.method == 'POST') {
            submits++;
            return http.Response('{"run_id":"run-$submits"}', 202);
          }
          final shape = shapes[int.parse(request.url.pathSegments.last.split('-').last) - 1];
          return http.Response(
            '{"run_id":"x","run_type":"hairstyle","status":"completed",'
            '"result":{"appearance":{"faceShape":"$shape"},'
            '"confidence":0.8,"needs_more_data":true,'
            '"recommendations":{"top":{"id":"t","name":"t",'
            '"description":"d","matchScore":0.9,"reasons":[],'
            '"stylingTips":"","maintenance":"","bestFor":""},'
            '"alternatives":[]}}}',
            200,
          );
        }),
        pollInterval: const Duration(milliseconds: 1),
      );
      final service = HairstyleService(client: client);
      addTearDown(service.dispose);

      final result = await service.runMultiAngleAnalysis(
        frontBytes: Uint8List.fromList(const [1]),
        leftBytes: Uint8List.fromList(const [2]),
        rightBytes: Uint8List.fromList(const [3]),
      );

      expect(result, isNull);
      expect(service.analysisError, isNotNull);
    });
  });
}
