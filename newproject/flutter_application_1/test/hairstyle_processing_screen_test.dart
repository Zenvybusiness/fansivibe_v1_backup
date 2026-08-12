import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/domain/hairstyle_service.dart';
import 'package:fansivibe/features/hairstyle/presentation/face_processing_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/hairstyle_result_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/widgets/hairstyle_widgets.dart';
import 'support/controllable_hairstyle_service.dart';

GoRouter _processingRouter(HairstyleService service) => GoRouter(
  initialLocation: '/processing',
  routes: [
    GoRoute(
      path: '/',
      name: RouteNames.hairstyle,
      builder: (_, __) => const Scaffold(body: SizedBox()),
      routes: [
        GoRoute(
          path: 'processing',
          name: RouteNames.hairstyleProcessing,
          builder: (_, __) => FaceProcessingScreen(service: service),
          routes: [
            GoRoute(
              path: 'result',
              name: RouteNames.hairstyleResult,
              builder: (_, state) => HairstyleResultScreen(
                result: state.extra as HairstyleAnalysisResult?,
              ),
            ),
          ],
        ),
      ],
    ),
  ],
);

void main() {
  group('FaceProcessingScreen Widget Tests', () {
    testWidgets('renders app bar with analyzing title', (
      WidgetTester tester,
    ) async {
      final service = ControllableHairstyleService();
      addTearDown(service.dispose);
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _processingRouter(service)),
      );

      expect(find.text('Analyzing Face'), findsOneWidget);
      expect(service.started, isTrue);
    });

    testWidgets('renders processing stages', (WidgetTester tester) async {
      final service = ControllableHairstyleService();
      addTearDown(service.dispose);
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _processingRouter(service)),
      );

      expect(find.text('Detecting face features'), findsOneWidget);
      expect(find.byType(HairstyleStageIndicator), findsNWidgets(5));
    });

    testWidgets('shows progress indicator during processing', (
      WidgetTester tester,
    ) async {
      final service = ControllableHairstyleService();
      addTearDown(service.dispose);
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _processingRouter(service)),
      );

      expect(find.byType(CircularProgressIndicator), findsWidgets);
    });

    testWidgets('navigates to result when analysis completes', (
      WidgetTester tester,
    ) async {
      final service = ControllableHairstyleService();
      addTearDown(service.dispose);
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _processingRouter(service)),
      );

      service.finish();
      await tester.pumpAndSettle();

      expect(find.text('Hairstyle Results'), findsOneWidget);
      expect(find.text('Textured Quiff'), findsOneWidget);
    });

    testWidgets('shows an error state when the backend run failed', (
      WidgetTester tester,
    ) async {
      final service = ControllableHairstyleService();
      addTearDown(service.dispose);
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _processingRouter(service)),
      );

      service.failWith("We couldn't finish this request.");
      await tester.pumpAndSettle();

      expect(find.text('Analysis Failed'), findsOneWidget);
      expect(find.text('Something went wrong'), findsOneWidget);
      expect(find.text("We couldn't finish this request."), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);
      expect(find.text('Hairstyle Results'), findsNothing);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      final service = ControllableHairstyleService();
      addTearDown(service.dispose);
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _processingRouter(service)),
      );

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });
}
