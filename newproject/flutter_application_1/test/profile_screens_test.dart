import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/features/assistant/data/assistant_client.dart';
import 'package:fansivibe/features/profile/data/saved_looks_models.dart';
import 'package:fansivibe/features/profile/data/saved_looks_repository.dart';
import 'package:fansivibe/features/profile/data/user_profile_client.dart';
import 'package:fansivibe/features/profile/data/user_profile_repository.dart';
import 'package:fansivibe/features/profile/presentation/preferences_screen.dart';
import 'package:fansivibe/features/profile/presentation/saved_looks_screen.dart';
import 'package:fansivibe/features/profile/presentation/subscription_screen.dart';
import 'package:fansivibe/features/profile/presentation/support_screen.dart';
import 'package:fansivibe/features/profile/presentation/settings_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

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

  @override
  Future<SavedLookItem?> getSavedLook({
    required String id,
    bool includeItems = true,
  }) async {
    return rows.where((r) => r.id == id).firstOrNull;
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
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    AuthSession.resetForTest();
    // Auth boundary: the SavedLooks tests exercise the authenticated
    // collection, so they sign in.
    await AuthSession.saveSession('profile-screens-test-token');
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    LocalStorage.resetForTest();
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

    testWidgets('tapping chip syncs the mapped code', (
      WidgetTester tester,
    ) async {
      final client = AssistantClient(
        client: MockClient((request) async {
          if (request.method == 'GET') {
            return http.Response(
              jsonEncode({
                'preferences': {'preferredOccasions': <String>[]},
              }),
              200,
            );
          }
          return http.Response('{"displayName":"Dev User"}', 200);
        }),
      );
      await tester.pumpWidget(
        wrapApp(PreferencesScreen(preferencesClient: client)),
      );
      await tester.pumpAndSettle();

      final chipFinder = find.text('Business');
      await tester.ensureVisible(chipFinder);
      await tester.tap(chipFinder);
      await tester.pumpAndSettle();

      // Mapped label syncs truthfully end-to-end (P1-2).
      expect(find.text('Synced: Business'), findsOneWidget);
      client.dispose();
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
    testWidgets('shows honest unavailable state', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SubscriptionScreen()));

      expect(find.text('Subscriptions'), findsOneWidget);
      expect(find.text('Premium plans are not available'), findsOneWidget);
      expect(find.text('No plans connected'), findsOneWidget);
      expect(
        find.text(
          'This build does not include billing or subscription plans. No purchases can be made from this screen.',
        ),
        findsOneWidget,
      );
    });

    testWidgets('does not show fake plans or subscribe actions', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(wrapApp(const SubscriptionScreen()));

      expect(find.text('Premium'), findsNothing);
      expect(find.text('Elite'), findsNothing);
      expect(find.text('Subscribe'), findsNothing);
      expect(find.byType(ElevatedButton), findsNothing);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SubscriptionScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });

  group('SupportScreen Widget Tests', () {
    testWidgets('renders title and honest subtitle', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(wrapApp(const SupportScreen()));

      expect(find.text('Help & Support'), findsOneWidget);
      expect(find.text('Help topics and support status'), findsOneWidget);
    });

    testWidgets('renders help topics without dead navigation', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(wrapApp(const SupportScreen()));

      expect(find.text('Getting Started'), findsOneWidget);
      expect(find.text('Style Score'), findsOneWidget);
      expect(find.text('Wardrobe Management'), findsOneWidget);
      expect(find.text('Account & Privacy'), findsOneWidget);
      expect(find.text('Report a Bug'), findsOneWidget);
      expect(find.text('Contact Us'), findsNothing);
      expect(find.byIcon(Icons.chevron_right_rounded), findsNothing);
    });

    testWidgets('shows direct support as unavailable', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(wrapApp(const SupportScreen()));

      expect(find.text('Direct support is not configured'), findsOneWidget);
      expect(
        find.text('No support channel is connected in this build.'),
        findsOneWidget,
      );
      expect(find.text('We typically respond within 24 hours'), findsNothing);
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

    testWidgets('shows account actions for authenticated users', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(wrapApp(const SettingsScreen()));

      expect(find.text('Account'), findsOneWidget);
      expect(find.text('Sign Out'), findsOneWidget);
      expect(find.text('Delete Account'), findsOneWidget);
    });

    testWidgets('delete account requires typed confirmation', (
      WidgetTester tester,
    ) async {
      final requests = <http.Request>[];
      final client = MockClient((request) async {
        requests.add(request);
        if (request.method == 'DELETE') {
          return http.Response('', 204);
        }
        return http.Response('{}', 404);
      });
      final repo = UserProfileRepositoryImpl(
        client: UserProfileClient(client: client),
      );
      await tester.pumpWidget(
        wrapApp(SettingsScreen(userProfileRepository: repo)),
      );

      await tester.ensureVisible(find.text('Delete Account'));
      await tester.tap(find.text('Delete Account'));
      await tester.pumpAndSettle();

      expect(find.text('Delete account?'), findsOneWidget);
      expect(find.byType(TextField), findsOneWidget);
      TextButton deleteButton() => tester.widget<TextButton>(
        find.ancestor(
          of: find.text('Delete account'),
          matching: find.byType(TextButton),
        ),
      );
      expect(deleteButton().onPressed, isNull);

      await tester.enterText(find.byType(TextField), 'delete');
      await tester.pump();
      expect(deleteButton().onPressed, isNull);

      await tester.enterText(find.byType(TextField), 'DELETE');
      await tester.pump();
      expect(deleteButton().onPressed, isNotNull);

      await tester.tap(find.text('Delete account'));
      await tester.pumpAndSettle();

      expect(requests.where((request) => request.method == 'DELETE').length, 1);
      expect(
        requests.where((request) => request.method == 'DELETE').single.url.path,
        '/v1/users/me',
      );
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const SettingsScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });
}
