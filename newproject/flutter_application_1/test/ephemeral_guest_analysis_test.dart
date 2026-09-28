import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/grooming/data/grooming_client.dart';
import 'package:fansivibe/features/grooming/data/grooming_models.dart';
import 'package:fansivibe/features/grooming/data/grooming_service.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_input_screen.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_processing_screen.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_result_screen.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_client.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/domain/hairstyle_service.dart';
import 'package:fansivibe/features/hairstyle/presentation/face_processing_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/hairstyle_result_screen.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/outfit_scan/data/outfit_scan_client.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_analysis_screen.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_scan_screen.dart';
import 'package:fansivibe/features/wardrobe/data/garment_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show AddItemConfig;
import 'package:fansivibe/features/wardrobe/presentation/add_wardrobe_item_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/pending_auth_intent.dart';

import 'support/controllable_hairstyle_service.dart';

/// D-01 STEP 2: guest ephemeral analysis integration.
///
/// Guests analyze through the unauthenticated `/ephemeral` endpoints and
/// reach results; account-owned persistence still gates on sign-in via the
/// existing `promptGuestSignIn` + `PendingAuthIntent` continuation.
/// Authenticated transport is asserted unchanged throughout.

/// 1x1 transparent PNG (valid `Image.memory` bytes in widget tests).
Uint8List _png() => base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
);

Map<String, dynamic> _hairstyleSnapshot() => {
  'appearance': {
    'faceShape': 'Oval',
    'skinTone': 'Warm Medium',
    'bodyType': '',
    'styleType': 'Modern Classic',
    'sourceRunId': 'ephemeral-test-id',
  },
  'confidence': 0.9,
  'needs_more_data': false,
  'recommendations': {
    'top': {
      'id': 'textured_quiff',
      'name': 'Textured Quiff',
      'description': 'A test recommendation.',
      'matchScore': 0.94,
      'reasons': ['Grounded reason'],
      'stylingTips': 'Tips',
      'maintenance': 'Low',
      'bestFor': 'Oval',
    },
    'alternatives': [],
  },
};

