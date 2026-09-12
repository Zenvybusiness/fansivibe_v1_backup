import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/app.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/outfit_builder/outfit_builder.dart';
import 'package:fansivibe/features/outfit_builder/presentation/build_outfit_screen.dart';
import 'package:fansivibe/features/outfit_builder/presentation/outfit_generation_screen.dart';
import 'package:fansivibe/features/outfit_builder/presentation/outfit_recommendation_screen.dart';
import 'package:fansivibe/features/outfit_builder/presentation/widgets/outfit_builder_widgets.dart';

/// Creates a [FansivibeApp] booted directly into the main shell (Stylist tab)
/// to avoid re-running the onboarding Entry flow in navigation tests.
Widget _freshApp() {
  return FansivibeApp(
    router: GoRouter(initialLocation: '/stylist', routes: appRoutes),
  );
}

const String _uuid1 = '78ff3686-c950-4cd6-84c3-7e18d6634dfa';
const String _uuid2 = '4412f646-56a9-4afa-8717-b330da03b3d0';
const String _uuid3 = '9d8f2c1a-3b4e-4f5a-8c6d-7e8f9a0b1c2d';

Map<String, dynamic> _wire({String title = 'Office Outfit'}) => {
  'title': title,
  'matchScore': 0.87,
  'components': [
    {
      'id': _uuid1,
      'name': 'Navy Blazer',
      'category': 'outerwear',
      'color': 'navy',
      'material': 'wool',
      'reason': 'Chosen outerwear piece for your Office outfit',
    },
    {
      'id': _uuid2,
      'name': 'White Tee',
      'category': 'tops',
      'color': 'white',
      'reason': 'Chosen tops piece for your Office outfit',
    },
    {
      'id': _uuid3,
      'name': 'Dark Jeans',
      'category': 'bottoms',
      'color': 'indigo',
      'material': 'denim',
      'reason': 'Chosen bottoms piece for your Office outfit',
    },
  ],
  'reasons': [
    'Picked for a Office occasion',
    'Covers 3 categories: tops, bottoms, outerwear',
  ],
  'colorHarmony': 'warm palette across 3 pieces: navy, white, indigo.',
  'bodyFit': 'Assembled for a tailored fit across 3 pieces.',
  'occasionMatch': 'Matched for Office across 3 categories.',
  'styleScoreImpact': '87% ensemble match from 3 owned pieces.',
  'improvementSuggestion': 'Consider adding footwear to complete the coverage.',
  'selectedOccasion': 'office',
  'selectedMood': 'classic',
  'selectedColorPalette': 'warm',
};

Map<String, dynamic> _savedWire(Map<String, dynamic> snapshot) => {
  'id': 'b3e1a2c4-5d6f-47a8-b9c0-d1e2f3a4b5c6',
  'lookId': null,
  'title': 'Office Outfit',
  'sourceContext': 'outfit',
  'snapshot': snapshot,
  'sourceRunId': null,
  'createdAt': '2030-08-15T10:00:00.000Z',
};

OutfitRecommendation _rec(Map<String, dynamic> wire) =>
    OutfitRecommendation.fromJson(wire);

const OutfitGenerateRequest _request = OutfitGenerateRequest(
  occasion: 'office',
  mood: 'classic',
  fit: 'tailored',
  colorPalette: 'warm',
);

/// Scriptable fake: scripted results, full call accounting, no network.
class ScriptedOutfitRepository implements OutfitBuilderRepository {
  ScriptedOutfitRepository();

  Future<OutfitResult> Function()? genHandler;
  Future<SavedOutfit?> Function()? saveHandler;

  int genCalls = 0;
  int saveCalls = 0;
  final List<String?> genSeeds = [];
  final List<String> saveTitles = [];
  final List<Map<String, dynamic>> saveSnapshots = [];
  final List<String> saveKeys = [];

  @override
  Future<OutfitResult> generateOutfit({
    required String occasion,
    required String mood,
    required String fit,
    required String colorPalette,
    String? seed,
  }) {
    genCalls += 1;
    genSeeds.add(seed);
    return genHandler!();
  }

