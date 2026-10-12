import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';

import 'package:fansivibe/features/assistant/data/assistant_client.dart';
import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/assistant/domain/assistant_service.dart';
import 'package:fansivibe/features/assistant/presentation/assistant_screen.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';

// 1x1 transparent PNG — decodes in the widget-test binding.
final Uint8List kPngBytes = Uint8List.fromList([
  137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 1,
  0, 0, 0, 1, 8, 6, 0, 0, 0, 31, 21, 196, 137, 0, 0, 0, 10, 73, 68, 65, 84,
  120, 156, 99, 0, 1, 0, 0, 5, 0, 1, 13, 10, 45, 180, 0, 0, 0, 0, 73, 69,
  78, 68, 174, 66, 96, 130,
]);

class _FakeImageClient extends AssistantClient {
  Uint8List? lastBytes;
  String? lastFilename;
  String? lastMessage;
  List<Map<String, String>>? lastHistory;
  Map<String, dynamic>? lastUser;
  int calls = 0;
  bool fail = false;

  AssistantReply get reply => const AssistantReply(
    intent: 'outfit_image',
    text: 'I can see oxford shirt in light blue in this photo.',
    cards: [
      SuggestionCard(
        kind: 'outfit',
        title: 'Observed: oxford shirt',
        subtitle: 'Measured from your photo.',
        items: ['category: tops', 'color: light blue'],
      ),
    ],
  );

  @override
  Future<AssistantReply?> chatWithImage({
    required Uint8List bytes,
    required String filename,
    required String message,
    required List<AssistantMessage> history,
    required AssistantUserContext context,
  }) async {
    calls++;
    lastBytes = bytes;
    lastFilename = filename;
    lastMessage = message;
    lastHistory =
        history.map((m) => {'role': m.role, 'content': m.text}).toList();
    lastUser = context.toJson();
    if (fail) return null;
    return reply;
  }
}

class _FakeLearning implements LearningRepository {
  _FakeLearning(this.items);

  final List<WardrobeEntry> items;
  final List<(String, String)> recordedSignals = [];

  @override
  List<WardrobeEntry> get wardrobe => items;
  @override
  FaceProfile? get face => null;
  @override
  String? get styleType => null;
  @override
  List<String> get savedLooks => const [];
  @override
  List<String> get preferredOccasions => const [];
  @override
  List<LearningSignal> get signals => const [];
  @override
  int get styleScore => 0;
  @override
  Future<void> load() async {}
  @override
  void addItem(WardrobeEntry item) {}
  @override
  void setFace(FaceProfile face) {}
  @override
  void setStyleType(String styleType) {}
  @override
  void addSavedLook(String title) {}
  @override
  void addPreferredOccasion(String occasion) {}
  @override
  void recordSignal(String type, String label) =>
      recordedSignals.add((type, label));
  @override
  void updateItem(String itemId, WardrobeEntry item) {}
}

AssistantService _service(_FakeImageClient client) =>
    AssistantService(client: client);

