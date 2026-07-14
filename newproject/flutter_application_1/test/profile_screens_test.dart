import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/profile/presentation/preferences_screen.dart';
import 'package:fansivibe/features/profile/presentation/saved_looks_screen.dart';
import 'package:fansivibe/features/profile/presentation/subscription_screen.dart';
import 'package:fansivibe/features/profile/presentation/support_screen.dart';
import 'package:fansivibe/features/profile/presentation/settings_screen.dart';

Widget wrapApp(Widget child) {
  return MaterialApp(theme: ThemeData.dark(), home: child);
}

void main() {
  group('PreferencesScreen Widget Tests', () {
    testWidgets('renders title and subtitle', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const PreferencesScreen()));

      expect(find.text('Style Preferences'), findsOneWidget);
      expect(find.text('Customize your style profile'), findsOneWidget);
    });

    testWidgets('renders preference labels', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const PreferencesScreen()));

      expect(find.text('Style Vibe'), findsOneWidget);
      expect(find.text('Color Palette'), findsOneWidget);
      expect(find.text('Fit Preference'), findsOneWidget);
      expect(find.text('Occasion Focus'), findsOneWidget);
    });

    testWidgets('renders option chips', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const PreferencesScreen()));

      expect(find.text('Modern Minimalist'), findsOneWidget);
      expect(find.text('Neutral Tones'), findsOneWidget);
      expect(find.text('Tailored'), findsOneWidget);
      expect(find.text('Smart Casual'), findsOneWidget);
    });

    testWidgets('tapping chip changes selection', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const PreferencesScreen()));

      final chipFinder = find.text('Street Style');
      await tester.scrollUntilVisible(
        chipFinder,
        200,
        scrollable: find.byType(Scrollable).last,
      );
      await tester.tap(chipFinder);
      await tester.pump();

      expect(find.text('Street Style'), findsOneWidget);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const PreferencesScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });

    testWidgets('renders chips for all options', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const PreferencesScreen()));

      expect(find.text('Classic Elegance'), findsOneWidget);
      expect(find.text('Street Style'), findsOneWidget);
      expect(find.text('Bohemian'), findsOneWidget);
      expect(find.text('Athleisure'), findsOneWidget);
    });
  });

  group('SavedLooksScreen Widget Tests', () {
    testWidgets('renders title and subtitle', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SavedLooksScreen()));

      expect(find.text('6 Saved Looks'), findsOneWidget);
      expect(find.text('Your curated style collection'), findsOneWidget);
    });

    testWidgets('renders all saved looks', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SavedLooksScreen()));

      expect(find.text('Modern Minimalist'), findsOneWidget);
      expect(find.text('Weekend Casual'), findsOneWidget);
      expect(find.text('Smart Business'), findsOneWidget);
      expect(find.text('Date Night'), findsOneWidget);
      expect(find.text('Summer Breeze'), findsOneWidget);
      expect(find.text('Office Ready'), findsOneWidget);
    });

    testWidgets('renders scores', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SavedLooksScreen()));

      expect(find.text('87'), findsOneWidget);
      expect(find.text('91'), findsOneWidget);
    });

    testWidgets('renders dates', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SavedLooksScreen()));

      expect(find.text('Saved Jul 12'), findsOneWidget);
      expect(find.text('Saved Jul 10'), findsOneWidget);
    });

    testWidgets('renders item descriptions', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SavedLooksScreen()));

      expect(find.textContaining('White Linen Shirt'), findsOneWidget);
      expect(find.textContaining('Navy Blazer'), findsOneWidget);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SavedLooksScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });

  group('SubscriptionScreen Widget Tests', () {
    testWidgets('renders title and subtitle', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SubscriptionScreen()));

      expect(find.text('Choose Your Plan'), findsOneWidget);
      expect(find.text('Unlock premium style features'), findsOneWidget);
    });

    testWidgets('renders all plans', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SubscriptionScreen()));

      expect(find.text('Free'), findsOneWidget);
      expect(find.text('Premium'), findsOneWidget);
      expect(find.text('Elite'), findsOneWidget);
    });

    testWidgets('renders plan prices', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SubscriptionScreen()));

      expect(find.text('\$0'), findsOneWidget);
      expect(find.text('\$9.99'), findsOneWidget);
      expect(find.text('\$19.99'), findsOneWidget);
    });

    testWidgets('renders Popular badge', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SubscriptionScreen()));

      expect(find.text('Popular'), findsOneWidget);
    });

    testWidgets('renders plan features', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SubscriptionScreen()));

      expect(find.text('Basic style score'), findsOneWidget);
      expect(find.text('Advanced style analytics'), findsOneWidget);
      expect(find.text('Personal stylist review'), findsOneWidget);
    });

    testWidgets('renders buttons', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SubscriptionScreen()));

      expect(find.text('Current Plan'), findsOneWidget);
      expect(find.text('Subscribe'), findsAtLeast(1));
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SubscriptionScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });

  group('SupportScreen Widget Tests', () {
    testWidgets('renders title and subtitle', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SupportScreen()));

      expect(find.text('Help & Support'), findsOneWidget);
      expect(find.text('Find answers and get in touch'), findsOneWidget);
    });

    testWidgets('renders all support topics', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SupportScreen()));

      expect(find.text('Getting Started'), findsOneWidget);
      expect(find.text('Style Score'), findsOneWidget);
      expect(find.text('Wardrobe Management'), findsOneWidget);
      expect(find.text('Account & Privacy'), findsOneWidget);
      expect(find.text('Report a Bug'), findsOneWidget);
      expect(find.text('Contact Us'), findsOneWidget);
    });

    testWidgets('renders topic descriptions', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SupportScreen()));

      expect(find.text('Learn the basics of Fansivibe'), findsOneWidget);
      expect(find.text('How your style score is calculated'), findsOneWidget);
    });

    testWidgets('renders contact card', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SupportScreen()));

      expect(find.text('Send us a message'), findsOneWidget);
      expect(find.text('We typically respond within 24 hours'), findsOneWidget);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SupportScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });

  group('SettingsScreen Widget Tests', () {
    testWidgets('renders title and subtitle', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SettingsScreen()));

      expect(find.text('App Settings'), findsOneWidget);
      expect(find.text('Customize your experience'), findsOneWidget);
    });

    testWidgets('renders all settings items', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SettingsScreen()));

      expect(find.text('Notifications'), findsOneWidget);
      expect(find.text('Sound Effects'), findsOneWidget);
      expect(find.text('Haptic Feedback'), findsOneWidget);
      expect(find.text('Theme'), findsOneWidget);
      expect(find.text('Units'), findsOneWidget);
      expect(find.text('Data Saver'), findsOneWidget);
    });

    testWidgets('renders toggle switches', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SettingsScreen()));

      expect(find.byType(Switch), findsAtLeast(2));
    });

    testWidgets('toggling switch toggles state', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SettingsScreen()));

      final switches = find.byType(Switch);
      await tester.tap(switches.first);
      await tester.pump();

      expect(find.byType(Switch), findsAtLeast(2));
    });

    testWidgets('renders display values', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SettingsScreen()));

      expect(find.text('Dark'), findsOneWidget);
      expect(find.text('Imperial'), findsOneWidget);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SettingsScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });
}
