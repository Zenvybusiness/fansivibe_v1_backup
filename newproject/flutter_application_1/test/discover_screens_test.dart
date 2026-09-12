import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import 'package:fansivibe/features/discover/discover.dart';
import 'package:fansivibe/features/discover/presentation/discover_screen.dart';
import 'package:fansivibe/features/discover/presentation/look_details_screen.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_widgets.dart';

LookSummary summary({
  String id = 'textured_quiff',
  String title = 'Textured Quiff',
  int matchScore = 94,
}) {
  return LookSummary(
    id: id,
    title: title,
    description: 'A modern take on the classic quiff.',
    matchScore: matchScore,
    reasons: const ['Volume on top suits oval faces'],
  );
}

LookDetail detail({String id = 'textured_quiff'}) {
  return LookDetail(
    id: id,
    title: 'Textured Quiff',
    description: 'A modern take on the classic quiff.',
    matchScore: 94,
    reasons: const ['Volume on top suits oval faces'],
    stylingTips: 'Apply mousse to damp hair.',
    maintenance: 'Medium. Trim every 4-5 weeks',
    bestFor: 'Oval, Heart, and Rectangle face shapes',
  );
}

LookFeedPage page({
  List<LookSummary>? items,
  String? nextCursor,
  bool hasMore = false,
}) {
  return LookFeedPage(
    items:
        items ??
        [
          summary(),
          summary(
            id: 'classic_pompadour',
            title: 'Classic Pompadour',
            matchScore: 87,
          ),
        ],
    nextCursor: nextCursor,
    hasMore: hasMore,
  );
}

/// Scriptable fake: queued feed results, full call accounting, no network.
class ScriptedDiscoverRepository implements DiscoverRepository {
  ScriptedDiscoverRepository();

  final List<DiscoverFeedResult> feedQueue = [];
  DiscoverFeedResult feedFallback = const DiscoverFeedResult.failure(
    DiscoverFailure.networkError,
  );
  final List<Map<String, Object?>> feedRequests = [];

  Future<LookDetailResult> Function(String lookId)? detailHandler;
  final List<String> detailRequests = [];

  @override
  Future<DiscoverFeedResult> getLookFeed({
    String? occasion,
    String? style,
    String? fit,
    String? cursor,
    int? limit,
  }) async {
    feedRequests.add({
      'occasion': occasion,
      'style': style,
      'fit': fit,
      'cursor': cursor,
      'limit': limit,
    });
    if (feedQueue.isNotEmpty) return feedQueue.removeAt(0);
    return feedFallback;
  }

  @override
  Future<LookDetailResult> getLookDetail({required String lookId}) {
    detailRequests.add(lookId);
    return detailHandler!(lookId);
  }
}

Widget discoverHarness(ScriptedDiscoverRepository repo) {
  return MaterialApp(home: DiscoverScreen(repository: repo));
}

Widget detailsHarness(
  ScriptedDiscoverRepository repo, {
  String id = 'textured_quiff',
}) {
  return MaterialApp(
    home: LookDetailsScreen(lookId: id, repository: repo),
  );
}

