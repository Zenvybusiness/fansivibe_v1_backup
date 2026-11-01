import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/grooming/data/grooming_client.dart';
import 'package:fansivibe/features/grooming/data/grooming_models.dart';
import 'package:fansivibe/features/grooming/data/grooming_service.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_input_screen.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_processing_screen.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_result_screen.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

class _RecordingGroomingClient extends GroomingClient {
  String? submitResult;
  GroomingRun? pollResult;
  String? recordedFaceShape;
  String? recordedBeardStyle;
  String? recordedBeardDensity;
  String? recordedBeardColor;
  String? recordedIdempotencyKey;
  int submitCalls = 0;

  @override
  Future<String?> submitGroomingAnalysis({
    String? faceShape,
    String? beardStyle,
    String? beardDensity,
    String? beardColor,
    String? idempotencyKey,
  }) async {
    submitCalls++;
    recordedFaceShape = faceShape;
    recordedBeardStyle = beardStyle;
    recordedBeardDensity = beardDensity;
    recordedBeardColor = beardColor;
    recordedIdempotencyKey = idempotencyKey;
    return submitResult;
  }

  @override
  Future<GroomingRun?> pollGroomingRun({required String runId}) async =>
      pollResult;

  int ephemeralCalls = 0;
  ({Map<String, dynamic>? snapshot, String? failureReason}) ephemeralResult = (
    snapshot: _mockGroomingRunResult,
    failureReason: null,
  );

  @override
  Future<({Map<String, dynamic>? snapshot, String? failureReason})>
  submitGroomingEphemeral({
    required String faceShape,
    String skinTone = '',
    String bodyType = '',
    String styleType = '',
  }) async {
    ephemeralCalls++;
    return ephemeralResult;
  }
}

