import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/app.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/widgets/wardrobe_widgets.dart';

/// Creates a [FansivibeApp] booted directly into the main shell so tab
/// navigation can be exercised without re-running the onboarding Entry flow.
Widget _freshApp() {
  return FansivibeApp(
    router: GoRouter(initialLocation: '/home', routes: appRoutes),
  );
}

void main() {
  group('WardrobeScreen Widget Tests', () {
    testWidgets('renders wardrobe header with title, count, and style type', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      // Navigate to Wardrobe tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('My Wardrobe'), findsOneWidget);
      expect(find.text('24 items'), findsWidgets);
      expect(find.text('Modern Minimalist'), findsOneWidget);
    });

    testWidgets('hides insight card when backend is unreachable', (
      WidgetTester tester,
    ) async {
      // Full-app wiring uses the live repository; with no backend the
      // insight future resolves to null and the card must stay hidden —
      // the static mock must never pose as live intelligence.
      await tester.pumpWidget(_freshApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('AI Insight'), findsNothing);
      expect(
        find.textContaining('Your wardrobe is balanced across seasons'),
        findsNothing,
      );
      expect(find.text('View Analysis'), findsNothing);
      // The wardrobe item list is unaffected by the missing insight.
      expect(find.text('My Wardrobe'), findsOneWidget);
      expect(find.text('Merino Crew Neck'), findsOneWidget);
    });

    testWidgets('renders category filters', (WidgetTester tester) async {
      await tester.pumpWidget(_freshApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify category filter pills render
      expect(find.byType(CategoryTile), findsWidgets);
      // Verify a visible category chip
      expect(find.text('All Items'), findsWidgets);
      expect(find.text('Tops'), findsOneWidget);
    });

    testWidgets('renders clothing item grid with all items', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify section title (appears as chip and section title)
      expect(find.text('All Items'), findsWidgets);
      expect(find.text('24 items'), findsWidgets);

      // Verify some items appear
      expect(find.text('Merino Crew Neck'), findsOneWidget);
      expect(find.text('Leather Chelsea Boots'), findsOneWidget);
    });

    testWidgets('filtering by category shows only matching items', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      // Tap the Tops category filter
      await tester.ensureVisible(find.text('Tops'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Tops'));
      await tester.pumpAndSettle();

      // Should show "Tops" section title with correct count
      expect(find.text('Tops'), findsWidgets);
      expect(find.text('8 items'), findsOneWidget);
    });

    testWidgets('Add Item button navigates to category selection', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      // Scroll to bottom
      await tester.scrollUntilVisible(
        find.text('Add Item to Wardrobe'),
        500.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Add Item to Wardrobe'));
      await tester.pumpAndSettle();

      expect(find.text('Add Item'), findsOneWidget);
      expect(find.text('Select a Category'), findsOneWidget);
      expect(find.text('Tops'), findsOneWidget);
    });

    testWidgets('item tap navigates to item details screen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      // Scroll down to make items visible
      await tester.ensureVisible(find.text('Merino Crew Neck'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Merino Crew Neck'));
      await tester.pumpAndSettle();

      // Should show details screen with item info
      expect(find.text('Details'), findsOneWidget);
      expect(find.text('Color'), findsOneWidget);
      expect(find.text('Charcoal'), findsOneWidget);
      expect(find.text('Material'), findsOneWidget);
      expect(find.text('Wool'), findsOneWidget);
      expect(find.text('Edit Item'), findsOneWidget);
      expect(find.text('Add to Outfit'), findsOneWidget);
      expect(find.text('Delete'), findsOneWidget);
    });

    testWidgets('Wardrobe screen is scrollable', (WidgetTester tester) async {
      await tester.pumpWidget(_freshApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      // Scroll down to reveal all sections
      await tester.drag(
        find.byType(SingleChildScrollView),
        const Offset(0, -1000),
      );
      await tester.pumpAndSettle();

      // All major sections should render (the insight card stays hidden
      // with no backend; see 'hides insight card when backend is unreachable').
      expect(find.text('My Wardrobe'), findsOneWidget);
      expect(find.byType(CategoryTile), findsWidgets);
      expect(find.text('Add Item to Wardrobe'), findsOneWidget);
    });
  });

  group('Wardrobe Feature Widgets Tests', () {
    testWidgets('WardrobeHeader renders correctly', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const Scaffold(
            body: WardrobeHeader(totalItems: 10, styleType: 'Casual'),
          ),
        ),
      );

      expect(find.text('My Wardrobe'), findsOneWidget);
      expect(find.text('10 items'), findsOneWidget);
      expect(find.text('Casual'), findsOneWidget);
    });

    testWidgets('WardrobeInsightCard renders with action', (
      WidgetTester tester,
    ) async {
      bool tapped = false;
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: WardrobeInsightCard(
              data: WardrobeInsightData.mock,
              onActionPressed: () => tapped = true,
            ),
          ),
        ),
      );

      expect(find.text('Wardrobe Health'), findsOneWidget);
      expect(find.text('AI Insight'), findsOneWidget);
      expect(find.text('View Analysis'), findsOneWidget);

      await tester.tap(find.text('View Analysis'));
      await tester.pump();
      expect(tapped, true);
    });

    testWidgets('ClothingItemCard renders item info', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: ClothingItemCard(item: WardrobeMockData.items.first),
          ),
        ),
      );

      expect(find.text('Merino Crew Neck'), findsOneWidget);
      expect(find.text('Charcoal'), findsOneWidget);
    });

    testWidgets('ClothingItemCard shows favorite icon for favorite items', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: ClothingItemCard(item: WardrobeMockData.items.first),
          ),
        ),
      );

      expect(find.byIcon(Icons.favorite_rounded), findsOneWidget);
    });

    testWidgets('ClothingItemCard does not show favorite for non-favorites', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: ClothingItemCard(
              item:
                  WardrobeMockData.items[1], // Linen Button-Down, not favorite
            ),
          ),
        ),
      );

      expect(find.byIcon(Icons.favorite_rounded), findsNothing);
    });

    testWidgets('renders real backend items from repository', (
      WidgetTester tester,
    ) async {
      final realBackendItems = [
        const WardrobeItemData(
          id: 'backend-uuid-1',
          name: 'Real Custom Blazer',
          category: 'outerwear',
          color: 'Black',
          material: 'Wool',
          isFavorite: true,
        ),
        const WardrobeItemData(
          id: 'backend-uuid-2',
          name: 'Real Graphic Tee',
          category: 'tops',
          color: 'White',
        ),
      ];

      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: WardrobeScreen(
            repository: _MockWardrobeRepository(items: realBackendItems),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('My Wardrobe'), findsOneWidget);
      expect(find.text('Real Custom Blazer'), findsOneWidget);
      expect(find.text('Real Graphic Tee'), findsOneWidget);
      expect(find.text('2 items'), findsWidgets);
    });

    testWidgets('renders empty state when backend items list is empty', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: WardrobeScreen(
            repository: _MockWardrobeRepository(items: const []),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('No items in this category yet'), findsOneWidget);
      expect(find.text('Add your first piece to get started'), findsOneWidget);
      expect(find.text('0 items'), findsWidgets);
    });

    testWidgets('renders error state and retry button on repository error', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: WardrobeScreen(
            repository: _MockWardrobeRepository(throwError: true),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text('Failed to load wardrobe. Please check your connection.'),
        findsOneWidget,
      );
      expect(find.text('Retry'), findsOneWidget);
    });
  });
}

class _MockWardrobeRepository implements WardrobeRepository {
  _MockWardrobeRepository({
    this.items = const [],
    this.throwError = false,
  });

  final List<WardrobeItemData> items;
  final bool throwError;

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async {
    if (throwError) throw Exception('Network error');
    if (category == null || category == 'all') return items;
    return items.where((i) => i.category == category).toList();
  }

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async => null;

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
  }) async => null;

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
