import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_input_screen.dart';
import 'package:fansivibe/features/grooming/presentation/widgets/grooming_widgets.dart';

void main() {
  group('GroomingInputScreen Widget Tests', () {
    testWidgets('renders app bar with title', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const GroomingInputScreen()));

      expect(find.text('Beard / Glasses'), findsOneWidget);
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
    });

    testWidgets('renders header', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const GroomingInputScreen()));

      expect(find.text('Grooming Profile'), findsOneWidget);
    });

    testWidgets('renders all four option sections', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const GroomingInputScreen()));

      expect(find.text('Face Shape'), findsOneWidget);
      expect(find.text('Beard Style'), findsOneWidget);
      expect(find.text('Beard Density'), findsOneWidget);
      expect(find.text('Beard Color'), findsOneWidget);
    });

    testWidgets('renders analyze button', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const GroomingInputScreen()));

      expect(find.text('Analyze Features'), findsOneWidget);
    });

    testWidgets('analyze button exists', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const GroomingInputScreen()));

      expect(find.text('Analyze Features'), findsOneWidget);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const GroomingInputScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });

    testWidgets('renders option chips for all sections', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const GroomingInputScreen()));

      expect(find.byType(GroomingOptionChip), findsNWidgets(21));
    });
  });
}
