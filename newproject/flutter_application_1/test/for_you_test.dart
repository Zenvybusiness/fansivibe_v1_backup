import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/discover/data/discover_client.dart';
import 'package:fansivibe/features/discover/data/discover_models.dart';
import 'package:fansivibe/features/discover/data/discover_repository.dart';
import 'package:fansivibe/features/discover/presentation/discover_screen.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_widgets.dart';

/// M12 P2 focused tests: For You response parsing, endpoint routing,
/// pagination, honest UI copy, and failure behavior. Fakes stand in for
/// transport only — no mock look content is ever presented as backend
/// data beyond the scripted responses under test.

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

Map<String, dynamic> forYouWire({
  List<LookSummary>? items,
  String? nextCursor,
  bool hasMore = false,
  required bool personalized,
}) {
  return {
    'items': (items ?? [summary()]).map((e) => e.toJson()).toList(),
    'next_cursor': nextCursor,
    'has_more': hasMore,
    'personalized': personalized,
  };
}

class ScriptedForYouRepository implements DiscoverRepository {
  final List<ForYouFeedResult> forYouQueue = [];
  final List<Map<String, Object?>> forYouRequests = [];
  DiscoverFeedResult exploreFallback = const DiscoverFeedResult.failure(
    DiscoverFailure.networkError,
  );

  @override
  Future<ForYouFeedResult> getForYouFeed({String? cursor, int? limit}) async {
    forYouRequests.add({'cursor': cursor, 'limit': limit});
    return forYouQueue.removeAt(0);
  }

  @override
  Future<DiscoverFeedResult> getLookFeed({
    String? occasion,
    String? style,
    String? fit,
    String? cursor,
    int? limit,
  }) async => exploreFallback;

  @override
  Future<LookDetailResult> getLookDetail({required String lookId}) =>
      throw UnimplementedError();
}