class _EmptyLearningRepository implements LearningRepository {
  @override
  FaceProfile? get face => null;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _OvalLearningRepository implements LearningRepository {
  @override
  FaceProfile? get face => const FaceProfile(faceShape: 'Oval');

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

const Map<String, dynamic> _mockGroomingRunResult = {
  'appearance': {'faceShape': 'square'},
  'recommendations': {
    'top': {
      'id': 'classic_stubble',
      'name': 'Classic Stubble',
      'description': 'Low-maintenance 3mm stubble.',
      'matchScore': 0.88,
      'reasons': ['Grounded test reason for square face.'],
      'stylingTips': 'Trim regularly',
      'maintenance': 'Low',
      'bestFor': 'Square',
    },
    'alternatives': <dynamic>[],
  },
};

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    AuthSession.resetForTest();
    await AuthSession.saveSession('test-auth-token');
    clearPendingEphemeralResult();
  });

  tearDown(() async {
    LocalStorage.savedLocally = false;
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    clearPendingEphemeralResult();
  });

  group('Authenticated Grooming Analysis Repair (Stage 2 P0-2)', () {
    testWidgets('1. manual grooming inputs survive navigation', (
      WidgetTester tester,
    ) async {
      Map<String, String>? capturedArgs;

      final router = GoRouter(
        initialLocation: '/input',
        routes: [
          GoRoute(
            path: '/input',
            name: RouteNames.grooming,
            builder: (context, state) => const GroomingInputScreen(),
          ),
          GoRoute(
            path: '/processing',
            name: RouteNames.groomingProcessing,
            builder: (context, state) {
              final extra = state.extra;
              if (extra is Map) {
                capturedArgs = extra.map(
                  (k, v) => MapEntry(k.toString(), v?.toString() ?? ''),
                );
              }
              return const Scaffold(body: Text('Processing Screen'));
            },
          ),
        ],
      );

      tester.view.physicalSize = const Size(800, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      // Select face shape: Square
      await tester.tap(find.text('Square'));
      await tester.pumpAndSettle();

      // Select beard style: Stubble
      await tester.tap(find.text('Stubble'));
      await tester.pumpAndSettle();

      // Select density: Medium
      await tester.tap(find.text('Medium'));
      await tester.pumpAndSettle();

      // Select color: Dark Brown
      await tester.tap(find.text('Dark Brown'));
      await tester.pumpAndSettle();

      // Tap analyze
      await tester.ensureVisible(find.text('Analyze Style'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Analyze Style'));
      await tester.pumpAndSettle();

      expect(find.text('Processing Screen'), findsOneWidget);
      expect(capturedArgs, isNotNull);
      expect(capturedArgs!['faceShape'], 'square');
      expect(capturedArgs!['beardStyle'], 'stubble');
      expect(capturedArgs!['beardDensity'], 'medium');
      expect(capturedArgs!['beardColor'], 'dark_brown');
    });

    testWidgets(
      '2. processing screen forwards actual inputs to service and client',
      (WidgetTester tester) async {
        final client = _RecordingGroomingClient()
          ..submitResult = 'run-42'
          ..pollResult = const GroomingRun(
            runId: 'run-42',
            runType: 'grooming',
            status: 'completed',
            result: _mockGroomingRunResult,
          );
        final service = GroomingService(client: client)
          ..attachLearning(_EmptyLearningRepository());

        final router = GoRouter(
          initialLocation: '/processing',
          routes: [
            GoRoute(
              path: '/processing',
              name: RouteNames.groomingProcessing,
              builder: (context, state) => GroomingProcessingScreen(
                faceShape: 'square',
                beardStyle: 'stubble',
                beardDensity: 'dense',
                beardColor: 'black',
                service: service,
              ),
              routes: [
                GoRoute(
                  path: 'result',
                  name: RouteNames.groomingResult,
                  builder: (context, state) => const Text('Result Screen'),
                ),
              ],
            ),
          ],
        );

        await tester.pumpWidget(MaterialApp.router(routerConfig: router));
        await tester.pumpAndSettle();

        expect(client.submitCalls, 1);
        expect(client.recordedFaceShape, 'square');
        expect(client.recordedBeardStyle, 'stubble');
        expect(client.recordedBeardDensity, 'dense');
        expect(client.recordedBeardColor, 'black');
      },
    );

    testWidgets(
      '3. authenticated user without face scan receives valid recommendations when inputs are sufficient',
      (WidgetTester tester) async {
        final client = _RecordingGroomingClient()
          ..submitResult = 'run-success'
          ..pollResult = const GroomingRun(
            runId: 'run-success',
            runType: 'grooming',
            status: 'completed',
            result: _mockGroomingRunResult,
          );
        final service = GroomingService(client: client)
          ..attachLearning(_EmptyLearningRepository());

        final router = GoRouter(
          initialLocation: '/processing',
          routes: [
            GoRoute(
              path: '/input',
              name: RouteNames.grooming,
              builder: (context, state) => const Text('Grooming Input'),
            ),
            GoRoute(
              path: '/processing',
              name: RouteNames.groomingProcessing,
              builder: (context, state) => GroomingProcessingScreen(
                faceShape: 'square',
                beardStyle: 'stubble',
                beardDensity: 'medium',
                beardColor: 'black',
                service: service,
              ),
              routes: [
                GoRoute(
                  path: 'result',
                  name: RouteNames.groomingResult,
                  builder: (context, state) {
                    final result = state.extra as GroomingAnalysisResult;
                    return GroomingResultScreen(
                      faceShape: result.faceShape,
                      beardStyle: result.beardStyle,
                      beardDensity: result.beardDensity,
                      beardColor: result.beardColor,
                      result: result,
                    );
                  },
                ),
              ],
            ),
          ],
        );

        await tester.pumpWidget(MaterialApp.router(routerConfig: router));
        await tester.pumpAndSettle();

        // Must NOT fall back to mock
        expect(service.isMockResult, isFalse);
        expect(service.analysisError, isNull);

        // Grounded recommendation rendered
        expect(find.text('Classic Stubble is your top match'), findsOneWidget);
        expect(find.text('square'), findsOneWidget);
      },
    );

    testWidgets(
      '4. empty or genuinely insufficient input produces an honest validation state',
      (WidgetTester tester) async {
        final client = _RecordingGroomingClient();
        final service = GroomingService(client: client)
          ..attachLearning(_EmptyLearningRepository());

        final router = GoRouter(
          initialLocation: '/processing',
          routes: [
            GoRoute(
              path: '/input',
              name: RouteNames.grooming,
              builder: (context, state) =>
                  const Scaffold(body: Center(child: Text('Grooming Input'))),
            ),
            GoRoute(
              path: '/processing',
              name: RouteNames.groomingProcessing,
              builder: (context, state) => GroomingProcessingScreen(
                faceShape: '',
                beardStyle: '',
                beardDensity: '',
                beardColor: '',
                service: service,
              ),
            ),
          ],
        );

        await tester.pumpWidget(MaterialApp.router(routerConfig: router));
        await tester.pumpAndSettle();

        expect(client.submitCalls, 0);
        expect(
          find.text('Please select your grooming preferences to continue.'),
          findsOneWidget,
        );
        expect(find.text('Grooming Input'), findsOneWidget);
      },
    );

    testWidgets('5. API failures are handled correctly without fake success', (
      WidgetTester tester,
    ) async {
      final client = _RecordingGroomingClient()..submitResult = null;
      final service = GroomingService(client: client)
        ..attachLearning(_EmptyLearningRepository());

      final router = GoRouter(
        initialLocation: '/processing',
        routes: [
          GoRoute(
            path: '/input',
            name: RouteNames.grooming,
            builder: (context, state) =>
                const Scaffold(body: Center(child: Text('Grooming Input'))),
          ),
          GoRoute(
            path: '/processing',
            name: RouteNames.groomingProcessing,
            builder: (context, state) => GroomingProcessingScreen(
              faceShape: 'square',
              beardStyle: 'stubble',
              beardDensity: 'medium',
              beardColor: 'black',
              service: service,
            ),
          ),
        ],
      );

      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      expect(service.isMockResult, isTrue);
      expect(
        find.text('Grooming service unreachable. Please try again.'),
        findsOneWidget,
      );
      expect(find.text('Grooming Input'), findsOneWidget);
      expect(find.text('Classic Stubble is your top match'), findsNothing);
    });

    testWidgets('6. retry preserves the original request context', (
      WidgetTester tester,
    ) async {
      final client = _RecordingGroomingClient()..submitResult = null;
      final service = GroomingService(client: client)
        ..attachLearning(_EmptyLearningRepository());

      final router = GoRouter(
        initialLocation: '/processing',
        routes: [
          GoRoute(
            path: '/input',
            name: RouteNames.grooming,
            builder: (context, state) =>
                const Scaffold(body: Center(child: Text('Grooming Input'))),
          ),
          GoRoute(
            path: '/processing',
            name: RouteNames.groomingProcessing,
            builder: (context, state) => GroomingProcessingScreen(
              faceShape: 'square',
              beardStyle: 'stubble',
              beardDensity: 'medium',
              beardColor: 'black',
              service: service,
            ),
          ),
        ],
      );

      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      expect(client.submitCalls, 1);
      final firstKey = client.recordedIdempotencyKey;
      expect(firstKey, isNotNull);

      // Subsequent retry through service preserves the original manual inputs
      await service.runAnalysis(
        faceShape: 'square',
        beardStyle: 'stubble',
        beardDensity: 'medium',
        beardColor: 'black',
      );

      expect(client.submitCalls, 2);
      expect(client.recordedFaceShape, 'square');
      expect(client.recordedBeardStyle, 'stubble');
      expect(client.recordedBeardDensity, 'medium');
      expect(client.recordedBeardColor, 'black');
      // Same idempotency key is reused across retry
      expect(client.recordedIdempotencyKey, firstKey);
    });

    testWidgets('7. existing face-scan grooming flow remains functional', (
      WidgetTester tester,
    ) async {
      final client = _RecordingGroomingClient()
        ..submitResult = 'run-profile'
        ..pollResult = const GroomingRun(
          runId: 'run-profile',
          runType: 'grooming',
          status: 'completed',
          result: {
            'appearance': {'faceShape': 'Oval'},
            'recommendations': {
              'top': {
                'id': 'structured_goatee',
                'name': 'Structured Goatee',
                'description': 'A refined goatee.',
                'matchScore': 0.95,
                'reasons': ['Matches oval faces.'],
                'stylingTips': 'Keep clean',
                'maintenance': 'Medium',
                'bestFor': 'Oval',
              },
              'alternatives': <dynamic>[],
            },
          },
        );
      final service = GroomingService(client: client)
        ..attachLearning(_OvalLearningRepository());

      final router = GoRouter(
        initialLocation: '/processing',
        routes: [
          GoRoute(
            path: '/processing',
            name: RouteNames.groomingProcessing,
            builder: (context, state) => GroomingProcessingScreen(
              faceShape: '', // Empty manual input, uses learning profile
              beardStyle: 'goatee',
              beardDensity: 'medium',
              beardColor: 'dark_brown',
              service: service,
            ),
            routes: [
              GoRoute(
                path: 'result',
                name: RouteNames.groomingResult,
                builder: (context, state) {
                  final result = state.extra as GroomingAnalysisResult;
                  return GroomingResultScreen(
                    faceShape: result.faceShape,
                    beardStyle: result.beardStyle,
                    beardDensity: result.beardDensity,
                    beardColor: result.beardColor,
                    result: result,
                  );
                },
              ),
            ],
          ),
        ],
      );

      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      expect(client.recordedFaceShape, 'Oval'); // Derived from profile
      expect(find.text('Structured Goatee is your top match'), findsOneWidget);
    });

    testWidgets('8. guest authentication boundaries remain intact', (
      WidgetTester tester,
    ) async {
      await AuthSession.clearSession();
      // Enable guest mode
      LocalStorage.savedLocally = true;

      expect(isGuestUser, isTrue);

      final client = _RecordingGroomingClient();
      final service = GroomingService(client: client);

      final router = GoRouter(
        initialLocation: '/processing',
        routes: [
          GoRoute(
            path: '/input',
            name: RouteNames.grooming,
            builder: (context, state) =>
                const Scaffold(body: Center(child: Text('Grooming Input'))),
          ),
          GoRoute(
            path: '/processing',
            name: RouteNames.groomingProcessing,
            builder: (context, state) => GroomingProcessingScreen(
              faceShape: 'square',
              beardStyle: 'full_beard',
              beardDensity: 'medium',
              beardColor: 'black',
              service: service,
            ),
            routes: [
              GoRoute(
                path: 'result',
                name: RouteNames.groomingResult,
                builder: (context, state) => const Text('Guest Result Screen'),
              ),
            ],
          ),
        ],
      );

      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      // Guest flow executes ephemeral without Bearer auth or database writes
      expect(client.submitCalls, 0); // No authenticated DB run
      expect(client.ephemeralCalls, 1); // Ephemeral endpoint invoked
      expect(find.text('Guest Result Screen'), findsOneWidget);
    });
  });
}
