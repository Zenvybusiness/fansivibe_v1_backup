import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/events/data/event_models.dart';
import 'package:fansivibe/features/events/data/events_client.dart';
import 'package:fansivibe/features/events/data/events_repository.dart';

const String _uuid = '78ff3686-c950-4cd6-84c3-7e18d6634dfa';
const String _uuid2 = '4412f646-56a9-4afa-8717-b330da03b3d0';

Map<String, dynamic> _wireEvent({
  String id = _uuid,
  String title = 'Company Gala',
  String eventType = 'formal',
  String eventDate = '2030-08-15',
  Object? time = '19:00',
  Object? location = 'Grand Ballroom',
  Object? notes = 'Black tie',
}) {
  return {
    'id': id,
    'title': title,
    'eventType': eventType,
    'eventDate': eventDate,
    'time': time,
    'location': location,
    'notes': notes,
    'createdAt': '2030-01-01T10:00:00.000Z',
    'updatedAt': '2030-01-02T10:00:00.000Z',
  };
}

Map<String, dynamic> _wireOutfit() {
  return {
    'title': 'Formal Outfit',
    'matchScore': 0.39,
    'components': [
      {
        'id': _uuid2,
        'name': 'Tee',
        'category': 'tops',
        'color': 'black',
        'reason': 'Chosen tops piece',
      },
    ],
    'reasons': ['Picked for a Formal occasion'],
    'selectedOccasion': 'formal',
  };
}

