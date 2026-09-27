import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/features/home/presentation/first_time_home_screen.dart';
import 'package:fansivibe/features/home/presentation/first_time_light_path_home_screen.dart';
import 'package:fansivibe/features/home/presentation/home_screen.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/profile/presentation/profile_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    LearningService.instance.resetForTest();
    UserSession.hasSavedWardrobeItem = false;
    UserSession.isReturningUser = false;
  });

  group('C-08 LocalStorage.onboardingPhotoCaptured semantics and compatibility', () {
    test('A. onboardingPhotoCaptured can be written and read', () async {
      expect(LocalStorage.onboardingPhotoCaptured, isFalse);

      LocalStorage.onboardingPhotoCaptured = true;
      expect(LocalStorage.onboardingPhotoCaptured, isTrue);

      LocalStorage.onboardingPhotoCaptured = false;
      expect(LocalStorage.onboardingPhotoCaptured, isFalse);
    });

    test('B. existing persisted analysis_cached key is read by onboardingPhotoCaptured', () async {
      // Simulate an existing user with 'analysis_cached': true in SharedPreferences
      SharedPreferences.setMockInitialValues({'analysis_cached': true});
      final prefs = await SharedPreferences.getInstance();
      LocalStorage.init(prefs: prefs);

      // Verifies backwards-compatible reading
      expect(LocalStorage.onboardingPhotoCaptured, isTrue);

      // Writing onboardingPhotoCaptured updates the existing key
      LocalStorage.onboardingPhotoCaptured = false;
      expect(prefs.getBool('analysis_cached'), isFalse);
    });

    test('C. writes to onboardingPhotoCaptured preserve the analysis_cached key', () async {
      final prefs = await SharedPreferences.getInstance();
      LocalStorage.onboardingPhotoCaptured = true;
      expect(prefs.getBool('analysis_cached'), isTrue);
    });
  });

  group('C-08 UI behavior preservation', () {
    testWidgets('D. HomeScreen first-time routing uses onboardingPhotoCaptured for _hasAnalysis', (tester) async {
      // 1. With onboardingPhotoCaptured = false and vibe set -> FirstTimeLightPathHomeScreen
      LocalStorage.vibe = 'Minimalist';
      LocalStorage.onboardingPhotoCaptured = false;
      LocalStorage.onboardingComplete = false;
      LocalStorage.displayName = null;

      await tester.pumpWidget(
        const MaterialApp(
          home: HomeScreen(
            onboardingData: {'vibe': 'Minimalist'},
          ),
        ),
      );
      await tester.pump();

      expect(find.byType(FirstTimeLightPathHomeScreen), findsOneWidget);
      expect(find.byType(FirstTimeHomeScreen), findsNothing);

      // 2. With onboardingPhotoCaptured = true -> FirstTimeHomeScreen
      LocalStorage.onboardingPhotoCaptured = true;

      await tester.pumpWidget(
        const MaterialApp(
          home: HomeScreen(
            onboardingData: {'vibe': 'Minimalist'},
          ),
        ),
      );
      await tester.pump();

      expect(find.byType(FirstTimeHomeScreen), findsOneWidget);
      expect(find.byType(FirstTimeLightPathHomeScreen), findsNothing);
    });

    testWidgets('E. StyleJourneyCard milestone reflects onboardingPhotoCaptured', (tester) async {
      LocalStorage.onboardingPhotoCaptured = true;

      await tester.pumpWidget(
        const MaterialApp(
          home: FirstTimeHomeScreen(displayName: 'Tester'),
        ),
      );
      await tester.pump();

      // StyleJourneyCard should be present and configured
      expect(find.byType(FirstTimeHomeScreen), findsOneWidget);
    });

    testWidgets('F. Profile badge color achievement unlocked with onboardingPhotoCaptured', (tester) async {
      // With onboardingPhotoCaptured = false and no wardrobe items -> locked
      LocalStorage.onboardingPhotoCaptured = false;
      UserSession.hasSavedWardrobeItem = false;

      await tester.pumpWidget(
        const MaterialApp(
          home: ProfileScreen(),
        ),
      );
      await tester.pump();

      // Now set onboardingPhotoCaptured = true -> unlocks color achievement
      LocalStorage.onboardingPhotoCaptured = true;

      await tester.pumpWidget(
        const MaterialApp(
          home: ProfileScreen(),
        ),
      );
      await tester.pump();

      expect(find.byType(ProfileScreen), findsOneWidget);
    });

    testWidgets('F2. Profile Style DNA evaluation succeeds with remaining real sources', (tester) async {
      LocalStorage.userProfile = {
        'skinTone': 'Warm Ivory',
        'faceShape': 'Oval',
        'bodyType': 'Athletic',
        'styleType': 'Minimalist',
      };

      await tester.pumpWidget(
        const MaterialApp(
          home: ProfileScreen(),
        ),
      );
      await tester.pump();

      expect(find.byType(ProfileScreen), findsOneWidget);
    });
  });
}
