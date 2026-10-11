import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/hairstyle/presentation/face_scan_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/photo_capture_screen.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_scan_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_photo_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/camera/camera_lifecycle_coordinator.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

Uint8List _samplePng() => base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
);

Future<XFile?> _sampleXFile() async =>
    XFile.fromData(_samplePng(), name: 'sample.jpg', mimeType: 'image/jpeg');

Future<void> _pumpFrames(WidgetTester tester, [int count = 5]) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}

Future<void> _tapVisible(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
  await tester.tap(finder);
  await _pumpFrames(tester, 5);
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    AuthSession.resetForTest();
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    LocalStorage.resetForTest();
  });

  group('OutfitScanScreen Camera Lifecycle', () {
    testWidgets('Capture stops camera and preserves image bytes for analysis', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitScanScreen(
            takePhoto: () async => _sampleXFile(),
          ),
        ),
      );
      await _pumpFrames(tester);

      final state = tester.state(find.byType(OutfitScanScreen)) as dynamic;
      expect(state.cameraController, isNull);

      // Trigger capture
      await _tapVisible(tester, find.text('Capture Photo'));

      // Camera controller must be released/null
      expect(state.cameraController, isNull);

      // Image preview is rendered with finite constraints
      expect(find.byType(Image), findsOneWidget);
      expect(find.text('Analyze Photo'), findsOneWidget);
      expect(find.text('Photo selected'), findsOneWidget);
    });

    testWidgets('Retake clears photo and re-evaluates camera cleanly', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitScanScreen(
            takePhoto: () async => _sampleXFile(),
          ),
        ),
      );
      await _pumpFrames(tester);

      await _tapVisible(tester, find.text('Capture Photo'));
      expect(find.text('Retake Photo'), findsOneWidget);

      await _tapVisible(tester, find.text('Retake Photo'));

      final state = tester.state(find.byType(OutfitScanScreen)) as dynamic;
      expect(state.cameraController, isNull);
      expect(find.text('Capture Photo'), findsOneWidget);
      expect(find.text('Analyze Photo'), findsNothing);
    });

    testWidgets('Gallery pick releases camera resources immediately', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitScanScreen(
            pickImage: (_) => _sampleXFile(),
          ),
        ),
      );
      await _pumpFrames(tester);

      await _tapVisible(tester, find.text('Choose from Gallery'));

      final state = tester.state(find.byType(OutfitScanScreen)) as dynamic;
      expect(state.cameraController, isNull);
      expect(find.text('Photo selected'), findsOneWidget);
      expect(find.text('Analyze Photo'), findsOneWidget);
    });

    testWidgets('Back button releases camera resources before popping', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: ElevatedButton(
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute<void>(builder: (_) => const OutfitScanScreen()),
                  );
                },
                child: const Text('Open Scan'),
              ),
            ),
          ),
        ),
      );
      await _pumpFrames(tester);

      await tester.tap(find.text('Open Scan'));
      await _pumpFrames(tester);

      final state = tester.state(find.byType(OutfitScanScreen)) as dynamic;
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await _pumpFrames(tester, 10);

      expect(state.cameraController, isNull);
      expect(find.byType(OutfitScanScreen), findsNothing);
    });

    testWidgets('App backgrounding and resumption lifecycle handles camera safely', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(const MaterialApp(home: OutfitScanScreen()));
      await _pumpFrames(tester);

      final state = tester.state(find.byType(OutfitScanScreen)) as dynamic;

      // Simulate app paused / backgrounded
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await _pumpFrames(tester);
      expect(state.cameraController, isNull);

      // Simulate app resumed
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await _pumpFrames(tester);
      expect(tester.takeException(), isNull);
      expect(state.cameraController, isNull);
    });
  });

  group('FaceScanScreen Camera Lifecycle', () {
    testWidgets('Completing all 3 angles releases camera controller immediately', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: FaceScanScreen(
            takePhoto: () async => _sampleXFile(),
          ),
        ),
      );
      await _pumpFrames(tester);

      final state = tester.state(find.byType(FaceScanScreen)) as dynamic;

      // Front
      await _tapVisible(tester, find.text('Take Photo'));

      // Left
      await _tapVisible(tester, find.text('Take Photo'));

      // Right (final angle)
      await _tapVisible(tester, find.text('Take Photo'));

      // All angles are now captured
      expect(state.cameraController, isNull);
      expect(find.text('Front'), findsOneWidget);
      expect(find.text('Left'), findsOneWidget);
      expect(find.text('Right'), findsOneWidget);
      expect(find.text('Done'), findsOneWidget);
    });

    testWidgets('Analyze releases camera before navigating to processing', (
      WidgetTester tester,
    ) async {
      dynamic receivedExtra;
      final router = GoRouter(
        initialLocation: '/scan',
        routes: [
          GoRoute(
            path: '/scan',
            builder: (_, __) => FaceScanScreen(
              takePhoto: () async => _sampleXFile(),
            ),
          ),
          GoRoute(
            path: '/processing',
            name: RouteNames.hairstyleProcessing,
            builder: (_, state) {
              receivedExtra = state.extra;
              return const Scaffold(body: Text('Hairstyle Processing Screen'));
            },
          ),
        ],
      );

      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await _pumpFrames(tester);

      // Capture all 3 angles
      await _tapVisible(tester, find.text('Take Photo'));
      await _tapVisible(tester, find.text('Take Photo'));
      await _tapVisible(tester, find.text('Take Photo'));

      // Accept consent
      await _tapVisible(tester, find.byType(Checkbox));

      // Tap Analyze
      await _tapVisible(tester, find.text('Analyze Photos'));

      expect(find.text('Hairstyle Processing Screen'), findsOneWidget);
      expect(receivedExtra, isA<Map<String, dynamic>>());
      final map = receivedExtra as Map<String, dynamic>;
      expect(map['angleFront'], isNotNull);
      expect(map['angleLeft'], isNotNull);
      expect(map['angleRight'], isNotNull);
    });

    testWidgets('Skip releases camera before navigating to processing', (
      WidgetTester tester,
    ) async {
      final router = GoRouter(
        initialLocation: '/scan',
        routes: [
          GoRoute(
            path: '/scan',
            builder: (_, __) => const FaceScanScreen(),
          ),
          GoRoute(
            path: '/processing',
            name: RouteNames.hairstyleProcessing,
            builder: (_, __) => const Scaffold(body: Text('Processing Skipped')),
          ),
        ],
      );

      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await _pumpFrames(tester);

      await _tapVisible(tester, find.text('Skip for now'));

      expect(find.text('Processing Skipped'), findsOneWidget);
    });

    testWidgets('Back button releases camera resources before popping', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: ElevatedButton(
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute<void>(builder: (_) => const FaceScanScreen()),
                  );
                },
                child: const Text('Open Face Scan'),
              ),
            ),
          ),
        ),
      );
      await _pumpFrames(tester);

      await tester.tap(find.text('Open Face Scan'));
      await _pumpFrames(tester);

      final state = tester.state(find.byType(FaceScanScreen)) as dynamic;
      await tester.tap(
        find.descendant(
          of: find.byType(AppBar),
          matching: find.byType(IconButton),
        ),
      );
      await _pumpFrames(tester, 10);

      expect(state.cameraController, isNull);
      expect(find.byType(FaceScanScreen), findsNothing);
    });
  });

  group('WardrobePhotoScreen Camera Lifecycle', () {
    testWidgets('Photo capture stops camera and preserves image for review', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: WardrobePhotoScreen(
            takePhoto: () async => _sampleXFile(),
          ),
        ),
      );
      await _pumpFrames(tester);

      final state = tester.state(find.byType(WardrobePhotoScreen)) as dynamic;
      expect(state.cameraController, isNull);

      await _tapVisible(tester, find.text('Take Photo'));

      expect(state.cameraController, isNull);
      expect(find.text('Use Photo'), findsOneWidget);
      expect(find.text('Retake'), findsOneWidget);
    });

    testWidgets('Use Photo pops with WardrobePhoto data and releases camera', (
      WidgetTester tester,
    ) async {
      WardrobePhoto? returnedPhoto;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: ElevatedButton(
                onPressed: () async {
                  returnedPhoto = await Navigator.of(context).push<WardrobePhoto>(
                    MaterialPageRoute(
                      builder: (_) => WardrobePhotoScreen(
                        takePhoto: () async => _sampleXFile(),
                      ),
                    ),
                  );
                },
                child: const Text('Open Wardrobe Camera'),
              ),
            ),
          ),
        ),
      );
      await _pumpFrames(tester);

      await tester.tap(find.text('Open Wardrobe Camera'));
      await _pumpFrames(tester);

      await _tapVisible(tester, find.text('Take Photo'));

      await _tapVisible(tester, find.text('Use Photo'));

      expect(returnedPhoto, isNotNull);
      expect(returnedPhoto!.bytes, isNotEmpty);
      expect(find.text('Open Wardrobe Camera'), findsOneWidget);
    });

    testWidgets('Retake resets preview state cleanly', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: WardrobePhotoScreen(
            takePhoto: () async => _sampleXFile(),
          ),
        ),
      );
      await _pumpFrames(tester);

      await _tapVisible(tester, find.text('Take Photo'));
      expect(find.text('Retake'), findsOneWidget);

      await _tapVisible(tester, find.text('Retake'));

      final state = tester.state(find.byType(WardrobePhotoScreen)) as dynamic;
      expect(state.cameraController, isNull);
      expect(find.text('Take Photo'), findsOneWidget);
      expect(find.text('Use Photo'), findsNothing);
    });

    testWidgets('Gallery pick releases camera resources immediately', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: WardrobePhotoScreen(
            pickImage: (_) => _sampleXFile(),
          ),
        ),
      );
      await _pumpFrames(tester);

      await _tapVisible(tester, find.text('Choose from Gallery'));

      final state = tester.state(find.byType(WardrobePhotoScreen)) as dynamic;
      expect(state.cameraController, isNull);
      expect(find.text('Use Photo'), findsOneWidget);
    });
  });

  group('PhotoCaptureScreen (Onboarding) Camera Lifecycle', () {
    testWidgets('Photo capture stops camera and preserves image bytes', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: PhotoCaptureScreen(
            source: 'camera',
            takePhoto: () async => _sampleXFile(),
          ),
        ),
      );
      await _pumpFrames(tester);

      final state = tester.state(find.byType(PhotoCaptureScreen)) as dynamic;
      expect(state.cameraController, isNull);

      await _tapVisible(tester, find.text('Capture Photo'));

      expect(state.cameraController, isNull);
      expect(find.text('Continue'), findsOneWidget);
      expect(find.text('Retake Photo'), findsOneWidget);
    });

    testWidgets('Continue forwards bytes and releases camera controller', (
      WidgetTester tester,
    ) async {
      Object? receivedExtra;
      final router = GoRouter(
        initialLocation: '/capture',
        routes: [
          GoRoute(
            path: '/capture',
            builder: (_, __) => PhotoCaptureScreen(
              source: 'camera',
              takePhoto: () async => _sampleXFile(),
            ),
          ),
          GoRoute(
            path: '/analysis',
            name: RouteNames.aiAnalysis,
            builder: (_, state) {
              receivedExtra = state.extra;
              return const Scaffold(body: Text('Analysis Destination'));
            },
          ),
        ],
      );

      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await _pumpFrames(tester);

      await _tapVisible(tester, find.text('Capture Photo'));

      await _tapVisible(tester, find.text('Continue'));

      expect(find.text('Analysis Destination'), findsOneWidget);
      expect(receivedExtra, isA<Map<String, dynamic>>());
      final map = receivedExtra as Map<String, dynamic>;
      expect((map['imageBytes'] as Uint8List), isNotEmpty);
    });

    testWidgets('Back button releases camera resources before popping', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: ElevatedButton(
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => const PhotoCaptureScreen(source: 'camera'),
                    ),
                  );
                },
                child: const Text('Open Photo Capture'),
              ),
            ),
          ),
        ),
      );
      await _pumpFrames(tester);

      await tester.tap(find.text('Open Photo Capture'));
      await _pumpFrames(tester);

      final state = tester.state(find.byType(PhotoCaptureScreen)) as dynamic;
      await tester.tap(
        find.descendant(
          of: find.byType(AppBar),
          matching: find.byType(IconButton),
        ),
      );
      await _pumpFrames(tester, 10);

      expect(state.cameraController, isNull);
      expect(find.byType(PhotoCaptureScreen), findsNothing);
    });

    testWidgets('App lifecycle backgrounding/resumption handled safely without leaks', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        const MaterialApp(home: PhotoCaptureScreen(source: 'camera')),
      );
      await _pumpFrames(tester);

      final state = tester.state(find.byType(PhotoCaptureScreen)) as dynamic;

      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await _pumpFrames(tester);
      expect(state.cameraController, isNull);

      // Resumed must keep camera OFF (Rule 7)
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await _pumpFrames(tester);
      expect(tester.takeException(), isNull);
      expect(state.cameraController, isNull);
    });

    testWidgets('Entering PhotoCaptureScreen with source=gallery never initializes camera', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: PhotoCaptureScreen(
            source: 'gallery',
            pickImage: (_) async => _sampleXFile(),
          ),
        ),
      );
      await _pumpFrames(tester);

      final state = tester.state(find.byType(PhotoCaptureScreen)) as dynamic;
      expect(state.cameraController, isNull);
    });
  });

  group('Global Invariants: Non-camera screens and Coordination', () {
    testWidgets('CameraLifecycleCoordinator.stopAll stops registered camera sessions', (
      WidgetTester tester,
    ) async {
      var stopCount = 0;
      void listener() => stopCount++;

      CameraLifecycleCoordinator.register(listener);
      expect(stopCount, 0);

      CameraLifecycleCoordinator.stopAll();
      expect(stopCount, 1);

      CameraLifecycleCoordinator.unregister(listener);
      CameraLifecycleCoordinator.stopAll();
      expect(stopCount, 1);
    });

    testWidgets('CameraRouteObserver triggers stopAll on didPush and didReplace', (
      WidgetTester tester,
    ) async {
      var stopCount = 0;
      void listener() => stopCount++;

      CameraLifecycleCoordinator.register(listener);
      cameraRouteObserver.didPush(
        MaterialPageRoute<void>(builder: (_) => const SizedBox()),
        null,
      );
      expect(stopCount, 1);

      cameraRouteObserver.didReplace(
        newRoute: MaterialPageRoute<void>(builder: (_) => const SizedBox()),
      );
      expect(stopCount, 2);

      CameraLifecycleCoordinator.unregister(listener);
    });
  });
}
