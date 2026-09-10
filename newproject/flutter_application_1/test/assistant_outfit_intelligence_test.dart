import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/assistant/data/assistant_client.dart';
import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/assistant/domain/assistant_service.dart';
import 'package:fansivibe/features/assistant/presentation/widgets/outfit_recommendation_card.dart';

void main() {
  const tCompleteJson = '''
    {
      "intent": "outfit",
      "text": "For office, I'd go with the Refined Office Ensemble. Tap the card to build it.",
      "outfitIntelligence": {
        "selectedItemIds": ["blazer-001", "shirt-001", "trousers-001", "derbies-001", "watch-001"],
        "outfitComposition": {
          "topIds": ["shirt-001"],
          "bottomIds": ["trousers-001"],
          "outerwearIds": ["blazer-001"],
          "footwearIds": ["derbies-001"],
          "accessoryIds": ["watch-001"],
          "styleScore": 91
        },
        "occasion": "office",
        "stylingRationale": "Navy blazer pairs well with crisp white shirt and charcoal trousers for a professional office look.",
        "compatibilityRationale": "All items are from your current wardrobe and coordinate in neutral tones.",
        "confidence": 0.94,
        "explanation": "Based on your wardrobe, this combination works best for an office setting.",
        "dataAvailability": "full"
      }
    }
  ''';

  const tSelectedIdsOnly = '''
    {
      "intent": "outfit",
      "text": "Here's an outfit suggestion.",
      "outfitIntelligence": {
        "selectedItemIds": ["shirt-001", "trousers-001"]
      }
    }
  ''';

  const tNoOutfitIntelligence = '''
    {
      "intent": "hairstyle",
      "text": "Your top pick is the Classic Quiff (85% match). Good volume and texture.",
      "cards": []
    }
  ''';

  const tHairResponse = '''
    {
      "intent": "hairstyle",
      "text": "Your top pick is the Classic Quiff (85% match). Good volume and texture.",
      "cards": [
        {
          "kind": "hairstyle",
          "title": "Classic Quiff",
          "subtitle": "Good volume and texture.",
          "score": 85,
          "items": ["Good volume and texture", "Medium hold", "Best for round faces"],
          "action": "open_hairstyle"
        }
      ]
    }
  ''';

  const tGroomingResponse = '''
    {
      "intent": "grooming",
      "text": "The fade suits you best (78% match). Regular trimming keeps it sharp.",
      "cards": [
        {
          "kind": "grooming",
          "title": "Fade",
          "subtitle": "Regular trimming keeps it sharp.",
          "score": 78,
          "items": ["Short sides", "Long top", "Maintenance every 2 weeks"],
          "action": "open_grooming"
        }
      ]
    }
  ''';

  const tWardrobeResponse = '''
    {
      "intent": "wardrobe",
      "text": "Here’s what I know about your wardrobe: 12 items across 5 categories, 3 favourites.",
      "cards": []
    }
  ''';

  group('Outfit Intelligence - Complete Response', () {
    test('parses successfully with all fields', () {
      final reply = AssistantReply.fromJson(jsonDecode(tCompleteJson) as Map<String, dynamic>);
      expect(reply.intent, 'outfit');
      expect(reply.text, isNotEmpty);
      expect(reply.outfitIntelligence, isNotNull);

      final oi = reply.outfitIntelligence!;
      expect(oi.selectedItemIds, equals(['blazer-001', 'shirt-001', 'trousers-001', 'derbies-001', 'watch-001']));
      expect(oi.outfitComposition.topIds, equals(['shirt-001']));
      expect(oi.outfitComposition.bottomIds, equals(['trousers-001']));
      expect(oi.outfitComposition.outerwearIds, equals(['blazer-001']));
      expect(oi.outfitComposition.footwearIds, equals(['derbies-001']));
      expect(oi.outfitComposition.accessoryIds, equals(['watch-001']));
      expect(oi.outfitComposition.styleScore, equals(91));
      expect(oi.occasion, equals('office'));
      expect(oi.stylingRationale, isNotEmpty);
      expect(oi.compatibilityRationale, isNotEmpty);
      expect(oi.confidence, equals(0.94));
      expect(oi.explanation, isNotEmpty);
      expect(oi.dataAvailability, equals('full'));
    });
  });

  group('Outfit Intelligence - Selected Item IDs', () {
    test('remains exact List<String>, not a concatenated string', () {
      final reply = AssistantReply.fromJson(jsonDecode(tCompleteJson) as Map<String, dynamic>);
      final oi = reply.outfitIntelligence!;
      // Must be a List<String> - assert length > 0 and each element is a String
      expect(oi.selectedItemIds, isA<List<dynamic>>());
      expect(oi.selectedItemIds.length, greaterThan(0));
      expect(oi.selectedItemIds.first, isA<String>());
      // Critical: NOT a single concatenated string
      expect(oi.selectedItemIds, isNot(contains(',')));
    });

    test('pass-through selectedItemIds with only two IDs', () {
      final reply = AssistantReply.fromJson(jsonDecode(tSelectedIdsOnly) as Map<String, dynamic>);
      expect(reply.outfitIntelligence?.selectedItemIds, equals(['shirt-001', 'trousers-001']));
    });
  });

  group('Outfit Intelligence - Composition Categories', () {
    test('preserves exact IDs per category', () {
      final reply = AssistantReply.fromJson(jsonDecode(tCompleteJson) as Map<String, dynamic>);
      final oi = reply.outfitIntelligence!;
      expect(oi.outfitComposition.topIds, hasLength(1));
      expect(oi.outfitComposition.bottomIds, hasLength(1));
      expect(oi.outfitComposition.outerwearIds, hasLength(1));
      expect(oi.outfitComposition.footwearIds, hasLength(1));
      expect(oi.outfitComposition.accessoryIds, hasLength(1));
      expect(oi.outfitComposition.styleScore, greaterThan(0));
    });
  });

  group('Outfit Intelligence - Style Score & Confidence', () {
    test('styleScore parses as int', () {
      final reply = AssistantReply.fromJson(jsonDecode(tCompleteJson) as Map<String, dynamic>);
      expect(reply.outfitIntelligence!.outfitComposition.styleScore, isA<int>());
      expect(reply.outfitIntelligence!.outfitComposition.styleScore, equals(91));
    });

    test('confidence parses as double', () {
      final reply = AssistantReply.fromJson(jsonDecode(tCompleteJson) as Map<String, dynamic>);
      expect(reply.outfitIntelligence!.confidence, isA<double>());
      expect(reply.outfitIntelligence!.confidence, equals(0.94));
    });
  });

  group('Outfit Intelligence - Rationale & Data Availability', () {
    test('occasion parses correctly', () {
      final reply = AssistantReply.fromJson(jsonDecode(tCompleteJson) as Map<String, dynamic>);
      expect(reply.outfitIntelligence!.occasion, equals('office'));
    });

    test('stylingRationale parses as string', () {
      final reply = AssistantReply.fromJson(jsonDecode(tCompleteJson) as Map<String, dynamic>);
      expect(reply.outfitIntelligence!.stylingRationale, isA<String>());
      expect(reply.outfitIntelligence!.stylingRationale, isNotEmpty);
    });

    test('compatibilityRationale parses as string', () {
      final reply = AssistantReply.fromJson(jsonDecode(tCompleteJson) as Map<String, dynamic>);
      expect(reply.outfitIntelligence!.compatibilityRationale, isA<String>());
      expect(reply.outfitIntelligence!.compatibilityRationale, isNotEmpty);
    });

    test('explanation parses as string', () {
      final reply = AssistantReply.fromJson(jsonDecode(tCompleteJson) as Map<String, dynamic>);
      expect(reply.outfitIntelligence!.explanation, isA<String>());
      expect(reply.outfitIntelligence!.explanation, isNotEmpty);
    });

    test('dataAvailability parses as string', () {
      final reply = AssistantReply.fromJson(jsonDecode(tCompleteJson) as Map<String, dynamic>);
      expect(reply.outfitIntelligence!.dataAvailability, isA<String>());
      expect(reply.outfitIntelligence!.dataAvailability, equals('full'));
    });
  });

  group('Backward Compatibility - No Outfit Intelligence', () {
    test('parse succeeds with outfitIntelligence == null', () {
      final reply = AssistantReply.fromJson(jsonDecode(tNoOutfitIntelligence) as Map<String, dynamic>);
      expect(reply.outfitIntelligence, isNull);
      expect(reply.intent, equals('hairstyle'));
      expect(reply.text, isNotEmpty);
    });

    test('hairstyle response still parses correctly', () {
      final reply = AssistantReply.fromJson(jsonDecode(tHairResponse) as Map<String, dynamic>);
      expect(reply.intent, equals('hairstyle'));
      expect(reply.text, isNotEmpty);
      expect(reply.cards, isNotEmpty);
      expect(reply.cards.single.kind, equals('hairstyle'));
    });

    test('grooming response still parses correctly', () {
      final reply = AssistantReply.fromJson(jsonDecode(tGroomingResponse) as Map<String, dynamic>);
      expect(reply.intent, equals('grooming'));
      expect(reply.text, isNotEmpty);
      expect(reply.cards, isNotEmpty);
      expect(reply.cards.single.kind, equals('grooming'));
    });

    test('wardrobe response still parses correctly', () {
      final reply = AssistantReply.fromJson(jsonDecode(tWardrobeResponse) as Map<String, dynamic>);
      expect(reply.intent, equals('wardrobe'));
      expect(reply.text, isNotEmpty);
    });
  });

  OutfitIntelligence testIntelligence() => OutfitIntelligence.fromJson(
    (jsonDecode(tCompleteJson) as Map<String, dynamic>)['outfitIntelligence']
        as Map<String, dynamic>,
  );

  group('Outfit Save Request - backend contract', () {
    test('uses lookId null and sourceContext outfit', () {
      final request = OutfitSaveRequest.fromOutfitIntelligence(
        testIntelligence(),
      );
      final json = request.toJson();
      expect(json['lookId'], isNull);
      expect(json['sourceContext'], equals('outfit'));
      expect(json['title'], equals('Office Outfit'));
    });

    test('falls back to Saved Outfit for empty/unknown occasion', () {
      expect(OutfitSaveRequest.titleForOccasion(''), equals('Saved Outfit'));
      expect(
        OutfitSaveRequest.titleForOccasion('unknown'),
        equals('Saved Outfit'),
      );
      expect(
        OutfitSaveRequest.titleForOccasion('office'),
        equals('Office Outfit'),
      );
    });

    test('snapshot preserves existing OutfitIntelligence fields only', () {
      final request = OutfitSaveRequest.fromOutfitIntelligence(
        testIntelligence(),
      );
      final snapshot = request.snapshot;
      expect(
        snapshot.keys,
        unorderedEquals([
          'selectedItemIds',
          'outfitComposition',
          'occasion',
          'stylingRationale',
          'compatibilityRationale',
          'confidence',
          'explanation',
          'dataAvailability',
        ]),
      );
      expect(
        snapshot['selectedItemIds'],
        equals(['blazer-001', 'shirt-001', 'trousers-001', 'derbies-001', 'watch-001']),
      );
      expect(
        (snapshot['outfitComposition'] as Map<String, dynamic>)['styleScore'],
        equals(91),
      );
      expect(snapshot, isNot(contains('appearance_source_run_id')));
      expect(snapshot, isNot(contains('appearanceSourceRunId')));
    });

    test('idempotency keys are fresh per attempt and UUID-shaped', () {
      final first = newOutfitIdempotencyKey();
      final second = newOutfitIdempotencyKey();
      expect(first, isNot(equals(second)));
      final uuid = RegExp(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
      );
      expect(uuid.hasMatch(first), isTrue);
      expect(uuid.hasMatch(second), isTrue);
    });
  });

  group('Outfit Save Client - POST /v1/looks/saved', () {
    test('sends contract JSON with Idempotency-Key, parses 201', () async {
      Map<String, String>? seenHeaders;
      Map<String, dynamic>? seenBody;
      final client = AssistantClient(
        client: MockClient((request) async {
          seenHeaders = request.headers;
          seenBody = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
            jsonEncode({
              'id': 'saved-1',
              'title': 'Office Outfit',
              'sourceContext': 'outfit',
              'snapshot': seenBody!['snapshot'],
            }),
            201,
          );
        }),
      );
      final request = OutfitSaveRequest.fromOutfitIntelligence(
        testIntelligence(),
      );
      final saved = await client.saveOutfitLook(
        request: request,
        idempotencyKey: 'key-123',
      );
      expect(seenHeaders!['Idempotency-Key'], equals('key-123'));
      expect(seenBody!['lookId'], isNull);
      expect(seenBody!['sourceContext'], equals('outfit'));
      expect(seenBody!['title'], equals('Office Outfit'));
      expect(saved, isNotNull);
      expect(saved!.id, equals('saved-1'));
      client.dispose();
    });

    test('returns null on backend error so UI stays unsaved', () async {
      final client = AssistantClient(
        client: MockClient(
          (_) async => http.Response('{"error":"boom"}', 500),
        ),
      );
      final saved = await client.saveOutfitLook(
        request: OutfitSaveRequest.fromOutfitIntelligence(testIntelligence()),
        idempotencyKey: 'key-err',
      );
      expect(saved, isNull);
      client.dispose();
    });
  });

  group('Outfit Save Service - orchestration', () {
    test('returns true on success, false on failure (retry possible)', () async {
      var calls = 0;
      final okService = AssistantService(
        client: AssistantClient(
          client: MockClient(
            (_) async => http.Response(
              jsonEncode({'id': 's1', 'title': 'Office Outfit'}),
              201,
            ),
          ),
        ),
      );
      expect(await okService.saveOutfit(testIntelligence()), isTrue);

      final failService = AssistantService(
        client: AssistantClient(
          client: MockClient((_) async {
            calls++;
            return http.Response('err', 500);
          }),
        ),
      );
      expect(await failService.saveOutfit(testIntelligence()), isFalse);
      // Retry remains possible: a second attempt re-issues the request.
      expect(await failService.saveOutfit(testIntelligence()), isFalse);
      expect(calls, equals(2));
      okService.dispose();
      failService.dispose();
    });
  });

  group('OutfitRecommendationCard - save state machine', () {
    Widget buildSaveCard({
      Future<bool> Function()? onSave,
      bool initialSaved = false,
    }) => MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: OutfitRecommendationCard(
            outfitIntelligence: testIntelligence(),
            wardrobeItems: const [],
            onSave: onSave,
            initialSaved: initialSaved,
          ),
        ),
      ),
    );

    FilledButton saveButton(WidgetTester tester) =>
        tester.widget<FilledButton>(find.byType(FilledButton));

    testWidgets('save action is available with an onSave callback', (
      tester,
    ) async {
      await tester.pumpWidget(buildSaveCard(onSave: () async => true));
      expect(find.text('Save'), findsOneWidget);
      expect(saveButton(tester).onPressed, isNotNull);
    });

    testWidgets('tapping Save shows saving state and blocks repeat taps', (
      tester,
    ) async {
      final pending = Completer<bool>();
      var calls = 0;
      await tester.pumpWidget(
        buildSaveCard(
          onSave: () {
            calls++;
            return pending.future;
          },
        ),
      );
      await tester.tap(find.text('Save'));
      await tester.pump();
      expect(find.text('Saving...'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(saveButton(tester).onPressed, isNull);
      // Repeat tap while pending must not re-trigger the save.
      await tester.tap(find.text('Saving...'));
      await tester.pump();
      expect(calls, equals(1));
      pending.complete(true);
      await tester.pumpAndSettle();
      expect(find.text('Saved'), findsOneWidget);
    });

    testWidgets('successful save shows Saved and disables the action', (
      tester,
    ) async {
      await tester.pumpWidget(buildSaveCard(onSave: () async => true));
      await tester.tap(find.text('Save'));
      await tester.pumpAndSettle();
      expect(find.text('Saved'), findsOneWidget);
      expect(find.text('Save'), findsNothing);
      expect(saveButton(tester).onPressed, isNull);
    });

    testWidgets('failed save shows retry message and stays unsaved', (
      tester,
    ) async {
      await tester.pumpWidget(buildSaveCard(onSave: () async => false));
      await tester.tap(find.text('Save'));
      await tester.pumpAndSettle();
      expect(find.text("Couldn't save. Try again."), findsOneWidget);
      expect(find.text('Saved'), findsNothing);
      expect(find.text('Save'), findsOneWidget);
      expect(saveButton(tester).onPressed, isNotNull);
    });

    testWidgets('retry after failure can succeed', (tester) async {
      var calls = 0;
      await tester.pumpWidget(
        buildSaveCard(
          onSave: () async {
            calls++;
            return calls > 1;
          },
        ),
      );
      await tester.tap(find.text('Save'));
      await tester.pumpAndSettle();
      expect(find.text("Couldn't save. Try again."), findsOneWidget);
      await tester.tap(find.text('Save'));
      await tester.pumpAndSettle();
      expect(find.text('Saved'), findsOneWidget);
      expect(calls, equals(2));
    });

    testWidgets('initialSaved shows Saved immediately without active action', (
      tester,
    ) async {
      await tester.pumpWidget(
        buildSaveCard(onSave: () async => true, initialSaved: true),
      );
      expect(find.text('Saved'), findsOneWidget);
      expect(saveButton(tester).onPressed, isNull);
    });

    testWidgets('card without onSave exposes no active save interaction', (
      tester,
    ) async {
      await tester.pumpWidget(buildSaveCard());
      expect(find.text('Save'), findsOneWidget);
      expect(saveButton(tester).onPressed, isNull);
    });
  });
}