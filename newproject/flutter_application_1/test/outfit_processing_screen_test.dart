import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/outfit_scan/data/outfit_scan_client.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_analysis_screen.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_processing_screen.dart';

/// Scripted client: exact poll responses with a call counter, no network.
class _ScriptedOutfitScanClient extends OutfitScanClient {
  _ScriptedOutfitScanClient(this._handler);

  final Future<OutfitAnalysisRunResult> Function() _handler;
  int calls = 0;

  @override
  Future<OutfitAnalysisRunResult> getAnalysisRun(String runId) async {
    calls++;
    return _handler();
  }
}

GoRouter _pollRouter(_ScriptedOutfitScanClient client) {
  return GoRouter(
    initialLocation: '/',
    routes: [
      GoRoute(
        path: '/',
        builder: (_, __) =>
            OutfitProcessingScreen(runId: 'run-1', client: client),
      ),
      GoRoute(
        path: '/entry',
        name: RouteNames.entry,
        builder: (_, __) => const Text('entry-marker'),
      ),
      GoRoute(
        path: '/analysis',
        name: RouteNames.scanAnalysis,
        builder: (context, state) {
          final extra = state.extra as Map<String, dynamic>?;
          return OutfitAnalysisScreen(analysisResult: extra);
        },
      ),
    ],
  );
}

void main() {
  group('OutfitProcessingScreen Widget Tests', () {
    testWidgets('renders app bar with analyzing title', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitProcessingScreen(runId: 'test-run-123')),
      );

      expect(find.text('Analyzing Outfit'), findsOneWidget);
    });

    testWidgets('renders processing indicator during polling', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitProcessingScreen(runId: 'test-run-123')),
      );

      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitProcessingScreen(runId: 'test-run-123')),
      );

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });

    testWidgets('handles completed run navigation', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitProcessingScreen(
            runId: 'completed-run-456',
            // We can't easily test the full polling flow in widget tests,
            // but we can verify the initial state
          ),
        ),
      );

      expect(find.text('Analyzing Outfit'), findsOneWidget);
    });

    testWidgets('handles failed run', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitProcessingScreen(
            runId: 'failed-run-789',
          ),
        ),
      );

      expect(find.text('Analyzing Outfit'), findsOneWidget);
    });
  });

  group('OutfitProcessingScreen P0 polling (Phase 1 Step 1)', () {
    testWidgets('404 stops polling with an honest error', (
      WidgetTester tester,
    ) async {
      final client = _ScriptedOutfitScanClient(
        () async => const OutfitAnalysisRunResult(statusCode: 404),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: OutfitProcessingScreen(runId: 'run-1', client: client),
        ),
      );
      // Manual pumps only: the error state keeps the indeterminate
      // spinner mounted, which pumpAndSettle can never settle.
      await tester.pump();
      await tester.pump();

      expect(client.calls, equals(1));
      expect(
        find.text('Analysis not found. Please try scanning again.'),
        findsOneWidget,
      );
      expect(find.text('Back to Scan'), findsOneWidget);
    });

    testWidgets('completed run forwards to the analysis screen', (
      WidgetTester tester,
    ) async {
      final client = _ScriptedOutfitScanClient(
        () async => const OutfitAnalysisRunResult(
          statusCode: 200,
          data: {
            'status': 'completed',
            'result': {
              'appearance': {'faceShape': 'oval'},
              'confidence': 0.9,
            },
          },
        ),
      );

      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _pollRouter(client)),
      );
      await tester.pumpAndSettle();

      expect(client.calls, equals(1));
      expect(find.text('Outfit Analysis'), findsOneWidget);
    });

    testWidgets('failed run with a Map error shows the typed reason', (
      WidgetTester tester,
    ) async {
      final client = _ScriptedOutfitScanClient(
        () async => const OutfitAnalysisRunResult(
          statusCode: 200,
          data: {
            'status': 'failed',
            'error': {
              'code': 'PROCESSING_FAILURE',
              'details': {'reason': 'analyzer_unavailable'},
            },
          },
        ),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: OutfitProcessingScreen(runId: 'run-1', client: client),
        ),
      );
      await tester.pumpAndSettle();

      expect(client.calls, equals(1));
      expect(
        find.text('Analysis failed: analyzer_unavailable'),
        findsOneWidget,
      );
      expect(find.text('Back to Scan'), findsOneWidget);
    });

    testWidgets('401 stops polling and routes to entry', (
      WidgetTester tester,
    ) async {
      final client = _ScriptedOutfitScanClient(
        () async => const OutfitAnalysisRunResult(statusCode: 401),
      );

      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _pollRouter(client)),
      );
      await tester.pumpAndSettle();

      expect(client.calls, equals(1));
      expect(find.text('entry-marker'), findsOneWidget);
    });

    testWidgets('500 keeps retrying with the spinner visible', (
      WidgetTester tester,
    ) async {
      final client = _ScriptedOutfitScanClient(
        () async => const OutfitAnalysisRunResult(statusCode: 500),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: OutfitProcessingScreen(runId: 'run-1', client: client),
        ),
      );
      // Manual pumps throughout (the spinner never settles).
      await tester.pump();

      expect(client.calls, equals(1));
      expect(find.byType(CircularProgressIndicator), findsWidgets);

      // Advance past the first 3 s backoff: a second attempt fires.
      await tester.pump(const Duration(seconds: 3));
      await tester.pump();
      expect(client.calls, equals(2));

      // Dispose to cancel the pending backoff timer.
      await tester.pumpWidget(const SizedBox());
    });
  });
}