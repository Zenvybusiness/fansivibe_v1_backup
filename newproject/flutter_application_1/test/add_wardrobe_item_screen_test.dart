import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/add_wardrobe_item_screen.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';

Widget createTestApp(
  AddItemCategoryConfig category, {
  WardrobeRepository? repository,
}) {
  return MaterialApp(
    theme: FansivibeTheme.darkTheme,
    home: AddWardrobeItemScreen(category: category, repository: repository),
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

    testWidgets('saves item and pops with data when valid (repository-backed)', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        createTestApp(topsCategory, repository: _MockAddRepo(success: true)),
      );

      // Select a type
      await tester.tap(find.text('T-Shirt'));
      await tester.pumpAndSettle();

      // Select a color
      await tester.scrollUntilVisible(
        find.text('Black'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
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
      await tester.scrollUntilVisible(
        find.text('Save Item'),
        300.0,
        scrollable: find.byType(Scrollable).first,
      );
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

    testWidgets('shows loading indicator during submission', (
      WidgetTester tester,
    ) async {
      final completer = Completer<WardrobeItemData?>();
      final repo = _CompleterAddRepo(completer);
      await tester.pumpWidget(createTestApp(topsCategory, repository: repo));

      await tester.tap(find.text('T-Shirt'));
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.text('Black'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Black'));
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.text('Save Item'),
        300.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Save Item'));
      await tester.pump();

      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      completer.complete(null);
      await tester.pumpAndSettle();
    });

    testWidgets('shows error message on API failure', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        createTestApp(topsCategory, repository: _MockAddRepo(success: false)),
      );

      await tester.tap(find.text('T-Shirt'));
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.text('Black'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Black'));
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.text('Save Item'),
        300.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Save Item'));
      await tester.pumpAndSettle();

      expect(find.text('Failed to add item. Please try again.'), findsOneWidget);
    });
  });
}

class _MockAddRepo implements WardrobeRepository {
  _MockAddRepo({this.success = true});
  final bool success;

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
  }) async {
    if (!success) return null;
    return WardrobeItemData(
      id: 'mock-uuid-1',
      name: name,
      category: category,
      color: color,
      material: material,
    );
  }

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async => null;
  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async => const [];
  @override
  Future<WardrobeItemData?> updateItem({
    required String itemId,
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
  }) async => null;
  @override
  Future<bool?> deleteItem({required String itemId}) async => null;
  @override
  Future<WardrobeInsightData?> getInsight() async => null;
  @override
  Future<WearSummary?> getWearSummary() async => null;
  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async => null;
}

class _CompleterAddRepo implements WardrobeRepository {
  _CompleterAddRepo(this.completer);
  final Completer<WardrobeItemData?> completer;

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
  }) => completer.future;

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async => null;
  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async => const [];
  @override
  Future<WardrobeItemData?> updateItem({
    required String itemId,
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
  }) async => null;
  @override
  Future<bool?> deleteItem({required String itemId}) async => null;
  @override
  Future<WardrobeInsightData?> getInsight() async => null;
  @override
  Future<WearSummary?> getWearSummary() async => null;
  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async => null;
}