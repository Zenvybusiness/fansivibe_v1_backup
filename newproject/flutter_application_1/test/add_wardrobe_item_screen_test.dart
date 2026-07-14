import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/presentation/add_wardrobe_item_screen.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';

Widget createTestApp(AddItemCategoryConfig category) {
  return MaterialApp(
    theme: FansivibeTheme.darkTheme,
    home: AddWardrobeItemScreen(category: category),
  );
}

void main() {
  group('AddWardrobeItemScreen Widget Tests', () {
    late AddItemCategoryConfig topsCategory;

    setUp(() {
      topsCategory = AddItemConfig.categories.firstWhere((c) => c.id == 'tops');
    });

    testWidgets('renders app bar with category name', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(createTestApp(topsCategory));

      expect(find.text('Add Tops'), findsOneWidget);
    });

    testWidgets('renders all section labels', (WidgetTester tester) async {
      await tester.pumpWidget(createTestApp(topsCategory));

      expect(find.text('Type'), findsOneWidget);
      expect(find.text('Color'), findsOneWidget);
      expect(find.text('Texture (optional)'), findsOneWidget);
    });

    testWidgets('renders Save Item button', (WidgetTester tester) async {
      await tester.pumpWidget(createTestApp(topsCategory));

      expect(find.text('Save Item'), findsOneWidget);
    });

    testWidgets('renders type chips for the category', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(createTestApp(topsCategory));

      for (final type in topsCategory.types.take(4)) {
        expect(find.text(type), findsOneWidget);
      }
    });

    testWidgets('renders color chips', (WidgetTester tester) async {
      await tester.pumpWidget(createTestApp(topsCategory));

      for (final color in AddItemConfig.colors.take(4)) {
        expect(find.text(color.name), findsOneWidget);
      }
    });

    testWidgets('renders texture chips', (WidgetTester tester) async {
      await tester.pumpWidget(createTestApp(topsCategory));

      for (final texture in AddItemConfig.textures.take(4)) {
        expect(find.text(texture.name), findsOneWidget);
      }
    });

    testWidgets('shows validation error when type and color not selected', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(createTestApp(topsCategory));

      await tester.scrollUntilVisible(
        find.text('Save Item'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Save Item'));
      await tester.pumpAndSettle();

      expect(find.text('Please select a type and color.'), findsOneWidget);
    });

    testWidgets('saves item and pops with data when valid', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(createTestApp(topsCategory));

      // Select a type
      await tester.tap(find.text('T-Shirt'));
      await tester.pumpAndSettle();

      // Select a color
      await tester.tap(find.text('Black'));
      await tester.pumpAndSettle();

      // Select a texture
      await tester.scrollUntilVisible(
        find.text('Cotton'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Cotton'));
      await tester.pumpAndSettle();

      // Save
      await tester.tap(find.text('Save Item'));
      await tester.pumpAndSettle();

      // Screen should be popped
      expect(find.text('Add Tops'), findsNothing);
    });

    testWidgets('tapping back button pops the screen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(createTestApp(topsCategory));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();

      expect(find.text('Add Tops'), findsNothing);
    });
  });
}
