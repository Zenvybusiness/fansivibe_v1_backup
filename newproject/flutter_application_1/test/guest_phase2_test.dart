import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/features/discover/data/discover_models.dart';
import 'package:fansivibe/features/discover/data/discover_repository.dart';
import 'package:fansivibe/features/discover/presentation/discover_screen.dart';
import 'package:fansivibe/features/discover/presentation/look_details_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/face_processing_screen.dart';
import 'package:fansivibe/features/outfit_builder/outfit_builder.dart';
import 'package:fansivibe/features/outfit_builder/presentation/outfit_generation_screen.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_processing_screen.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/presentation/add_wardrobe_item_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_item_details_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_screen.dart';
import 'package:fansivibe/features/profile/data/saved_looks_models.dart';
import 'package:fansivibe/features/profile/data/saved_looks_repository.dart';
import 'package:fansivibe/features/profile/presentation/preferences_screen.dart';
import 'package:fansivibe/features/profile/presentation/profile_screen.dart';
import 'package:fansivibe/features/profile/presentation/saved_looks_screen.dart';
import 'package:fansivibe/features/home/data/today_look_models.dart';
import 'package:fansivibe/features/home/data/today_look_repository.dart';
import 'package:fansivibe/features/home/presentation/daily_outfit_screen.dart';
import 'package:fansivibe/features/home/presentation/home_screen.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

class _CountingSummaryRepository implements LearningSummaryRepository {
  int calls = 0;

  @override
  Future<LearningSummary?> getSummary() async {
    calls++;
    return null;
  }
}

class _CountingTodayLookRepository implements TodayLookRepository {
  int calls = 0;

  @override
  Future<TodayLookResult> getTodayLook() async {
    calls++;
    return const TodayLookResult.failure(TodayLookFailure.networkError);
  }

  @override
  Future<TodayLookResult> regenerateTodayLook({String? seed}) async {
    calls++;
    return const TodayLookResult.failure(TodayLookFailure.networkError);
  }

  @override
  Future<SavedTodayLook?> saveTodayLook({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async {
    calls++;
    return null;
  }
}

class _CountingWardrobeRepository implements WardrobeRepository {
  int calls = 0;

  @override
  Future<WardrobeInsightData?> getInsight() async {
    calls++;
    return null;
  }

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async {
    calls++;
    return [];
  }

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async {
    calls++;
    return null;
  }

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
  }) async {
    calls++;
    return null;
  }

  @override
  Future<WardrobeItemData?> updateItem({
    required String itemId,
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
  }) async {
    calls++;
    return null;
  }

  @override
  Future<bool?> deleteItem({required String itemId}) async {
    calls++;
    return null;
  }

  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async {
    calls++;
    return null;
  }

  @override
  Future<WearSummary?> getWearSummary() async {
    calls++;
    return null;
  }
}

Future<void> _initGuest() async {
  SharedPreferences.setMockInitialValues({});
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
  AuthSession.resetForTest();
  await AuthSession.clearSession();
  LearningService.instance.resetForTest();
  LocalStorage.displayName = null;
  LocalStorage.onboardingComplete = false;
  // Explicit guest (Continue Without Account): no session token.
  LocalStorage.savedLocally = true;
  LocalStorage.analysisCached = true;
}

class _CountingDiscoverRepository implements DiscoverRepository {
  int feedCalls = 0;
  int detailCalls = 0;
  int forYouCalls = 0;

  @override
  Future<DiscoverFeedResult> getLookFeed({
    String? occasion,
    String? style,
    String? fit,
    String? cursor,
    int? limit,
  }) async {
    feedCalls++;
    return const DiscoverFeedResult.failure(DiscoverFailure.networkError);
  }

  @override
  Future<LookDetailResult> getLookDetail({required String lookId}) async {
    detailCalls++;
    return const LookDetailResult.failure(DiscoverFailure.networkError);
  }

  @override
  Future<ForYouFeedResult> getForYouFeed({String? cursor, int? limit}) async {
    forYouCalls++;
    return const ForYouFeedResult.failure(DiscoverFailure.networkError);
  }
}

class _CountingOutfitRepository implements OutfitBuilderRepository {
  int genCalls = 0;

  @override
  Future<OutfitResult> generateOutfit({
    required String occasion,
    required String mood,
    required String fit,
    required String colorPalette,
    String? seed,
  }) async {
    genCalls++;
    throw StateError('must not be called for guests');
  }

