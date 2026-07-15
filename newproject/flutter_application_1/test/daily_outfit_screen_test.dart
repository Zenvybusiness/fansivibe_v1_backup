import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/home/data/daily_outfit_mock_data.dart';
import 'package:fansivibe/features/home/presentation/daily_outfit_screen.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

GoRouter _testRouter() {
  return GoRouter(
    initialLocation: '/daily-outfit',
    routes: [
      GoRoute(
        path: '/daily-outfit',
        name: RouteNames.dailyOutfit,
        builder: (context, state) => const DailyOutfitScreen(),
      ),
      GoRoute(
        path: '/outfit/build',
        name: RouteNames.buildOutfit,
        builder: (context, state) =>
            const Scaffold(body: Center(child: Text('Build Outfit Screen'))),
      ),
      GoRoute(
        path: '/wardrobe',
        name: RouteNames.wardrobe,
        builder: (context, state) =>
            const Scaffold(body: Center(child: Text('Wardrobe Screen'))),
      ),
    ],
  );
}

Widget _buildTestApp() {
  return MaterialApp.router(
    routerConfig: _testRouter(),
    theme: ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: FansivibeColors.background,
      colorScheme: const ColorScheme.dark(surface: FansivibeColors.surface),
    ),
  );
}

void main() {
  group('DailyOutfitScreen Widget Tests', () {
    testWidgets('renders app bar with title and back button', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());

      expect(find.text('Daily Outfit'), findsOneWidget);
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
    });

    testWidgets('renders header with title and description', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());

      expect(find.text('Modern Minimalist'), findsNWidgets(2));
      expect(find.text('Work \u2022 Casual Friday'), findsOneWidget);
      expect(
        find.textContaining('Clean lines meet relaxed sophistication'),
        findsOneWidget,
      );
    });

    testWidgets('renders weather info in header', (WidgetTester tester) async {
      await tester.pumpWidget(_buildTestApp());

      expect(find.text('68\u00B0F \u2022 Partly Cloudy'), findsOneWidget);
    });

    testWidgets('renders match and style score sections', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());

      expect(find.text('Match'), findsOneWidget);
      expect(find.text('Style Score'), findsWidgets);
      expect(find.text('91%'), findsOneWidget);
      expect(find.text('87%'), findsOneWidget);
    });

    testWidgets('renders outfit components', (WidgetTester tester) async {
      await tester.pumpWidget(_buildTestApp());

      expect(find.text('Outfit Components'), findsOneWidget);
      expect(find.text('5 curated pieces'), findsOneWidget);

      expect(find.text('Charcoal Unstructured Blazer'), findsOneWidget);
      expect(find.text('Merino Wool Crewneck'), findsOneWidget);
      expect(find.text('Tapered Wool Trousers'), findsOneWidget);
      expect(find.text('Leather Chelsea Boots'), findsOneWidget);
      expect(find.text('Minimalist Leather Belt'), findsOneWidget);
    });

    testWidgets('renders component replace buttons with category names', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());

      expect(find.text('Change Outerwear'), findsOneWidget);
      expect(find.text('Change Tops'), findsOneWidget);
      expect(find.text('Change Bottoms'), findsOneWidget);
      expect(find.text('Change Footwear'), findsOneWidget);
    });

    testWidgets('renders why this works section', (WidgetTester tester) async {
      await tester.pumpWidget(_buildTestApp());

      expect(find.text('Why This Look Works'), findsOneWidget);
      expect(find.text('Personalized recommendation reasons'), findsOneWidget);
    });

    testWidgets('renders all four recommendation reasons', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());

      final data = DailyOutfitData.mock;
      for (final reason in data.reasons) {
        expect(find.textContaining(reason.substring(0, 30)), findsOneWidget);
      }
    });

    testWidgets('renders Style DNA section with all attributes', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());

      expect(find.text('Your Style DNA'), findsOneWidget);
      expect(find.text('Modern Minimalist'), findsNWidgets(2));
      expect(find.text('Athletic'), findsOneWidget);
      expect(find.text('Medium'), findsOneWidget);
      expect(find.text('Oval'), findsOneWidget);
    });

    testWidgets('renders Wardrobe Context section', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());

      expect(find.text('Wardrobe Context'), findsOneWidget);
      expect(find.text('42'), findsOneWidget);
      expect(find.text('8'), findsOneWidget);
      expect(find.text('Total Items'), findsOneWidget);
      expect(find.text('Matching'), findsOneWidget);
      expect(
        find.textContaining('Adding a charcoal unstructured blazer'),
        findsOneWidget,
      );
    });

    testWidgets('renders action buttons', (WidgetTester tester) async {
      await tester.pumpWidget(_buildTestApp());

      expect(find.text('Wear This'), findsOneWidget);
      expect(find.text('Save Outfit'), findsOneWidget);
      expect(find.text('Change Style'), findsWidgets);
      expect(find.text('Review Closet'), findsOneWidget);
    });

    testWidgets('Wear This shows snackbar on tap', (WidgetTester tester) async {
      await tester.pumpWidget(_buildTestApp());

      await tester.scrollUntilVisible(find.text('Wear This'), 200);
      await tester.tap(find.text('Wear This'));
      await tester.pumpAndSettle();

      expect(find.text('Wearing this look!'), findsOneWidget);
    });

    testWidgets('Save Outfit shows snackbar on tap', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());

      await tester.scrollUntilVisible(find.text('Save Outfit'), 200);
      await tester.tap(find.text('Save Outfit'));
      await tester.pumpAndSettle();

      expect(find.text('Outfit saved to your looks'), findsOneWidget);
    });

    testWidgets('replace component shows snackbar on tap', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());

      await tester.scrollUntilVisible(find.text('Change Tops'), 200);
      await tester.tap(find.text('Change Tops'));
      await tester.pumpAndSettle();

      expect(
        find.text('Replace Merino Wool Crewneck coming soon'),
        findsOneWidget,
      );
    });

    testWidgets('Change Style navigates to Build Outfit screen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());

      await tester.scrollUntilVisible(find.text('Change Style').last, 200);
      await tester.tap(find.text('Change Style').last);
      await tester.pumpAndSettle();

      expect(find.text('Build Outfit Screen'), findsOneWidget);
    });

    testWidgets('Review Closet navigates to Wardrobe screen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());

      await tester.scrollUntilVisible(find.text('Review Closet'), 200);
      await tester.tap(find.text('Review Closet'));
      await tester.pumpAndSettle();

      expect(find.text('Wardrobe Screen'), findsOneWidget);
    });

    testWidgets('back button pops the screen', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Builder(
            builder: (context) {
              return Navigator(
                onGenerateRoute: (settings) {
                  return MaterialPageRoute(
                    builder: (_) => const DailyOutfitScreen(),
                  );
                },
              );
            },
          ),
        ),
      );

      // Tap back and ensure the widget is popped (no longer visible).
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();

      expect(find.text('Daily Outfit'), findsNothing);
    });

    testWidgets('DailyOutfitScreen is scrollable', (WidgetTester tester) async {
      await tester.pumpWidget(_buildTestApp());

      await tester.drag(
        find.byType(SingleChildScrollView),
        const Offset(0, -500),
      );
      await tester.pumpAndSettle();

      expect(find.text('Review Closet'), findsOneWidget);
    });
  });

  group('DailyOutfitData Mock Tests', () {
    test('mock data has all required fields', () {
      final data = DailyOutfitData.mock;

      expect(data.title, isNotEmpty);
      expect(data.occasion, isNotEmpty);
      expect(data.weather, isNotEmpty);
      expect(data.description, isNotEmpty);
      expect(data.matchScore, inInclusiveRange(0, 100));
      expect(data.styleScore, inInclusiveRange(0, 100));
      expect(data.components.length, greaterThan(0));
      expect(data.reasons.length, greaterThan(0));
      expect(data.styleDna.styleType, isNotEmpty);
      expect(data.wardrobeContext.totalItems, greaterThan(0));
    });

    test('mock components have required fields', () {
      final components = DailyOutfitData.mock.components;

      for (final component in components) {
        expect(component.id, isNotEmpty);
        expect(component.name, isNotEmpty);
        expect(component.category, isNotEmpty);
        expect(component.color, isNotEmpty);
      }
    });
  });
}
