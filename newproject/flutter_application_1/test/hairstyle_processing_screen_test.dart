import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/hairstyle/presentation/face_processing_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/widgets/hairstyle_widgets.dart';

void main() {
  group('FaceProcessingScreen Widget Tests', () {
    testWidgets('renders app bar with analyzing title', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const FaceProcessingScreen()));

      expect(find.text('Analyzing Face'), findsOneWidget);
    });

    testWidgets('renders processing stages', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const FaceProcessingScreen()));

      expect(find.text('Detecting face features'), findsOneWidget);
      expect(find.byType(HairstyleStageIndicator), findsNWidgets(5));
    });

    testWidgets('shows progress indicator during processing', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const FaceProcessingScreen()));

      expect(find.byType(CircularProgressIndicator), findsWidgets);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const FaceProcessingScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });
}
