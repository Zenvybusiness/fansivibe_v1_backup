import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_models.dart';
import 'package:fansivibe/features/hairstyle/domain/hairstyle_service.dart';
import 'package:fansivibe/features/stylist/presentation/stylist_history_screen.dart';
import 'package:fansivibe/features/stylist/presentation/stylist_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

class _FakeHistoryService extends HairstyleService {
  _FakeHistoryService(this._runs);

  final List<AnalysisRun> _runs;

  @override
  Future<List<AnalysisRun>> listRuns() async => _runs;

  @override
  Future<AnalysisRun?> getRun(String runId) async {
    for (final run in _runs) {
      if (run.runId == runId) return run;
    }
    return null;
  }
}

Finder _richTextContaining(String text) => find.byWidgetPredicate(
  (widget) => widget is RichText && widget.text.toPlainText().contains(text),
);

void main() {
  final runs = <AnalysisRun>[
    AnalysisRun(
      runId: 'run-1',
      runType: 'hairstyle',
      status: 'completed',
      createdAt: DateTime(2026, 11, 28, 10, 30),
      result: const {'summary': 'Classic taper'},
    ),
  ];

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
    AuthSession.resetForTest();
  });

  tearDown(() {
    AuthSession.resetForTest();
    LocalStorage.resetForTest();
  });

  testWidgets('Stylist history entry opens the list and passes the run id', (
    tester,
  ) async {
    final router = GoRouter(
      initialLocation: '/stylist',
      routes: [
        GoRoute(
          path: '/stylist',
          name: RouteNames.stylist,
          builder: (_, __) => const StylistScreen(),
        ),
        GoRoute(
          path: '/stylist/analysis-history',
          name: RouteNames.analysisHistory,
          builder: (_, __) =>
              StylistHistoryScreen(service: _FakeHistoryService(runs)),
          routes: [
            GoRoute(
              path: 'details',
              name: RouteNames.analysisHistoryDetail,
              builder: (_, state) =>
                  Text('Detail route ${state.extra as String?}'),
            ),
          ],
        ),
      ],
    );

    await tester.pumpWidget(
      MaterialApp.router(theme: FansivibeTheme.darkTheme, routerConfig: router),
    );
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Analysis History'), 300);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Analysis History'));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('analysis_run_run-1')), findsOneWidget);
    await tester.tap(find.byKey(const Key('analysis_run_run-1')));
    await tester.pumpAndSettle();

    expect(find.text('Detail route run-1'), findsOneWidget);
  });

  testWidgets('Analysis history detail shows stored run data', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: FansivibeTheme.darkTheme,
        home: StylistHistoryDetailScreen(
          runId: 'run-1',
          service: _FakeHistoryService(runs),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Analysis Detail'), findsOneWidget);
    expect(find.text('HAIRSTYLE'), findsOneWidget);
    expect(_richTextContaining('status: completed'), findsOneWidget);
    expect(_richTextContaining('summary: Classic taper'), findsOneWidget);
  });
}
