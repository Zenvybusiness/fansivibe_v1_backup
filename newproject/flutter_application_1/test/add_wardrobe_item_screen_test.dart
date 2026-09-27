import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
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

    testWidgets('saves item and shows post-save actions, Done pops with data', (
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

      // Screen stays with the post-save actions (C-04), not popped.
      expect(find.text('Add Tops'), findsOneWidget);
      expect(find.text('Build with this item'), findsOneWidget);

      // Done pops with the created item.
      await tester.scrollUntilVisible(
        find.text('Done'),
        300.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();

      expect(find.text('Add Tops'), findsNothing);
    });

    testWidgets('Build action hidden for guest-local ids', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        createTestApp(
          topsCategory,
          repository: _MockAddRepo(success: true, itemId: 'local-123'),
        ),
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

      // Saved, but no build action for a non-UUID id; Done still pops.
      expect(find.text('Build with this item'), findsNothing);
      expect(find.text('Done'), findsOneWidget);
      await tester.scrollUntilVisible(
        find.text('Done'),
        300.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();
      expect(find.text('Add Tops'), findsNothing);
    });

    testWidgets('Build with this item navigates with the saved UUID', (
      WidgetTester tester,
    ) async {
      const savedUuid = '78ff3686-c950-4cd6-84c3-7e18d6634dfa';
      Map<String, String>? seenExtra;
      final router = GoRouter(
        initialLocation: '/',
        routes: [
          GoRoute(
            path: '/',
            builder: (context, state) => AddWardrobeItemScreen(
              category: topsCategory,
              repository: _MockAddRepo(success: true, itemId: savedUuid),
            ),
          ),
          GoRoute(
            path: '/build-outfit',
            name: RouteNames.buildOutfit,
            builder: (context, state) {
              seenExtra = state.extra as Map<String, String>?;
              return const Text('builder reached');
            },
          ),
        ],
      );
      await tester.pumpWidget(
        MaterialApp.router(
          theme: FansivibeTheme.darkTheme,
          routerConfig: router,
        ),
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

      await tester.scrollUntilVisible(
        find.text('Build with this item'),
        300.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Build with this item'));
      await tester.pumpAndSettle();

      // Navigation carries exactly the saved wardrobe UUID.
      expect(seenExtra, {'preferredItemId': savedUuid});
      expect(find.text('builder reached'), findsOneWidget);

      // Back navigation returns normally.
      router.pop();
      await tester.pumpAndSettle();
      expect(find.text('Add Tops'), findsOneWidget);
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
  _MockAddRepo({this.success = true, this.itemId = 'mock-uuid-1'});
  final bool success;
  final String itemId;

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
    String? fit,
    double? fitConfidence,
  }) async {
    if (!success) return null;
    return WardrobeItemData(
      id: itemId,
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
    String? fit,
    double? fitConfidence,
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
    String? fit,
    double? fitConfidence,
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
    String? fit,
    double? fitConfidence,
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