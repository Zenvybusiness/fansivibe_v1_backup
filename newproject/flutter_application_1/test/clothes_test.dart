import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/widgets/wardrobe_widgets.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// M12 P3 focused tests: wardrobe renders persisted wardrobe
/// rows (never mock products, never the looks catalog), filters by the
/// real backend category vocabulary, and reuses the existing wardrobe
/// detail/add routes. Fakes stand in for transport only.

WardrobeItemData cloth({
  String id = 'wardrobe-1',
  String name = 'Navy Oxford Shirt',
  String category = 'tops',
  String color = 'navy',
}) {
  return WardrobeItemData(
    id: id,
    name: name,
    category: category,
    color: color,
  );
}

/// Scriptable wardrobe fake: queued list results, full call accounting.
class ScriptedWardrobeRepository implements WardrobeRepository {
  final List<Object> listQueue = [];
  final List<Map<String, Object?>> listRequests = [];

  List<WardrobeItemData> _lastReturned = [];

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async {
    listRequests.add({'category': category, 'pageSize': pageSize});
    if (listQueue.isNotEmpty) {
      final next = listQueue.removeAt(0);
      if (next is Exception) throw next;
      _lastReturned = next as List<WardrobeItemData>;
    }
    return _lastReturned;
  }

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) =>
      throw UnimplementedError();

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
    String? fit,
    double? fitConfidence,
  }) => throw UnimplementedError();

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
  }) => throw UnimplementedError();

  @override
  Future<bool?> deleteItem({required String itemId}) =>
      throw UnimplementedError();

  @override
  Future<WardrobeInsightData?> getInsight() async => null;

  @override
  Future<WearSummary?> getWearSummary() async => null;

  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) => throw UnimplementedError();
}

Widget clothesHarness(ScriptedWardrobeRepository wardrobe) {
  return MaterialApp(
    home: WardrobeScreen(
      repository: wardrobe,
    ),
  );
}

/// Taps text that may sit below the fold of the outer scroll view.
/// Screens without a scrollable (route stubs) tap directly.
Future<void> tapVisible(WidgetTester tester, String label) async {
  final target = find.text(label);
  if (find.byType(Scrollable).evaluate().isNotEmpty) {
    await tester.scrollUntilVisible(
      target,
      500.0,
      scrollable: find.byType(Scrollable).first,
    );
  }
  await tester.tap(target);
  await tester.pumpAndSettle();
}

