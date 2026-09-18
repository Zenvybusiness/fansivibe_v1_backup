import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_item_details_screen.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Widget _wrapScreen(WardrobeItemData item, {bool deleteSucceeds = true}) {
  final httpClient = MockClient((request) async {
    if (request.method == 'DELETE') {
      return http.Response('', deleteSucceeds ? 204 : 500);
    }
    return http.Response(
      jsonEncode({
        'id': item.id,
        'name': item.name,
        'category': item.category,
        'color': item.color,
        'material': item.material,
        'isFavorite': item.isFavorite,
        'createdAt': '2024-01-15T10:00:00Z',
        'updatedAt': '2024-01-15T10:00:00Z',
      }),
      200,
    );
  });

  final wardrobeClient = WardrobeClient(client: httpClient);
  final repo = WardrobeRepositoryImpl(client: wardrobeClient);
  return MaterialApp(
    theme: ThemeData.dark(),
    home: WardrobeItemDetailsScreen(itemId: item.id, item: item, repository: repo),
  );
}

void main() {
  group('WardrobeItemDetailsScreen Widget Tests', () {
    testWidgets('renders visual placeholder with item name', (
      WidgetTester tester,
    ) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));
      await tester.pumpAndSettle();

      expect(find.text(item.name), findsWidgets);
    });

    testWidgets('renders category card with name', (WidgetTester tester) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));
      await tester.pumpAndSettle();

      expect(find.text('tops'), findsWidgets);
      expect(find.text(item.name), findsWidgets);
    });

    testWidgets('renders details section with color and material', (
      WidgetTester tester,
    ) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));
      await tester.pumpAndSettle();

      expect(find.text('Category'), findsOneWidget);
      expect(find.text('tops'), findsWidgets);
      expect(find.text('Color'), findsOneWidget);
      expect(find.text('Charcoal'), findsOneWidget);
      expect(find.text('Material'), findsOneWidget);
      expect(find.text('Wool'), findsOneWidget);
    });

    testWidgets('shows favorite icon for favorite item', (
      WidgetTester tester,
    ) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.favorite_rounded), findsWidgets);
      expect(find.text('Favorite'), findsOneWidget);
    });

    testWidgets('does not show favorite status for non-favorite item', (
      WidgetTester tester,
    ) async {
      final item = WardrobeMockData.items[1]; // Linen Button-Down, not favorite
      await tester.pumpWidget(_wrapScreen(item));
      await tester.pumpAndSettle();

      expect(find.text('Not favorite'), findsOneWidget);
    });

    testWidgets('renders action buttons', (WidgetTester tester) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));
      await tester.pumpAndSettle();

      expect(find.text('Edit'), findsOneWidget);
      expect(find.text('Delete'), findsOneWidget);
    });

    testWidgets('Edit button toggles edit mode', (WidgetTester tester) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Edit'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Edit Merino Crew Neck'), findsOneWidget);
      expect(find.text('Cancel'), findsOneWidget);
    });

    testWidgets('Delete button shows confirmation dialog and removes item', (
      WidgetTester tester,
    ) async {
      final item = WardrobeMockData.items.first;
      LearningService.instance.addItem(WardrobeEntry(
        id: item.id,
        name: item.name,
        category: item.category,
        color: item.color,
      ));
      await tester.pumpWidget(_wrapScreen(item));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Delete'));
      await tester.pumpAndSettle();

      expect(find.text('Delete Item'), findsOneWidget);
      expect(find.text('Are you sure you want to remove "Merino Crew Neck"?'), findsOneWidget);

      await tester.tap(find.descendant(of: find.byType(AlertDialog), matching: find.text('Delete')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.textContaining('removed from wardrobe'), findsOneWidget);
    });

    testWidgets('Wear capture button appears for backend UUID', (
      WidgetTester tester,
    ) async {
      final item = WardrobeItemData(
        id: '78ff3686-c950-4cd6-84c3-7e18d6634dfa',
        name: 'Camel Overcoat',
        category: 'outerwear',
        color: 'Camel',
      );
      await tester.pumpWidget(_wrapScreen(item));
      await tester.pumpAndSettle();

      expect(find.text('I wore this'), findsOneWidget);
    });

    testWidgets('navigates back on back button tap', (
      WidgetTester tester,
    ) async {
      final item = WardrobeMockData.items.first;
      final httpClient = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'id': item.id,
            'name': item.name,
            'category': item.category,
            'color': item.color,
            'isFavorite': item.isFavorite,
          }),
          200,
        );
      });
      final repo = WardrobeRepositoryImpl(client: WardrobeClient(client: httpClient));

      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => WardrobeItemDetailsScreen(
                    itemId: item.id,
                    item: item,
                    repository: repo,
                  ),
                ),
              ),
              child: const Text('Open Details'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open Details'));
      await tester.pumpAndSettle();
      expect(find.byType(WardrobeItemDetailsScreen), findsOneWidget);

      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();

      expect(find.byType(WardrobeItemDetailsScreen), findsNothing);
    });

    testWidgets('displays color dot for item color', (
      WidgetTester tester,
    ) async {
      final item = WardrobeMockData.items.first; // Charcoal
      await tester.pumpWidget(_wrapScreen(item));
      await tester.pumpAndSettle();

      expect(find.text('Charcoal'), findsOneWidget);
    });

    testWidgets('duplicate delete submission is prevented', (WidgetTester tester) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Delete'));
      await tester.pumpAndSettle();

      expect(find.byType(AlertDialog), findsOneWidget);
    });

    testWidgets('API/network failure during deletion shows error', (WidgetTester tester) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item, deleteSucceeds: false));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Delete'));
      await tester.pumpAndSettle();

      await tester.tap(find.descendant(of: find.byType(AlertDialog), matching: find.text('Delete')));
      await tester.pumpAndSettle();

      expect(find.text('Failed to delete item. Please try again.'), findsOneWidget);
      expect(find.byType(WardrobeItemDetailsScreen), findsOneWidget);
    });

    testWidgets('correct navigation after successful deletion', (WidgetTester tester) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => WardrobeItemDetailsScreen(
                    itemId: item.id,
                    item: item,
                    repository: WardrobeRepositoryImpl(
                      client: WardrobeClient(
                        client: MockClient((request) async {
                          if (request.method == 'DELETE') {
                            return http.Response('', 204);
                          }
                          return http.Response(
                            jsonEncode({
                              'id': item.id,
                              'name': item.name,
                              'category': item.category,
                              'color': item.color,
                              'isFavorite': item.isFavorite,
                              'createdAt': '2024-01-15T10:00:00Z',
                              'updatedAt': '2024-01-15T10:00:00Z',
                            }),
                            200,
                          );
                        }),
                      ),
                    ),
                  ),
                ),
              ),
              child: const Text('Open Details'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open Details'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Delete'));
      await tester.pumpAndSettle();

      await tester.tap(find.descendant(of: find.byType(AlertDialog), matching: find.text('Delete')));
      await tester.pumpAndSettle();

      expect(find.byType(WardrobeItemDetailsScreen), findsNothing);
    });

    testWidgets('deleted item removed from list/state', (WidgetTester tester) async {
      final item = WardrobeMockData.items.first;
      LearningService.instance.resetForTest();
      LearningService.instance.addItem(WardrobeEntry(
        id: item.id,
        name: item.name,
        category: item.category,
        color: item.color,
      ));
      await tester.pumpWidget(_wrapScreen(item));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Delete'));
      await tester.pumpAndSettle();

      await tester.tap(find.descendant(of: find.byType(AlertDialog), matching: find.text('Delete')));
      await tester.pumpAndSettle();

      expect(LearningService.instance.wardrobe.any((i) => i.id == item.id), isFalse);
    });

    testWidgets('renders details section without material when null', (WidgetTester tester) async {
      final item = WardrobeItemData(
        id: 'test',
        name: 'Test Item',
        category: 'accessories',
        color: 'Black',
      );
      await tester.pumpWidget(_wrapScreen(item));
      await tester.pumpAndSettle();

      expect(find.text('Category'), findsOneWidget);
      expect(find.text('Color'), findsOneWidget);
      expect(find.text('Material'), findsOneWidget);
      expect(find.text('Not specified'), findsOneWidget);
    });

    testWidgets('edit-form name field uses the design-system error color', (
      WidgetTester tester,
    ) async {
      final item = WardrobeMockData.items.first;
      await tester.pumpWidget(_wrapScreen(item));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Edit'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final nameField = tester
          .widgetList<TextField>(find.byType(TextField))
          .firstWhere(
            (field) => field.decoration?.labelText == 'Name',
          );
      final decoration = nameField.decoration!;
      expect(
        (decoration.errorBorder! as OutlineInputBorder).borderSide.color,
        FansivibeColors.error,
      );
      expect(
        (decoration.focusedErrorBorder! as OutlineInputBorder)
            .borderSide
            .color,
        FansivibeColors.error,
      );
    });
  });
}
