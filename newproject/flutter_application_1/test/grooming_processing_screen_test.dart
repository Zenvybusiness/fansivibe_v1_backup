import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/grooming/data/grooming_client.dart';
import 'package:fansivibe/features/grooming/data/grooming_models.dart';
import 'package:fansivibe/features/grooming/data/grooming_service.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_processing_screen.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_result_screen.dart';
import 'package:fansivibe/features/grooming/presentation/widgets/grooming_widgets.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

class _ProcessingGroomingService extends GroomingService {
  @override
  bool get isProcessing => true;
}

class _FakeGroomingClient extends GroomingClient {
  String? submitResult;
  GroomingRun? pollResult;

  @override
  Future<String?> submitGroomingAnalysis({String? idempotencyKey}) async =>
      submitResult;

  @override
  Future<GroomingRun?> pollGroomingRun({required String runId}) async =>
      pollResult;
}

class _FaceLearningRepository implements LearningRepository {
  @override
  FaceProfile? get face => const FaceProfile(faceShape: 'oval');

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

const Map<String, dynamic> _completedRunResult = {
  'appearance': {'faceShape': 'oval'},
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
    'alternatives': <dynamic>[],
  },
};

GoRouter _processingRouter(GroomingService service) {
  return GoRouter(
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
          service: service,
          faceShape: 'oval',
          beardStyle: 'Full Beard',
          beardDensity: 'Medium',
          beardColor: 'Dark Brown',
        ),
        routes: [
          GoRoute(
            path: 'result',
            name: RouteNames.groomingResult,
            builder: (context, state) {
              final result = state.extra as GroomingAnalysisResult;
              return GroomingResultScreen(
                faceShape: result.faceShape,
                beardStyle: 'Full Beard',
                beardDensity: 'Medium',
                beardColor: 'Dark Brown',
                result: result,
              );
            },
          ),
        ],
      ),
    ],
  );
}

void main() {
  // Auth boundary: the processing screen gates on a live session, so
  // tests sign in unless they explicitly exercise the signed-out path.
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    AuthSession.resetForTest();
    await AuthSession.saveSession('grooming-test-token');
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
  });

  testWidgets('renders app bar with analyzing title', (
      WidgetTester tester,
      ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: GroomingProcessingScreen(
          faceShape: 'Oval',
          beardStyle: 'Full Beard',
          beardDensity: 'Medium',
          beardColor: 'Dark Brown',
          service: _ProcessingGroomingService(),
        ),
      ),
    );

    expect(find.text('Analyzing Features'), findsOneWidget);
  });

  testWidgets('renders processing stages', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: const GroomingProcessingScreen(
          faceShape: 'Oval',
          beardStyle: 'Full Beard',
          beardDensity: 'Medium',
          beardColor: 'Dark Brown',
        ),
      ),
    );

    expect(find.text('Analyzing face shape'), findsOneWidget);
    expect(find.byType(GroomingStageIndicator), findsNWidgets(5));
  });

  testWidgets('shows progress indicator during processing', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: GroomingProcessingScreen(
          faceShape: 'Oval',
          beardStyle: 'Full Beard',
          beardDensity: 'Medium',
          beardColor: 'Dark Brown',
          service: _ProcessingGroomingService(),
        ),
      ),
    );

    expect(find.byType(CircularProgressIndicator), findsWidgets);
  });

  testWidgets('signed-out without session is redirected honestly', (
    WidgetTester tester,
  ) async {
    // No guest flag and no session: there is no account analysis to run,
    // so the screen reports that and returns to the input instead of
    // sitting dead or firing an unauthenticated request.
    AuthSession.resetForTest();
    await AuthSession.clearSession();

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
          builder: (context, state) => const GroomingProcessingScreen(
            faceShape: 'Oval',
            beardStyle: 'Full Beard',
            beardDensity: 'Medium',
            beardColor: 'Dark Brown',
          ),
        ),
      ],
    );
    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    await tester.pumpAndSettle();

    expect(
      find.text('Sign in to run grooming analysis.'),
      findsOneWidget,
    );
    expect(find.text('Analyzing Features'), findsNothing);
    expect(find.text('Grooming Input'), findsOneWidget);
  });

  group('authenticated analysis wiring', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStorage.init(prefs: await SharedPreferences.getInstance());
      AuthSession.resetForTest();
      await AuthSession.saveSession('grooming-test-token');
    });

    tearDown(() async {
      AuthSession.resetForTest();
      await AuthSession.clearSession();
    });

    testWidgets('signed-in user runs the live analysis to a real result', (
      WidgetTester tester,
    ) async {
      final client = _FakeGroomingClient()
        ..submitResult = 'run-1'
        ..pollResult = const GroomingRun(
          runId: 'run-1',
          runType: 'grooming',
          status: 'completed',
          result: _completedRunResult,
        );
      // The screen owns and disposes the injected service.
      final service = GroomingService(client: client)
        ..attachLearning(_FaceLearningRepository());

      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _processingRouter(service)),
      );
      await tester.pumpAndSettle();

      // Real backend-shaped result renders — never the offline mock.
      expect(service.isMockResult, isFalse);
      expect(find.text('Structured Goatee is your top match'), findsOneWidget);
    });

    testWidgets('unreachable backend fails honestly without mock content', (
      WidgetTester tester,
    ) async {
      final client = _FakeGroomingClient()..submitResult = null;
      // The screen owns and disposes the injected service.
      final service = GroomingService(client: client)
        ..attachLearning(_FaceLearningRepository());

      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _processingRouter(service)),
      );
      await tester.pumpAndSettle();

      expect(service.isMockResult, isTrue);
      expect(
        find.text('Grooming service unreachable. Please try again.'),
        findsOneWidget,
      );
      expect(find.text('Grooming Input'), findsOneWidget);
      expect(find.text('Structured Goatee'), findsNothing);
    });

    testWidgets('empty run payload fails honestly without mock content', (
      WidgetTester tester,
    ) async {
      final client = _FakeGroomingClient()
        ..submitResult = 'run-1'
        ..pollResult = const GroomingRun(
          runId: 'run-1',
          runType: 'grooming',
          status: 'completed',
        );
      final service = GroomingService(client: client)
        ..attachLearning(_FaceLearningRepository());
      addTearDown(service.dispose);

      final result = await service.runAnalysis();

      expect(service.isMockResult, isTrue);
      expect(result, GroomingAnalysisResult.mock);
      expect(
        service.analysisError,
        'Grooming analysis returned no result. Please try again.',
      );
    });
  });
}