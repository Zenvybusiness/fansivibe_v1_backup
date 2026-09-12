import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/profile/data/saved_looks_client.dart';
import 'package:fansivibe/features/profile/data/saved_looks_models.dart';
import 'package:fansivibe/features/profile/data/saved_looks_repository.dart';
import 'package:fansivibe/features/profile/presentation/saved_looks_screen.dart';

Map<String, dynamic> _wireItem({
  required String id,
  required String title,
  String? sourceContext = 'hairstyle',
  Map<String, dynamic>? snapshot,
  String? sourceRunId,
}) {
  return {
    'id': id,
    'lookId': 'textured_quiff',
    'title': title,
    'sourceContext': sourceContext,
    'snapshot': snapshot ?? const {},
    'sourceRunId': sourceRunId,
    'createdAt': '2026-09-01T10:00:00.000Z',
  };
}

String _wirePage(List<Map<String, dynamic>> items, {int? total}) {
  return jsonEncode({
    'items': items,
    'page': 1,
    'page_size': 20,
    'total': total ?? items.length,
  });
}

SavedLookItem _item({
  required String id,
  required String title,
  String? sourceContext = 'hairstyle',
  Map<String, dynamic>? snapshot,
}) {
  return SavedLookItem(
    id: id,
    title: title,
    createdAt: DateTime.utc(2026, 9, 1, 10),
    sourceContext: sourceContext,
    snapshot: snapshot ?? const {},
  );
}

List<SavedLookItem> _mixedRows() {
  return [
    _item(
      id: '11111111-1111-1111-1111-111111111111',
      title: 'Textured Quiff',
      sourceContext: 'hairstyle',
      snapshot: const {
        'matchScore': 0.87,
        'description': 'Volume on top flatters oval faces.',
        'reasons': ['Matches your Style DNA'],
      },
    ),
    _item(
      id: '22222222-2222-2222-2222-222222222222',
      title: 'Corporate Beard',
      sourceContext: 'grooming',
      snapshot: const {
        'matchScore': 0.91,
        'description': 'Short boxed beard, crisp cheek line.',
      },
    ),
    _item(
      id: '33333333-3333-3333-3333-333333333333',
      title: 'Date Night Outfit',
      sourceContext: 'outfit',
      snapshot: const {
        'selectedItemIds': ['a-uuid-1', 'a-uuid-2', 'a-uuid-3'],
      },
    ),
    _item(
      id: '44444444-4444-4444-4444-444444444444',
      title: 'Old Save',
      sourceContext: null,
      snapshot: const {},
    ),
  ];
}

/// Scriptable repository double: the backend envelope is the only source.
class _FakeSavedLooksRepository implements SavedLooksRepository {
  _FakeSavedLooksRepository({List<SavedLookItem>? rows})
    : rows = rows ?? const [];

  List<SavedLookItem> rows;
  bool failList = false;
  int deleteCalls = 0;
  final List<String> deletedIds = <String>[];
  Future<SavedLookDeleteOutcome?> Function(String id)? onDelete;

  @override
  Future<SavedLookListPage?> listSavedLooks({
    int page = 1,
    int pageSize = 20,
  }) async {
    if (failList) return null;
    return SavedLookListPage(
      items: List.of(rows),
      page: page,
      pageSize: pageSize,
      total: rows.length,
    );
  }

  @override
  Future<SavedLookDeleteOutcome?> deleteSavedLook({required String id}) async {
    deleteCalls++;
    deletedIds.add(id);
    if (onDelete != null) return onDelete!(id);
    rows = rows.where((row) => row.id != id).toList();
    return SavedLookDeleteOutcome.deleted;
  }
}

Widget _wrap(Widget child) {
  return MaterialApp(theme: ThemeData.dark(), home: child);
}

/// Scrolls the first card's Remove control into view before tapping it:
/// hero cards are taller than the test viewport.
Future<void> _tapFirstRemove(WidgetTester tester) async {
  final remove = find.text('Remove').first;
  await tester.scrollUntilVisible(remove, 500.0);
  await tester.pumpAndSettle();
  await tester.tap(remove);
  await tester.pumpAndSettle();
}