void main() {
  group('AssistantService.sendWithImage', () {
    test('actual bytes reach the verified endpoint with the question', () async {
      final client = _FakeImageClient();
      final service = _service(client);
      await service.sendWithImage(
        text: 'Does this suit me?',
        imageBytes: kPngBytes,
        filename: 'outfit.jpg',
      );
      expect(client.calls, 1);
      expect(client.lastBytes, kPngBytes);
      expect(client.lastFilename, 'outfit.jpg');
      expect(client.lastMessage, 'Does this suit me?');
      expect(service.messages.length, 2);
      expect(service.messages[0].isUser, isTrue);
      expect(service.messages[0].imageBytes, kPngBytes);
      expect(service.messages[0].text, 'Does this suit me?');
      expect(service.messages[1].text, contains('oxford shirt'));
      service.dispose();
    });

    test('image-only message is allowed', () async {
      final client = _FakeImageClient();
      final service = _service(client);
      await service.sendWithImage(text: '  ', imageBytes: kPngBytes);
      expect(client.calls, 1);
      expect(client.lastMessage, '');
      expect(service.messages[0].text, '');
      expect(service.messages[0].imageBytes, isNotNull);
      service.dispose();
    });

    test('failure shows honest error with retry, never offline fallback',
        () async {
      final client = _FakeImageClient()..fail = true;
      final service = _service(client);
      await service.sendWithImage(text: 'What is this?', imageBytes: kPngBytes);
      expect(service.messages.length, 2);
      final error = service.messages[1];
      expect(error.isOffline, isFalse);
      expect(error.text, contains("couldn't analyze"));
      expect(
        error.clarifications.map((c) => c.label),
        contains('Retry analysis'),
      );
      service.dispose();
    });

    test('retry resends kept photo without duplicating the user turn',
        () async {
      final client = _FakeImageClient()..fail = true;
      final service = _service(client);
      await service.sendWithImage(text: 'What is this?', imageBytes: kPngBytes);
      client.fail = false;
      await service.retryLastImage();
      expect(client.calls, 2);
      expect(client.lastBytes, kPngBytes);
      expect(
        service.messages.where((m) => m.isUser && m.imageBytes != null).length,
        1,
      );
      expect(service.messages.last.text, contains('oxford shirt'));
      service.dispose();
    });

    test('retry chip routes through selectClarification', () async {
      final client = _FakeImageClient()..fail = true;
      final service = _service(client);
      await service.sendWithImage(text: 'Hi', imageBytes: kPngBytes);
      client.fail = false;
      await service.selectClarification(
        const ClarificationOption(
          label: 'Retry analysis',
          value: AssistantService.retryImageValue,
        ),
      );
      expect(client.calls, 2);
      service.dispose();
    });

    test('duplicate sends while sending are ignored', () async {
      final client = _FakeImageClient();
      final service = _service(client);
      service.sendWithImage(text: 'one', imageBytes: kPngBytes);
      service.sendWithImage(text: 'two', imageBytes: kPngBytes);
      await Future<void>.delayed(Duration.zero);
      expect(client.calls, 1);
      service.dispose();
    });

    test('empty bytes are refused', () async {
      final client = _FakeImageClient();
      final service = _service(client);
      await service.sendWithImage(text: 'hi', imageBytes: Uint8List(0));
      expect(client.calls, 0);
      expect(service.messages, isEmpty);
      service.dispose();
    });

    test('wardrobe photo bytes are stripped from the image-chat context',
        () async {
      final client = _FakeImageClient();
      final service = _service(client);
      service.attachLearning(
        _FakeLearning([
          WardrobeEntry(
            id: '1',
            name: 'Blue Shirt',
            category: 'tops',
            color: 'blue',
            imageBase64: 'ZmFrZS1ieXRlcw==',
          ),
        ]),
      );
      await service.sendWithImage(text: 'Match?', imageBytes: kPngBytes);
      final wardrobe = client.lastUser!['wardrobe'] as List;
      expect(wardrobe.length, 1);
      expect(
        (wardrobe.first as Map).containsKey('imageBase64'),
        isFalse,
        reason: 'photo bytes must not ride the image-chat request',
      );
      service.dispose();
    });

    test('text-only send still uses the offline fallback', () async {
      final service = AssistantService(client: _FakeImageClient());
      await service.send('hello');
      expect(service.messages.length, 2);
      service.dispose();
    });
  });

  group('AssistantScreen image composer', () {
    Future<XFile?> pickOk(ImageSource source) async =>
        XFile.fromData(kPngBytes, name: 'outfit.jpg', mimeType: 'image/jpeg');

    Future<XFile?> pickCancel(ImageSource source) async => null;

    Widget app(AssistantService service, Future<XFile?> Function(ImageSource)? pick) =>
        MaterialApp(home: AssistantScreen(service: service, pickImage: pick));

    testWidgets('image button appears beside Send', (tester) async {
      final service = _service(_FakeImageClient());
      await tester.pumpWidget(app(service, pickOk));
      expect(find.byKey(const Key('assistant_attach_button')), findsOneWidget);
      expect(find.byIcon(Icons.send_rounded), findsOneWidget);
      service.dispose();
    });

    testWidgets('gallery selection shows preview; remove keeps text',
        (tester) async {
      final service = _service(_FakeImageClient());
      await tester.pumpWidget(app(service, pickOk));
      await tester.enterText(find.byType(TextField), 'my question');
      await tester.tap(find.byKey(const Key('assistant_attach_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('assistant_pick_gallery')));
      await tester.pumpAndSettle();
      expect(
        find.byKey(const Key('assistant_attachment_preview')),
        findsOneWidget,
      );
      await tester.tap(find.byKey(const Key('assistant_attachment_remove')));
      await tester.pump();
      expect(
        find.byKey(const Key('assistant_attachment_preview')),
        findsNothing,
      );
      expect(find.text('my question'), findsOneWidget);
      service.dispose();
    });

    testWidgets('picker cancel keeps unsent text', (tester) async {
      final service = _service(_FakeImageClient());
      await tester.pumpWidget(app(service, pickCancel));
      await tester.enterText(find.byType(TextField), 'keep me');
      await tester.tap(find.byKey(const Key('assistant_attach_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('assistant_pick_gallery')));
      await tester.pumpAndSettle();
      expect(
        find.byKey(const Key('assistant_attachment_preview')),
        findsNothing,
      );
      expect(find.text('keep me'), findsOneWidget);
      service.dispose();
    });

    testWidgets('invalid file shows error and stages nothing', (tester) async {
      Future<XFile?> pickBad(ImageSource source) async =>
          XFile.fromData(kPngBytes, name: 'outfit.gif', mimeType: 'image/gif');
      final service = _service(_FakeImageClient());
      await tester.pumpWidget(app(service, pickBad));
      await tester.tap(find.byKey(const Key('assistant_attach_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('assistant_pick_gallery')));
      await tester.pumpAndSettle();
      expect(find.textContaining('Unsupported photo format'), findsOneWidget);
      expect(
        find.byKey(const Key('assistant_attachment_preview')),
        findsNothing,
      );
      service.dispose();
    });

    testWidgets('send with image posts photo turn and renders reply',
        (tester) async {
      final service = _service(_FakeImageClient());
      await tester.pumpWidget(app(service, pickOk));
      await tester.tap(find.byKey(const Key('assistant_attach_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('assistant_pick_gallery')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'What is this?');
      await tester.tap(find.byIcon(Icons.send_rounded));
      await tester.pumpAndSettle();
      expect(find.byType(Image), findsWidgets);
      expect(find.text('What is this?'), findsOneWidget);
      expect(find.textContaining('oxford shirt'), findsWidgets);
      service.dispose();
    });
  });
}
