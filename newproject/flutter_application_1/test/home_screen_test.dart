import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/app.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/features/home/data/home_mock_data.dart';
import 'package:fansivibe/features/home/presentation/home_screen.dart';
import 'package:fansivibe/features/home/presentation/widgets/home_widgets.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';

/// Creates a [FansivibeApp] with an isolated router to prevent state
/// leaking across navigation tests.
Widget _freshApp() {
  return FansivibeApp(
    router: GoRouter(initialLocation: '/home', routes: appRoutes),
  );
}

void main() {
  group('HomeScreen Widget Tests', () {
    testWidgets('renders greeting header with personalized greeting', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      // Verify greeting is displayed
      expect(find.text('Good morning, Alex'), findsOneWidget);
    });

    testWidgets('renders Today\'s Look card with all components', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      // Verify Today's Look card elements
      expect(find.text('TODAY\'S LOOK'), findsOneWidget);
      expect(find.text('Your Look'), findsOneWidget);
      expect(find.text('Everyday'), findsOneWidget);
      expect(find.text('Style Score'), findsOneWidget);
      expect(find.text('87%'), findsWidgets); // Style score badge

      // Verify description
      expect(
        find.textContaining(
          'Great start with Unstructured Blazer and Merino Crew Neck',
        ),
        findsOneWidget,
      );

      // Verify outfit items (built from the default wardrobe)
      expect(find.text('Unstructured Blazer'), findsOneWidget);
      expect(find.text('Merino Crew Neck'), findsOneWidget);

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
      await tester.pumpWidget(_freshApp());

      // Scroll to find Style Score section
      await tester.scrollUntilVisible(find.text('Style Score'), 500.0);

      expect(find.text('Style Score'), findsOneWidget);
      expect(find.text('Your weekly style performance'), findsOneWidget);
      expect(find.text('84'), findsWidgets); // Current score
      expect(find.text('+3 pts'), findsOneWidget);
      expect(find.text('this week'), findsOneWidget);

      // Verify breakdown categories
      expect(find.text('Fit'), findsOneWidget);
      expect(find.text('Color'), findsOneWidget);
      expect(find.text('Occasion'), findsOneWidget);
      expect(find.text('Creativity'), findsOneWidget);
    });

    testWidgets('renders Quick Actions section', (WidgetTester tester) async {
      await tester.pumpWidget(_freshApp());

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
      await tester.pumpWidget(_freshApp());

      await tester.scrollUntilVisible(find.text('Style Streak'), 500.0);

      expect(find.text('Style Streak'), findsOneWidget);
      expect(find.text('Keep your daily style momentum'), findsOneWidget);
      expect(find.text('Current'), findsOneWidget);
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
      await tester.pumpWidget(_freshApp());

      await tester.scrollUntilVisible(find.text('AI Insight'), 500.0);

      expect(find.text('AI Insight'), findsOneWidget);
      expect(find.text('Wardrobe Insight'), findsOneWidget);
      expect(
        find.textContaining('You have 4 outerwear pieces and 8 tops'),
        findsOneWidget,
      );
      expect(find.text('View Recommendations'), findsOneWidget);
    });

    testWidgets('HomeScreen is scrollable with all sections', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      await tester.drag(
        find.byType(SingleChildScrollView),
        const Offset(0, -1000),
      );
      await tester.pumpAndSettle();

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
      await tester.pumpWidget(_freshApp());

      final homeScreen = find.byType(HomeScreen);
      expect(homeScreen, findsOneWidget);

      final materialApp = tester.widget<MaterialApp>(find.byType(MaterialApp));
      expect(materialApp.theme?.brightness, Brightness.dark);
      expect(materialApp.theme?.primaryColor, const Color(0xFFE3C373));
    });

    testWidgets('Try This Look navigates to Daily Outfit screen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      await tester.scrollUntilVisible(find.text('Try This Look'), 500.0);
      await tester.pumpAndSettle();
      await tester.tap(find.byType(FansiButton).first);
      await tester.pumpAndSettle();

      expect(find.text("TODAY'S LOOK"), findsOneWidget);
    });

    testWidgets(
      'Change Style button in Today\'s Look navigates to Build Outfit',
      (WidgetTester tester) async {
        await tester.pumpWidget(_freshApp());

        await tester.pumpAndSettle();

        // Tap the on-screen "Change Style" inside the scroll view.
        final changeStyleFinder = find.text('Change Style').first;
        expect(changeStyleFinder, findsOneWidget);

        await tester.scrollUntilVisible(changeStyleFinder, 1000.0);
        await tester.pumpAndSettle();

        await tester.tap(changeStyleFinder);
        await tester.pumpAndSettle();

        expect(find.text('Build Outfit'), findsNWidgets(2));
      },
    );

    testWidgets('Quick action cards navigate to respective screens', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      final scrollable = find.byType(SingleChildScrollView);
      await tester.dragUntilVisible(
        find.text('Scan My Outfit'),
        scrollable,
        const Offset(0, -300),
        maxIteration: 30,
      );

      final scanTitle = find.text('Scan My Outfit');
      expect(scanTitle, findsOneWidget);

      await tester.tap(scanTitle);
      // Use pump() instead of pumpAndSettle() because the scan screen has
      // an indeterminate CircularProgressIndicator that never settles.
      await tester.pump();
      await tester.pump();

      expect(find.text('View Analysis'), findsOneWidget);
    });

    testWidgets('View Recommendations button on AI Insight shows snackbar', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_freshApp());

      final scrollable = find.byType(SingleChildScrollView);
      await tester.dragUntilVisible(
        find.text('View Recommendations'),
        scrollable,
        const Offset(0, -300),
        maxIteration: 30,
      );

      final viewRecButton = find.text('View Recommendations');
      expect(viewRecButton, findsOneWidget);

      await tester.tap(viewRecButton);
      await tester.pump();
      await tester.pump();

      expect(find.text('Opening Wardrobe Recommendations...'), findsOneWidget);
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
      expect(find.text('87%'), findsWidgets);
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
      expect(find.text('Best'), findsOneWidget);
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
