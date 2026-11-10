import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/profile/data/saved_looks_models.dart';
import 'package:fansivibe/features/profile/data/saved_looks_repository.dart';
import 'package:fansivibe/features/profile/presentation/saved_look_details_screen.dart';
import 'package:fansivibe/features/profile/presentation/saved_looks_screen.dart';
import 'package:fansivibe/features/profile/presentation/widgets/saved_look_mosaic_image.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/ensemble_wear_confirmation_sheet.dart';
import 'package:fansivibe/features/wardrobe/presentation/widgets/wardrobe_widgets.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

// ---------------------------------------------------------------------------
// Test Doubles
// ---------------------------------------------------------------------------

class FakeSavedLooksRepo implements SavedLooksRepository {
  FakeSavedLooksRepo(this.rows);

  List<SavedLookItem> rows;
  int deleteCalls = 0;
  String? lastDeletedId;

  @override
  Future<SavedLookListPage?> listSavedLooks({
    int page = 1,
    int pageSize = 20,
    bool includeItems = true,
  }) async {
    return SavedLookListPage(
      items: List.of(rows),
      page: page,
      pageSize: pageSize,
      total: rows.length,
    );
  }

  @override
  Future<SavedLookItem?> getSavedLook({
    required String id,
    bool includeItems = true,
  }) async {
    return rows.where((r) => r.id == id).firstOrNull;
  }

  @override
  Future<SavedLookDeleteOutcome?> deleteSavedLook({required String id}) async {
    deleteCalls++;
    lastDeletedId = id;
    rows = rows.where((r) => r.id != id).toList();
    return SavedLookDeleteOutcome.deleted;
  }
}

class FakeWardrobeRepo implements WardrobeRepository {
  int logWearCalls = 0;
  List<String>? lastLoggedGarmentIds;