void main() {
  group('SavedLookItem decoding (A)', () {
    test('paginated envelope decodes with UUID and sourceContext intact', () {
      final page = SavedLookListPage.fromJson(
        jsonDecode(
              _wirePage([
                _wireItem(id: 'id-1', title: 'Quiff'),
                _wireItem(
                  id: 'id-2',
                  title: 'Beard',
                  sourceContext: 'grooming',
                ),
                _wireItem(
                  id: 'id-3',
                  title: 'Outfit',
                  sourceContext: 'outfit',
                  snapshot: const {
                    'selectedItemIds': ['u1', 'u2'],
                  },
                ),
                _wireItem(id: 'id-4', title: 'Legacy', sourceContext: null),
              ]),
            )
            as Map<String, dynamic>,
      );

      expect(page.total, 4);
      expect(page.page, 1);
      expect(page.pageSize, 20);
      expect(page.items.map((e) => e.id).toList(), [
        'id-1',
        'id-2',
        'id-3',
        'id-4',
      ]);
      expect(page.items.map((e) => e.sourceContext).toList(), [
        'hairstyle',
        'grooming',
        'outfit',
        isNull,
      ]);
      expect(page.items[2].selectedItemIds, ['u1', 'u2']);
      expect(page.items[0].snapshot['description'], isNull);
    });

    test('snapshot and provenance survive decoding', () {
      final item = SavedLookItem.fromJson(
        _wireItem(
          id: 'id-9',
          title: 'Quiff',
          snapshot: const {
            'matchScore': 0.87,
            'reasons': ['r1'],
          },
          sourceRunId: 'run-1',
        ),
      );

      expect(item.snapshot['matchScore'], 0.87);
      expect(item.snapshot['reasons'], ['r1']);
      expect(item.sourceRunId, 'run-1');
      expect(item.lookId, 'textured_quiff');
    });

    test('roundtrip preserves null sourceContext', () {
      final item = _item(id: 'x', title: 'Old', sourceContext: null);
      final back = SavedLookItem.fromJson(item.toJson());

      expect(back.sourceContext, isNull);
      expect(back.id, 'x');
    });
  });

  group('SavedLooksClient (A)', () {
    test('list uses backend path with page params and auth', () async {
      late Uri seen;
      Map<String, String>? seenHeaders;
      final client = SavedLooksClient(
        client: MockClient((request) async {
          seen = request.url;
          seenHeaders = request.headers;
          return http.Response(_wirePage([]), 200);
        }),
      );

      final page = await client.listSavedLooks(page: 1, pageSize: 20);

      expect(page, isNotNull);
      expect(seen.path, '/v1/looks/saved');
      expect(seen.queryParameters['page'], '1');
      expect(seen.queryParameters['page_size'], '20');
      expect(seenHeaders?['Authorization'], 'Bearer dev');
    });

    test(
      'list returns null on malformed body, error status, offline',
      () async {
        final malformed = SavedLooksClient(
          client: MockClient((_) async => http.Response('not-json{{{', 200)),
        );
        expect(await malformed.listSavedLooks(), isNull);

        final serverError = SavedLooksClient(
          client: MockClient((_) async => http.Response('{}', 500)),
        );
        expect(await serverError.listSavedLooks(), isNull);

        final offline = SavedLooksClient(
          client: MockClient((_) async => throw Exception('down')),
        );
        expect(await offline.listSavedLooks(), isNull);
      },
    );

    test('delete maps 204/404 and nulls failures', () async {
      late Uri seen;
      final ok = SavedLooksClient(
        client: MockClient((request) async {
          seen = request.url;
          return http.Response('', 204);
        }),
      );
      expect(
        await ok.deleteSavedLook(id: 'backend-uuid-1'),
        SavedLookDeleteOutcome.deleted,
      );
      expect(seen.path, '/v1/looks/saved/backend-uuid-1');

      final gone = SavedLooksClient(
        client: MockClient((_) async => http.Response('{}', 404)),
      );
      expect(
        await gone.deleteSavedLook(id: 'backend-uuid-1'),
        SavedLookDeleteOutcome.alreadyGone,
      );

      final broken = SavedLooksClient(
        client: MockClient((_) async => http.Response('{}', 500)),
      );
      expect(await broken.deleteSavedLook(id: 'backend-uuid-1'), isNull);

      final offline = SavedLooksClient(
        client: MockClient((_) async => throw Exception('down')),
      );
      expect(await offline.deleteSavedLook(id: 'backend-uuid-1'), isNull);
    });
  });

  group('SavedLooksRepositoryImpl passthrough', () {
    test('list and delete delegate verbatim with null passthrough', () async {
      final repo = SavedLooksRepositoryImpl(
        client: SavedLooksClient(
          client: MockClient((request) async {
            if (request.method == 'DELETE') {
              return http.Response('', 204);
            }
            return http.Response(
              _wirePage([_wireItem(id: 'i', title: 'T')]),
              200,
            );
          }),
        ),
      );

      final page = await repo.listSavedLooks(page: 1, pageSize: 20);
      expect(page?.items.single.id, 'i');
      expect(
        await repo.deleteSavedLook(id: 'i'),
        SavedLookDeleteOutcome.deleted,
      );

      final failing = SavedLooksRepositoryImpl(
        client: SavedLooksClient(
          client: MockClient((_) async => http.Response('{}', 500)),
        ),
      );
      expect(await failing.listSavedLooks(), isNull);
      expect(await failing.deleteSavedLook(id: 'i'), isNull);
    });
  });

  group('SavedLooksScreen backend source of truth (B)', () {
    testWidgets('renders backend rows without service merge', (
      WidgetTester tester,
    ) async {
      final repo = _FakeSavedLooksRepository(rows: _mixedRows());
      await tester.pumpWidget(_wrap(SavedLooksScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('4 Saved Looks'), findsOneWidget);
      expect(find.text('Textured Quiff'), findsOneWidget);
      expect(find.text('Corporate Beard'), findsOneWidget);
      expect(find.text('Date Night Outfit'), findsOneWidget);
      expect(find.text('Old Save'), findsOneWidget);
    });

    testWidgets('empty backend list produces empty state', (
      WidgetTester tester,
    ) async {
      final repo = _FakeSavedLooksRepository(rows: const []);
      await tester.pumpWidget(_wrap(SavedLooksScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('0 Saved Looks'), findsOneWidget);
      expect(find.text('No saved looks yet'), findsOneWidget);
    });

    testWidgets('unreachable backend shows error with retry', (
      WidgetTester tester,
    ) async {
      final repo = _FakeSavedLooksRepository(rows: _mixedRows())
        ..failList = true;
      await tester.pumpWidget(_wrap(SavedLooksScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('0 Saved Looks'), findsOneWidget);
      expect(
        find.text('Couldn\'t load saved looks. Please check your connection.'),
        findsOneWidget,
      );

      repo
        ..failList = false
        ..rows = _mixedRows();
      await tester.tap(find.text('Try Again'));
      await tester.pumpAndSettle();

      expect(find.text('4 Saved Looks'), findsOneWidget);
      expect(find.text('Textured Quiff'), findsOneWidget);
    });
  });

  group('Outfit and legacy rendering (C, D)', () {
    testWidgets('outfit row renders generically with count, no names', (
      WidgetTester tester,
    ) async {
      final repo = _FakeSavedLooksRepository(rows: _mixedRows());
      await tester.pumpWidget(_wrap(SavedLooksScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('OUTFIT LOOK'), findsOneWidget);
      expect(find.text('3 items'), findsOneWidget);
      expect(find.textContaining('a-uuid-1'), findsNothing);
    });

    testWidgets('null sourceContext renders generically, never inferred', (
      WidgetTester tester,
    ) async {
      final repo = _FakeSavedLooksRepository(rows: _mixedRows());
      await tester.pumpWidget(_wrap(SavedLooksScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('SAVED LOOK'), findsOneWidget);
      expect(find.text('Old Save'), findsOneWidget);
      // The legacy row must not borrow another type's label.
      expect(find.text('HAIRSTYLE LOOK'), findsOneWidget);
      expect(find.text('GROOMING LOOK'), findsOneWidget);
    });
  });

  group('Delete UX (E–J)', () {
    testWidgets('cancel leaves the row unchanged', (WidgetTester tester) async {
      final repo = _FakeSavedLooksRepository(rows: _mixedRows());
      await tester.pumpWidget(_wrap(SavedLooksScreen(repository: repo)));
      await tester.pumpAndSettle();

      await _tapFirstRemove(tester);

      expect(find.text('Delete Saved Look'), findsOneWidget);
      expect(find.textContaining('Textured Quiff'), findsNWidgets(2));

      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      expect(repo.deleteCalls, 0);
      expect(find.text('Textured Quiff'), findsOneWidget);
    });

    testWidgets('successful delete sends exact UUID and reloads', (
      WidgetTester tester,
    ) async {
      final repo = _FakeSavedLooksRepository(rows: _mixedRows());
      await tester.pumpWidget(_wrap(SavedLooksScreen(repository: repo)));
      await tester.pumpAndSettle();

      await _tapFirstRemove(tester);
      await tester.tap(find.text('Delete'));
      await tester.pumpAndSettle();

      expect(repo.deletedIds, ['11111111-1111-1111-1111-111111111111']);
      expect(find.text('Textured Quiff'), findsNothing);
      expect(find.text('3 Saved Looks'), findsOneWidget);
      expect(find.text('Look removed from saved looks'), findsOneWidget);
    });

    testWidgets('delete failure retains the row with error copy', (
      WidgetTester tester,
    ) async {
      final repo = _FakeSavedLooksRepository(rows: _mixedRows())
        ..onDelete = (_) async => null;
      await tester.pumpWidget(_wrap(SavedLooksScreen(repository: repo)));
      await tester.pumpAndSettle();

      await _tapFirstRemove(tester);
      await tester.tap(find.text('Delete'));
      await tester.pumpAndSettle();

      expect(find.text('Corporate Beard'), findsOneWidget);
      expect(find.text('4 Saved Looks'), findsOneWidget);
      expect(
        find.text('Failed to delete look. Please check your connection.'),
        findsOneWidget,
      );
    });

    testWidgets('404 delete removes the row without false success', (
      WidgetTester tester,
    ) async {
      final repo = _FakeSavedLooksRepository(rows: _mixedRows());
      repo.onDelete = (String id) async {
        repo.rows = repo.rows.where((row) => row.id != id).toList();
        return SavedLookDeleteOutcome.alreadyGone;
      };
      await tester.pumpWidget(_wrap(SavedLooksScreen(repository: repo)));
      await tester.pumpAndSettle();

      await _tapFirstRemove(tester);
      await tester.tap(find.text('Delete'));
      await tester.pumpAndSettle();

      expect(find.text('Textured Quiff'), findsNothing);
      expect(find.text('Look was already removed'), findsOneWidget);
      expect(find.text('Look removed from saved looks'), findsNothing);
    });

    testWidgets('pending guard prevents duplicate submissions', (
      WidgetTester tester,
    ) async {
      final gate = Completer<SavedLookDeleteOutcome?>();
      final repo = _FakeSavedLooksRepository(rows: _mixedRows());
      repo.onDelete = (String id) async {
        final outcome = await gate.future;
        if (outcome == SavedLookDeleteOutcome.deleted) {
          repo.rows = repo.rows.where((row) => row.id != id).toList();
        }
        return outcome;
      };
      await tester.pumpWidget(_wrap(SavedLooksScreen(repository: repo)));
      await tester.pumpAndSettle();

      await _tapFirstRemove(tester);
      await tester.tap(find.text('Delete'));
      await tester.pump();
      expect(find.text('Removing…'), findsOneWidget);

      // The control is disabled while the request is in flight.
      await tester.tap(find.text('Removing…'), warnIfMissed: false);
      await tester.pump();
      expect(repo.deleteCalls, 1);

      gate.complete(SavedLookDeleteOutcome.deleted);
      await tester.pumpAndSettle();
      expect(find.text('Textured Quiff'), findsNothing);
    });
  });
}
