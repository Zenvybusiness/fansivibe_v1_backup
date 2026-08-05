import 'package:flutter_test/flutter_test.dart';

import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/assistant/data/offline_assistant.dart';

void main() {
  final assistant = OfflineAssistant();
  const context = AssistantUserContext();

  group('OfflineAssistant greeting', () {
    test('greets on hello', () {
      final reply = assistant.replyFor('hello', context);
      expect(reply.intent, 'greeting');
      expect(reply.text, isNotEmpty);
    });
  });

  group('OfflineAssistant thanks', () {
    test('acknowledges thanks', () {
      final reply = assistant.replyFor('thanks a lot', context);
      expect(reply.intent, 'thanks');
      expect(reply.text, contains('Anytime'));
    });
  });

  group('OfflineAssistant outfit cards', () {
    test('office returns the office ensemble with office items', () {
      final reply = assistant.replyFor('office', context);
      expect(reply.intent, 'outfit');
      final card = reply.cards.single;
      expect(card.title, 'Refined Office Ensemble');
      expect(card.items, contains('Navy Textured Blazer - Outerwear'));
      expect(card.items, isNot(contains('White Cotton Tee - Tops')));
    });

    test('date returns date-night items, not the office default', () {
      final reply = assistant.replyFor('date', context);
      expect(reply.intent, 'outfit');
      final card = reply.cards.single;
      expect(card.title, 'Date Night Refined');
      expect(card.items, contains('Burgundy Polo - Tops'));
      expect(card.items, isNot(contains('Navy Textured Blazer - Outerwear')));
    });

    test('party and travel return their own look cards', () {
      final party = assistant.replyFor('party', context);
      expect(party.cards.single.title, 'Party Statement');

      final travel = assistant.replyFor('travel', context);
      expect(travel.cards.single.title, 'Travel Comfort');
    });

    test('ambiguous outfit question offers occasion chips', () {
      final reply = assistant.replyFor('what should I wear?', context);
      expect(reply.intent, 'outfit');
      expect(reply.clarifications, isNotEmpty);
      expect(reply.cards, isEmpty);
    });
  });
}
