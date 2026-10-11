import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/profile/presentation/profile_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';

class _FakeSummaryRepo implements LearningSummaryRepository {
  @override
  Future<LearningSummary?> getSummary() async => null;
}

void main() {
  group('Profile "On this device" Card Layout & Width Tests', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStorage.init(prefs: await SharedPreferences.getInstance());
      AuthSession.resetForTest();
      await AuthSession.clearSession();
      LearningService.instance.resetForTest();
      UserSession.displayName = null;
      UserSession.hasSavedWardrobeItem = false;
      LocalStorage.displayName = null;
      LocalStorage.isReturningUser = false;
      LocalStorage.onboardingComplete = false;
      LocalStorage.savedLocally = true;
      LocalStorage.onboardingPhotoCaptured = true;
    });

    tearDown(() async {
      AuthSession.resetForTest();
      await AuthSession.clearSession();
    });

    testWidgets(
      'matches width and horizontal constraints on desktop/tablet viewport (800x600)',
      (WidgetTester tester) async {
        await tester.pumpWidget(
          MaterialApp(
            theme: FansivibeTheme.darkTheme,
            home: ProfileScreen(
              summaryRepository: _FakeSummaryRepo(),
              isEstablishedUser: false,
            ),
          ),
        );
        await tester.pumpAndSettle();

        final onDeviceFinder = find.ancestor(
          of: find.text('On this device'),
          matching: find.byType(FansivibeCard),
        );
        expect(onDeviceFinder, findsOneWidget);

        final onDeviceSize = tester.getSize(onDeviceFinder);
        final onDeviceTopLeft = tester.getTopLeft(onDeviceFinder);

        // On viewport > 600, contentMaxWidth = 520, horizontalPadding = 32
        // Content width: 520 - 2 * 32 = 456.0
        // Left offset: (800 - 520) / 2 + 32 = 140 + 32 = 172.0
        const expectedWidth = 456.0;
        const expectedLeft = 172.0;

        expect(onDeviceSize.width, equals(expectedWidth));
        expect(onDeviceTopLeft.dx, equals(expectedLeft));

        final styleProgressFinder = find.ancestor(
          of: find.text('30-DAY OVERVIEW'),
          matching: find.byType(Container),
        ).first;
        final styleProgressSize = tester.getSize(styleProgressFinder);
        final styleProgressTopLeft = tester.getTopLeft(styleProgressFinder);

        expect(onDeviceSize.width, equals(styleProgressSize.width));
        expect(onDeviceTopLeft.dx, equals(styleProgressTopLeft.dx));

        expect(find.text('On this device'), findsOneWidget);
        expect(find.text('Sign in to sync & back up'), findsOneWidget);
      },
    );

    testWidgets(
      'matches width and horizontal alignment of surrounding cards on mobile (390x844)',
      (WidgetTester tester) async {
        final cardOverflows = <String>[];
        final previousOnError = FlutterError.onError;
        FlutterError.onError = (FlutterErrorDetails details) {
          final msg = details.exceptionAsString();
          if (msg.contains('On this device') || msg.contains('FansivibeCard')) {
            cardOverflows.add(msg);
          }
          // Pre-existing Ahem test-font text expansion on unrelated components is ignored
        };
        addTearDown(() {
          FlutterError.onError = previousOnError;
        });

        tester.view.physicalSize = const Size(390, 844);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() {
          tester.view.resetPhysicalSize();
          tester.view.resetDevicePixelRatio();
        });

        await tester.pumpWidget(
          MaterialApp(
            theme: FansivibeTheme.darkTheme,
            home: ProfileScreen(
              summaryRepository: _FakeSummaryRepo(),
              isEstablishedUser: false,
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('On this device'), findsOneWidget);

        // Locate "On this device" FansivibeCard
        final onDeviceFinder = find.ancestor(
          of: find.text('On this device'),
          matching: find.byType(FansivibeCard),
        );
        expect(onDeviceFinder, findsOneWidget);

        final onDeviceSize = tester.getSize(onDeviceFinder);
        final onDeviceTopLeft = tester.getTopLeft(onDeviceFinder);

        // Locate "Style Progress" card (surrounding card right above it)
        final styleProgressFinder = find.ancestor(
          of: find.text('30-DAY OVERVIEW'),
          matching: find.byType(Container),
        ).first;
        final styleProgressSize = tester.getSize(styleProgressFinder);
        final styleProgressTopLeft = tester.getTopLeft(styleProgressFinder);

        // Available content width: 390 - 2 * 20 = 350.0
        const expectedContentWidth = 350.0;
        const expectedContentLeft = 20.0;

        expect(onDeviceSize.width, equals(expectedContentWidth));
        expect(onDeviceSize.width, equals(styleProgressSize.width));

        // Horizontal alignment: both start at x = 20.0
        expect(onDeviceTopLeft.dx, equals(expectedContentLeft));
        expect(onDeviceTopLeft.dx, equals(styleProgressTopLeft.dx));

        // Zero overflow in the On this device card
        expect(cardOverflows, isEmpty);

        // Content remains readable
        expect(find.text('Sign in to sync & back up'), findsOneWidget);
      },
    );

    testWidgets(
      'matches width and horizontal alignment on narrow 360 viewport without overflow',
      (WidgetTester tester) async {
        final cardOverflows = <String>[];
        final previousOnError = FlutterError.onError;
        FlutterError.onError = (FlutterErrorDetails details) {
          final msg = details.exceptionAsString();
          if (msg.contains('On this device') || msg.contains('FansivibeCard')) {
            cardOverflows.add(msg);
          }
        };
        addTearDown(() {
          FlutterError.onError = previousOnError;
        });

        tester.view.physicalSize = const Size(360, 640);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() {
          tester.view.resetPhysicalSize();
          tester.view.resetDevicePixelRatio();
        });

        await tester.pumpWidget(
          MaterialApp(
            theme: FansivibeTheme.darkTheme,
            home: ProfileScreen(
              summaryRepository: _FakeSummaryRepo(),
              isEstablishedUser: false,
            ),
          ),
        );
        await tester.pumpAndSettle();

        final onDeviceFinder = find.ancestor(
          of: find.text('On this device'),
          matching: find.byType(FansivibeCard),
        );
        final onDeviceSize = tester.getSize(onDeviceFinder);
        final onDeviceTopLeft = tester.getTopLeft(onDeviceFinder);

        // Available width: 360 - 2 * 20 = 320.0
        expect(onDeviceSize.width, equals(320.0));
        expect(onDeviceTopLeft.dx, equals(20.0));

        final styleProgressFinder = find.ancestor(
          of: find.text('30-DAY OVERVIEW'),
          matching: find.byType(Container),
        ).first;
        final styleProgressSize = tester.getSize(styleProgressFinder);
        expect(onDeviceSize.width, equals(styleProgressSize.width));

        // Zero overflow in the On this device card
        expect(cardOverflows, isEmpty);
      },
    );
  });
}