  @override
  Future<WearEventLogResponse?> logEnsembleWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async {
    logWearCalls++;
    lastLoggedGarmentIds = itemIds;
    final now = wornAt ?? DateTime.now();
    return WearEventLogResponse(
      wearGroupId: 'group-uuid-123',
      wears: itemIds
          .map(
            (id) => WearEvent(
              id: 'event-$id',
              wardrobeItemId: id,
              wornAt: now,
              wearGroupId: 'group-uuid-123',
              createdAt: now,
            ),
          )
          .toList(),
      wornAt: now,
      created: true,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

SavedLookItem _buildSampleLook({bool hasArchived = false}) {
  return SavedLookItem(
    id: 'look-uuid-1',
    title: 'Summer Seaside',
    sourceContext: 'outfit',
    snapshot: {
      'matchScore': 0.92,
      'occasion': 'Vacation Brunch',
      'colorHarmony': 'Navy & White',
      'reasons': ['Breathable linen blend', 'Crisp silhouette balance'],
      'selectedItemIds': [
        'a0000000-0000-0000-0000-000000000001',
        'a0000000-0000-0000-0000-000000000002',
      ],
    },
    items: [
      const HydratedGarmentItem(
        id: 'a0000000-0000-0000-0000-000000000001',
        name: 'Linen Button Down',
        category: 'tops',
        color: 'white',
        material: 'linen',
        isFavorite: true,
        fit: 'relaxed',
        fitConfidence: 0.9,
        reason: 'Breathable linen blend for warm weather.',
        isArchived: false,
      ),
      HydratedGarmentItem(
        id: 'a0000000-0000-0000-0000-000000000002',
        name: 'Navy Chino Shorts',
        category: 'bottoms',
        color: 'navy',
        material: 'cotton',
        isFavorite: false,
        fit: 'tailored',
        fitConfidence: 0.85,
        reason: 'Crisp silhouette balance.',
        isArchived: hasArchived,
      ),
    ],
    createdAt: DateTime(2026, 11, 2, 10, 0),
  );
}

Widget _wrap(Widget child) {
  final router = GoRouter(
    initialLocation: '/details',
    routes: [
      GoRoute(
        path: '/',
        builder: (context, state) => const Scaffold(body: Text('Root Screen')),
        routes: [GoRoute(path: 'details', builder: (context, state) => child)],
      ),
      GoRoute(
        path: '/login',
        name: RouteNames.signIn,
        builder: (context, state) => const Scaffold(body: Text('Login Screen')),
      ),
      GoRoute(
        path: '/wardrobe-details',
        name: RouteNames.wardrobeItemDetails,
        builder: (context, state) =>
            const Scaffold(body: Text('Wardrobe Details Screen')),
      ),
    ],
  );

  return MaterialApp.router(routerConfig: router, theme: ThemeData.dark());
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    AuthSession.resetForTest();
    await AuthSession.saveSession('saved-looks-test-token');
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    LocalStorage.resetForTest();
  });

  group('P1-2 Saved Look Models & JSON Serialization', () {
    test('HydratedGarmentItem fromJson and toJson round-trip correctly', () {
      final json = {
        'id': 'g-100',
        'name': 'Silk Shirt',
        'category': 'tops',
        'color': 'cream',
        'material': 'silk',
        'isFavorite': true,
        'imageRef': {'uploadId': 'up-1', 'objectKey': 'users/u1/k.webp'},
        'imageUrl': 'https://cdn.example.com/k.webp',
        'fit': 'relaxed',
        'fitConfidence': 0.95,
        'reason': 'Lustrous texture',
        'isArchived': false,
      };

      final item = HydratedGarmentItem.fromJson(json);
      expect(item.id, 'g-100');
      expect(item.name, 'Silk Shirt');
      expect(item.category, 'tops');
      expect(item.color, 'cream');
      expect(item.material, 'silk');
      expect(item.isFavorite, isTrue);
      expect(item.imageUrl, 'https://cdn.example.com/k.webp');
      expect(item.fitConfidence, 0.95);
      expect(item.reason, 'Lustrous texture');
      expect(item.isArchived, isFalse);

      final back = item.toJson();
      expect(back['id'], 'g-100');
      expect(back['isArchived'], isFalse);
      expect(back['fitConfidence'], 0.95);
    });

    test('SavedLookItem deserializes hydrated items array', () {
      final json = {
        'id': 'look-200',
        'title': 'Evening Ensemble',
        'sourceContext': 'outfit',
        'snapshot': {
          'matchScore': 0.88,
          'selectedItemIds': ['g-1', 'g-2'],
        },
        'createdAt': '2026-11-02T10:00:00.000Z',
        'items': [
          {
            'id': 'g-1',
            'name': 'Cashmere Sweater',
            'category': 'tops',
            'color': 'black',
            'isArchived': false,
          },
          {
            'id': 'g-2',
            'name': 'Vintage Wool Coat',
            'category': 'outerwear',
            'color': 'camel',
            'isArchived': true,
          },
        ],
      };

      final look = SavedLookItem.fromJson(json);
      expect(look.id, 'look-200');
      expect(look.items, isNotNull);
      expect(look.items!.length, 2);
      expect(look.items![0].name, 'Cashmere Sweater');
      expect(look.items![0].isArchived, isFalse);
      expect(look.items![1].name, 'Vintage Wool Coat');
      expect(look.items![1].isArchived, isTrue);
    });
  });

  group('P1-2 SavedLookMosaicImage Widget', () {
    testWidgets('Renders FansiImageWell fallback when items is empty', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          const SizedBox(
            width: 300,
            height: 200,
            child: SavedLookMosaicImage(
              items: [],
              fallbackIcon: Icons.checkroom_rounded,
              fallbackColor: Colors.amber,
            ),
          ),
        ),
      );

      expect(find.byType(FansiImageWell), findsOneWidget);
    });

    testWidgets('Renders 1 garment full tile', (tester) async {
      final items = [
        const HydratedGarmentItem(
          id: 'g-1',
          name: 'Tee',
          category: 'tops',
          color: 'white',
        ),
      ];

      await tester.pumpWidget(
        _wrap(
          SizedBox(
            width: 300,
            height: 200,
            child: SavedLookMosaicImage(
              items: items,
              fallbackIcon: Icons.checkroom_rounded,
              fallbackColor: Colors.amber,
            ),
          ),
        ),
      );

      expect(find.byType(WardrobeItemImage), findsOneWidget);
    });

    testWidgets('Renders 2 garments split side-by-side', (tester) async {
      final items = [
        const HydratedGarmentItem(
          id: 'g-1',
          name: 'Tee',
          category: 'tops',
          color: 'white',
        ),
        const HydratedGarmentItem(
          id: 'g-2',
          name: 'Jeans',
          category: 'bottoms',
          color: 'blue',
        ),
      ];

      await tester.pumpWidget(
        _wrap(
          SizedBox(
            width: 300,
            height: 200,
            child: SavedLookMosaicImage(
              items: items,
              fallbackIcon: Icons.checkroom_rounded,
              fallbackColor: Colors.amber,
            ),
          ),
        ),
      );

      expect(find.byType(WardrobeItemImage), findsNWidgets(2));
    });