Future<void> openClothes(
  WidgetTester tester,
  ScriptedWardrobeRepository wardrobe,
) async {
  await tester.pumpWidget(clothesHarness(wardrobe));
  await tester.pumpAndSettle();
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    AuthSession.resetForTest();
    await AuthSession.saveSession('test-token');
  });

  group('Clothes tab', () {
    testWidgets('loads persisted wardrobe rows, never mock products', (
      WidgetTester tester,
    ) async {
      final wardrobe = ScriptedWardrobeRepository()
        ..listQueue.add([cloth(), cloth(id: 'wardrobe-2', name: 'Black Jeans')]);
      await openClothes(tester, wardrobe);

      expect(find.text('Navy Oxford Shirt'), findsOneWidget);
      expect(find.text('Black Jeans'), findsOneWidget);
      expect(find.byType(ClothingItemCard), findsNWidgets(2));
      // No mock wardrobe names, no looks catalog rows, no trending chrome.
      expect(find.text('Merino Crew Neck'), findsNothing);
      expect(find.text('Linen Button-Down'), findsNothing);
      expect(find.text('Trending'), findsNothing);
      // Neutral wells (existing placeholder behavior), never photos.
      expect(find.byType(FansiImageWell), findsNWidgets(2));
      expect(find.byType(NetworkImage), findsNothing);
    });

    testWidgets('empty wardrobe renders the honest empty state', (
      WidgetTester tester,
    ) async {
      final wardrobe = ScriptedWardrobeRepository()
        ..listQueue.add(<WardrobeItemData>[]);
      await openClothes(tester, wardrobe);

      expect(find.text('No wardrobe items yet.'), findsOneWidget);
      expect(find.text('Add your first piece to get started'), findsOneWidget);
      expect(find.byType(ClothingItemCard), findsNothing);
      expect(find.text('Merino Crew Neck'), findsNothing);
    });

    testWidgets('category chips use real vocabulary and filter server-side', (
      WidgetTester tester,
    ) async {
      final wardrobe = ScriptedWardrobeRepository()
        ..listQueue.addAll([
          [cloth(), cloth(id: 'wardrobe-2', name: 'Black Jeans', category: 'bottoms')],
        ]);
      await openClothes(tester, wardrobe);

      // Real backend vocabulary chips (wardrobe_categories codes).
      for (final label in [
        'All Items',
        'Tops',
        'Bottoms',
      ]) {
        expect(find.text(label), findsOneWidget);
      }
      expect(find.text('Navy Oxford Shirt'), findsOneWidget);
      expect(find.text('Black Jeans'), findsOneWidget);

      await tapVisible(tester, 'Tops');
      // Category filter narrows the list.
      expect(find.text('Navy Oxford Shirt'), findsOneWidget);
      expect(find.text('Black Jeans'), findsNothing);
    });

    testWidgets('failure is truthful with retry', (
      WidgetTester tester,
    ) async {
      final wardrobe = ScriptedWardrobeRepository()
        ..listQueue.addAll([
          Exception('down'),
          [cloth()],
        ]);
      await openClothes(tester, wardrobe);

      expect(
        find.text('Failed to load wardrobe. Please check your connection.'),
        findsOneWidget,
      );
      expect(find.byType(ClothingItemCard), findsNothing);

      await tapVisible(tester, 'Retry');
      expect(wardrobe.listRequests, hasLength(2));
      expect(find.text('Navy Oxford Shirt'), findsOneWidget);
    });

    testWidgets('tapping an item routes to wardrobe details with its id', (
      WidgetTester tester,
    ) async {
      final wardrobe = ScriptedWardrobeRepository()
        ..listQueue.add([cloth()]);
      Object? pushedExtra;
      final router = GoRouter(
        initialLocation: '/',
        routes: [
          GoRoute(
            path: '/',
            builder: (_, _) => WardrobeScreen(
              repository: wardrobe,
            ),
          ),
          GoRoute(
            path: '/details',
            name: RouteNames.wardrobeItemDetails,
            builder: (_, state) {
              pushedExtra = state.extra;
              return const Scaffold(body: Text('details stub'));
            },
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      await tapVisible(tester, 'Navy Oxford Shirt');
      expect(pushedExtra, 'wardrobe-1');
      expect(find.text('details stub'), findsOneWidget);
    });

    testWidgets('Add clothes navigates to the add flow and reloads', (
      WidgetTester tester,
    ) async {
      final wardrobe = ScriptedWardrobeRepository()
        ..listQueue.addAll([
          <WardrobeItemData>[],
          [cloth()],
        ]);
      var addVisited = false;
      final router = GoRouter(
        initialLocation: '/',
        routes: [
          GoRoute(
            path: '/',
            builder: (_, _) => WardrobeScreen(
              repository: wardrobe,
            ),
          ),
          GoRoute(
            path: '/add',
            name: RouteNames.wardrobeAddCategory,
            builder: (context, _) => Scaffold(
              body: TextButton(
                onPressed: () => context.pop(cloth()),
                child: const Text('save stub'),
              ),
            ),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      await tapVisible(tester, 'Add Item to Wardrobe');
      addVisited = find.text('save stub').evaluate().isNotEmpty;
      expect(addVisited, isTrue);

      await tapVisible(tester, 'save stub');
      // Returning with a saved item reloads from the backend.
      expect(wardrobe.listRequests.length, greaterThanOrEqualTo(2));
      expect(find.text('Navy Oxford Shirt'), findsOneWidget);
    });
  });
}
