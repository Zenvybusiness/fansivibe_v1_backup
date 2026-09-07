import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';

import 'package:fansivibe/features/assistant/data/models.dart';

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
}