void main() {
  group('DiscoverScreen backend states', () {
    testWidgets('shows loading then renders backend rows verbatim', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedDiscoverRepository()
        ..feedQueue.add(
          DiscoverFeedResult.page(
            page(
              items: [
                summary(),
                summary(id: 'full_beard', title: 'Full Beard', matchScore: 75),
              ],
            ),
          ),
        );
      await tester.pumpWidget(discoverHarness(repo));
      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      await tester.pumpAndSettle();
      expect(find.text('Textured Quiff'), findsOneWidget);
      expect(find.text('Full Beard'), findsOneWidget);
      // Card sequence follows server order (never re-sorted locally).
      final cards = tester.widgetList<LookCard>(find.byType(LookCard)).toList();
      expect(cards.map((card) => card.data.id), [
        'textured_quiff',
        'full_beard',
      ]);
      expect(repo.feedRequests.single['occasion'], isNull);
    });

    testWidgets('error state with Try Again refetches', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedDiscoverRepository()
        ..feedQueue.add(
          const DiscoverFeedResult.failure(DiscoverFailure.networkError),
        )
        ..feedQueue.add(DiscoverFeedResult.page(page()));
      await tester.pumpWidget(discoverHarness(repo));
      await tester.pumpAndSettle();
      expect(find.text('Looks unavailable'), findsOneWidget);

      await tester.tap(find.text('Try Again'));
      await tester.pumpAndSettle();
      expect(find.text('Textured Quiff'), findsOneWidget);
      expect(repo.feedRequests, hasLength(2));
    });

    testWidgets('empty page renders the truthful empty state', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedDiscoverRepository()
        ..feedQueue.add(
          DiscoverFeedResult.page(page(items: [], hasMore: false)),
        );
      await tester.pumpWidget(discoverHarness(repo));
      await tester.pumpAndSettle();
      expect(find.text('No looks found'), findsOneWidget);
    });

    testWidgets('unsupported filter surfaces a truthful reset state', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedDiscoverRepository()
        ..feedFallback = const DiscoverFeedResult.failure(
          DiscoverFailure.invalidInput,
        );
      await tester.pumpWidget(discoverHarness(repo));
      await tester.pumpAndSettle();
      expect(find.text('Filters not supported yet'), findsOneWidget);

      // Reset clears the (unsupported) selections and refetches unfiltered.
      repo.feedQueue.add(DiscoverFeedResult.page(page()));
      await tester.tap(find.text('Reset filters'));
      await tester.pumpAndSettle();
      expect(find.text('Textured Quiff'), findsOneWidget);
      expect(repo.feedRequests.last['occasion'], isNull);
      expect(repo.feedRequests.last['style'], isNull);
      expect(repo.feedRequests.last['fit'], isNull);
    });

    testWidgets('load more appends the next cursor page', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedDiscoverRepository()
        ..feedQueue.add(
          DiscoverFeedResult.page(
            page(items: [summary()], nextCursor: 'CUR-1', hasMore: true),
          ),
        )
        ..feedQueue.add(
          DiscoverFeedResult.page(
            page(
              items: [
                summary(id: 'full_beard', title: 'Full Beard', matchScore: 75),
              ],
            ),
          ),
        );
      await tester.pumpWidget(discoverHarness(repo));
      await tester.pumpAndSettle();
      expect(find.text('Load more'), findsOneWidget);

      await tester.ensureVisible(find.text('Load more'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Load more'));
      await tester.pumpAndSettle();
      expect(find.text('Textured Quiff'), findsOneWidget);
      expect(find.text('Full Beard'), findsOneWidget);
      expect(repo.feedRequests[1]['cursor'], 'CUR-1');
      expect(find.text('Load more'), findsNothing);
    });

    testWidgets('search narrows loaded rows without new requests', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedDiscoverRepository()
        ..feedQueue.add(
          DiscoverFeedResult.page(
            page(
              items: [
                summary(),
                summary(id: 'full_beard', title: 'Full Beard', matchScore: 75),
              ],
            ),
          ),
        );
      await tester.pumpWidget(discoverHarness(repo));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'beard');
      await tester.pumpAndSettle();
      expect(find.text('Full Beard'), findsOneWidget);
      expect(find.text('Textured Quiff'), findsNothing);
      expect(repo.feedRequests, hasLength(1));
    });

    testWidgets('no mock content is rendered', (WidgetTester tester) async {
      final repo = ScriptedDiscoverRepository()
        ..feedQueue.add(DiscoverFeedResult.page(page()));
      await tester.pumpWidget(discoverHarness(repo));
      await tester.pumpAndSettle();
      expect(find.text('Modern Minimalist'), findsNothing);
      expect(find.text('For You'), findsNothing);
      expect(find.text('Trending'), findsNothing);
    });

    testWidgets('tapping a card routes with the backend code', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedDiscoverRepository()
        ..feedQueue.add(DiscoverFeedResult.page(page(items: [summary()])));
      Object? pushedExtra;
      final router = GoRouter(
        initialLocation: '/',
        routes: [
          GoRoute(
            path: '/',
            builder: (_, _) => DiscoverScreen(repository: repo),
          ),
          GoRoute(
            path: '/details',
            // Same name the production router registers for look details.
            name: 'look-details',
            builder: (_, state) {
              pushedExtra = state.extra;
              return const Scaffold(body: Text('details stub'));
            },
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(LookCard));
      await tester.pumpAndSettle();
      // The backend catalog code travels verbatim — never a local id.
      expect(pushedExtra, 'textured_quiff');
      expect(find.text('details stub'), findsOneWidget);
    });
  });

  group('LookDetailsScreen backend states', () {
    testWidgets('renders the backend detail verbatim', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedDiscoverRepository()
        ..detailHandler = (_) async => LookDetailResult.available(detail());
      await tester.pumpWidget(detailsHarness(repo));
      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      await tester.pumpAndSettle();
      expect(find.text('Textured Quiff'), findsWidgets);
      expect(find.text('A modern take on the classic quiff.'), findsOneWidget);
      expect(find.text('Volume on top suits oval faces'), findsOneWidget);
      expect(find.text('Apply mousse to damp hair.'), findsOneWidget);
      expect(find.text('Medium. Trim every 4-5 weeks'), findsOneWidget);
      expect(
        find.text('Oval, Heart, and Rectangle face shapes'),
        findsOneWidget,
      );
      expect(repo.detailRequests, ['textured_quiff']);
    });

    testWidgets('unknown code renders the truthful gone state', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedDiscoverRepository()
        ..detailHandler = (_) async => const LookDetailResult.notFound();
      await tester.pumpWidget(detailsHarness(repo, id: 'fy_1'));
      await tester.pumpAndSettle();
      expect(find.text('Look not available'), findsOneWidget);
      expect(repo.detailRequests, ['fy_1']);
    });

    testWidgets('failure keeps retry with the same code', (
      WidgetTester tester,
    ) async {
      var calls = 0;
      final repo = ScriptedDiscoverRepository()
        ..detailHandler = (_) async {
          calls += 1;
          if (calls == 1) {
            return const LookDetailResult.failure(DiscoverFailure.networkError);
          }
          return LookDetailResult.available(detail());
        };
      await tester.pumpWidget(detailsHarness(repo));
      await tester.pumpAndSettle();
      expect(find.text('Look unavailable'), findsOneWidget);

      await tester.tap(find.text('Try Again'));
      await tester.pumpAndSettle();
      expect(find.text('Textured Quiff'), findsWidgets);
      expect(repo.detailRequests, ['textured_quiff', 'textured_quiff']);
    });

    testWidgets('no fake save and no sourceless sections', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedDiscoverRepository()
        ..detailHandler = (_) async => LookDetailResult.available(detail());
      await tester.pumpWidget(detailsHarness(repo));
      await tester.pumpAndSettle();
      expect(find.text('Save Look'), findsNothing);
      expect(find.byIcon(Icons.favorite_rounded), findsNothing);
      expect(find.byIcon(Icons.favorite_border_rounded), findsNothing);
      expect(find.text('STYLE & FIT'), findsNothing);
      expect(find.text('Complete The Look'), findsNothing);
      expect(find.text('Wardrobe Alternatives'), findsNothing);
      expect(find.text('Share'), findsOneWidget);
    });
  });
}
