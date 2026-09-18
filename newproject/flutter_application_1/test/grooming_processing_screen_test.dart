import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/grooming/data/grooming_service.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_processing_screen.dart';
import 'package:fansivibe/features/grooming/presentation/widgets/grooming_widgets.dart';

class _ProcessingGroomingService extends GroomingService {
  @override
  bool get isProcessing => true;
}

void main() {
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

  testWidgets('back button pops', (WidgetTester tester) async {
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

    await tester.tap(find.byIcon(Icons.arrow_back_rounded));
    await tester.pumpAndSettle();
  });
}