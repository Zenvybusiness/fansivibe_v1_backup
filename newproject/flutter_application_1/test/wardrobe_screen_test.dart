import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/app/app.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/presentation/widgets/wardrobe_widgets.dart';

void main() {
  group('WardrobeScreen Widget Tests', () {
    testWidgets('renders wardrobe header with title, count, and style type', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Navigate to Wardrobe tab
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('My Wardrobe'), findsOneWidget);
      expect(find.text('24 items'), findsWidgets);
      expect(find.text('Modern Minimalist'), findsOneWidget);
    });

    testWidgets('renders AI Wardrobe Insight card', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Wardrobe Health'), findsOneWidget);
      expect(find.text('AI Insight'), findsOneWidget);
      expect(
        find.textContaining('Your wardrobe is balanced across seasons'),
        findsOneWidget,
      );
      expect(find.text('View Analysis'), findsOneWidget);
    });

    testWidgets('renders category filters', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify categories section renders
      expect(find.text('Categories'), findsOneWidget);
      // Verify a visible category chip
      expect(find.text('All Items'), findsWidgets);
      expect(find.text('Tops'), findsOneWidget);
    });

    testWidgets('renders clothing item grid with all items', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      // Verify section title (appears as chip and section title)
      expect(find.text('All Items'), findsWidgets);
      expect(find.text('24 items'), findsWidgets);

      // Verify some items appear
      expect(find.text('Merino Crew Neck'), findsOneWidget);
      expect(find.text('Leather Chelsea Boots'), findsOneWidget);
    });

    testWidgets('filtering by category shows only matching items', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      // Tap the Tops category filter
      await tester.tap(find.text('Tops'));
      await tester.pumpAndSettle();

      // Should show "Tops" section title with correct count
      expect(find.text('Tops'), findsWidgets);
      expect(find.text('8 items'), findsOneWidget);
    });

    testWidgets('View Analysis button shows snackbar on tap', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      // Scroll to View Analysis button
      await tester.scrollUntilVisible(
        find.text('View Analysis'),
        500.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();

      // Tap the WardrobeActionButton (nearest match)
      final viewAnalysisBtn = find.text('View Analysis');
      await tester.tap(viewAnalysisBtn);
      await tester.pumpAndSettle();

      expect(find.text('Opening Wardrobe Analysis...'), findsOneWidget);
    });

    testWidgets('Add Item button navigates to category selection', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      // Scroll to bottom
      await tester.scrollUntilVisible(
        find.text('Add Item to Wardrobe'),
        500.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Add Item to Wardrobe'));
      await tester.pumpAndSettle();

      expect(find.text('Add Item'), findsOneWidget);
      expect(find.text('Select a Category'), findsOneWidget);
      expect(find.text('Tops'), findsOneWidget);
    });

    testWidgets('item tap navigates to item details screen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      // Scroll down to make items visible
      await tester.scrollUntilVisible(
        find.text('Merino Crew Neck'),
        500.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Merino Crew Neck'));
      await tester.pumpAndSettle();

      // Should show details screen with item info
      expect(find.text('Details'), findsOneWidget);
      expect(find.text('Color'), findsOneWidget);
      expect(find.text('Charcoal'), findsOneWidget);
      expect(find.text('Material'), findsOneWidget);
      expect(find.text('Wool'), findsOneWidget);
      expect(find.text('Edit Item'), findsOneWidget);
      expect(find.text('Add to Outfit'), findsOneWidget);
      expect(find.text('Delete'), findsOneWidget);
    });

    testWidgets('Wardrobe screen is scrollable', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Wardrobe'),
        ),
      );
      await tester.pumpAndSettle();

      // Scroll down to reveal all sections
      await tester.drag(
        find.byType(SingleChildScrollView),
        const Offset(0, -1000),
      );
      await tester.pumpAndSettle();

      // All major sections should render
      expect(find.text('My Wardrobe'), findsOneWidget);
      expect(find.text('Wardrobe Health'), findsOneWidget);
      expect(find.text('Categories'), findsOneWidget);
      expect(find.text('Add Item to Wardrobe'), findsOneWidget);
    });
  });

  group('Wardrobe Feature Widgets Tests', () {
    testWidgets('WardrobeHeader renders correctly', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const Scaffold(
            body: WardrobeHeader(totalItems: 10, styleType: 'Casual'),
          ),
        ),
      );

      expect(find.text('My Wardrobe'), findsOneWidget);
      expect(find.text('10 items'), findsOneWidget);
      expect(find.text('Casual'), findsOneWidget);
    });

    testWidgets('WardrobeInsightCard renders with action', (
      WidgetTester tester,
    ) async {
      bool tapped = false;
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: WardrobeInsightCard(
              data: WardrobeInsightData.mock,
              onActionPressed: () => tapped = true,
            ),
          ),
        ),
      );

      expect(find.text('Wardrobe Health'), findsOneWidget);
      expect(find.text('AI Insight'), findsOneWidget);
      expect(find.text('View Analysis'), findsOneWidget);

      await tester.tap(find.text('View Analysis'));
      await tester.pump();
      expect(tapped, true);
    });

    testWidgets('CategoryFilterChip renders and responds to selection', (
      WidgetTester tester,
    ) async {
      bool tapped = false;
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: CategoryFilterChip(
              category: WardrobeMockData.categories.first,
              isSelected: true,
              onTap: () => tapped = true,
            ),
          ),
        ),
      );

      expect(find.text('All Items'), findsOneWidget);
      await tester.tap(find.text('All Items'));
      await tester.pump();
      expect(tapped, true);
    });

    testWidgets('ClothingItemCard renders item info', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: ClothingItemCard(item: WardrobeMockData.items.first),
          ),
        ),
      );

      expect(find.text('Merino Crew Neck'), findsOneWidget);
      expect(find.text('Charcoal'), findsOneWidget);
    });

    testWidgets('ClothingItemCard shows favorite icon for favorite items', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: ClothingItemCard(item: WardrobeMockData.items.first),
          ),
        ),
      );

      expect(find.byIcon(Icons.favorite_rounded), findsOneWidget);
    });

    testWidgets('ClothingItemCard does not show favorite for non-favorites', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: ClothingItemCard(
              item:
                  WardrobeMockData.items[1], // Linen Button-Down, not favorite
            ),
          ),
        ),
      );

      expect(find.byIcon(Icons.favorite_rounded), findsNothing);
    });

    testWidgets('WardrobeActionButton renders and handles tap', (
      WidgetTester tester,
    ) async {
      bool tapped = false;
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: WardrobeActionButton(
              label: 'Test Action',
              icon: Icons.add_rounded,
              onPressed: () => tapped = true,
            ),
          ),
        ),
      );

      expect(find.text('Test Action'), findsOneWidget);
      await tester.tap(find.text('Test Action'));
      await tester.pump();
      expect(tapped, true);
    });

    testWidgets('WardrobeSectionTitle renders with title and subtitle', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const Scaffold(
            body: WardrobeSectionTitle(
              title: 'Test Section',
              subtitle: 'Test subtitle',
            ),
          ),
        ),
      );

      expect(find.text('Test Section'), findsOneWidget);
      expect(find.text('Test subtitle'), findsOneWidget);
    });
  });
}