    testWidgets('Renders 3 garments with 1 large and 2 stacked', (
      tester,
    ) async {
      final items = [
        const HydratedGarmentItem(
          id: 'g-1',
          name: 'Tee',
          category: 'tops',
          color: 'white',
        ),
        const HydratedGarmentItem(
          id: 'g-2',
          name: 'Jeans',
          category: 'bottoms',
          color: 'blue',
        ),
        const HydratedGarmentItem(
          id: 'g-3',
          name: 'Shoes',
          category: 'footwear',
          color: 'brown',
        ),
      ];

      await tester.pumpWidget(
        _wrap(
          SizedBox(
            width: 300,
            height: 200,
            child: SavedLookMosaicImage(
              items: items,
              fallbackIcon: Icons.checkroom_rounded,
              fallbackColor: Colors.amber,
            ),
          ),
        ),
      );

      expect(find.byType(WardrobeItemImage), findsNWidgets(3));
    });

    testWidgets('Renders 4 garments in 2x2 grid and shows archived badge', (
      tester,
    ) async {
      final items = [
        const HydratedGarmentItem(
          id: 'g-1',
          name: 'Tee',
          category: 'tops',
          color: 'white',
        ),
        const HydratedGarmentItem(
          id: 'g-2',
          name: 'Jeans',
          category: 'bottoms',
          color: 'blue',
          isArchived: true,
        ),
        const HydratedGarmentItem(
          id: 'g-3',
          name: 'Shoes',
          category: 'footwear',
          color: 'brown',
        ),
        const HydratedGarmentItem(
          id: 'g-4',
          name: 'Jacket',
          category: 'outerwear',
          color: 'black',
        ),
      ];

      await tester.pumpWidget(
        _wrap(
          SizedBox(
            width: 300,
            height: 200,
            child: SavedLookMosaicImage(
              items: items,
              fallbackIcon: Icons.checkroom_rounded,
              fallbackColor: Colors.amber,
            ),
          ),
        ),
      );

      expect(find.byType(WardrobeItemImage), findsNWidgets(4));
      expect(find.text('Archived'), findsOneWidget);
    });
  });

  group('P1-2 SavedLooksScreen Mosaic & Detail Navigation', () {
    testWidgets(
      'SavedLooksScreen renders mosaic image instead of generic well',
      (tester) async {
        final look = _buildSampleLook();
        final repo = FakeSavedLooksRepo([look]);

        await tester.pumpWidget(_wrap(SavedLooksScreen(repository: repo)));
        await tester.pumpAndSettle();

        expect(find.byType(SavedLookMosaicImage), findsOneWidget);
        expect(find.byType(WardrobeItemImage), findsNWidgets(2));
        expect(find.text('Summer Seaside'), findsOneWidget);
      },
    );
  });

  group('P1-2 SavedLookDetailsScreen Component Display & Interactions', () {
    testWidgets(
      'Renders outfit title, score badge, chips, reasons, and pieces',
      (tester) async {
        final look = _buildSampleLook();

        await tester.pumpWidget(_wrap(SavedLookDetailsScreen(look: look)));
        await tester.pumpAndSettle();

        expect(find.text('Summer Seaside'), findsOneWidget);
        expect(find.text('OUTFIT LOOK'), findsOneWidget);
        expect(find.text('92%'), findsOneWidget);
        expect(find.text('Vacation Brunch'), findsOneWidget);
        expect(find.text('Navy & White'), findsOneWidget);
        expect(find.text('WHY THIS WORKS'), findsOneWidget);
        expect(find.text('Linen Button Down'), findsOneWidget);
        expect(find.text('Navy Chino Shorts'), findsOneWidget);
        expect(find.text('Log Wear Today'), findsOneWidget);
      },
    );

    testWidgets('Renders archived piece clearly with notice banner', (
      tester,
    ) async {
      final look = _buildSampleLook(hasArchived: true);

      await tester.pumpWidget(_wrap(SavedLookDetailsScreen(look: look)));
      await tester.pumpAndSettle();

      expect(
        find.text('Archived piece (no longer in wardrobe)'),
        findsOneWidget,
      );
    });

    testWidgets(
      'Tapping archived garment shows info snackbar and does not navigate',
      (tester) async {
        final look = _buildSampleLook(hasArchived: true);

        await tester.pumpWidget(_wrap(SavedLookDetailsScreen(look: look)));
        await tester.pumpAndSettle();

        // Tap on the archived garment card (Navy Chino Shorts)
        await tester.tap(find.text('Navy Chino Shorts'));
        await tester.pumpAndSettle();

        expect(
          find.text('This piece was removed from your wardrobe.'),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'Log Wear Today opens confirmation sheet and logs wear on confirm',
      (tester) async {
        final look = _buildSampleLook();
        final wardrobeRepo = FakeWardrobeRepo();

        await tester.pumpWidget(
          _wrap(
            SavedLookDetailsScreen(
              look: look,
              wardrobeRepository: wardrobeRepo,
            ),
          ),
        );
        await tester.pumpAndSettle();

        // Tap Log Wear Today
        await tester.ensureVisible(find.text('Log Wear Today'));
        await tester.tap(find.text('Log Wear Today'));
        await tester.pumpAndSettle();

        // Confirmation sheet is displayed
        expect(find.byType(EnsembleWearConfirmationSheet), findsOneWidget);
        expect(find.text('RECORD ENSEMBLE WEAR'), findsOneWidget);
        expect(find.text('2 of 2 garments selected'), findsOneWidget);

        // Confirm wear in bottom sheet
        await tester.tap(find.byKey(const Key('confirm_wear_button')));
        await tester.pumpAndSettle();

        // Dismiss success view in sheet
        await tester.tap(find.byKey(const Key('wear_success_done_button')));
        await tester.pumpAndSettle();

        // Verify wear logging was called on repository
        expect(wardrobeRepo.logWearCalls, 1);
        expect(wardrobeRepo.lastLoggedGarmentIds, [
          'a0000000-0000-0000-0000-000000000001',
          'a0000000-0000-0000-0000-000000000002',
        ]);

        // Success feedback is shown and button state reflects worn today
        expect(
          find.text('Look successfully logged as worn today!'),
          findsOneWidget,
        );
        expect(find.text('Worn Today ✓'), findsOneWidget);
      },
    );

    testWidgets('Log Wear Today excludes archived garments from wear sheet', (
      tester,
    ) async {
      final look = _buildSampleLook(hasArchived: true);
      final wardrobeRepo = FakeWardrobeRepo();

      await tester.pumpWidget(
        _wrap(
          SavedLookDetailsScreen(look: look, wardrobeRepository: wardrobeRepo),
        ),
      );
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Log Wear Today'));
      await tester.tap(find.text('Log Wear Today'));
      await tester.pumpAndSettle();

      // Confirmation sheet only has 1 active garment
      expect(find.byType(EnsembleWearConfirmationSheet), findsOneWidget);
      expect(find.text('RECORD ENSEMBLE WEAR'), findsOneWidget);
      expect(find.text('1 of 1 garments selected'), findsOneWidget);

      await tester.tap(find.byKey(const Key('confirm_wear_button')));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('wear_success_done_button')));
      await tester.pumpAndSettle();

      expect(wardrobeRepo.logWearCalls, 1);
      // Only active garment 1 was passed!
      expect(wardrobeRepo.lastLoggedGarmentIds, [
        'a0000000-0000-0000-0000-000000000001',
      ]);
    });

    testWidgets('Remove look calls delete on repository and pops route', (
      tester,
    ) async {
      final look = _buildSampleLook();
      final savedLooksRepo = FakeSavedLooksRepo([look]);

      await tester.pumpWidget(
        _wrap(
          SavedLookDetailsScreen(
            look: look,
            savedLooksRepository: savedLooksRepo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Tap remove button
      await tester.ensureVisible(find.text('Remove from Saved Looks'));
      await tester.tap(find.text('Remove from Saved Looks'));
      await tester.pumpAndSettle();

      expect(savedLooksRepo.deleteCalls, 1);
      expect(savedLooksRepo.lastDeletedId, 'look-uuid-1');
    });

    testWidgets('Tapping active garment navigates to wardrobe item details', (
      tester,
    ) async {
      final look = _buildSampleLook();

      await tester.pumpWidget(_wrap(SavedLookDetailsScreen(look: look)));
      await tester.pumpAndSettle();

      // Tap on the active garment card (Linen Button Down)
      await tester.tap(find.text('Linen Button Down'));
      await tester.pumpAndSettle();

      expect(find.text('Wardrobe Details Screen'), findsOneWidget);
    });

    testWidgets('Guest mode prompts sign in on Log Wear Today', (tester) async {
      final look = _buildSampleLook();
      final wardrobeRepo = FakeWardrobeRepo();

      // Clear authentication to simulate guest
      AuthSession.resetForTest();
      await AuthSession.clearSession();

      await tester.pumpWidget(
        _wrap(
          SavedLookDetailsScreen(look: look, wardrobeRepository: wardrobeRepo),
        ),
      );
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Log Wear Today'));
      await tester.tap(find.text('Log Wear Today'));
      await tester.pumpAndSettle();

      // Zero wear calls executed
      expect(wardrobeRepo.logWearCalls, 0);
      expect(find.text('Login Screen'), findsOneWidget);

      // Restore session
      await AuthSession.saveSession('saved-looks-test-token');
    });
  });
}
