import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/profile/data/user_profile_models.dart';
import 'package:fansivibe/features/profile/data/user_profile_repository.dart';
import 'package:fansivibe/features/profile/presentation/preferences_screen.dart';
import 'package:fansivibe/features/profile/presentation/settings_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

class FakePreferencesProfileRepo implements UserProfileRepository {
  FakePreferencesProfileRepo({UserProfile? initialProfile})
      : _profile = initialProfile;

  UserProfile? _profile;
  bool failUpdates = false;
  final List<String> styleTypeUpdates = [];
  final List<Map<String, dynamic>> settingsUpdates = [];
  final List<List<String>> occasionUpdates = [];
  final Map<String, dynamic> _pendingEdits = {};

  @override
  UserProfile? get cachedProfile => _profile;

  @override
  Future<UserProfile?> fetchProfile({bool forceRefresh = false}) async {
    return _profile;
  }

  @override
  void recordPendingEdit({required String field, required dynamic value}) {
    _pendingEdits[field] = value;
  }

  @override
  void clearPendingEdits() {
    _pendingEdits.clear();
  }

  @override
  Map<String, dynamic> get pendingEdits => Map.unmodifiable(_pendingEdits);

  @override
  void clearCache() {
    _profile = null;
    _pendingEdits.clear();
  }

  @override
  Future<UserProfile?> updateStyleType(String styleType) async {
    if (failUpdates) return null;
    styleTypeUpdates.add(styleType);
    final updatedStyle = (_profile?.styleProfile ?? const UserStyleProfile())
        .copyWith(styleType: styleType);
    _profile = (_profile ??
            UserProfile(
              displayName: 'Test User',
              styleProfile: updatedStyle,
              version: 1,
            ))
        .copyWith(styleProfile: updatedStyle);
    return _profile;
  }

  @override
  Future<UserProfile?> updateSettings(Map<String, dynamic> settingsPatch) async {
    if (failUpdates) return null;
    settingsUpdates.add(settingsPatch);
    final merged = Map<String, dynamic>.from(_profile?.settings ?? {})
      ..addAll(settingsPatch);
    _profile = (_profile ??
            UserProfile(
              displayName: 'Test User',
              styleProfile: const UserStyleProfile(),
              settings: merged,
              version: 1,
            ))
        .copyWith(settings: merged);
    return _profile;
  }

  @override
  Future<UserProfile?> updatePreferredOccasions(
    List<String> occasions,
  ) async {
    if (failUpdates) return null;
    occasionUpdates.add(occasions);
    final mergedPrefs =
        Map<String, dynamic>.from(_profile?.preferences ?? {})
          ..['preferredOccasions'] = occasions;
    _profile = (_profile ??
            UserProfile(
              displayName: 'Test User',
              styleProfile: const UserStyleProfile(),
              preferences: mergedPrefs,
              version: 1,
            ))
        .copyWith(preferences: mergedPrefs);
    return _profile;
  }
}

