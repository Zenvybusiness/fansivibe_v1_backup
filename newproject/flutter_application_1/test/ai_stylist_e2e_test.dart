import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/assistant/data/assistant_client.dart';
import 'package:fansivibe/features/assistant/domain/assistant_service.dart';
import 'package:fansivibe/features/assistant/presentation/assistant_screen.dart';
import 'package:fansivibe/features/stylist/presentation/stylist_screen.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';

Widget _buildTestApp({
  required Widget child,
}) {
  return MaterialApp(
    theme: FansivibeTheme.darkTheme,
    home: Scaffold(body: child),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AI Stylist End-to-End Flutter Journey', () {
    testWidgets('StylistScreen renders Ask AI Stylist hero with quick prompt chips', (
      WidgetTester tester,
    ) async {
      await tester.binding.setSurfaceSize(const Size(800, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _buildTestApp(child: const StylistScreen()),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('Ask AI Stylist'), findsOneWidget);
      expect(find.text('What should I wear today?'), findsOneWidget);
      expect(find.text('Wedding outfit'), findsOneWidget);
      expect(find.text('Style my pieces'), findsOneWidget);
    });

    testWidgets('AssistantScreen executes initialQuery and renders recommendation with follow-up chips', (
      WidgetTester tester,
    ) async {
      await tester.binding.setSurfaceSize(const Size(800, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'intent': 'outfit',
            'text': 'Here is a tailored outfit for today.',
            'cards': [
              {
                'kind': 'outfit',
                'title': 'Contemporary Minimalist',
                'subtitle': '92% match • Balanced neutrals and clean silhouette',
                'score': 92,
                'items': [
                  'White Linen Shirt - Tops',
                  'Navy Wool Trousers - Bottoms',
                ],
                'action': 'open_outfit',
              }
            ],
            'outfitIntelligence': {
              'selectedItemIds': ['item-1', 'item-2'],
              'occasion': 'casual',
              'stylingRationale': 'Balanced neutrals and clean silhouette',
              'compatibilityRationale': 'Colors harmonize naturally',
              'confidence': 0.92,
              'dataAvailability': 'full',
              'status': 'success',
            },
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final service = AssistantService(
        client: AssistantClient(client: mockClient),
      );

      await tester.pumpWidget(
        _buildTestApp(
          child: AssistantScreen(
            service: service,
            initialQuery: 'What should I wear today?',
          ),
        ),
      );

      // Settle initialQuery post frame callback and network request
      await tester.pump();
      await tester.pumpAndSettle();

      expect(find.text('What should I wear today?'), findsOneWidget);
      expect(find.text('Your Outfit'), findsOneWidget);
      expect(find.text('Why it works'), findsOneWidget);
      expect(find.text('Balanced neutrals and clean silhouette'), findsOneWidget);
      expect(find.text('Make it more formal'), findsOneWidget);
      expect(find.text('Replace shoes'), findsOneWidget);
      expect(find.text('Show alternatives'), findsOneWidget);
    });

    testWidgets('Tapping follow-up chip triggers follow-up styling request', (
      WidgetTester tester,
    ) async {
      await tester.binding.setSurfaceSize(const Size(800, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      int requestCount = 0;
      final mockClient = MockClient((request) async {
        requestCount++;
        if (requestCount == 1) {
          return http.Response(
            jsonEncode({
              'intent': 'outfit',
              'text': 'Casual outfit ready.',
              'cards': [
                {
                  'kind': 'outfit',
                  'title': 'Casual Linen',
                  'subtitle': 'Relaxed styling',
                  'score': 85,
                  'items': ['White Linen Shirt - Tops'],
                  'action': 'open_outfit',
                }
              ],
              'outfitIntelligence': {
                'selectedItemIds': ['item-1'],
                'occasion': 'casual',
                'stylingRationale': 'Relaxed styling',
                'compatibilityRationale': 'Soft contrast',
                'confidence': 0.85,
                'dataAvailability': 'full',
                'status': 'success',
              },
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        } else {
          return http.Response(
            jsonEncode({
              'intent': 'outfit',
              'text': 'Adjusted to formal.',
              'cards': [
                {
                  'kind': 'outfit',
                  'title': 'Formal Tailored Suit',
                  'subtitle': 'Elevated formal styling',
                  'score': 95,
                  'items': ['Navy Blazer - Outerwear'],
                  'action': 'open_outfit',
                }
              ],
              'outfitIntelligence': {
                'selectedItemIds': ['item-2'],
                'occasion': 'formal',
                'stylingRationale': 'Elevated formal styling',
                'compatibilityRationale': 'Sophisticated lines',
                'confidence': 0.95,
                'dataAvailability': 'full',
                'status': 'success',
              },
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
      });

      final service = AssistantService(
        client: AssistantClient(client: mockClient),
      );

      await tester.pumpWidget(
        _buildTestApp(
          child: AssistantScreen(
            service: service,
            initialQuery: 'Suggest a casual outfit',
          ),
        ),
      );

      await tester.pump();
      await tester.pumpAndSettle();

      expect(find.text('Relaxed styling'), findsOneWidget);
      expect(find.text('Make it more formal'), findsOneWidget);

      // Tap the follow-up chip
      await tester.tap(find.text('Make it more formal'));
      await tester.pump();
      await tester.pumpAndSettle();

      expect(requestCount, 2);
      expect(find.text('Elevated formal styling'), findsOneWidget);
    });

    testWidgets('Empty wardrobe request displays truthful guidance card with Open action', (
      WidgetTester tester,
    ) async {
      await tester.binding.setSurfaceSize(const Size(800, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'intent': 'outfit',
            'text': 'Your wardrobe is currently empty. Add items to receive personalized recommendations.',
            'cards': [
              {
                'kind': 'outfit',
                'title': 'Empty Wardrobe',
                'subtitle': 'Add tops and bottoms to your wardrobe to get personalized outfit recommendations.',
                'score': null,
                'items': ['No wardrobe items catalogued yet'],
                'action': 'open_wardrobe',
              }
            ],
            'outfitIntelligence': {
              'selectedItemIds': <String>[],
              'occasion': 'casual',
              'stylingRationale': 'Empty wardrobe',
              'dataAvailability': 'none',
              'status': 'empty_wardrobe',
            },
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final service = AssistantService(
        client: AssistantClient(client: mockClient),
      );

      await tester.pumpWidget(
        _buildTestApp(
          child: AssistantScreen(
            service: service,
            initialQuery: 'What should I wear today?',
          ),
        ),
      );

      await tester.pump();
      await tester.pumpAndSettle();

      expect(find.text('Empty Wardrobe'), findsOneWidget);
      expect(find.text('No wardrobe items catalogued yet'), findsOneWidget);
      expect(find.text('Open'), findsOneWidget);
    });

    testWidgets('Save recommendation button saves look and updates button state', (
      WidgetTester tester,
    ) async {
      await tester.binding.setSurfaceSize(const Size(800, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      bool saveAttempted = false;
      final mockClient = MockClient((request) async {
        if (request.url.path.contains('looks/saved')) {
          saveAttempted = true;
          return http.Response(
            jsonEncode({'id': 'saved-look-1', 'title': 'Contemporary Look'}),
            201,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response(
          jsonEncode({
            'intent': 'outfit',
            'text': 'Here is an outfit.',
            'cards': [
              {
                'kind': 'outfit',
                'title': 'Contemporary Look',
                'subtitle': 'Clean aesthetic',
                'score': 90,
                'items': ['White Shirt - Tops'],
                'action': 'open_outfit',
              }
            ],
            'outfitIntelligence': {
              'selectedItemIds': ['b30740a1-4322-49fa-9488-dcff79c836ef'],
              'occasion': 'casual',
              'stylingRationale': 'Clean aesthetic',
              'compatibilityRationale': 'Complementary palette',
              'confidence': 0.9,
              'dataAvailability': 'full',
              'status': 'success',
            },
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final service = AssistantService(
        client: AssistantClient(client: mockClient),
      );

      await tester.pumpWidget(
        _buildTestApp(
          child: AssistantScreen(
            service: service,
            initialQuery: 'What should I wear today?',
          ),
        ),
      );

      await tester.pump();
      await tester.pumpAndSettle();

      expect(find.text('Save'), findsOneWidget);

      await tester.tap(find.text('Save'));
      await tester.pump();
      await tester.pumpAndSettle();

      expect(saveAttempted, isTrue);
      expect(find.text('Saved'), findsOneWidget);
    });
  });
}