  @override
  Future<SavedOutfit?> saveOutfit({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async {
    throw StateError('must not be called for guests');
  }
}

class _CountingSavedLooksRepository implements SavedLooksRepository {
  int calls = 0;

  @override
  Future<SavedLookListPage?> listSavedLooks({
    int page = 1,
    int pageSize = 20,
  }) async {
    calls++;
    return null;
  }

  @override
  Future<SavedLookDeleteOutcome?> deleteSavedLook({
    required String id,
  }) async {
    calls++;
    return null;
  }
}

void main() {
  group('Phase 2 guest Home', () {
    setUp(_initGuest);

    testWidgets('guest Home shows local score, never backend slots', (
      WidgetTester tester,
    ) async {
      final summary = _CountingSummaryRepository();
      final today = _CountingTodayLookRepository();
      final wardrobe = _CountingWardrobeRepository();
      await tester.pumpWidget(
        MaterialApp(
          home: HomeScreen(
            summaryRepository: summary,
            todayLookRepository: today,
            wardrobeRepository: wardrobe,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Local score card (24 seeded items -> 60 + 20 = 80), no streak
      // invention, Today's Look stays account-only.
      expect(find.text('Style Score'), findsOneWidget);
      expect(find.text('80'), findsOneWidget);
      expect(find.textContaining('on this device'), findsOneWidget);
      expect(find.text('Style Streak'), findsNothing);
      // Today's Look stays account-only: its wall keeps the Sign In CTA.
      expect(find.text("Today's Look"), findsOneWidget);
      expect(find.text('Sign In'), findsOneWidget);
      expect(summary.calls, isZero);
      expect(today.calls, isZero);
      expect(wardrobe.calls, isZero);
    });

    testWidgets('guest Daily Outfit renders sign-in prompt, never fetches', (
      WidgetTester tester,
    ) async {
      final today = _CountingTodayLookRepository();
      await tester.pumpWidget(
        MaterialApp(
          home: DailyOutfitScreen(todayLookRepository: today),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text("Today's Look"), findsOneWidget);
      expect(find.text('Sign In'), findsOneWidget);
      expect(today.calls, isZero);
    });
  });

  group('Phase 2 guest Discover', () {
    setUp(_initGuest);

    testWidgets('guest Discover renders sign-in prompt, never fetches', (
      WidgetTester tester,
    ) async {
      final repository = _CountingDiscoverRepository();
      final wardrobe = _CountingWardrobeRepository();
      await tester.pumpWidget(
        MaterialApp(
          home: DiscoverScreen(
            repository: repository,
            wardrobeRepository: wardrobe,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Discover'), findsOneWidget);
      expect(find.text('Discover looks'), findsOneWidget);
      expect(find.text('Sign In'), findsOneWidget);
      expect(repository.feedCalls, isZero);
      expect(repository.forYouCalls, isZero);
      expect(wardrobe.calls, isZero);
    });

    testWidgets('guest Look Details renders sign-in prompt, never fetches', (
      WidgetTester tester,
    ) async {
      final repository = _CountingDiscoverRepository();
      await tester.pumpWidget(
        MaterialApp(
          home: LookDetailsScreen(
            lookId: 'classic_pompadour',
            repository: repository,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Look Details'), findsWidgets);
      expect(find.text('Sign In'), findsOneWidget);
      expect(repository.detailCalls, isZero);
    });

    testWidgets('guest Clothes tab shows on-device wardrobe, never fetches', (
      WidgetTester tester,
    ) async {
      final repository = _CountingDiscoverRepository();
      final wardrobe = _CountingWardrobeRepository();
      await tester.pumpWidget(
        MaterialApp(
          home: DiscoverScreen(
            repository: repository,
            wardrobeRepository: wardrobe,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Clothes'));
      await tester.pumpAndSettle();

      expect(find.text('Merino Crew Neck'), findsOneWidget);
      expect(find.text('Sign In'), findsNothing);
      expect(repository.feedCalls, isZero);
      expect(repository.forYouCalls, isZero);
      expect(wardrobe.calls, isZero);
    });
  });

  group('Phase 2 guest AI Stylist', () {
    setUp(_initGuest);

    testWidgets('null run id never polls: honest error, no request', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        const MaterialApp(home: OutfitProcessingScreen(runId: null)),
      );
      // Bounded pumps only: the indeterminate spinner animates forever,
      // so pumpAndSettle would never settle.
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text('No run ID available'), findsOneWidget);
      expect(find.text('Back to Scan'), findsOneWidget);
    });

    testWidgets('guest generation renders sign-in prompt, never derives', (
      WidgetTester tester,
    ) async {
      final repository = _CountingOutfitRepository();
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitGenerationScreen(
            occasion: 'office',
            mood: 'classic',
            fit: 'tailored',
            colorPalette: 'warm',
            outfitRepository: repository,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Build Outfit'), findsOneWidget);
      expect(find.text('Sign In'), findsOneWidget);
      expect(repository.genCalls, isZero);
    });

    testWidgets('guest hairstyle processing renders sign-in, never submits', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        const MaterialApp(home: FaceProcessingScreen()),
      );
      await tester.pumpAndSettle();

      expect(find.text('Hairstyle Analysis'), findsWidgets);
      expect(find.text('Sign In'), findsOneWidget);
    });
  });

  group('Phase 2 guest Wardrobe', () {
    setUp(_initGuest);

    testWidgets('guest Wardrobe shows on-device items, never fetches', (
      WidgetTester tester,
    ) async {
      final repository = _CountingWardrobeRepository();
      await tester.pumpWidget(
        MaterialApp(home: WardrobeScreen(repository: repository)),
      );
      await tester.pumpAndSettle();

      expect(find.text('Merino Crew Neck'), findsOneWidget);
      expect(find.text('Add Item to Wardrobe'), findsOneWidget);
      expect(find.text('Your Wardrobe'), findsNothing);
      expect(find.text('Sign In'), findsNothing);
      expect(repository.calls, isZero);
    });

    testWidgets('guest item details opens on-device, never fetches', (
      WidgetTester tester,
    ) async {
      final repository = _CountingWardrobeRepository();
      await tester.pumpWidget(
        MaterialApp(
          home: WardrobeItemDetailsScreen(
            itemId: '1',
            repository: repository,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Merino Crew Neck'), findsWidgets);
      expect(find.text('Sign In'), findsNothing);
      expect(repository.calls, isZero);
    });

    testWidgets('guest add-item saves on-device with a local id', (
      WidgetTester tester,
    ) async {
      final category =
          AddItemConfig.categories.firstWhere((c) => c.id == 'tops');
      await tester.pumpWidget(
        MaterialApp(home: AddWardrobeItemScreen(category: category)),
      );
      await tester.pumpAndSettle();

      Future<void> tapVisible(Finder finder) async {
        await tester.scrollUntilVisible(
          finder,
          200,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(finder);
        await tester.pump();
      }

      await tapVisible(find.text(category.types.first));
      await tapVisible(find.text(AddItemConfig.colors.first.name));
      await tapVisible(find.text('Save Item'));
      await tester.pumpAndSettle();

      final created = LearningService.instance.wardrobe.where(
        (e) => e.id.startsWith('local-'),
      );
      expect(created, isNotEmpty);
      expect(created.first.name, category.types.first);
    });

    testWidgets('guest item edit persists on-device (favorite toggle)', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        const MaterialApp(home: WardrobeItemDetailsScreen(itemId: '2')),
      );
      // Bounded pumps only: the edit form shows an indeterminate
      // progress indicator while editable, so pumpAndSettle never
      // settles (pre-existing behavior, unchanged).
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.scrollUntilVisible(
        find.text('Edit'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Edit'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      await tester.scrollUntilVisible(
        find.text('Favorite'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Favorite'));
      await tester.pump();
      await tester.tap(find.byIcon(Icons.save_rounded));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final updated = LearningService.instance.wardrobe.firstWhere(
        (e) => e.id == '2',
      );
      expect(updated.isFavorite, isTrue);
    });
  });

  group('Phase 2 guest Profile', () {
    setUp(_initGuest);

    testWidgets('guest Profile shows on-device status, never fetches', (
      WidgetTester tester,
    ) async {
      final summary = _CountingSummaryRepository();
      await tester.pumpWidget(
        MaterialApp(home: ProfileScreen(summaryRepository: summary)),
      );
      await tester.pumpAndSettle();

      expect(find.text('Style Profile'), findsWidgets);
      expect(find.text('On this device'), findsOneWidget);
      expect(find.text('Sign In'), findsOneWidget);
      expect(summary.calls, isZero);
    });

    testWidgets('guest Saved Looks shows honest empty, never fetches', (
      WidgetTester tester,
    ) async {
      final repository = _CountingSavedLooksRepository();
      await tester.pumpWidget(
        MaterialApp(home: SavedLooksScreen(repository: repository)),
      );
      await tester.pumpAndSettle();

      expect(find.text('No saved looks yet'), findsOneWidget);
      expect(find.text('Sign In'), findsNothing);
      expect(repository.calls, isZero);
    });

    testWidgets('guest preference saves on-device only', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        const MaterialApp(home: PreferencesScreen()),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Business'));
      await tester.pumpAndSettle();

      expect(
        LearningService.instance.preferredOccasions,
        contains('Business'),
      );
      expect(find.textContaining('this device only'), findsOneWidget);
    });
  });
}