Widget wrapWithTheme(Widget child) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: child,
  );
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
    AuthSession.resetForTest();
    await AuthSession.saveSession('tok-test');
    LearningService.instance.resetForTest();
  });

  group('Phase 2 & 6: Style Preferences Persistence Flutter Tests', () {
    testWidgets('1. Style archetype hydrates from backend profile', (tester) async {
      final repo = FakePreferencesProfileRepo(
        initialProfile: UserProfile(
          displayName: 'Test User',
          styleProfile: const UserStyleProfile(styleType: 'Classic'),
          version: 1,
        ),
      );

      await tester.pumpWidget(
        wrapWithTheme(PreferencesScreen(userProfileRepository: repo)),
      );
      await tester.pumpAndSettle();

      expect(find.text('Style Archetype'), findsOneWidget);
      expect(find.text('Occasion Focus'), findsOneWidget);
      expect(find.text('Classic'), findsOneWidget);
      expect(find.text('Minimalist'), findsOneWidget);
      expect(find.text('Street Style'), findsOneWidget);
    });

    testWidgets('2. Selecting style archetype persists to backend', (tester) async {
      final repo = FakePreferencesProfileRepo(
        initialProfile: UserProfile(
          displayName: 'Test User',
          styleProfile: const UserStyleProfile(styleType: 'Minimalist'),
          version: 1,
        ),
      );

      await tester.pumpWidget(
        wrapWithTheme(PreferencesScreen(userProfileRepository: repo)),
      );
      await tester.pumpAndSettle();

      final chip = find.text('Street Style');
      await tester.ensureVisible(chip);
      await tester.tap(chip);
      await tester.pumpAndSettle();

      expect(repo.styleTypeUpdates, contains('Street Style'));
      expect(find.text('Synced: Street Style'), findsOneWidget);
      expect(LocalStorage.vibe, 'Street Style');
      expect(LearningService.instance.styleType, 'Street Style');
    });

    testWidgets('3. Failed style archetype update rolls back honestly', (tester) async {
      final repo = FakePreferencesProfileRepo(
        initialProfile: UserProfile(
          displayName: 'Test User',
          styleProfile: const UserStyleProfile(styleType: 'Classic'),
          version: 1,
        ),
      )..failUpdates = true;

      await tester.pumpWidget(
        wrapWithTheme(PreferencesScreen(userProfileRepository: repo)),
      );
      await tester.pumpAndSettle();

      final chip = find.text('Bold');
      await tester.ensureVisible(chip);
      await tester.tap(chip);
      await tester.pumpAndSettle();

      expect(find.textContaining('Sync failed'), findsOneWidget);
      expect(repo.styleTypeUpdates, isEmpty);
      // Reverted to Classic
      expect(LocalStorage.vibe, isNot('Bold'));
    });

    testWidgets('4. Guest mode style archetype remains device-local without API call', (tester) async {
      await AuthSession.clearSession();
      LocalStorage.authToken = null;
      LocalStorage.savedLocally = true;
      expect(isGuestUser, isTrue);

      final repo = FakePreferencesProfileRepo();

      await tester.pumpWidget(
        wrapWithTheme(PreferencesScreen(userProfileRepository: repo)),
      );
      await tester.pumpAndSettle();

      final chip = find.text('Bohemian');
      await tester.ensureVisible(chip);
      await tester.tap(chip);
      await tester.pumpAndSettle();

      expect(find.text('Saved: Bohemian (this device only)'), findsOneWidget);
      expect(repo.styleTypeUpdates, isEmpty);
      expect(LocalStorage.vibe, 'Bohemian');
      expect(LearningService.instance.styleType, 'Bohemian');
    });
  });

  group('Phase 3 & 6: Application Settings Persistence Flutter Tests', () {
    testWidgets('5. Settings load switch values from profile', (tester) async {
      final repo = FakePreferencesProfileRepo(
        initialProfile: UserProfile(
          displayName: 'Test User',
          styleProfile: const UserStyleProfile(),
          settings: {
            'notifications': false,
            'soundEffects': true,
            'hapticFeedback': false,
            'dataSaver': true,
          },
          version: 1,
        ),
      );

      await tester.pumpWidget(
        wrapWithTheme(SettingsScreen(userProfileRepository: repo)),
      );
      await tester.pumpAndSettle();

      final switches = tester.widgetList<Switch>(find.byType(Switch)).toList();
      expect(switches.length, 4);
      // notifications
      expect(switches[0].value, isFalse);
      // soundEffects
      expect(switches[1].value, isTrue);
      // hapticFeedback
      expect(switches[2].value, isFalse);
      // dataSaver
      expect(switches[3].value, isTrue);
    });

    testWidgets('6. Toggling switch persists partial update and preserves other settings', (tester) async {
      final repo = FakePreferencesProfileRepo(
        initialProfile: UserProfile(
          displayName: 'Test User',
          styleProfile: const UserStyleProfile(),
          settings: {
            'notifications': true,
            'soundEffects': false,
            'hapticFeedback': true,
            'dataSaver': false,
          },
          version: 1,
        ),
      );

      await tester.pumpWidget(
        wrapWithTheme(SettingsScreen(userProfileRepository: repo)),
      );
      await tester.pumpAndSettle();

      final switches = find.byType(Switch);
      // Toggle soundEffects (index 1, currently false -> true)
      await tester.tap(switches.at(1));
      await tester.pumpAndSettle();

      expect(repo.settingsUpdates, hasLength(1));
      expect(repo.settingsUpdates.single, {'soundEffects': true});
      // Ensure other settings preserved in repo profile
      expect(repo.cachedProfile?.settings['notifications'], isTrue);
      expect(repo.cachedProfile?.settings['soundEffects'], isTrue);
      expect(repo.cachedProfile?.settings['hapticFeedback'], isTrue);
      expect(repo.cachedProfile?.settings['dataSaver'], isFalse);
    });

    testWidgets('7. Failed settings update rolls back switch and shows honest error', (tester) async {
      final repo = FakePreferencesProfileRepo(
        initialProfile: UserProfile(
          displayName: 'Test User',
          styleProfile: const UserStyleProfile(),
          settings: {
            'notifications': true,
            'soundEffects': false,
            'hapticFeedback': true,
            'dataSaver': false,
          },
          version: 1,
        ),
      )..failUpdates = true;

      await tester.pumpWidget(
        wrapWithTheme(SettingsScreen(userProfileRepository: repo)),
      );
      await tester.pumpAndSettle();

      final switches = find.byType(Switch);
      // Toggle notifications (index 0, currently true -> false)
      await tester.tap(switches.at(0));
      await tester.pumpAndSettle();

      // Error SnackBar displayed
      expect(find.text('Failed to update setting. Please try again.'), findsOneWidget);

      // Rolled back to true
      final rolledBackSwitch = tester.widget<Switch>(switches.at(0));
      expect(rolledBackSwitch.value, isTrue);
    });

    testWidgets('8. Guest toggling switch persists to LocalStorage only', (tester) async {
      await AuthSession.clearSession();
      LocalStorage.authToken = null;
      LocalStorage.savedLocally = true;
      expect(isGuestUser, isTrue);

      final repo = FakePreferencesProfileRepo();

      await tester.pumpWidget(
        wrapWithTheme(SettingsScreen(userProfileRepository: repo)),
      );
      await tester.pumpAndSettle();

      final switches = find.byType(Switch);
      // Toggle notifications (index 0, default true -> false)
      await tester.tap(switches.at(0));
      await tester.pumpAndSettle();

      expect(repo.settingsUpdates, isEmpty);
      expect(LocalStorage.settings['notifications'], isFalse);
    });

    testWidgets('9. Server values override stale cached settings on hydration', (tester) async {
      // Set local stale value
      LocalStorage.settings = {'notifications': true};

      final repo = FakePreferencesProfileRepo(
        initialProfile: UserProfile(
          displayName: 'Test User',
          styleProfile: const UserStyleProfile(),
          settings: {'notifications': false},
          version: 2,
        ),
      );

      await tester.pumpWidget(
        wrapWithTheme(SettingsScreen(userProfileRepository: repo)),
      );
      await tester.pumpAndSettle();

      final switches = tester.widgetList<Switch>(find.byType(Switch)).toList();
      // Server false overrides stale local true
      expect(switches[0].value, isFalse);
    });
  });
}
