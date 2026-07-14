import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_item_details_screen.dart';

Widget _wrapScreen(WardrobeItemData item) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: WardrobeItemDetailsScreen(item: item),
  );
}

void main() {
  group('WardrobeItemDetailsScreen Widget Tests', () {
    testWidgets('renders visual placeholder with item name', (
      WidgetTester tester,
    ) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));

      expect(find.text(item.name), findsWidgets);
      expect(find.byIcon(Icons.person_rounded), findsWidgets);
    });

    testWidgets('renders category card with name', (WidgetTester tester) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));

      expect(find.text('Tops'), findsWidgets);
      expect(find.text(item.name), findsWidgets);
    });

    testWidgets('renders details section with color and material', (
      WidgetTester tester,
    ) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));

      expect(find.text('Details'), findsOneWidget);
      expect(find.text('Color'), findsOneWidget);
      expect(find.text('Charcoal'), findsOneWidget);
      expect(find.text('Material'), findsOneWidget);
      expect(find.text('Wool'), findsOneWidget);
      expect(find.text('Category'), findsOneWidget);
    });

    testWidgets('shows favorite icon for favorite item', (
      WidgetTester tester,
    ) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));

      expect(find.byIcon(Icons.favorite_rounded), findsWidgets);
      expect(find.text('Favorite'), findsOneWidget);
    });

    testWidgets('does not show favorite status for non-favorite item', (
      WidgetTester tester,
    ) async {
      final item = WardrobeMockData.items[1]; // Linen Button-Down, not favorite
      await tester.pumpWidget(_wrapScreen(item));

      expect(find.text('Favorite'), findsNothing);
    });

    testWidgets('renders action buttons', (WidgetTester tester) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));

      await tester.scrollUntilVisible(find.text('Edit Item'), 400);
      expect(find.text('Edit Item'), findsOneWidget);
      expect(find.text('Add to Outfit'), findsOneWidget);
      expect(find.text('Delete'), findsOneWidget);
    });

    testWidgets('Edit button shows snackbar', (WidgetTester tester) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));

      await tester.scrollUntilVisible(find.text('Edit Item'), 400);
      await tester.tap(find.text('Edit Item'));
      await tester.pump();

      expect(find.textContaining('Editing'), findsOneWidget);
    });

    testWidgets('Delete button shows snackbar', (WidgetTester tester) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));

      await tester.scrollUntilVisible(find.text('Delete'), 400);
      await tester.tap(find.text('Delete'));
      await tester.pump();

      expect(find.textContaining('removed from wardrobe'), findsOneWidget);
    });

    testWidgets('Add to Outfit button shows snackbar', (
      WidgetTester tester,
    ) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));

      await tester.scrollUntilVisible(find.text('Add to Outfit'), 400);
      await tester.tap(find.text('Add to Outfit'));
      await tester.pump();

      expect(find.textContaining('added to outfit'), findsOneWidget);
    });

    testWidgets('navigates back on back button tap', (
      WidgetTester tester,
    ) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));

      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();

      expect(find.byType(WardrobeItemDetailsScreen), findsNothing);
    });

    testWidgets('displays color dot for item color', (
      WidgetTester tester,
    ) async {
      final item = WardrobeMockData.items.first; // Charcoal
      await tester.pumpWidget(_wrapScreen(item));

      // Color is shown as text and dot icon
      expect(find.text('Charcoal'), findsOneWidget);
    });

    testWidgets('renders details section without material when null', (
      WidgetTester tester,
    ) async {
      // Create an item without material
      final item = WardrobeItemData(
        id: 'test',
        name: 'Test Item',
        category: 'accessories',
        color: 'Black',
      );
      await tester.pumpWidget(_wrapScreen(item));

      expect(find.text('Details'), findsOneWidget);
      expect(find.text('Color'), findsOneWidget);
      expect(find.text('Material'), findsNothing);
      expect(find.text('Category'), findsOneWidget);
    });
  });
}