void main() {
  group('EventItem models', () {
    test('parses the exact backend wire shape', () {
      final item = EventItem.fromJson(_wireEvent());

      expect(item.id, _uuid);
      expect(item.title, 'Company Gala');
      expect(item.eventType, 'formal');
      expect(item.eventDate, '2030-08-15');
      expect(item.eventTime, '19:00');
      expect(item.location, 'Grand Ballroom');
      expect(item.notes, 'Black tie');
    });

    test('nullable time/location/notes stay nullable', () {
      final item = EventItem.fromJson(
        _wireEvent(time: null, location: null, notes: null),
      );

      expect(item.eventTime, isNull);
      expect(item.location, isNull);
      expect(item.notes, isNull);
      expect(item.displayTime, isNull);
    });

    test('backend UUID preserved verbatim', () {
      final item = EventItem.fromJson(_wireEvent());

      expect(item.id, _uuid);
      expect(item.toJson()['id'], _uuid);
    });

    test('display helpers format ISO/HH:mm without changing the wire', () {
      final item = EventItem.fromJson(_wireEvent());

      expect(item.displayDate, 'Aug 15, 2030');
      expect(item.displayTime, '7:00 PM');
      expect(item.eventDate, '2030-08-15');
      expect(item.eventTime, '19:00');
    });

    test('copyWith can clear nullable fields', () {
      final item = EventItem.fromJson(_wireEvent());

      final cleared = item.copyWith(
        eventTime: () => null,
        location: () => null,
        notes: () => null,
      );

      expect(cleared.eventTime, isNull);
      expect(cleared.location, isNull);
      expect(cleared.notes, isNull);
      expect(cleared.id, _uuid);
    });

    test('list page reads the page_size wire key', () {
      final page = EventListPage.fromJson({
        'items': [_wireEvent()],
        'page': 1,
        'page_size': 20,
        'total': 1,
      });

      expect(page.items, hasLength(1));
      expect(page.pageSize, 20);
      expect(page.total, 1);
      expect(page.isEmpty, isFalse);
    });
  });

  group('Event outfit models', () {
    test('parses the honest M8-C subset', () {
      final outfit = EventOutfit.fromJson(_wireOutfit());

      expect(outfit.title, 'Formal Outfit');
      expect(outfit.matchScore, 0.39);
      expect(outfit.selectedOccasion, 'formal');
      expect(outfit.components, hasLength(1));
      expect(outfit.components.single.id, _uuid2);
      expect(outfit.components.single.material, isNull);
      expect(outfit.reasons, ['Picked for a Formal occasion']);
    });
  });

  group('EventsClient', () {
    test('listEvents hits the exact path/query with auth', () async {
      late Uri seen;
      late Map<String, String> headers;
      final client = EventsClient(
        client: MockClient((request) async {
          seen = request.url;
          headers = request.headers;
          return http.Response(
            jsonEncode({
              'items': <dynamic>[],
              'page': 1,
              'page_size': 20,
              'total': 0,
            }),
            200,
          );
        }),
      );

      final page = await client.listEvents();

      expect(seen.path, '/v1/events');
      expect(seen.queryParameters['page'], '1');
      expect(seen.queryParameters['page_size'], '20');
      expect(headers['Authorization'], 'Bearer dev');
      expect(page, isNotNull);
      expect(page!.isEmpty, isTrue);
    });

    test('listEvents maps failures to null without fallback', () async {
      for (final status in [401, 404, 422, 429, 500]) {
        final client = EventsClient(
          client: MockClient((_) async => http.Response('{}', status)),
        );
        expect(await client.listEvents(), isNull);
      }
      final offline = EventsClient(
        client: MockClient((_) async => throw Exception('down')),
      );
      expect(await offline.listEvents(), isNull);
    });

    test('createEvent posts the exact wire map without local IDs', () async {
      late String body;
      late Uri seen;
      final client = EventsClient(
        client: MockClient((request) async {
          seen = request.url;
          body = request.body;
          return http.Response(jsonEncode(_wireEvent()), 201);
        }),
      );

      final created = await client.createEvent(
        const EventCreateRequest(
          title: 'Company Gala',
          eventType: 'formal',
          eventDate: '2030-08-15',
          eventTime: '19:00',
          location: 'Grand Ballroom',
          notes: 'Black tie',
        ),
      );

      expect(seen.path, '/v1/events');
      expect(jsonDecode(body), {
        'title': 'Company Gala',
        'eventType': 'formal',
        'eventDate': '2030-08-15',
        'time': '19:00',
        'location': 'Grand Ballroom',
        'notes': 'Black tie',
      });
      expect(RegExp(r'"id"\s*:\s*"\d+"').hasMatch(body), isFalse);
      expect(created, isNotNull);
      expect(created!.id, _uuid);
    });

    test('createEvent omits nothing and maps rejection to null', () async {
      final rejected = EventsClient(
        client: MockClient((_) async => http.Response('{}', 422)),
      );
      expect(
        await rejected.createEvent(
          const EventCreateRequest(
            title: 'x',
            eventType: 'nope',
            eventDate: '2030-08-15',
          ),
        ),
        isNull,
      );
    });

    test(
      'updateEvent puts the exact UUID with the full-replace body',
      () async {
        late Uri seen;
        late String body;
        final client = EventsClient(
          client: MockClient((request) async {
            seen = request.url;
            body = request.body;
            return http.Response(jsonEncode(_wireEvent(title: 'Renamed')), 200);
          }),
        );

        final updated = await client.updateEvent(
          id: _uuid,
          request: const EventUpdateRequest(
            title: 'Renamed',
            eventType: 'party',
            eventDate: '2030-08-16',
            eventTime: null,
            location: null,
            notes: null,
          ),
        );

        expect(seen.path, '/v1/events/$_uuid');
        final decoded = jsonDecode(body) as Map<String, dynamic>;
        expect(decoded['title'], 'Renamed');
        expect(decoded['eventType'], 'party');
        expect(decoded['time'], isNull);
        expect(decoded['location'], isNull);
        expect(decoded['notes'], isNull);
        expect(updated, isNotNull);
        expect(updated!.title, 'Renamed');
      },
    );

    test('updateEvent maps 404/422 to null', () async {
      for (final status in [404, 422]) {
        final client = EventsClient(
          client: MockClient((_) async => http.Response('{}', status)),
        );
        expect(
          await client.updateEvent(
            id: _uuid,
            request: const EventUpdateRequest(
              title: 'x',
              eventType: 'formal',
              eventDate: '2030-08-15',
            ),
          ),
          isNull,
        );
      }
    });

    test('deleteEvent maps 204/404 exactly and retains otherwise', () async {
      final deleted = EventsClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/events/$_uuid');
          return http.Response('', 204);
        }),
      );
      expect(await deleted.deleteEvent(id: _uuid), EventDeleteOutcome.deleted);

      final gone = EventsClient(
        client: MockClient((_) async => http.Response('', 404)),
      );
      expect(await gone.deleteEvent(id: _uuid), EventDeleteOutcome.alreadyGone);

      final failed = EventsClient(
        client: MockClient((_) async => http.Response('', 500)),
      );
      expect(await failed.deleteEvent(id: _uuid), isNull);
    });

    test('generateEventOutfit posts the exact UUID with no body', () async {
      late Uri seen;
      late String body;
      final client = EventsClient(
        client: MockClient((request) async {
          seen = request.url;
          body = request.body;
          return http.Response(jsonEncode(_wireOutfit()), 200);
        }),
      );

      final result = await client.generateEventOutfit(id: _uuid);

      expect(seen.path, '/v1/events/$_uuid/outfit');
      expect(body, isEmpty);
      expect(result, isNotNull);
      expect(result!.available, isTrue);
      expect(result.outfit, isNotNull);
      expect(result.outfit!.selectedOccasion, 'formal');
      expect(result.outfit!.matchScore, 0.39);
      expect(result.outfit!.components.single.id, _uuid2);
    });

    test(
      'generateEventOutfit maps 204 to noneAvailable, errors to null',
      () async {
        final empty = EventsClient(
          client: MockClient((_) async => http.Response('', 204)),
        );
        final noneResult = await empty.generateEventOutfit(id: _uuid);
        expect(noneResult, isNotNull);
        expect(noneResult!.available, isFalse);
        expect(noneResult.outfit, isNull);

        for (final status in [401, 404, 422, 503]) {
          final client = EventsClient(
            client: MockClient((_) async => http.Response('{}', status)),
          );
          expect(await client.generateEventOutfit(id: _uuid), isNull);
        }
      },
    );

    test('malformed 200 bodies map to null instead of fake models', () async {
      final client = EventsClient(
        client: MockClient((_) async => http.Response('{"nope": true}', 200)),
      );
      expect(await client.listEvents(), isNull);
      expect(
        await client.createEvent(
          const EventCreateRequest(
            title: 'x',
            eventType: 'formal',
            eventDate: '2030-08-15',
          ),
        ),
        isNull,
      );
      expect(await client.generateEventOutfit(id: _uuid), isNull);
    });
  });

  group('EventsRepository', () {
    test('passes backend values through without merging mocks', () async {
      final repository = EventsRepositoryImpl(
        client: EventsClient(
          client: MockClient((request) async {
            final path = request.url.path;
            if (path == '/v1/events' && request.method == 'GET') {
              return http.Response(
                jsonEncode({
                  'items': [_wireEvent()],
                  'page': 1,
                  'page_size': 20,
                  'total': 1,
                }),
                200,
              );
            }
            return http.Response('', 204);
          }),
        ),
      );

      final page = await repository.listEvents();
      expect(page, isNotNull);
      expect(page!.items.single.id, _uuid);

      final missing = await repository.generateEventOutfit(id: _uuid);
      expect(missing, isNotNull);
      expect(missing!.available, isFalse);
    });

    test('null means unavailable, never a fabricated page', () async {
      final repository = EventsRepositoryImpl(
        client: EventsClient(
          client: MockClient((_) async => http.Response('', 500)),
        ),
      );

      expect(await repository.listEvents(), isNull);
      expect(await repository.deleteEvent(id: _uuid), isNull);
    });
  });
}