Map<String, dynamic> _groomingSnapshot() => {
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

Map<String, dynamic> _garmentSnapshot() => {
  'category': 'tops',
  'subcategory': 'T-Shirt',
  'color': 'Black',
  'pattern': 'solid',
  'material': 'Cotton',
  'style': 'casual',
  'fit': 'regular',
  'confidence': 0.84,
  'needs_review': false,
  'sourceRunId': 'ephemeral-test-id',
};

Future<void> _initPrefs() async {
  SharedPreferences.setMockInitialValues({});
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
  AuthSession.resetForTest();
}

void _asGuest() {
  LocalStorage.savedLocally = true;
}

void _asAuthenticated() {
  LocalStorage.savedLocally = false;
  LocalStorage.authToken = 'test-token';
}

Future<void> _tapVisible(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
  await tester.tap(finder);
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
}

void main() {
  setUp(() async {
    await _initPrefs();
  });

  tearDown(() {
    AuthSession.resetForTest();
    LocalStorage.resetForTest();
    LearningService.instance.resetForTest();
  });

  group('ephemeral client transport', () {
    test('hairstyle ephemeral posts without auth and parses the snapshot',
        () async {
      String? seenAuth;
      String? seenPath;
      final client = HairstyleClient(
        client: MockClient((request) async {
          seenPath = request.url.path;
          seenAuth = request.headers['Authorization'];
          expect(request.headers.containsKey('Idempotency-Key'), isFalse);
          return http.Response(jsonEncode(_hairstyleSnapshot()), 200);
        }),
      );
      final outcome = await client.submitHairstyleEphemeral(
        imageBytes: _png(),
      );
      expect(seenPath, '/v1/analysis/hairstyle/ephemeral');
      expect(seenAuth, isNull);
      expect(outcome.snapshot?['appearance']?['faceShape'], 'Oval');
      expect(outcome.failureReason, isNull);
    });

    test('hairstyle ephemeral sends no auth even when authenticated',
        () async {
      _asAuthenticated();
      String? seenAuth;
      final client = HairstyleClient(
        client: MockClient((request) async {
          seenAuth = request.headers['Authorization'];
          return http.Response(jsonEncode(_hairstyleSnapshot()), 200);
        }),
      );
      final outcome = await client.submitHairstyleEphemeral(
        imageBytes: _png(),
      );
      expect(seenAuth, isNull);
      expect(outcome.snapshot, isNotNull);
    });

    test('hairstyle ephemeral surfaces the typed 422 reason', () async {
      final client = HairstyleClient(
        client: MockClient(
          (request) async => http.Response(
            jsonEncode({
              'error': {
                'code': 'VALIDATION_ERROR',
                'details': {
                  'field_errors': [
                    {'field': 'image', 'error': 'no_face_detected'},
                  ],
                },
              },
            }),
            422,
          ),
        ),
      );
      final outcome = await client.submitHairstyleEphemeral(
        imageBytes: _png(),
      );
      expect(outcome.snapshot, isNull);
      expect(outcome.failureReason, 'no_face_detected');
    });

    test('authenticated hairstyle submit still sends auth (unchanged)',
        () async {
      String? seenAuth;
      final client = HairstyleClient(
        client: MockClient((request) async {
          seenAuth = request.headers['Authorization'];
          return http.Response('{"run_id": "run-1"}', 202);
        }),
      );
      await client.submitHairstyleAnalysis(imageBytes: _png());
      expect(seenAuth, 'Bearer dev');
    });

    test('outfit ephemeral posts without auth and parses the snapshot',
        () async {
      String? seenPath;
      String? seenAuth;
      final client = OutfitScanClient(
        client: MockClient((request) async {
          seenPath = request.url.path;
          seenAuth = request.headers['Authorization'];
          return http.Response(jsonEncode(_hairstyleSnapshot()), 200);
        }),
      );
      final outcome = await client.submitOutfitEphemeralBytes(_png());
      expect(seenPath, '/v1/analysis/outfit/ephemeral');
      expect(seenAuth, isNull);
      expect(outcome.snapshot?['recommendations']?['top']?['id'],
          'textured_quiff');
    });

    test('grooming ephemeral posts the request profile without auth',
        () async {
      String? seenPath;
      String? seenAuth;
      Map<String, dynamic>? seenBody;
      final client = GroomingClient(
        client: MockClient((request) async {
          seenPath = request.url.path;
          seenAuth = request.headers['Authorization'];
          seenBody = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(jsonEncode(_groomingSnapshot()), 200);
        }),
      );
      final outcome = await client.submitGroomingEphemeral(faceShape: 'oval');
      expect(seenPath, '/v1/analysis/grooming/ephemeral');
      expect(seenAuth, isNull);
      expect(seenBody?['face_shape'], 'oval');
      expect(seenBody?.containsKey('user_id'), isFalse);
      expect(outcome.snapshot?['appearance']?['faceShape'], 'oval');
    });

    test('garment ephemeral posts without auth and parses the observation',
        () async {
      String? seenPath;
      String? seenAuth;
      final client = GarmentClient(
        client: MockClient((request) async {
          seenPath = request.url.path;
          seenAuth = request.headers['Authorization'];
          return http.Response(jsonEncode(_garmentSnapshot()), 200);
        }),
      );
      final outcome = await client.submitGarmentEphemeralBytes(_png());
      expect(seenPath, '/v1/analysis/garment/ephemeral');
      expect(seenAuth, isNull);
      expect(outcome.snapshot?['category'], 'tops');
    });
  });

  group('pending ephemeral result slot', () {
    test('stash strips top-level and nested sourceRunId', () {
      stashPendingEphemeralResult(
        feature: EphemeralFeature.hairstyle,
        snapshot: _hairstyleSnapshot(),
      );
      final raw = LocalStorage.pendingEphemeralResult!;
      expect(raw, isNot(contains('ephemeral-test-id')));
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      expect(decoded['feature'], 'hairstyle');
      expect(
        (decoded['snapshot'] as Map<String, dynamic>)['appearance']?['faceShape'],
        'Oval',
      );
    });

    test('peek round-trips a fresh slot and clear drops it', () {
      stashPendingEphemeralResult(
        feature: EphemeralFeature.grooming,
        snapshot: _groomingSnapshot(),
      );
      final peeked = peekPendingEphemeralResult();
      expect(peeked?.feature, 'grooming');
      expect(peeked?.snapshot['appearance']?['faceShape'], 'oval');
      clearPendingEphemeralResult();
      expect(peekPendingEphemeralResult(), isNull);
    });

    test('expired and malformed slots fail closed', () {
      LocalStorage.pendingEphemeralResult = jsonEncode({
        'feature': 'hairstyle',
        'snapshot': _hairstyleSnapshot(),
        'savedAt': DateTime.now()
            .subtract(const Duration(hours: 25))
            .toIso8601String(),
      });
      expect(peekPendingEphemeralResult(), isNull);
      expect(LocalStorage.pendingEphemeralResult, isNull);

      LocalStorage.pendingEphemeralResult = 'not-json';
      expect(peekPendingEphemeralResult(), isNull);
    });
  });

  group('ephemeral services', () {
    test('hairstyle service resolves the snapshot without polling', () async {
      final service = HairstyleService(
        client: HairstyleClient(
          client: MockClient(
            (request) async =>
                http.Response(jsonEncode(_hairstyleSnapshot()), 200),
          ),
        ),
      );
      final result = await service.runEphemeralAnalysis(imageBytes: _png());
      expect(result.topRecommendation.id, 'textured_quiff');
      expect(service.isMockResult, isFalse);
      expect(service.analysisError, isNull);
      expect(service.lastEphemeralSnapshot?['confidence'], 0.9);
    });

    test('grooming service resolves the request-profile snapshot', () async {
      final service = GroomingService(
        client: GroomingClient(
          client: MockClient(
            (request) async =>
                http.Response(jsonEncode(_groomingSnapshot()), 200),
          ),
        ),
      );
      final result = await service.runEphemeralAnalysis(faceShape: 'oval');
      expect(result.topRecommendation.id, 'structured_goatee');
      expect(service.isMockResult, isFalse);
      expect(service.lastEphemeralSnapshot, isNotNull);
    });
  });

  group('guest hairstyle reaches analysis, not sign-in', () {
    testWidgets('processing runs ephemeral and lands on the result',
        (tester) async {
      _asGuest();
      final service = HairstyleService(
        client: HairstyleClient(
          client: MockClient((request) async {
            expect(request.url.path, '/v1/analysis/hairstyle/ephemeral');
            expect(request.headers['Authorization'], isNull);
            return http.Response(jsonEncode(_hairstyleSnapshot()), 200);
          }),
        ),
      );
      final router = GoRouter(
        initialLocation: '/processing',
        routes: [
          GoRoute(
            path: '/processing',
            builder: (_, __) => FaceProcessingScreen(
              service: service,
              imageBytes: _png(),
            ),
          ),
          GoRoute(
            path: '/result',
            name: RouteNames.hairstyleResult,
            builder: (_, state) => HairstyleResultScreen(
              result: state.extra as HairstyleAnalysisResult?,
            ),
          ),
          GoRoute(
            path: '/sign-in',
            name: RouteNames.signIn,
            builder: (_, __) => const Text('sign-in-marker'),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      expect(find.text('Textured Quiff'), findsOneWidget);
      expect(find.text('sign-in-marker'), findsNothing);
      final stashed = peekPendingEphemeralResult();
      expect(stashed?.feature, 'hairstyle');
      expect(
        jsonEncode(stashed?.snapshot),
        isNot(contains('ephemeral-test-id')),
      );
    });

    testWidgets('authenticated users still take the run-based path',
        (tester) async {
      _asAuthenticated();
      final service = ControllableHairstyleService();
      final router = GoRouter(
        initialLocation: '/processing',
        routes: [
          GoRoute(
            path: '/processing',
            builder: (_, __) => FaceProcessingScreen(
              service: service,
              imageBytes: _png(),
            ),
          ),
          GoRoute(
            path: '/result',
            name: RouteNames.hairstyleResult,
            builder: (_, state) => HairstyleResultScreen(
              result: state.extra as HairstyleAnalysisResult?,
            ),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pump();
      expect(service.started, isTrue);
      service.finish();
      await tester.pumpAndSettle();
      expect(find.text('Textured Quiff'), findsOneWidget);
    });
  });

  group('guest outfit scan reaches analysis, not sign-in', () {
    testWidgets('gallery pick → Analyze lands on the analysis screen',
        (tester) async {
      _asGuest();
      String? seenAuth;
      final client = OutfitScanClient(
        client: MockClient((request) async {
          seenAuth = request.headers['Authorization'];
          return http.Response(jsonEncode(_hairstyleSnapshot()), 200);
        }),
      );
      final router = GoRouter(
        initialLocation: '/scan',
        routes: [
          GoRoute(
            path: '/scan',
            builder: (_, __) => OutfitScanScreen(
              client: client,
              pickImage: (source) async => XFile.fromData(
                _png(),
                name: 'outfit.jpg',
                mimeType: 'image/jpeg',
              ),
            ),
          ),
          GoRoute(
            path: '/analysis',
            name: RouteNames.scanAnalysis,
            builder: (_, state) => OutfitAnalysisScreen(
              analysisResult: state.extra as Map<String, dynamic>?,
            ),
          ),
          GoRoute(
            path: '/sign-in',
            name: RouteNames.signIn,
            builder: (_, __) => const Text('sign-in-marker'),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      // ponytail: bounded pumps — OutfitScanScreen keeps an indeterminate
      // spinner on screen, so pumpAndSettle can never complete here.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      await _tapVisible(tester, find.text('Choose from Gallery'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      await _tapVisible(tester, find.text('Analyze Photo'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(seenAuth, isNull);
      expect(find.text('Outfit Analysis'), findsOneWidget);
      expect(find.text('sign-in-marker'), findsNothing);
      expect(
        peekPendingEphemeralResult()?.feature,
        EphemeralFeature.outfit,
      );
    });
  });

  group('guest grooming reaches analysis, not sign-in', () {
    testWidgets('Beard/Glasses input → processing → result', (tester) async {
      _asGuest();
      final service = GroomingService(
        client: GroomingClient(
          client: MockClient((request) async {
            expect(request.url.path, '/v1/analysis/grooming/ephemeral');
            expect(request.headers['Authorization'], isNull);
            return http.Response(jsonEncode(_groomingSnapshot()), 200);
          }),
        ),
      );
      final router = GoRouter(
        initialLocation: '/grooming',
        routes: [
          GoRoute(
            path: '/grooming',
            builder: (_, __) => const GroomingInputScreen(),
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
                    builder: (_, state) {
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
            builder: (_, __) => const Text('sign-in-marker'),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      // Step 10 verdict: Glasses shares this Beard/Glasses pipeline.
      expect(find.text('Beard / Glasses'), findsOneWidget);
      await _tapVisible(tester, find.text('Oval'));
      await _tapVisible(tester, find.text('Full Beard'));
      await _tapVisible(tester, find.text('Medium'));
      await _tapVisible(tester, find.text('Dark Brown'));
      await _tapVisible(tester, find.text('Analyze Style'));
      await tester.pumpAndSettle();

      expect(find.text('Structured Goatee'), findsOneWidget);
      expect(find.text('sign-in-marker'), findsNothing);
      expect(
        peekPendingEphemeralResult()?.feature,
        EphemeralFeature.grooming,
      );
    });
  });

  group('guest garment reaches analysis, not sign-in', () {
    testWidgets('photo → Analyze prefills without sign-in', (tester) async {
      _asGuest();
      final garments = _EphemeralGarmentClient();
      final category = AddItemConfig.categories.firstWhere(
        (c) => c.id == 'tops',
      );
      final router = GoRouter(
        initialLocation: '/',
        routes: [
          GoRoute(
            path: '/',
            builder: (_, __) => AddWardrobeItemScreen(
              category: category,
              garmentClient: garments,
              photoGalleryPick: (source) async => XFile.fromData(
                _png(),
                name: 'shirt.jpg',
                mimeType: 'image/jpeg',
              ),
            ),
          ),
          GoRoute(
            path: '/sign-in',
            name: RouteNames.signIn,
            builder: (_, __) => const Text('sign-in-marker'),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.text('Take Photo'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Take Photo'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Choose from Gallery').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Use Photo'));
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.text('Analyze Item'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Analyze Item'));
      await tester.pumpAndSettle();

      expect(garments.ephemeralCalls, 1);
      expect(garments.authedCalls, 0);
      expect(
        find.text('AI suggestion — confirmed below, edit if needed'),
        findsOneWidget,
      );
      expect(find.text('sign-in-marker'), findsNothing);
    });
  });

  group('pending result banner restores the stashed snapshot', () {
    testWidgets('scan banner View reopens the analysis, Dismiss clears',
        (tester) async {
      _asGuest();
      stashPendingEphemeralResult(
        feature: EphemeralFeature.outfit,
        snapshot: _hairstyleSnapshot(),
      );
      final router = GoRouter(
        initialLocation: '/scan',
        routes: [
          GoRoute(
            path: '/scan',
            builder: (_, __) => OutfitScanScreen(
              client: OutfitScanClient(
                client: MockClient(
                  (request) async => http.Response('{}', 500),
                ),
              ),
            ),
          ),
          GoRoute(
            path: '/analysis',
            name: RouteNames.scanAnalysis,
            builder: (_, state) => OutfitAnalysisScreen(
              analysisResult: state.extra as Map<String, dynamic>?,
            ),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      // ponytail: bounded pumps — the scan screen spinner never settles.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('Your outfit analysis is saved'), findsOneWidget);
      await _tapVisible(tester, find.text('View Result'));
      // ponytail: bounded pumps — the scan screen spinner never settles.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.text('Outfit Analysis'), findsOneWidget);
      expect(find.text('Textured Quiff'), findsOneWidget);
    });

    testWidgets('scan banner Dismiss drops the slot', (tester) async {
      _asGuest();
      stashPendingEphemeralResult(
        feature: EphemeralFeature.outfit,
        snapshot: _hairstyleSnapshot(),
      );
      final router = GoRouter(
        initialLocation: '/scan',
        routes: [
          GoRoute(
            path: '/scan',
            builder: (_, __) => OutfitScanScreen(
              client: OutfitScanClient(
                client: MockClient(
                  (request) async => http.Response('{}', 500),
                ),
              ),
            ),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      // ponytail: bounded pumps — the scan screen spinner never settles.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      await _tapVisible(tester, find.text('Dismiss'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.text('Your outfit analysis is saved'), findsNothing);
      expect(peekPendingEphemeralResult(), isNull);
    });
  });

  group('guest Save still opens the existing auth flow', () {
    testWidgets('hairstyle Save records intent without saving', (
      tester,
    ) async {
      _asGuest();
      final service = StubSaveHairstyleService();
      final router = GoRouter(
        initialLocation: '/result',
        routes: [
          GoRoute(
            path: '/result',
            builder: (_, __) => HairstyleResultScreen(
              result: HairstyleAnalysisResult.fromRunResult(
                _hairstyleSnapshot(),
              ),
              service: service,
            ),
          ),
          GoRoute(
            path: '/sign-in',
            name: RouteNames.signIn,
            builder: (_, __) => const Text('sign-in-marker'),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Save Style'));
      await tester.pumpAndSettle();

      expect(find.text('sign-in-marker'), findsOneWidget);
      expect(service.saveCalls, 0);
      final intent = takePendingAuthIntent();
      expect(intent, isNotNull);
      expect(intent?.route, '/result');
      expect(
        intent?.action,
        'Sign in to save your hairstyle. Browsing stays free.',
      );
    });

    testWidgets('grooming Save records intent without saving', (
      tester,
    ) async {
      _asGuest();
      final router = GoRouter(
        initialLocation: '/result',
        routes: [
          GoRoute(
            path: '/result',
            builder: (_, __) => GroomingResultScreen(
              faceShape: 'oval',
              beardStyle: 'structured_goatee',
              beardDensity: '',
              beardColor: '',
              result: GroomingAnalysisResult.fromSnapshot(
                _groomingSnapshot(),
              ),
            ),
          ),
          GoRoute(
            path: '/sign-in',
            name: RouteNames.signIn,
            builder: (_, __) => const Text('sign-in-marker'),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Save Look'));
      await tester.pumpAndSettle();

      expect(find.text('sign-in-marker'), findsOneWidget);
      expect(takePendingAuthIntent(), isNotNull);
    });

    testWidgets('outfit Save still prompts without faking persistence',
        (tester) async {
      _asGuest();
      final router = GoRouter(
        initialLocation: '/analysis',
        routes: [
          GoRoute(
            path: '/analysis',
            builder: (_, __) => OutfitAnalysisScreen(
              analysisResult: _hairstyleSnapshot(),
            ),
          ),
          GoRoute(
            path: '/sign-in',
            name: RouteNames.signIn,
            builder: (_, __) => const Text('sign-in-marker'),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Save Profile'));
      await tester.pumpAndSettle();

      expect(find.text('sign-in-marker'), findsOneWidget);
    });

    testWidgets('authenticated hairstyle Save works normally', (
      tester,
    ) async {
      _asAuthenticated();
      final service = StubSaveHairstyleService();
      await tester.pumpWidget(
        MaterialApp(
          home: HairstyleResultScreen(
            result: HairstyleAnalysisResult.fromRunResult(
              _hairstyleSnapshot(),
            ),
            service: service,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Save Style'));
      await tester.pumpAndSettle();

      expect(service.saveCalls, 1);
      expect(service.savedLookIds, ['textured_quiff']);
      expect(find.text('Hairstyle saved to profile'), findsOneWidget);
    });
  });

  group('save payloads never carry a transient run id', () {
    test('hairstyle save snapshot has no sourceRunId', () async {
      String? postedBody;
      final service = HairstyleService(
        client: HairstyleClient(
          client: MockClient((request) async {
            postedBody = request.body;
            return http.Response('{"id": "saved-1"}', 201);
          }),
        ),
      );
      final ok = await service.saveLook(
        recommendation: HairstyleAnalysisResult.fromRunResult(
          _hairstyleSnapshot(),
        ).topRecommendation,
        title: 'Textured Quiff',
      );
      expect(ok, isTrue);
      expect(postedBody, isNotNull);
      expect(postedBody, isNot(contains('sourceRunId')));
      expect(postedBody, isNot(contains('ephemeral-test-id')));
    });

    test('grooming save snapshot has no sourceRunId', () async {
      String? postedBody;
      final service = GroomingService(
        client: GroomingClient(
          client: MockClient((request) async {
            postedBody = request.body;
            return http.Response('{"id": "saved-1"}', 201);
          }),
        ),
      );
      final ok = await service.saveGroomingLook(
        recommendation: GroomingAnalysisResult.fromSnapshot(
          _groomingSnapshot(),
        ).topRecommendation,
        title: 'Structured Goatee',
      );
      expect(ok, isTrue);
      expect(postedBody, isNot(contains('sourceRunId')));
    });
  });
}

/// Garment client fake: ephemeral succeeds, the authenticated submit is
/// never used (proves guests no longer touch the run-based path).
class _EphemeralGarmentClient extends GarmentClient {
  int ephemeralCalls = 0;
  int authedCalls = 0;

  @override
  Future<({Map<String, dynamic>? snapshot, String? failureReason})>
  submitGarmentEphemeralBytes(
    Uint8List bytes, {
    String filename = 'wardrobe_item.jpg',
  }) async {
    ephemeralCalls++;
    return (
      snapshot: {
        'category': 'tops',
        'subcategory': 'T-Shirt',
        'color': 'Black',
        'pattern': 'solid',
        'material': 'Cotton',
        'style': 'casual',
        'fit': 'regular',
        'confidence': 0.84,
        'needs_review': false,
        'sourceRunId': 'ephemeral-test-id',
      },
      failureReason: null,
    );
  }

  @override
  Future<String?> submitGarmentAnalysisBytes(
    Uint8List bytes, {
    String filename = 'wardrobe_item.jpg',
    String? idempotencyKey,
  }) async {
    authedCalls++;
    return null;
  }

  @override
  Future<GarmentAnalysisRun?> pollGarmentRun({
    required String runId,
    int attempts = 30,
  }) async => null;
}
