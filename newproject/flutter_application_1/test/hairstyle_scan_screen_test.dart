import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/hairstyle/presentation/face_scan_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/widgets/hairstyle_widgets.dart';

void main() {
  group('FaceScanScreen Widget Tests', () {
    testWidgets('renders app bar with title', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      expect(find.text('Face Scan'), findsOneWidget);
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
    });

    testWidgets('renders face preview placeholder', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      expect(find.byType(FacePreviewPlaceholder), findsOneWidget);
      expect(
        find.text('Position your face within the oval guide'),
        findsOneWidget,
      );
    });

    testWidgets('renders Face Detection Active indicator', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      expect(find.text('Face Detection Active'), findsOneWidget);
    });

    testWidgets('renders check indicators', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      expect(find.byType(HairstyleCheckIndicator), findsNWidgets(3));
      expect(find.text('Lighting'), findsOneWidget);
      expect(find.text('Distance'), findsOneWidget);
      expect(find.text('Alignment'), findsOneWidget);
    });

    testWidgets('renders alignment improvement message', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      expect(find.text('Center your face in the frame'), findsOneWidget);
    });

    testWidgets('renders Start Scan button', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      expect(find.text('Start Scan'), findsOneWidget);
      expect(find.byIcon(Icons.face_rounded), findsWidgets);
    });

    testWidgets('start scan navigates to processing screen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      await tester.tap(find.text('Start Scan'));
      for (var i = 0; i < 30; i++) {
        await tester.pump(const Duration(milliseconds: 16));
      }

      expect(find.text('Analyzing Face'), findsOneWidget);
      expect(find.text('Detecting face features'), findsOneWidget);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });
}