  @override
  Future<SavedOutfit?> saveOutfit({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) {
    saveCalls += 1;
    saveTitles.add(title);
    saveSnapshots.add(snapshot);
    saveKeys.add(idempotencyKey);
    return saveHandler!();
  }
}

Widget _generationWith(ScriptedOutfitRepository repo) {
  return MaterialApp(
    home: OutfitGenerationScreen(
      occasion: 'office',
      mood: 'classic',
      fit: 'tailored',
      colorPalette: 'warm',
      outfitRepository: repo,
    ),
  );
}

/// Full generation → recommendation flow through a test router using one
/// shared fake repository.
Widget _flowApp(ScriptedOutfitRepository repo) {
  return MaterialApp.router(
    routerConfig: GoRouter(
      initialLocation: '/gen',
      routes: [
        GoRoute(
          path: '/gen',
          builder: (context, state) => OutfitGenerationScreen(
            occasion: 'office',
            mood: 'classic',
            fit: 'tailored',
            colorPalette: 'warm',
            outfitRepository: repo,
          ),
          routes: [
            GoRoute(
              path: 'rec',
              name: RouteNames.outfitRecommendation,
              builder: (context, state) {
                final data = state.extra as Map<String, dynamic>;
                return OutfitRecommendationScreen(
                  recommendation: OutfitRecommendation.fromJson(
                    Map<String, dynamic>.from(data['recommendation'] as Map),
                  ),
                  request: OutfitGenerateRequest.fromJson(
                    Map<String, dynamic>.from(data['request'] as Map),
                  ),
                  outfitRepository: repo,
                );
              },
            ),
          ],
        ),
      ],
    ),
  );
}

Widget _recommendationWith(
  ScriptedOutfitRepository repo,
  OutfitRecommendation rec,
) {
  return MaterialApp(
    home: OutfitRecommendationScreen(
      recommendation: rec,
      request: _request,
      outfitRepository: repo,
    ),
  );
}

void main() {
  group('BuildOutfitScreen Widget Tests', () {
    testWidgets('renders app bar and header', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const BuildOutfitScreen()));

      // "Build Outfit" appears in both the app bar and the build button.
      expect(find.text('Build Outfit'), findsNWidgets(2));
      expect(find.text('Create Your Look'), findsOneWidget);
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
    });