void main() {
  group('ForYouFeedPage parsing', () {
    test('personalized=true is preserved with cursor state', () {
      final page = ForYouFeedPage.fromJson(
        forYouWire(
          items: [summary(), summary(id: 'side_part', title: 'Side Part')],
          nextCursor: 'cursor-1',
          hasMore: true,
          personalized: true,
        ),
      );
      expect(page.personalized, isTrue);
      expect(page.hasMore, isTrue);
      expect(page.nextCursor, 'cursor-1');
      expect(page.items.map((e) => e.id), ['textured_quiff', 'side_part']);
    });

    test('personalized=false is preserved (cold start)', () {
      final page = ForYouFeedPage.fromJson(
        forYouWire(personalized: false),
      );
      expect(page.personalized, isFalse);
      expect(page.hasMore, isFalse);
      expect(page.nextCursor, isNull);
    });
  });

  group('DiscoverClient.getForYouFeed', () {
    test('calls /v1/looks/for-you, never /v1/looks', () async {
      final requested = <Uri>[];
      final client = DiscoverClient(
        client: MockClient((request) async {
          requested.add(request.url);
          return http.Response(
            '{"items": [], "next_cursor": null, "has_more": false, "personalized": false}',
            200,
          );
        }),
      );
      final result = await client.getForYouFeed();
      expect(result.isPage, isTrue);
      expect(requested, hasLength(1));
      expect(requested.single.path, endsWith('/v1/looks/for-you'));
    });

    test('pagination forwards cursor and limit verbatim', () async {
      final requested = <Uri>[];
      var calls = 0;
      final client = DiscoverClient(
        client: MockClient((request) async {
          requested.add(request.url);
          calls++;
          if (calls == 1) {
            return http.Response(
              '{"items": [], "next_cursor": "c1", "has_more": true, "personalized": true}',
              200,
            );
          }
          return http.Response(
            '{"items": [], "next_cursor": null, "has_more": false, "personalized": true}',
            200,
          );
        }),
      );
      final first = await client.getForYouFeed(limit: 20);
      expect(first.page!.nextCursor, 'c1');
      final second = await client.getForYouFeed(cursor: 'c1');
      expect(second.page!.hasMore, isFalse);
      expect(requested[1].queryParameters['cursor'], 'c1');
      expect(requested[0].queryParameters['limit'], '20');
    });

    test('backend error produces failure, never mock content', () async {
      final client = DiscoverClient(
        client: MockClient((_) async => http.Response('{}', 500)),
      );
      final result = await client.getForYouFeed();
      expect(result.isPage, isFalse);
      expect(result.page, isNull);
      expect(result.failure, DiscoverFailure.unknown);
    });

    test('malformed 200 fails closed', () async {
      final client = DiscoverClient(
        client: MockClient((_) async => http.Response('{"nope": true}', 200)),
      );
      final result = await client.getForYouFeed();
      expect(result.isPage, isFalse);
      expect(result.page, isNull);
    });
  });

  group('DiscoverRepositoryImpl.getForYouFeed', () {
    test('passes through verbatim', () async {
      final repo = DiscoverRepositoryImpl(
        client: DiscoverClient(
          client: MockClient(
            (_) async => http.Response(
              '{"items": [], "next_cursor": null, "has_more": false, "personalized": true}',
              200,
            ),
          ),
        ),
      );
      final result = await repo.getForYouFeed();
      expect(result.isPage, isTrue);
      expect(result.page!.personalized, isTrue);
    });
  });

  group('DiscoverScreen For You tab', () {
    Future<void> openForYou(
      WidgetTester tester,
      ScriptedForYouRepository repo,
    ) async {
      await tester.pumpWidget(
        MaterialApp(home: DiscoverScreen(repository: repo)),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('For You'));
      await tester.pumpAndSettle();
    }

    testWidgets('tab switch fetches for-you once with null cursor', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedForYouRepository()
        ..forYouQueue.add(
          ForYouFeedResult.page(
            ForYouFeedPage(
              items: [summary()],
              nextCursor: null,
              hasMore: false,
              personalized: false,
            ),
          ),
        );
      await openForYou(tester, repo);
      expect(repo.forYouRequests, hasLength(1));
      expect(repo.forYouRequests.single['cursor'], isNull);
      expect(find.text('Textured Quiff'), findsOneWidget);
    });

    testWidgets('personalized=true renders honest For You copy', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedForYouRepository()
        ..forYouQueue.add(
          ForYouFeedResult.page(
            ForYouFeedPage(
              items: [summary()],
              nextCursor: null,
              hasMore: false,
              personalized: true,
            ),
          ),
        );
      await openForYou(tester, repo);
      expect(
        find.textContaining('based on looks you\u2019ve saved'),
        findsOneWidget,
      );
      expect(find.textContaining('Trending'), findsNothing);
      expect(find.textContaining('Popular'), findsNothing);
    });

    testWidgets('personalized=false renders honest cold-start copy', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedForYouRepository()
        ..forYouQueue.add(
          ForYouFeedResult.page(
            ForYouFeedPage(
              items: [summary()],
              nextCursor: null,
              hasMore: false,
              personalized: false,
            ),
          ),
        );
      await openForYou(tester, repo);
      expect(find.textContaining('save looks you love'), findsOneWidget);
      expect(find.textContaining('Trending'), findsNothing);
      expect(find.textContaining('Popular'), findsNothing);
      expect(find.textContaining('Recommended for you'), findsNothing);
    });

    testWidgets('load more appends without duplicating ids', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedForYouRepository()
        ..forYouQueue.addAll([
          ForYouFeedResult.page(
            ForYouFeedPage(
              items: [
                summary(),
                summary(id: 'side_part', title: 'Side Part', matchScore: 82),
              ],
              nextCursor: 'c1',
              hasMore: true,
              personalized: true,
            ),
          ),
          // Overlapping second page: side_part repeats, full_beard is new.
          ForYouFeedResult.page(
            ForYouFeedPage(
              items: [
                summary(id: 'side_part', title: 'Side Part', matchScore: 82),
                summary(id: 'full_beard', title: 'Full Beard', matchScore: 75),
              ],
              nextCursor: null,
              hasMore: false,
              personalized: true,
            ),
          ),
        ]);
      await openForYou(tester, repo);
      await tester.scrollUntilVisible(
        find.text('Load more'),
        500.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Load more'));
      await tester.pumpAndSettle();
      expect(repo.forYouRequests.last['cursor'], 'c1');
      expect(find.text('Side Part'), findsOneWidget);
      expect(find.text('Full Beard'), findsOneWidget);
      expect(find.byType(LookCard), findsNWidgets(3));
    });

    testWidgets('failure renders error state, never mock rows', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedForYouRepository()
        ..forYouQueue.add(
          const ForYouFeedResult.failure(DiscoverFailure.networkError),
        );
      await openForYou(tester, repo);
      expect(find.text('Looks unavailable'), findsOneWidget);
      expect(find.byType(LookCard), findsNothing);
    });

    testWidgets('explore tab still uses the /v1/looks feed', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedForYouRepository();
      await tester.pumpWidget(
        MaterialApp(home: DiscoverScreen(repository: repo)),
      );
      await tester.pumpAndSettle();
      // Explore is the default tab: backend error surfaces, no for-you call.
      expect(repo.forYouRequests, isEmpty);
      expect(find.text('Looks unavailable'), findsOneWidget);
      expect(find.text('Explore'), findsOneWidget);
      expect(find.text('For You'), findsOneWidget);
    });
  });
}
