import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/app/app.dart';
import 'package:fansivibe/features/home/data/home_mock_data.dart';
import 'package:fansivibe/features/home/presentation/home_screen.dart';
import 'package:fansivibe/features/home/presentation/widgets/home_widgets.dart';

void main() {
  group('HomeScreen Widget Tests', () {
    testWidgets('renders greeting header with personalized greeting', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Verify greeting is displayed
      expect(find.text('Good morning, Alex'), findsOneWidget);
      expect(find.text('Monday, January 13'), findsOneWidget);
    });

    testWidgets('renders Today\'s Look card with all components', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Verify Today's Look card elements
      expect(find.text('TODAY\'S LOOK'), findsOneWidget);
      expect(find.text('Modern Minimalist'), findsOneWidget);
      expect(find.text('Work • Casual Friday'), findsOneWidget);
      expect(find.text('Style Score'), findsOneWidget);
      expect(find.text('87'), findsWidgets); // Style score badge

      // Verify description
      expect(
        find.textContaining('Clean lines meet relaxed sophistication'),
        findsOneWidget,
      );

      // Verify outfit items
      expect(find.text('Charcoal Unstructured Blazer'), findsOneWidget);
      expect(find.text('Merino Wool Crewneck'), findsOneWidget);
      expect(find.text('Tapered Wool Trousers'), findsOneWidget);
      expect(find.text('Leather Chelsea Boots'), findsOneWidget);
      expect(find.text('Minimalist Leather Belt'), findsOneWidget);

      // Verify action buttons
      expect(find.text('Try This Look'), findsOneWidget);
      expect(
        find.text('Change Style'),
        findsWidgets,
      ); // Appears in Today's Look and Quick Actions
    });

    testWidgets('renders Style Score card with breakdown', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Scroll to find Style Score section
      await tester.scrollUntilVisible(find.text('Style Score'), 500.0);

      expect(find.text('Style Score'), findsOneWidget);
      expect(find.text('Your weekly style performance'), findsOneWidget);
      expect(find.text('84'), findsWidgets); // Current score
      expect(find.text('+3 vs last week'), findsOneWidget);

      // Verify breakdown categories
      expect(find.text('Fit'), findsOneWidget);
      expect(find.text('Color'), findsOneWidget);
      expect(find.text('Occasion'), findsOneWidget);
      expect(find.text('Creativity'), findsOneWidget);
    });

    testWidgets('renders Quick Actions section', (WidgetTester tester) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.scrollUntilVisible(find.text('Quick Actions'), 500.0);

      expect(find.text('Quick Actions'), findsOneWidget);
      expect(find.text('Scan My Outfit'), findsOneWidget);
      expect(find.text('Get AI analysis of your current look'), findsOneWidget);
      expect(find.text('Build Outfit'), findsOneWidget);
      expect(find.text('Create a look from your wardrobe'), findsOneWidget);
      expect(
        find.text('Change Style'),
        findsWidgets,
      ); // Appears in both Today's Look and Quick Actions
      expect(find.text('Adjust today\'s recommendation'), findsOneWidget);
    });

    testWidgets('renders Style Streak card with progress', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.scrollUntilVisible(find.text('Style Streak'), 500.0);

      expect(find.text('Style Streak'), findsOneWidget);
      expect(find.text('Keep your daily style momentum'), findsOneWidget);
      expect(find.text('Current'), findsOneWidget);
      expect(find.text('Longest'), findsOneWidget);
      expect(find.text('Total'), findsOneWidget);

      // Verify streak days
      expect(find.text('Mon'), findsOneWidget);
      expect(find.text('Tue'), findsOneWidget);
      expect(find.text('Wed'), findsOneWidget);
      expect(find.text('Thu'), findsOneWidget);
      expect(find.text('Fri'), findsOneWidget);
      expect(find.text('Sat'), findsOneWidget);
      expect(find.text('Sun'), findsOneWidget);
    });

    testWidgets('renders AI Wardrobe Insight card', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.scrollUntilVisible(find.text('AI Insight'), 500.0);

      expect(find.text('AI Insight'), findsOneWidget);
      expect(find.text('Wardrobe Gap Detected'), findsOneWidget);
      expect(
        find.textContaining(
          'You have 3 navy blazers but no lightweight spring jackets',
        ),
        findsOneWidget,
      );
      expect(find.text('View Recommendations'), findsOneWidget);
    });

    testWidgets('Try This Look button shows snackbar on tap', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Find and tap the Try This Look button (need to scroll to it first)
      await tester.scrollUntilVisible(find.text('Try This Look'), 500.0);
      await tester.pumpAndSettle();
      await tester.tap(find.byType(HomeActionButton).first);
      await tester.pumpAndSettle();

      // Verify snackbar appears
      expect(find.text('Navigating to Daily Outfit Detail...'), findsOneWidget);
    });

    testWidgets('Change Style button in Today\'s Look shows snackbar on tap', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Scroll to Today's Look section first
      await tester.scrollUntilVisible(find.text("TODAY'S LOOK"), 500.0);
      await tester.pumpAndSettle();

      // Find the Change Style button in Today's Look (it's the second HomeActionButton)
      final changeStyleButton = find.byType(HomeActionButton).at(1);
      expect(changeStyleButton, findsOneWidget);

      // Scroll to the button and tap
      await tester.scrollUntilVisible(changeStyleButton, 500.0);
      await tester.pumpAndSettle();
      await tester.tap(changeStyleButton);
      await tester.pumpAndSettle();

      expect(find.text('Opening Style Adjustment...'), findsOneWidget);
    });

    testWidgets('Quick action cards show snackbar on tap', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.scrollUntilVisible(
        find.byType(QuickActionCard).first,
        500.0,
      );

      // Tap the first quick action card
      await tester.tap(find.byType(QuickActionCard).first);
      await tester.pumpAndSettle();

      expect(find.text('Opening Scan My Outfit...'), findsOneWidget);
    });

    testWidgets('View Recommendations button on AI Insight shows snackbar', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      await tester.scrollUntilVisible(
        find.byType(HomeActionButton).last,
        500.0,
      );

      // Tap the last HomeActionButton (View Recommendations in AI Insight)
      await tester.tap(find.byType(HomeActionButton).last);
      await tester.pumpAndSettle();

      expect(find.text('Opening Wardrobe Recommendations...'), findsOneWidget);
    });

    testWidgets('HomeScreen is scrollable with all sections', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      // Verify we can scroll through the entire content
      await tester.drag(
        find.byType(SingleChildScrollView),
        const Offset(0, -1000),
      );
      await tester.pumpAndSettle();

      // All major sections should be rendered
      expect(find.text('Good morning, Alex'), findsOneWidget);
      expect(find.text("TODAY'S LOOK"), findsOneWidget);
      expect(find.text('Style Score'), findsOneWidget);
      expect(find.text('Quick Actions'), findsOneWidget);
      expect(find.text('Style Streak'), findsOneWidget);
      expect(find.text('AI Insight'), findsOneWidget);
    });

    testWidgets('HomeScreen uses correct theme colors', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const FansivibeApp());

      final homeScreen = find.byType(HomeScreen);
      expect(homeScreen, findsOneWidget);

      // Verify the app uses the dark theme
      final materialApp = tester.widget<MaterialApp>(find.byType(MaterialApp));
      expect(materialApp.theme?.brightness, Brightness.dark);
      expect(
        materialApp.theme?.primaryColor,
        const Color(0xFFC5A059),
      ); // Fansivibe gold
    });
  });

  group('Home Feature Widgets Tests', () {
    testWidgets('GreetingHeader renders correctly', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const Scaffold(body: GreetingHeader(data: GreetingData.mock)),
        ),
      );

      expect(find.text('Good morning, Alex'), findsOneWidget);
      expect(find.text('Monday, January 13'), findsOneWidget);
    });

    testWidgets('TodaysLookCard renders all components', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: SingleChildScrollView(
              child: TodaysLookCard(
                data: TodaysLookData.mock,
                onTryThisLook: () {},
                onChangeStyle: () {},
              ),
            ),
          ),
        ),
      );

      expect(find.text('TODAY\'S LOOK'), findsOneWidget);
      expect(find.text('Modern Minimalist'), findsOneWidget);
      expect(find.text('87'), findsWidgets);
      expect(find.text('Try This Look'), findsOneWidget);
      expect(find.text('Change Style'), findsOneWidget);
    });

    testWidgets('StyleScoreCard renders with breakdown', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(body: StyleScoreCard(data: StyleScoreData.mock)),
        ),
      );

      expect(find.text('Style Score'), findsOneWidget);
      expect(find.text('84'), findsWidgets);
      expect(find.text('Fit'), findsOneWidget);
      expect(find.text('Color'), findsOneWidget);
      expect(find.text('Occasion'), findsOneWidget);
      expect(find.text('Creativity'), findsOneWidget);
    });

    testWidgets('StyleStreakCard renders with progress ring', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(body: StyleStreakCard(data: StyleStreakData.mock)),
        ),
      );

      expect(find.text('Style Streak'), findsOneWidget);
      expect(find.text('Current'), findsOneWidget);
      expect(find.text('Longest'), findsOneWidget);
      expect(find.text('Total'), findsOneWidget);
    });

    testWidgets('AIInsightCard renders with action button', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: AIInsightCard(
              data: AIWardrobeInsightData.mock,
              onActionPressed: () {},
            ),
          ),
        ),
      );

      expect(find.text('Wardrobe Gap Detected'), findsOneWidget);
      expect(find.text('AI Insight'), findsOneWidget);
      expect(find.text('View Recommendations'), findsOneWidget);
    });

    testWidgets('QuickActionCard renders and handles tap', (
      WidgetTester tester,
    ) async {
      bool tapped = false;
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: QuickActionCard(
              data: QuickActionData.mockActions.first,
              onTap: () => tapped = true,
            ),
          ),
        ),
      );

      expect(find.text('Scan My Outfit'), findsOneWidget);
      expect(find.text('Get AI analysis of your current look'), findsOneWidget);

      await tester.tap(find.byType(QuickActionCard));
      await tester.pump();

      expect(tapped, true);
    });

    testWidgets('HomeCard renders with proper styling', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(body: HomeCard(child: const Text('Test Content'))),
        ),
      );

      expect(find.text('Test Content'), findsOneWidget);
      expect(find.byType(Container), findsWidgets);
    });

    testWidgets('HomeActionButton renders primary and secondary variants', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: Column(
              children: [
                HomeActionButton(
                  label: 'Primary',
                  icon: Icons.check_rounded,
                  onPressed: () {},
                  isPrimary: true,
                ),
                HomeActionButton(
                  label: 'Secondary',
                  icon: Icons.refresh_rounded,
                  onPressed: () {},
                  isPrimary: false,
                ),
              ],
            ),
          ),
        ),
      );

      expect(find.text('Primary'), findsOneWidget);
      expect(find.text('Secondary'), findsOneWidget);
    });

    testWidgets('OutfitItemChip renders with category icon', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: OutfitItemChip(
              item: const OutfitItemData(
                id: '1',
                name: 'Test Blazer',
                category: 'outerwear',
                color: 'Navy',
              ),
            ),
          ),
        ),
      );

      expect(find.text('Test Blazer'), findsOneWidget);
      expect(find.byIcon(Icons.checkroom_rounded), findsOneWidget);
    });

    testWidgets('StreakDayIndicator shows styled and unstyled days', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: Row(
              children: [
                StreakDayIndicator(
                  day: 'Mon',
                  styled: true,
                  score: 87,
                  isToday: true,
                ),
                StreakDayIndicator(day: 'Tue', styled: false, isToday: false),
              ],
            ),
          ),
        ),
      );

      expect(find.text('Mon'), findsOneWidget);
      expect(find.text('Tue'), findsOneWidget);
      expect(find.text('87'), findsOneWidget);
      expect(find.byIcon(Icons.check_rounded), findsOneWidget);
      expect(find.byIcon(Icons.close_rounded), findsOneWidget);
    });
  });
}