    testWidgets('renders all four option sections', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const BuildOutfitScreen()));

      expect(find.text('Occasion'), findsOneWidget);
      expect(find.text('Mood'), findsOneWidget);
      expect(find.text('Preferred Fit'), findsOneWidget);
      expect(find.text('Color Palette'), findsOneWidget);
    });

    testWidgets('render all option chips', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const BuildOutfitScreen()));

      expect(find.text('Casual'), findsOneWidget);
      expect(find.text('Office'), findsOneWidget);
      expect(find.text('Date'), findsOneWidget);
      expect(find.text('Party'), findsOneWidget);
      expect(find.text('Travel'), findsOneWidget);

      expect(find.text('Minimal'), findsOneWidget);
      expect(find.text('Bold'), findsOneWidget);
      expect(find.text('Classic'), findsOneWidget);
      expect(find.text('Eclectic'), findsOneWidget);

      expect(find.text('Slim'), findsOneWidget);
      expect(find.text('Relaxed'), findsOneWidget);
      expect(find.text('Tailored'), findsOneWidget);

      expect(find.text('Monochrome'), findsOneWidget);
      expect(find.text('Warm'), findsOneWidget);
      expect(find.text('Cool'), findsOneWidget);
    });

    testWidgets('build button is disabled when no selections made', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const BuildOutfitScreen()));

      final buildButton = find.widgetWithText(FilledButton, 'Build Outfit');
      expect(buildButton, findsOneWidget);
      expect(tester.widget<FilledButton>(buildButton).onPressed, isNull);
    });

    testWidgets('build button enables after all selections', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const BuildOutfitScreen()));

      await tester.tap(find.text('Casual'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Classic'), 200);
      await tester.tap(find.text('Classic'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Tailored'), 200);
      await tester.tap(find.text('Tailored'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Warm'), 200);
      await tester.tap(find.text('Warm'));
      await tester.pump();

      final buildButton = find.widgetWithText(FilledButton, 'Build Outfit');
      expect(buildButton, findsOneWidget);
      expect(tester.widget<FilledButton>(buildButton).onPressed, isNotNull);
    });

    testWidgets('selecting an option shows check icon', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const BuildOutfitScreen()));

      await tester.tap(find.text('Casual'));
      await tester.pump();

      expect(find.byIcon(Icons.check_circle_rounded), findsAtLeast(1));
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const BuildOutfitScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });

  group('BuildOutfitScreen Navigation', () {
    testWidgets('build button navigates to generation screen via go_router', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text('Build Outfit'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Casual'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Classic'), 200);
      await tester.tap(find.text('Classic'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Tailored'), 200);
      await tester.tap(find.text('Tailored'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Warm'), 200);
      await tester.tap(find.text('Warm'));
      await tester.pump();

      final buildButton = find.widgetWithText(FilledButton, 'Build Outfit');
      await tester.scrollUntilVisible(buildButton, 200);
      await tester.tap(buildButton);
      await tester.pump();
      await tester.pump();

      expect(find.text('Building Outfit'), findsOneWidget);
    });
  });

  group('OutfitGenerationScreen Widget Tests', () {
    testWidgets('renders app bar with building title while loading', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedOutfitRepository()
        ..genHandler = () => Completer<OutfitResult>().future;
      await tester.pumpWidget(_generationWith(repo));
      await tester.pump();

      expect(find.text('Building Outfit'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsWidgets);
    });

    testWidgets('renders selection summary while loading', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedOutfitRepository()
        ..genHandler = () => Completer<OutfitResult>().future;
      await tester.pumpWidget(_generationWith(repo));
      await tester.pump();

      expect(find.text('Your Preferences'), findsOneWidget);
      expect(find.text('Office'), findsAtLeast(1));
      expect(find.text('Classic'), findsAtLeast(1));
      expect(find.text('Tailored'), findsAtLeast(1));
      expect(find.text('Warm'), findsAtLeast(1));
    });

    testWidgets('renders generation stages without fake progress', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedOutfitRepository()
        ..genHandler = () => Completer<OutfitResult>().future;
      await tester.pumpWidget(_generationWith(repo));
      await tester.pump();

      expect(find.text('Analyzing wardrobe items'), findsOneWidget);
      expect(find.text('Matching occasion preferences'), findsOneWidget);
      expect(find.text('Applying Style DNA'), findsOneWidget);
      expect(find.text('Selecting complementary pieces'), findsOneWidget);
      expect(find.text('Generating outfit recommendations'), findsOneWidget);
      // No fake completion state while the request is pending.
      expect(find.text('Generation Complete'), findsNothing);
      expect(find.text('View Generation'), findsNothing);
    });

    testWidgets('empty wardrobe renders honest empty state with retry', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedOutfitRepository()
        ..genHandler = () async => const OutfitResult.noneAvailable();
      await tester.pumpWidget(_generationWith(repo));
      await tester.pumpAndSettle();

      expect(find.text('No matching outfit'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);
      expect(find.text('OUTFIT RECOMMENDATION'), findsNothing);
    });

    testWidgets('error state is truthful with retry', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedOutfitRepository()
        ..genHandler = () async =>
            const OutfitResult.failure(OutfitFailure.networkError);
      await tester.pumpWidget(_generationWith(repo));
      await tester.pumpAndSettle();

      expect(find.text('Couldn\'t build your outfit'), findsOneWidget);
      expect(
        find.textContaining('Please check your connection'),
        findsOneWidget,
      );
      expect(find.text('Try Again'), findsOneWidget);
      expect(find.text('OUTFIT RECOMMENDATION'), findsNothing);
    });

    testWidgets('success forwards the backend outfit to recommendation', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedOutfitRepository()
        ..genHandler = () async => OutfitResult.available(_rec(_wire()));
      await tester.pumpWidget(_flowApp(repo));
      await tester.pumpAndSettle();

      expect(repo.genCalls, 1);
      expect(repo.genSeeds, [isNull]);
      expect(find.text('Office Outfit'), findsWidgets);
      expect(find.text('87%'), findsOneWidget);
      expect(find.text('Navy Blazer'), findsOneWidget);
    });

    testWidgets('retry refetches and forwards after failure', (
      WidgetTester tester,
    ) async {
      var calls = 0;
      final repo = ScriptedOutfitRepository()
        ..genHandler = () async {
          calls += 1;
          if (calls == 1) {
            return const OutfitResult.failure(OutfitFailure.networkError);
          }
          return OutfitResult.available(_rec(_wire()));
        };
      await tester.pumpWidget(_flowApp(repo));
      await tester.pumpAndSettle();
      expect(find.text('Couldn\'t build your outfit'), findsOneWidget);

      await tester.tap(find.text('Try Again'));
      await tester.pumpAndSettle();

      expect(calls, 2);
      expect(find.text('Office Outfit'), findsWidgets);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      final repo = ScriptedOutfitRepository()
        ..genHandler = () => Completer<OutfitResult>().future;
      await tester.pumpWidget(_generationWith(repo));
      await tester.pump();

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });

  group('OutfitRecommendationScreen Widget Tests', () {
    testWidgets('renders app bar and backend header', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedOutfitRepository();
      await tester.pumpWidget(_recommendationWith(repo, _rec(_wire())));
      await tester.pumpAndSettle();

      expect(find.text('Your Outfit'), findsOneWidget);
      expect(find.text('Office Outfit'), findsOneWidget);
      expect(find.text('office • classic • warm'), findsOneWidget);
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
      // No mock leftovers posing as data.
      expect(find.text('Refined Office Ensemble'), findsNothing);
    });

    testWidgets('renders match score', (WidgetTester tester) async {
      final repo = ScriptedOutfitRepository();
      await tester.pumpWidget(_recommendationWith(repo, _rec(_wire())));
      await tester.pumpAndSettle();

      expect(find.text('87%'), findsOneWidget);
      expect(find.text('Match Score'), findsOneWidget);
    });

    testWidgets('renders outfit components', (WidgetTester tester) async {
      final repo = ScriptedOutfitRepository();
      await tester.pumpWidget(_recommendationWith(repo, _rec(_wire())));
      await tester.pumpAndSettle();

      expect(find.text('Outfit Components'), findsOneWidget);
      expect(find.text('3 curated pieces'), findsOneWidget);
      expect(find.byType(OutfitComponentCard), findsNWidgets(3));
      expect(find.text('Navy Blazer'), findsOneWidget);
      expect(find.text('White Tee'), findsOneWidget);
      expect(find.text('Dark Jeans'), findsOneWidget);
    });

    testWidgets('renders recommendation reasons', (WidgetTester tester) async {
      final repo = ScriptedOutfitRepository();
      await tester.pumpWidget(_recommendationWith(repo, _rec(_wire())));
      await tester.pumpAndSettle();

      expect(find.text('Why This Look Works'), findsOneWidget);
      expect(find.text('Picked for a Office occasion'), findsOneWidget);
    });

    testWidgets('renders metric cards', (WidgetTester tester) async {
      final repo = ScriptedOutfitRepository();
      await tester.pumpWidget(_recommendationWith(repo, _rec(_wire())));
      await tester.pumpAndSettle();

      expect(find.text('Color Harmony'), findsOneWidget);
      expect(find.text('Body Fit'), findsOneWidget);
      expect(find.text('Occasion Match'), findsOneWidget);
    });

    testWidgets('renders Style Score impact', (WidgetTester tester) async {
      final repo = ScriptedOutfitRepository();
      await tester.pumpWidget(_recommendationWith(repo, _rec(_wire())));
      await tester.pumpAndSettle();

      expect(find.text('Style Score Impact'), findsOneWidget);
      expect(find.textContaining('87% ensemble match'), findsOneWidget);
    });

    testWidgets('renders improvement suggestion', (WidgetTester tester) async {
      final repo = ScriptedOutfitRepository();
      await tester.pumpWidget(_recommendationWith(repo, _rec(_wire())));
      await tester.pumpAndSettle();

      expect(find.text('Improvement Suggestion'), findsOneWidget);
      expect(find.textContaining('Consider adding'), findsOneWidget);
    });

    testWidgets('renders action buttons without wear confusion', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedOutfitRepository();
      await tester.pumpWidget(_recommendationWith(repo, _rec(_wire())));
      await tester.pumpAndSettle();

      expect(find.text('Save Outfit'), findsOneWidget);
      expect(find.text('Regenerate'), findsOneWidget);
      expect(find.text('Wearing this look!'), findsNothing);
    });

    testWidgets('renders Replace buttons for components', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedOutfitRepository();
      await tester.pumpWidget(_recommendationWith(repo, _rec(_wire())));
      await tester.pumpAndSettle();

      expect(find.text('Replace'), findsNWidgets(3));
    });

    testWidgets('regenerate swaps in the backend outfit with a seed', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedOutfitRepository()
        ..genHandler = () async =>
            OutfitResult.available(_rec(_wire(title: 'Evening Rotation')));
      await tester.pumpWidget(_recommendationWith(repo, _rec(_wire())));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Regenerate'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Regenerate'));
      await tester.pumpAndSettle();

      expect(repo.genCalls, 1);
      expect(repo.genSeeds, ['outfit-1']);
      expect(find.text('Evening Rotation'), findsOneWidget);
    });

    testWidgets('regenerate pending guard ignores repeated taps', (
      WidgetTester tester,
    ) async {
      final gate = Completer<OutfitResult>();
      final repo = ScriptedOutfitRepository()..genHandler = () => gate.future;
      await tester.pumpWidget(_recommendationWith(repo, _rec(_wire())));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Regenerate'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Regenerate'));
      await tester.pump();
      expect(find.text('Regenerating…'), findsOneWidget);
      await tester.tap(find.text('Regenerating…'));
      await tester.pump();
      expect(repo.genCalls, 1);

      gate.complete(OutfitResult.available(_rec(_wire(title: 'Fresh'))));
      await tester.pumpAndSettle();
      expect(find.text('Fresh'), findsOneWidget);
    });

    testWidgets('failed regenerate keeps the outfit with feedback', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedOutfitRepository()
        ..genHandler = () async =>
            const OutfitResult.failure(OutfitFailure.serviceUnavailable);
      await tester.pumpWidget(_recommendationWith(repo, _rec(_wire())));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Regenerate'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Regenerate'));
      await tester.pumpAndSettle();

      expect(find.text('Office Outfit'), findsOneWidget);
      expect(
        find.text('Style service unavailable. Please try again.'),
        findsOneWidget,
      );
    });

    testWidgets('save calls backend then shows success feedback', (
      WidgetTester tester,
    ) async {
      final wire = _wire();
      final repo = ScriptedOutfitRepository()
        ..saveHandler = () async => SavedOutfit.fromJson(_savedWire(wire));
      await tester.pumpWidget(_recommendationWith(repo, _rec(wire)));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Save Outfit'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save Outfit'));
      await tester.pumpAndSettle();

      expect(repo.saveCalls, 1);
      expect(repo.saveTitles.single, 'Office Outfit');
      expect(repo.saveKeys.single, isNotEmpty);
      expect(find.text('Outfit saved'), findsOneWidget);
      expect(find.text('Saved'), findsOneWidget);
      expect(find.text('Wearing this look!'), findsNothing);
    });

    testWidgets('save pending guard ignores repeated taps', (
      WidgetTester tester,
    ) async {
      final gate = Completer<SavedOutfit?>();
      final repo = ScriptedOutfitRepository()..saveHandler = () => gate.future;
      await tester.pumpWidget(_recommendationWith(repo, _rec(_wire())));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Save Outfit'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save Outfit'));
      await tester.pump();
      expect(find.text('Saving…'), findsOneWidget);
      await tester.tap(find.text('Saving…'));
      await tester.pump();
      expect(repo.saveCalls, 1);

      gate.complete(null);
      await tester.pumpAndSettle();
      expect(repo.saveCalls, 1);
    });

    testWidgets('failed save keeps the outfit visible with retry feedback', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedOutfitRepository()..saveHandler = () async => null;
      await tester.pumpWidget(_recommendationWith(repo, _rec(_wire())));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Save Outfit'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save Outfit'));
      await tester.pumpAndSettle();

      expect(find.text('Office Outfit'), findsOneWidget);
      expect(find.text('Navy Blazer'), findsOneWidget);
      expect(
        find.text('Couldn\'t save this outfit. Please try again.'),
        findsOneWidget,
      );
      expect(find.text('Save Outfit'), findsOneWidget);
      expect(find.text('Saved'), findsNothing);
    });

    testWidgets('stale component IDs render safely without invented names', (
      WidgetTester tester,
    ) async {
      final stale = Map<String, dynamic>.from(_wire());
      stale['components'] = [
        {
          'id': 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
          'name': 'Mystery Top',
          'category': 'tops',
          'color': 'grey',
          'reason': 'Chosen tops piece for your Office outfit',
        },
      ];
      final repo = ScriptedOutfitRepository();
      await tester.pumpWidget(_recommendationWith(repo, _rec(stale)));
      await tester.pumpAndSettle();

      expect(find.text('Mystery Top'), findsOneWidget);
      expect(find.text('Unknown Item'), findsNothing);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      final repo = ScriptedOutfitRepository();
      await tester.pumpWidget(_recommendationWith(repo, _rec(_wire())));
      await tester.pumpAndSettle();

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });
}
