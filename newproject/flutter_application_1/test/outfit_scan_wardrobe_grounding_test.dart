import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_analysis_screen.dart';
import 'package:fansivibe/features/wardrobe/data/garment_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/add_wardrobe_item_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

class _RecordingWardrobeRepo implements WardrobeRepository {
  _RecordingWardrobeRepo({this.shouldSucceed = true});

  final bool shouldSucceed;
  int createCalls = 0;
  Map<String, dynamic>? lastPayload;

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
    createCalls++;
    lastPayload = {
      'name': name,
      'category': category,
      'color': color,
      'material': material,
      'imageRef': imageRef,
      'fit': fit,
      'fitConfidence': fitConfidence,
    };
    if (!shouldSucceed) {
      return null;
    }
    return WardrobeItemData(
      id: 'mock-uuid-1234',
      name: name,
      category: category,
      color: color,
      material: material,
    );
  }

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
  Future<WardrobeItemData?> getItem({required String itemId}) async => null;

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
  Future<bool?> deleteItem({required String itemId}) async => true;

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

  @override
  Future<WearEventLogResponse?> logEnsembleWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) =>
      logWear(
        itemIds: itemIds,
        wornAt: wornAt,
        idempotencyKey: idempotencyKey,
      );

}

Map<String, dynamic> _buildOutfitResult({
  Map<String, dynamic>? garment,
  List<Map<String, dynamic>>? detectedItems,
  Map<String, dynamic>? appearance,
  String? profilePersistence = 'saved',
}) {
  return {
    'appearance': appearance ?? {
      'faceShape': 'Oval',
      'skinTone': 'Warm Medium',
      'bodyType': 'Athletic',
      'styleType': 'Modern Classic',
    },
    'confidence': 0.88,
    'needs_more_data': false,
    if (profilePersistence != null) 'profile_persistence': profilePersistence,
    'recommendations': {
      'top': {
        'id': 'rec-1',
        'name': 'Casual Smart Look',
        'matchScore': 0.92,
        'description': 'Recommended look',
      },
    },
    if (garment != null) 'garment': garment,
    if (detectedItems != null) 'detected_items': detectedItems,
  };
}

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: FansivibeTheme.darkTheme,
    home: child,
  );
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    AuthSession.resetForTest();
    LocalStorage.savedLocally = false;
    LocalStorage.authToken = 'mock-auth-token';
  });

  group('Outfit Scan Garment Grounding & Honest Presentation', () {
    testWidgets('surfaces honest confidence with AI estimate label', (
      WidgetTester tester,
    ) async {
      final result = _buildOutfitResult(
        garment: {
          'category': 'tops',
          'subcategory': 'Crewneck',
          'color': 'Navy',
          'confidence': 0.84,
          'needs_review': false,
        },
      );

      await tester.pumpWidget(_wrap(OutfitAnalysisScreen(analysisResult: result)));
      await tester.pumpAndSettle();

      expect(find.text('Confidence: 84% (AI estimate)'), findsOneWidget);
      expect(find.textContaining('probability'), findsNothing);
      expect(find.textContaining('calibrated'), findsNothing);
    });

    testWidgets('displays review state when needs_review is true', (
      WidgetTester tester,
    ) async {
      final result = _buildOutfitResult(
        garment: {
          'category': 'tops',
          'color': 'Black',
          'confidence': 0.65,
          'needs_review': true,
        },
      );

      await tester.pumpWidget(_wrap(OutfitAnalysisScreen(analysisResult: result)));
      await tester.pumpAndSettle();

      expect(find.text('Needs Review'), findsOneWidget);
      expect(find.text('Confirmed'), findsNothing);
    });

    testWidgets('displays confirmed state when needs_review is false', (
      WidgetTester tester,
    ) async {
      final result = _buildOutfitResult(
        garment: {
          'category': 'tops',
          'color': 'White',
          'confidence': 0.92,
          'needs_review': false,
        },
      );

      await tester.pumpWidget(_wrap(OutfitAnalysisScreen(analysisResult: result)));
      await tester.pumpAndSettle();

      expect(find.text('Confirmed'), findsOneWidget);
      expect(find.text('Needs Review'), findsNothing);
    });

    testWidgets('renders Confidence unavailable when confidence is missing', (
      WidgetTester tester,
    ) async {
      final result = _buildOutfitResult(
        garment: {
          'category': 'bottoms',
          'color': 'Indigo',
          'needs_review': true,
        },
      );

      await tester.pumpWidget(_wrap(OutfitAnalysisScreen(analysisResult: result)));
      await tester.pumpAndSettle();

      expect(find.text('Confidence unavailable'), findsOneWidget);
      expect(find.textContaining('% (AI estimate)'), findsNothing);
    });

    testWidgets('does not fabricate missing optional garment attributes', (
      WidgetTester tester,
    ) async {
      // Missing pattern, material, fit, and style
      final result = _buildOutfitResult(
        garment: {
          'category': 'outerwear',
          'subcategory': 'Bomber Jacket',
          'color': 'Olive',
          'confidence': 0.79,
          'needs_review': false,
        },
      );

      await tester.pumpWidget(_wrap(OutfitAnalysisScreen(analysisResult: result)));
      await tester.pumpAndSettle();

      // Present attributes are shown
      expect(find.text('outerwear'), findsOneWidget);
      expect(find.text('Bomber Jacket'), findsOneWidget);
      expect(find.text('Olive'), findsOneWidget);

      // Missing optional attributes are omitted, never fabricated
      expect(find.textContaining('Pattern:'), findsNothing);
      expect(find.textContaining('Material:'), findsNothing);
      expect(find.textContaining('Fit:'), findsNothing);
      expect(find.textContaining('Style:'), findsNothing);
    });

    testWidgets('renders all optional attributes when present', (
      WidgetTester tester,
    ) async {
      final result = _buildOutfitResult(
        garment: {
          'category': 'tops',
          'subcategory': 'Oxford Shirt',
          'color': 'Light Blue',
          'pattern': 'Striped',
          'material': 'Cotton',
          'fit': 'Slim',
          'style': 'Smart Casual',
          'confidence': 0.88,
          'needs_review': false,
        },
      );

      await tester.pumpWidget(_wrap(OutfitAnalysisScreen(analysisResult: result)));
      await tester.pumpAndSettle();

      expect(find.text('tops'), findsOneWidget);
      expect(find.text('Oxford Shirt'), findsOneWidget);
      expect(find.text('Light Blue'), findsOneWidget);
      expect(find.text('Striped'), findsOneWidget);
      expect(find.text('Cotton'), findsWidgets);
      expect(find.text('Slim'), findsWidgets);
      expect(find.text('Smart Casual'), findsOneWidget);
    });
  });

  group('Add to Wardrobe Flow from Outfit Scan', () {
    testWidgets('selecting a detected garment opens prefilled AddWardrobeItemScreen', (
      WidgetTester tester,
    ) async {
      final result = _buildOutfitResult(
        garment: {
          'category': 'tops',
          'subcategory': 'T-Shirt',
          'color': 'Navy',
          'material': 'Cotton',
          'fit': 'Regular',
          'pattern': 'Solid',
          'confidence': 0.85,
          'needs_review': false,
        },
      );

      await tester.pumpWidget(_wrap(OutfitAnalysisScreen(analysisResult: result)));
      await tester.pumpAndSettle();

      final addButton = find.text('Add to Wardrobe');
      await tester.scrollUntilVisible(
        addButton,
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(addButton);
      await tester.pumpAndSettle();

      // Verifies navigation to AddWardrobeItemScreen
      expect(find.text('Add Tops'), findsOneWidget);
      expect(find.textContaining('AI suggestion'), findsOneWidget);
      expect(find.text('Save Item'), findsOneWidget);

      // Verifies prefilled values
      expect(find.text('T-Shirt'), findsWidgets);
      expect(find.text('Navy'), findsWidgets);
      expect(find.text('Regular'), findsWidgets);
      expect(find.text('Cotton'), findsWidgets);
    });

    testWidgets('user can edit prefilled fields before explicit confirmation', (
      WidgetTester tester,
    ) async {
      final repo = _RecordingWardrobeRepo();
      final initialGarment = GarmentAnalysisResult(
        category: 'tops',
        subcategory: 'T-Shirt',
        color: 'Navy',
        material: 'Cotton',
        fit: 'Regular',
        confidence: 0.85,
        needsReview: false,
      );

      final categoryConfig = AddItemConfig.categoryConfigFor('tops');
      await tester.pumpWidget(
        _wrap(
          AddWardrobeItemScreen(
            category: categoryConfig,
            initialGarmentResult: initialGarment,
            repository: repo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Change Type to 'Hoodie'
      await tester.scrollUntilVisible(
        find.text('Hoodie'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Hoodie'));
      await tester.pumpAndSettle();

      // Change Fit to 'Slim'
      await tester.scrollUntilVisible(
        find.text('Slim'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Slim'));
      await tester.pumpAndSettle();

      // Explicit confirmation
      await tester.scrollUntilVisible(
        find.text('Save Item'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Save Item'));
      await tester.pumpAndSettle();

      expect(repo.createCalls, equals(1));
      expect(repo.lastPayload?['category'], equals('tops'));
      expect(repo.lastPayload?['name'], equals('Cotton Hoodie'));
      expect(repo.lastPayload?['fit'], equals('Slim'));
    });

    testWidgets('explicit confirmation: canceling or navigating back leaves wardrobe untouched', (
      WidgetTester tester,
    ) async {
      final repo = _RecordingWardrobeRepo();
      final initialGarment = GarmentAnalysisResult(
        category: 'tops',
        subcategory: 'T-Shirt',
        color: 'Navy',
        material: 'Cotton',
      );

      final categoryConfig = AddItemConfig.categoryConfigFor('tops');
      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: Scaffold(
            body: Builder(
              builder: (context) {
                return ElevatedButton(
                  onPressed: () {
                    Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => AddWardrobeItemScreen(
                          category: categoryConfig,
                          initialGarmentResult: initialGarment,
                          repository: repo,
                        ),
                      ),
                    );
                  },
                  child: const Text('Open Add'),
                );
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Open Add'));
      await tester.pumpAndSettle();
      expect(find.text('Add Tops'), findsOneWidget);

      // Back navigation without confirmation
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();

      // Nothing was persisted
      expect(repo.createCalls, equals(0));
      expect(find.text('Open Add'), findsOneWidget);
    });

    testWidgets('successful wardrobe persistence provides accurate confirmation and Done returns item', (
      WidgetTester tester,
    ) async {
      final repo = _RecordingWardrobeRepo(shouldSucceed: true);
      final initialGarment = GarmentAnalysisResult(
        category: 'tops',
        subcategory: 'T-Shirt',
        color: 'Navy',
        material: 'Cotton',
        fit: 'Regular',
        confidence: 0.85,
        needsReview: false,
      );

      final categoryConfig = AddItemConfig.categoryConfigFor('tops');
      await tester.pumpWidget(
        _wrap(
          AddWardrobeItemScreen(
            category: categoryConfig,
            initialGarmentResult: initialGarment,
            repository: repo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.text('Save Item'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Save Item'));
      await tester.pumpAndSettle();

      expect(repo.createCalls, equals(1));
      expect(find.text('Saved Cotton T-Shirt to your wardrobe.'), findsOneWidget);
      expect(find.text('Done'), findsOneWidget);
    });

    testWidgets('failed wardrobe persistence shows honest error banner without pretending success', (
      WidgetTester tester,
    ) async {
      final failingRepo = _RecordingWardrobeRepo(shouldSucceed: false);
      final initialGarment = GarmentAnalysisResult(
        category: 'tops',
        subcategory: 'T-Shirt',
        color: 'Navy',
      );

      final categoryConfig = AddItemConfig.categoryConfigFor('tops');
      await tester.pumpWidget(
        _wrap(
          AddWardrobeItemScreen(
            category: categoryConfig,
            initialGarmentResult: initialGarment,
            repository: failingRepo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.text('Save Item'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Save Item'));
      await tester.pumpAndSettle();

      expect(failingRepo.createCalls, equals(1));
      // Honest failure banner is displayed
      expect(find.text('Failed to add item. Please try again.'), findsOneWidget);
      // Screen remains open for retry
      expect(find.text('Save Item'), findsOneWidget);
    });

    testWidgets('existing manual wardrobe entry remains fully functional', (
      WidgetTester tester,
    ) async {
      final repo = _RecordingWardrobeRepo();
      final categoryConfig = AddItemConfig.categoryConfigFor('tops');

      // Opened without initialGarmentResult (manual flow)
      await tester.pumpWidget(
        _wrap(
          AddWardrobeItemScreen(
            category: categoryConfig,
            repository: repo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Manual flow buttons remain visible
      expect(find.text('Take Photo'), findsOneWidget);
      expect(find.text('Choose from Gallery'), findsOneWidget);
      expect(find.text('Detected from outfit scan'), findsNothing);

      // Select type
      await tester.scrollUntilVisible(
        find.text('T-Shirt'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('T-Shirt'));
      await tester.pumpAndSettle();

      // Select color
      await tester.scrollUntilVisible(
        find.text('Black'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Black'));
      await tester.pumpAndSettle();

      // Select fit
      await tester.scrollUntilVisible(
        find.text('Regular'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Regular'));
      await tester.pumpAndSettle();

      // Save item
      await tester.scrollUntilVisible(
        find.text('Save Item'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Save Item'));
      await tester.pumpAndSettle();

      expect(repo.createCalls, equals(1));
      expect(repo.lastPayload?['name'], equals('T-Shirt'));
      expect(repo.lastPayload?['color'], equals('Black'));
      expect(repo.lastPayload?['fit'], equals('Regular'));
      expect(repo.lastPayload?['imageRef'], isNull);
    });
  });

  group('Separation of Garment and Person-Profile Attributes', () {
    testWidgets('Save Appearance Profile does not write garment data to person profile', (
      WidgetTester tester,
    ) async {
      final result = _buildOutfitResult(
        appearance: {
          'faceShape': 'Oval',
          'skinTone': 'Warm Medium',
        },
        garment: {
          'category': 'tops',
          'color': 'Navy',
          'material': 'Cotton',
          'fit': 'Regular',
        },
      );

      await tester.pumpWidget(_wrap(OutfitAnalysisScreen(analysisResult: result)));
      await tester.pumpAndSettle();

      // The button is accurately labeled Save Appearance Profile
      final saveAppearanceBtn = find.text('Save Appearance Profile');
      expect(saveAppearanceBtn, findsOneWidget);

      await tester.scrollUntilVisible(
        saveAppearanceBtn,
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(saveAppearanceBtn);
      await tester.pumpAndSettle();

      // Discloses that appearance was saved, and garments are saved separately
      expect(
        find.text('Appearance profile saved to your account. Garments can be added to your wardrobe above.'),
        findsOneWidget,
      );
    });

    testWidgets('Save Appearance Profile honesty when appearance branch failed', (
      WidgetTester tester,
    ) async {
      final result = {
        'appearance_error': {'reason': 'no_face_detected'},
        'garment': {
          'category': 'tops',
          'color': 'Navy',
        },
        'confidence': 0.82,
        'needs_more_data': false,
      };

      await tester.pumpWidget(_wrap(OutfitAnalysisScreen(analysisResult: result)));
      await tester.pumpAndSettle();

      final saveAppearanceBtn = find.text('Save Appearance Profile');
      await tester.scrollUntilVisible(
        saveAppearanceBtn,
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(saveAppearanceBtn);
      await tester.pumpAndSettle();

      // Honestly informs that no appearance profile was detected
      expect(
        find.text('No appearance profile was detected in this photo. Garments can be added to your wardrobe above.'),
        findsOneWidget,
      );
      expect(
        find.text('Appearance profile saved to your account. Garments can be added to your wardrobe above.'),
        findsNothing,
      );
    });
  });

  group('Stage 1D Batch 3A.1 Persistence Outcome Integrity (D-B3A-01)', () {
    testWidgets('saved state shows accurate confirmation and checkmark icon', (
      WidgetTester tester,
    ) async {
      final result = _buildOutfitResult(
        profilePersistence: 'saved',
        appearance: {
          'faceShape': 'Oval',
          'skinTone': 'Warm Medium',
        },
      );

      await tester.pumpWidget(_wrap(OutfitAnalysisScreen(analysisResult: result)));
      await tester.pumpAndSettle();

      // Renders with checkmark icon for confirmed persistence
      expect(find.byIcon(Icons.check_circle_outline), findsOneWidget);

      final saveBtn = find.text('Save Appearance Profile');
      await tester.scrollUntilVisible(
        saveBtn,
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(saveBtn);
      await tester.pumpAndSettle();

      expect(
        find.text('Appearance profile saved to your account. Garments can be added to your wardrobe above.'),
        findsOneWidget,
      );
    });

    testWidgets('not_saved state shows clear persistence failure and error icon', (
      WidgetTester tester,
    ) async {
      final result = _buildOutfitResult(
        profilePersistence: 'not_saved',
        appearance: {
          'faceShape': 'Oval',
          'skinTone': 'Warm Medium',
        },
      );

      await tester.pumpWidget(_wrap(OutfitAnalysisScreen(analysisResult: result)));
      await tester.pumpAndSettle();

      // Renders with error icon for persistence failure
      expect(find.byIcon(Icons.error_outline), findsOneWidget);

      final saveBtn = find.text('Save Appearance Profile');
      await tester.scrollUntilVisible(
        saveBtn,
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(saveBtn);
      await tester.pumpAndSettle();

      // Shows honest persistence failure message
      expect(
        find.text('Appearance profile could not be saved to your account. Garments can be added to your wardrobe above.'),
        findsOneWidget,
      );
      // NEVER claims success
      expect(
        find.text('Appearance profile saved to your account. Garments can be added to your wardrobe above.'),
        findsNothing,
      );
    });

    testWidgets('not_applicable state explains guest preview does not save profile', (
      WidgetTester tester,
    ) async {
      final result = _buildOutfitResult(
        profilePersistence: 'not_applicable',
        appearance: {
          'faceShape': 'Oval',
          'skinTone': 'Warm Medium',
        },
      );

      await tester.pumpWidget(_wrap(OutfitAnalysisScreen(analysisResult: result)));
      await tester.pumpAndSettle();

      final saveBtn = find.text('Save Appearance Profile');
      await tester.scrollUntilVisible(
        saveBtn,
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(saveBtn);
      await tester.pumpAndSettle();

      // Explains guest preview does not save a personal profile
      expect(
        find.text('Guest preview does not save a personal appearance profile. Garments can be added to your wardrobe above.'),
        findsOneWidget,
      );
      // NEVER claims success
      expect(
        find.text('Appearance profile saved to your account. Garments can be added to your wardrobe above.'),
        findsNothing,
      );
    });

    testWidgets('unknown state explains persistence could not be verified', (
      WidgetTester tester,
    ) async {
      final result = _buildOutfitResult(
        profilePersistence: 'unknown',
        appearance: {
          'faceShape': 'Oval',
          'skinTone': 'Warm Medium',
        },
      );

      await tester.pumpWidget(_wrap(OutfitAnalysisScreen(analysisResult: result)));
      await tester.pumpAndSettle();

      final saveBtn = find.text('Save Appearance Profile');
      await tester.scrollUntilVisible(
        saveBtn,
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(saveBtn);
      await tester.pumpAndSettle();

      // Explains persistence could not be verified
      expect(
        find.text('Appearance profile persistence could not be verified. Garments can be added to your wardrobe above.'),
        findsOneWidget,
      );
      // NEVER claims success
      expect(
        find.text('Appearance profile saved to your account. Garments can be added to your wardrobe above.'),
        findsNothing,
      );
    });

    testWidgets('missing profile_persistence defaults to unknown and never claims success', (
      WidgetTester tester,
    ) async {
      final result = _buildOutfitResult(
        profilePersistence: null,
        appearance: {
          'faceShape': 'Oval',
          'skinTone': 'Warm Medium',
        },
      );

      await tester.pumpWidget(_wrap(OutfitAnalysisScreen(analysisResult: result)));
      await tester.pumpAndSettle();

      final saveBtn = find.text('Save Appearance Profile');
      await tester.scrollUntilVisible(
        saveBtn,
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(saveBtn);
      await tester.pumpAndSettle();

      expect(
        find.text('Appearance profile persistence could not be verified. Garments can be added to your wardrobe above.'),
        findsOneWidget,
      );
      expect(
        find.text('Appearance profile saved to your account. Garments can be added to your wardrobe above.'),
        findsNothing,
      );
    });

    testWidgets('Flutter never displays success message across any non-saved states', (
      WidgetTester tester,
    ) async {
      const nonSavedStates = [
        'not_saved',
        'not_applicable',
        'unknown',
        null,
        'unrecognized_value',
      ];

      for (final state in nonSavedStates) {
        final result = _buildOutfitResult(
          profilePersistence: state,
          appearance: {
            'faceShape': 'Oval',
            'skinTone': 'Warm Medium',
          },
        );

        await tester.pumpWidget(_wrap(OutfitAnalysisScreen(analysisResult: result)));
        await tester.pumpAndSettle();

        final saveBtn = find.text('Save Appearance Profile');
        await tester.scrollUntilVisible(
          saveBtn,
          200.0,
          scrollable: find.byType(Scrollable).first,
        );
        ScaffoldMessenger.of(tester.element(saveBtn)).clearSnackBars();
        await tester.pumpAndSettle();

        await tester.tap(saveBtn);
        await tester.pumpAndSettle();

        expect(
          find.text('Appearance profile saved to your account. Garments can be added to your wardrobe above.'),
          findsNothing,
          reason: 'Non-saved state "$state" must NEVER claim profile was saved',
        );
      }
    });
  });
}
