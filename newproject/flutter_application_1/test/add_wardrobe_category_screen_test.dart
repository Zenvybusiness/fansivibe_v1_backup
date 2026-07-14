import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/presentation/add_wardrobe_category_screen.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';

Widget createTestApp() {
  return MaterialApp(
    theme: FansivibeTheme.darkTheme,
    home: const AddWardrobeCategoryScreen(),
  );
}

void main() {
  group('AddWardrobeCategoryScreen Widget Tests', () {
    testWidgets('renders title and subtitle', (WidgetTester tester) async {
      await tester.pumpWidget(createTestApp());

      expect(find.text('Add Item'), findsOneWidget);
      expect(find.text('Select a Category'), findsOneWidget);
    });

    testWidgets('renders all category cards with names and type counts', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(createTestApp());

      for (final category in AddItemConfig.categories) {
        expect(find.text(category.name), findsOneWidget);
      }
      // Verify type counts appear (some categories share the same count)
      expect(find.text('12 types'), findsOneWidget);
      expect(find.text('9 types'), findsAtLeast(1));
      expect(find.text('10 types'), findsOneWidget);
    });

    testWidgets('tapping a category navigates to AddWardrobeItemScreen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(createTestApp());

      await tester.tap(find.text('Tops'));
      await tester.pumpAndSettle();

      expect(find.text('Add Tops'), findsOneWidget);
      expect(find.text('Type'), findsOneWidget);
      expect(find.text('Color'), findsOneWidget);
    });

    testWidgets('tapping back button pops the screen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(createTestApp());

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();

      expect(find.text('Select a Category'), findsNothing);
    });
  });
}
