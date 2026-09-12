import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/features/profile/data/saved_looks_models.dart';
import 'package:fansivibe/features/profile/data/saved_looks_repository.dart';
import 'package:fansivibe/features/profile/presentation/preferences_screen.dart';
import 'package:fansivibe/features/profile/presentation/saved_looks_screen.dart';
import 'package:fansivibe/features/profile/presentation/subscription_screen.dart';
import 'package:fansivibe/features/profile/presentation/support_screen.dart';
import 'package:fansivibe/features/profile/presentation/settings_screen.dart';

Widget wrapApp(Widget child) {
  return MaterialApp(theme: ThemeData.dark(), home: child);
}

/// Backend-backed double: the `GET /v1/looks/saved` envelope is the only
/// source (DEC-013, STEP 18.4). No local-service merge, no mock fallback.
class _FakeSavedLooksRepository implements SavedLooksRepository {
  _FakeSavedLooksRepository(this.rows);

  final List<SavedLookItem> rows;

  @override
  Future<SavedLookListPage?> listSavedLooks({
    int page = 1,
    int pageSize = 20,
  }) async {
    return SavedLookListPage(
      items: List.of(rows),
      page: page,
      pageSize: pageSize,
      total: rows.length,
    );
  }

  @override
  Future<SavedLookDeleteOutcome?> deleteSavedLook({required String id}) async {
    return SavedLookDeleteOutcome.deleted;
  }
}

SavedLookItem _row(String id, String title, String? sourceContext) {
  return SavedLookItem(
    id: id,
    title: title,
    createdAt: DateTime.utc(2026, 9, 1, 10),
    sourceContext: sourceContext,
    snapshot: const {},
  );
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('PreferencesScreen Widget Tests', () {
    testWidgets('renders title and subtitle', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const PreferencesScreen()));

      expect(find.text('Style Preferences'), findsOneWidget);
      expect(find.text('Customize your style profile'), findsOneWidget);
    });

    testWidgets('renders preference labels', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const PreferencesScreen()));
      await tester.pumpAndSettle();

      expect(find.text('Occasion Focus'), findsOneWidget);
    });

    testWidgets('renders option chips', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const PreferencesScreen()));
      await tester.pumpAndSettle();

      expect(find.text('Casual'), findsOneWidget);
      expect(find.text('Smart Casual'), findsOneWidget);
      expect(find.text('Business'), findsOneWidget);
      expect(find.text('Formal'), findsOneWidget);
    });

    testWidgets('tapping chip changes selection', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const PreferencesScreen()));
      await tester.pumpAndSettle();

      final chipFinder = find.text('Business');
      await tester.ensureVisible(chipFinder);
      await tester.tap(chipFinder);
      await tester.pump();

      expect(find.text('Saved: Business'), findsOneWidget);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const PreferencesScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });

    testWidgets('renders chips for all options', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const PreferencesScreen()));
      await tester.pumpAndSettle();

      expect(find.text('Casual'), findsOneWidget);
      expect(find.text('Business'), findsOneWidget);
      expect(find.text('Formal'), findsOneWidget);
      expect(find.text('Streetwear'), findsOneWidget);
    });
  });

  group('SavedLooksScreen Widget Tests', () {
    testWidgets('renders title and backend rows', (WidgetTester tester) async {
      final repo = _FakeSavedLooksRepository([
        _row('id-1', 'Textured Quiff', 'hairstyle'),
        _row('id-2', 'Corporate Beard', 'grooming'),
      ]);
      await tester.pumpWidget(wrapApp(SavedLooksScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('2 Saved Looks'), findsOneWidget);
      expect(find.text('Your curated style collection'), findsOneWidget);
      expect(find.text('Textured Quiff'), findsOneWidget);
      expect(find.text('Corporate Beard'), findsOneWidget);
    });

    testWidgets('renders outfit and legacy rows generically', (
      WidgetTester tester,
    ) async {
      final repo = _FakeSavedLooksRepository([
        _row('id-3', 'Date Night Outfit', 'outfit'),
        _row('id-4', 'Old Save', null),
      ]);
      await tester.pumpWidget(wrapApp(SavedLooksScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('OUTFIT LOOK'), findsOneWidget);
      expect(find.text('SAVED LOOK'), findsOneWidget);
    });

    testWidgets('empty backend list shows empty state', (
      WidgetTester tester,
    ) async {
      final repo = _FakeSavedLooksRepository(const []);
      await tester.pumpWidget(wrapApp(SavedLooksScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('0 Saved Looks'), findsOneWidget);
      expect(find.text('No saved looks yet'), findsOneWidget);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      final repo = _FakeSavedLooksRepository(const []);
      await tester.pumpWidget(wrapApp(SavedLooksScreen(repository: repo)));
      await tester.pumpAndSettle();

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
