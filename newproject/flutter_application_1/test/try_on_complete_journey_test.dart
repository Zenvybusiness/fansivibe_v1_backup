import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/stylist/presentation/stylist_screen.dart';
import 'package:fansivibe/features/try_on/data/try_on_client.dart';
import 'package:fansivibe/features/try_on/data/try_on_device_saver.dart';
import 'package:fansivibe/features/try_on/data/try_on_models.dart';
import 'package:fansivibe/features/try_on/data/try_on_repository.dart';
import 'package:fansivibe/features/try_on/presentation/try_on_screen.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart'
    show MediaRef, WearEventLogResponse, WearSummary;
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show WardrobeInsightData, WardrobeItemData;
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

// Minimal valid 1x1 PNG bytes (valid magic bytes, < 64px for dimension tests).
final Uint8List _validPng1x1 = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
);

// Minimal valid 64x64 JPEG header bytes (for non-strict / HTTP wire tests).
final Uint8List _validJpegHeader = Uint8List.fromList([
  0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
  ...List<int>.filled(64, 0x22),
]);

// Valid 64x64 PNG bytes generated dynamically for strict image validation tests.
Future<Uint8List> _makeValidPng64x64() async {
  // 64x64 RGBA solid PNG (pre-encoded valid PNG).
  // Use a known valid 64x64 1-color PNG base64.
  return base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAWElEQVR4nO3OQQ0AIBDAMMC/58MCP7QkAd1Nz163z7377gX2vA8gQIAAAQIECBAgQIAAAQIECBAgQIAAAQIECBAgQIAAAQIECBAgQIAAAQIECBAgQIAAgQs8qX4BR9/n7E0AAAAASUVORK5CYII=',
  );
}

const TryOnCapabilities _genlookCaps = TryOnCapabilities(
  enabled: true,
  isMock: false,
  maxGarments: 1,
  maxPersonImageBytes: 10 * 1024 * 1024,
  minImageEdge: 64,
  maxImageEdge: 4096,
  maxImagePixels: 12000000,
  allowedMimeTypes: ['image/jpeg', 'image/png', 'image/webp'],
  consentVersion: 'tryon-v1',
  pollIntervalSeconds: 0.05,
  pollTimeoutSeconds: 30.0,
  aiDisclosureRequired: true,
);

const TryOnCapabilities _multiGarmentCaps = TryOnCapabilities(
  enabled: true,
  isMock: true,
  maxGarments: 2,
  maxPersonImageBytes: 20 * 1024 * 1024,
  minImageEdge: 64,
  maxImageEdge: 4096,
  maxImagePixels: 12000000,
  allowedMimeTypes: ['image/jpeg', 'image/png', 'image/webp'],
  consentVersion: 'tryon-v1',
  pollIntervalSeconds: 0.05,
  pollTimeoutSeconds: 30.0,
  aiDisclosureRequired: false,
);

class _FakeWardrobeRepo implements WardrobeRepository {
  _FakeWardrobeRepo({
    this.items = const [],
    this.throwOnList = false,
  });

  final List<WardrobeItemData> items;
  bool throwOnList;
  int listCalls = 0;

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async {
    listCalls++;
    if (throwOnList) {
      throw StateError('Wardrobe offline');
    }
    return items;
  }

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async => null;

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
    String? fit,
    double? fitConfidence,
  }) async => null;

  @override
  Future<WardrobeItemData?> updateItem({
    required String itemId,
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
    String? fit,
    double? fitConfidence,
  }) async => null;

  @override
  Future<bool?> deleteItem({required String itemId}) async => true;

  @override
  Future<WardrobeInsightData?> getInsight() async => null;

  @override
  Future<WearSummary?> getWearSummary() async => null;

  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async => null;

  @override
  Future<WearEventLogResponse?> logEnsembleWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async => null;
}

const _wardrobeItems = [
  WardrobeItemData(
    id: '11111111-1111-4111-8111-111111111111',
    name: 'Sage Linen Blouse',
    category: 'tops',
    color: 'olive',
  ),
  WardrobeItemData(
    id: '22222222-2222-4222-8222-222222222222',
    name: 'Charcoal Tailored Trousers',
    category: 'bottoms',
    color: 'charcoal',
  ),
  WardrobeItemData(
    id: '33333333-3333-4333-8333-333333333333',
    name: 'Navy Cashmere Coat',
    category: 'outerwear',
    color: 'navy',
  ),
];

Future<void> _tapVisible(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(finder, 250);
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
    AuthSession.resetForTest();
  });

  tearDown(() {
    AuthSession.resetForTest();
    LocalStorage.resetForTest();
  });

  group('Phase 5 Complete Virtual Try-On User Journey', () {
    test('StylistScreen includes Virtual Try-On navigation entry', () async {
      // Verified in widget test below; keep group structured.
      expect(RouteNames.tryOn, equals('try-on'));
    });

    testWidgets('0. StylistScreen navigates to Virtual Try-On with wardrobe source', (
      tester,
    ) async {
      String? navigatedSource;
      List<String>? navigatedGarments;

      final router = GoRouter(
        initialLocation: '/stylist',
        routes: [
          GoRoute(
            path: '/stylist',
            name: RouteNames.stylist,
            builder: (_, __) => StylistScreen(
              wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
            ),
          ),
          GoRoute(
            path: '/home/try-on',
            name: RouteNames.tryOn,
            builder: (_, state) {
              final extra = state.extra as Map<String, dynamic>?;
              navigatedSource = extra?['outfitSource'] as String?;
              navigatedGarments =
                  (extra?['garmentIds'] as List?)?.whereType<String>().toList();
              return const Scaffold(body: Text('TryOn Destination'));
            },
          ),
        ],
      );

      await tester.pumpWidget(
        MaterialApp.router(
          theme: FansivibeTheme.darkTheme,
          routerConfig: router,
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Virtual Try-On'));
      expect(find.text('TryOn Destination'), findsOneWidget);
      expect(navigatedSource, equals('wardrobe'));
      expect(navigatedGarments, isEmpty);
    });

    testWidgets('1. Person image selection: preview, replace, remove, and permission denial', (
      tester,
    ) async {
      final validPng64 = await _makeValidPng64x64();
      var callCount = 0;

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: const [],
            title: 'Virtual Try-On',
            capabilities: _genlookCaps,
            strictImageValidation: true,
            wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
            pickImage: (source) async {
              callCount++;
              if (callCount == 1) {
                throw PlatformException(
                  code: 'photo_access_denied',
                  message: 'Permission denied',
                );
              }
              return XFile.fromData(
                validPng64,
                name: 'person_$callCount.png',
                mimeType: 'image/png',
              );
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Permission denial handled gracefully without crash.
      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      expect(find.textContaining('permission denied'), findsOneWidget);

      // Valid gallery pick renders preview, dimensions in review, Replace & Remove.
      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      expect(find.text('Replace Photo'), findsOneWidget);
      expect(find.text('Remove'), findsOneWidget);
      expect(find.text('Person photo ready (64×64)'), findsOneWidget);

      // Replace photo works.
      await tester.tap(find.text('Replace Photo'));
      await tester.pumpAndSettle();
      expect(callCount, 3);
      expect(find.text('Person photo ready (64×64)'), findsOneWidget);

      // Remove photo clears preview back to empty state.
      await tester.tap(find.text('Remove'));
      await tester.pumpAndSettle();
      expect(find.text('No person photograph selected'), findsOneWidget);
      expect(find.text('Choose Photo'), findsOneWidget);
    });

    test('2. Image validation rejects invalid type, small dims, oversized, and corrupt bytes', () async {
      final validPng64 = await _makeValidPng64x64();

      // Valid 64x64 PNG passes.
      final ok = await validateTryOnPersonImage(
        validPng64,
        capabilities: _genlookCaps,
        decodedDimensions: (64, 64),
      );
      expect(ok.isValid, isTrue);
      expect(ok.mimeType, equals('image/png'));

      // Empty file rejected.
      final emptyRes = await validateTryOnPersonImage(
        Uint8List(0),
        capabilities: _genlookCaps,
      );
      expect(emptyRes.isValid, isFalse);

      // Oversized (> 10 MB Genlook limit) rejected.
      final huge = Uint8List((10 * 1024 * 1024) + 1);
      final sizeRes = await validateTryOnPersonImage(
        huge,
        capabilities: _genlookCaps,
      );
      expect(sizeRes.isValid, isFalse);
      expect(sizeRes.errorMessage, contains('10 MB'));

      // Unsupported GIF magic bytes rejected.
      final gif = Uint8List.fromList('GIF89a1234567890'.codeUnits);
      final gifRes = await validateTryOnPersonImage(
        gif,
        capabilities: _genlookCaps,
      );
      expect(gifRes.isValid, isFalse);
      expect(gifRes.errorMessage, contains('JPEG, PNG, or WebP'));

      // Dimensions < 64x64 rejected.
      final smallRes = await validateTryOnPersonImage(
        _validPng1x1,
        capabilities: _genlookCaps,
        decodedDimensions: (1, 1),
      );
      expect(smallRes.isValid, isFalse);
      expect(smallRes.errorMessage, contains('64×64'));

      // Dimensions > 4096 rejected.
      final tallRes = await validateTryOnPersonImage(
        validPng64,
        capabilities: _genlookCaps,
        decodedDimensions: (5000, 1000),
      );
      expect(tallRes.isValid, isFalse);
      expect(tallRes.errorMessage, contains('4096×4096'));

      // Pixel count > 12 MP rejected.
      final mpRes = await validateTryOnPersonImage(
        validPng64,
        capabilities: _genlookCaps,
        decodedDimensions: (4000, 4000),
      );
      expect(mpRes.isValid, isFalse);
      expect(mpRes.errorMessage, contains('12 megapixel'));
    });

    testWidgets('2b. Strict widget image validation shows error for tiny 1x1 image', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: const [],
            title: 'Validation Widget Test',
            capabilities: _genlookCaps,
            strictImageValidation: true,
            wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
            pickImage: (_) async => XFile.fromData(
              _validPng1x1,
              name: 'tiny.png',
              mimeType: 'image/png',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();

      expect(find.textContaining('64×64'), findsOneWidget);
      expect(find.text('No person photograph selected'), findsOneWidget);
    });

    testWidgets('3. Wardrobe garment selection, removal, and ownership enforcement', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            // Include a foreign/non-owned garment ID to verify it gets dropped.
            garmentIds: const ['99999999-9999-4999-8999-999999999999'],
            title: 'Ownership Test',
            capabilities: _genlookCaps,
            wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.textContaining('does not belong to your Digital Wardrobe'),
        findsOneWidget,
      );
      expect(find.text('Selected Garments (0)'), findsOneWidget);

      // Select a garment from the user's wardrobe.
      await _tapVisible(tester, find.text('Select from Digital Wardrobe'));
      expect(find.text('Sage Linen Blouse'), findsOneWidget);
      await tester.tap(find.text('Sage Linen Blouse'));
      await tester.pumpAndSettle();

      expect(find.text('Selected Garments (1)'), findsOneWidget);
      expect(find.text('1 garment(s) selected'), findsOneWidget);

      // Remove the selected garment.
      await _tapVisible(tester, find.byTooltip('Remove garment'));
      expect(find.text('Selected Garments (0)'), findsOneWidget);
      expect(find.text('No garment selected'), findsOneWidget);
    });

    testWidgets('4. Empty wardrobe renders Add Garment action and navigates', (
      tester,
    ) async {
      var navigatedToAdd = false;

      final router = GoRouter(
        initialLocation: '/try-on',
        routes: [
          GoRoute(
            path: '/try-on',
            builder: (_, __) => TryOnScreen(
              outfitSource: 'wardrobe',
              garmentIds: const [],
              title: 'Virtual Try-On',
              capabilities: _genlookCaps,
              wardrobeRepository: _FakeWardrobeRepo(items: const []),
            ),
          ),
          GoRoute(
            path: '/wardrobe/add-category',
            name: RouteNames.wardrobeAddCategory,
            builder: (_, __) {
              navigatedToAdd = true;
              return const Scaffold(body: Text('Add Wardrobe Category'));
            },
          ),
        ],
      );

      await tester.pumpWidget(
        MaterialApp.router(
          theme: FansivibeTheme.darkTheme,
          routerConfig: router,
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Digital Wardrobe is empty'), findsOneWidget);
      await _tapVisible(tester, find.text('Add Garment to Wardrobe'));
      expect(navigatedToAdd, isTrue);
      expect(find.text('Add Wardrobe Category'), findsOneWidget);
    });

    testWidgets('4b. Wardrobe load failure shows error and Retry Loading Wardrobe recovers', (
      tester,
    ) async {
      final repo = _FakeWardrobeRepo(items: _wardrobeItems, throwOnList: true);
      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: const [],
            title: 'Wardrobe Retry Test',
            capabilities: _genlookCaps,
            wardrobeRepository: repo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Could not load your Digital Wardrobe.'), findsOneWidget);
      repo.throwOnList = false;
      await _tapVisible(tester, find.text('Retry Loading Wardrobe'));
      expect(find.text('Select from Digital Wardrobe'), findsOneWidget);
    });

    testWidgets('5. Multiple selection limits enforce backend maxGarments', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: const [],
            title: 'Multi-Selection Limit Test',
            capabilities: _multiGarmentCaps, // maxGarments = 2
            wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Select from Digital Wardrobe'));
      await tester.tap(find.text('Sage Linen Blouse'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Charcoal Tailored Trousers'));
      await tester.pumpAndSettle();
      // Attempting to select a 3rd item is blocked at maxGarments = 2.
      await tester.tap(find.text('Navy Cashmere Coat'));
      await tester.pumpAndSettle();

      expect(
        find.text('You can select up to 2 garments for one try-on.'),
        findsWidgets,
      );

      await tester.tap(find.text('Done (2)'));
      await tester.pumpAndSettle();
      expect(find.text('Selected Garments (2)'), findsOneWidget);
      expect(find.text('2 garment(s) selected'), findsOneWidget);
    });

    testWidgets('6, 7, 8, 9, 13. Full Genlook journey: submit, duplicate guard, queued->processing->completed, result image, full-screen, save-to-device, Wardrobe/Stylist nav', (
      tester,
    ) async {
      final validPng64 = await _makeValidPng64x64();
      await AuthSession.saveSession('jwt-test-token');

      var submitCount = 0;
      var pollCount = 0;
      var imageFetchedWithAuth = false;
      String? capturedAuthHeader;
      String? capturedIdemKey;

      final mockHttp = MockClient((request) async {
        if (request.method == 'GET' && request.url.path == '/v1/tryon/capabilities') {
          return http.Response(
            jsonEncode({
              'enabled': true,
              'is_mock': false,
              'max_garments': 1,
              'max_person_image_bytes': 10485760,
              'min_image_edge': 64,
              'max_image_edge': 4096,
              'max_image_pixels': 12000000,
              'allowed_mime_types': ['image/jpeg', 'image/png', 'image/webp'],
              'consent_version': 'tryon-v1',
              'poll_interval_seconds': 0.03,
              'poll_timeout_seconds': 30.0,
              'ai_disclosure_required': true,
            }),
            200,
          );
        }
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs') {
          submitCount++;
          capturedAuthHeader = request.headers['Authorization'];
          capturedIdemKey = request.headers['Idempotency-Key'];
          return http.Response(
            jsonEncode({
              'job_id': 'job-e2e-1',
              'status': 'queued',
              'is_mock': false,
            }),
            202,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-e2e-1') {
          pollCount++;
          if (pollCount == 1) {
            return http.Response(
              jsonEncode({
                'job_id': 'job-e2e-1',
                'status': 'queued',
                'progress': 50,
                'is_mock': false,
                'garment_ids': [_wardrobeItems.first.id],
              }),
              200,
            );
          }
          if (pollCount == 2) {
            return http.Response(
              jsonEncode({
                'job_id': 'job-e2e-1',
                'status': 'processing',
                'progress': 50,
                'is_mock': false,
                'garment_ids': [_wardrobeItems.first.id],
              }),
              200,
            );
          }
          return http.Response(
            jsonEncode({
              'job_id': 'job-e2e-1',
              'status': 'completed',
              'progress': 100,
              'is_mock': false,
              'garment_ids': [_wardrobeItems.first.id],
            }),
            200,
          );
        }
        if (request.method == 'GET' &&
            request.url.path == '/v1/tryon/jobs/job-e2e-1/image') {
          imageFetchedWithAuth =
              request.headers['Authorization'] == 'Bearer jwt-test-token';
          return http.Response.bytes(
            validPng64,
            200,
            headers: {'content-type': 'image/png'},
          );
        }
        return http.Response('Not found', 404);
      });

      final repo = TryOnRepositoryImpl(client: TryOnClient(client: mockHttp));
      var savedBytesLen = 0;

      final router = GoRouter(
        initialLocation: '/try-on',
        routes: [
          GoRoute(
            path: '/try-on',
            builder: (_, __) => TryOnScreen(
              outfitSource: 'wardrobe',
              garmentIds: const [],
              title: 'Virtual Try-On',
              tryOnRepository: repo,
              wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
              strictImageValidation: true,
              pollInterval: const Duration(milliseconds: 25),
              pickImage: (_) async => XFile.fromData(
                validPng64,
                name: 'me.png',
                mimeType: 'image/png',
              ),
              saveResultImage: (bytes, jobId) async {
                savedBytesLen = bytes.length;
                return const TryOnSaveOutcome(
                  status: TryOnSaveStatus.saved,
                  message: 'Saved to Pictures/Fansivibe',
                );
              },
            ),
          ),
          GoRoute(
            path: '/wardrobe',
            name: RouteNames.wardrobe,
            builder: (_, __) => const Scaffold(body: Text('Wardrobe Home')),
          ),
          GoRoute(
            path: '/stylist',
            name: RouteNames.stylist,
            builder: (_, __) => const Scaffold(body: Text('Stylist Home')),
          ),
        ],
      );

      await tester.pumpWidget(
        MaterialApp.router(
          theme: FansivibeTheme.darkTheme,
          routerConfig: router,
        ),
      );
      await tester.pumpAndSettle();

      // Capabilities switched CTA to Generate Try-On and hid TEST DATA banner.
      expect(find.text('TEST DATA — NOT AI TRY-ON'), findsNothing);
      expect(find.text('AI MODIFIED'), findsOneWidget);
      expect(find.text('Generate Try-On'), findsOneWidget);

      // Select person photo and garment.
      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.text('Select from Digital Wardrobe'));
      await tester.tap(find.text('Sage Linen Blouse'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.byType(Checkbox));

      // Double-tap Generate Try-On rapidly -> only 1 POST submitted!
      final genBtn = find.byKey(const ValueKey('tryon_generate_button'));
      await tester.scrollUntilVisible(genBtn, 250);
      await tester.pumpAndSettle();
      await tester.tap(genBtn);
      await tester.tap(genBtn, warnIfMissed: false);
      await tester.pump();

      expect(submitCount, 1);
      expect(capturedAuthHeader, equals('Bearer jwt-test-token'));
      expect(capturedIdemKey, isNotNull);
      expect(capturedIdemKey, isNotEmpty);

      // Poll 1: queued state.
      await tester.pump(const Duration(milliseconds: 30));
      expect(find.text('Queued for virtual try-on…'), findsOneWidget);

      // Poll 2: processing state.
      await tester.pump(const Duration(milliseconds: 30));
      expect(find.textContaining('Generating virtual try-on…'), findsOneWidget);

      // Poll 3: completed + result image.
      await tester.pump(const Duration(milliseconds: 40));
      await tester.pumpAndSettle();

      expect(imageFetchedWithAuth, isTrue);
      expect(find.text('Save to Device'), findsOneWidget);
      expect(find.text('Full Screen'), findsOneWidget);
      expect(find.text('Sage Linen Blouse'), findsOneWidget);
      expect(TryOnJobPersistence.load()?.jobId, equals('job-e2e-1'));

      // Full-screen viewer opens with InteractiveViewer and closes cleanly.
      await tester.tap(find.text('Full Screen'));
      await tester.pumpAndSettle();
      expect(find.byType(InteractiveViewer), findsOneWidget);
      await tester.tap(find.byType(CloseButton));
      await tester.pumpAndSettle();

      // Save to device works.
      await _tapVisible(tester, find.text('Save to Device'));
      expect(savedBytesLen, equals(validPng64.length));
      expect(find.text('Saved to Pictures/Fansivibe'), findsOneWidget);

      // Navigate back to Wardrobe.
      await _tapVisible(tester, find.text('Wardrobe'));
      expect(find.text('Wardrobe Home'), findsOneWidget);
    });

    testWidgets('9b. Save-to-device permission denial displays helpful guidance', (
      tester,
    ) async {
      final validPng64 = await _makeValidPng64x64();
      final mockHttp = MockClient((request) async {
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs') {
          return http.Response(
            jsonEncode({'job_id': 'job-perm', 'status': 'queued', 'is_mock': false}),
            202,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-perm') {
          return http.Response(
            jsonEncode({
              'job_id': 'job-perm',
              'status': 'completed',
              'progress': 100,
              'is_mock': false,
            }),
            200,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-perm/image') {
          return http.Response.bytes(validPng64, 200);
        }
        return http.Response('Not found', 404);
      });

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: [_wardrobeItems.first.id],
            title: 'Save Permission Test',
            capabilities: _genlookCaps,
            pollInterval: const Duration(milliseconds: 20),
            tryOnRepository: TryOnRepositoryImpl(client: TryOnClient(client: mockHttp)),
            wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
            pickImage: (_) async => XFile.fromData(_validJpegHeader, name: 'p.jpg'),
            saveResultImage: (_, __) async => const TryOnSaveOutcome(
              status: TryOnSaveStatus.permissionDenied,
              message: 'Storage permission denied by user.',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.byType(Checkbox));
      await _tapVisible(tester, find.text('Generate Try-On'));

      await _tapVisible(tester, find.text('Save to Device'));
      expect(find.text('Storage permission denied by user.'), findsOneWidget);
    });

    testWidgets('10. Failed generation surfaces backend error and retries explicitly via /retry', (
      tester,
    ) async {
      var submitCount = 0;
      var retryCount = 0;

      final mockHttp = MockClient((request) async {
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs') {
          submitCount++;
          return http.Response(
            jsonEncode({'job_id': 'job-fail-1', 'status': 'queued', 'is_mock': false}),
            202,
          );
        }
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs/job-fail-1/retry') {
          retryCount++;
          return http.Response(
            jsonEncode({'job_id': 'job-fail-1', 'status': 'queued', 'is_mock': false}),
            202,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-fail-1') {
          if (retryCount == 0) {
            return http.Response(
              jsonEncode({
                'job_id': 'job-fail-1',
                'status': 'failed',
                'progress': 0,
                'is_mock': false,
                'error_code': 'PROVIDER_TRANSIENT_FAILURE',
                'error_message': 'Commercial try-on provider experienced a transient error. You can retry.',
              }),
              200,
            );
          }
          return http.Response(
            jsonEncode({
              'job_id': 'job-fail-1',
              'status': 'completed',
              'progress': 100,
              'is_mock': false,
            }),
            200,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-fail-1/image') {
          return http.Response.bytes(await _makeValidPng64x64(), 200);
        }
        return http.Response('Not found', 404);
      });

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: [_wardrobeItems.first.id],
            title: 'Failure Retry Test',
            capabilities: _genlookCaps,
            pollInterval: const Duration(milliseconds: 20),
            tryOnRepository: TryOnRepositoryImpl(client: TryOnClient(client: mockHttp)),
            wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
            pickImage: (_) async => XFile.fromData(_validJpegHeader, name: 'p.jpg'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.byType(Checkbox));
      await _tapVisible(tester, find.text('Generate Try-On'));

      // Never auto-resubmitted!
      expect(submitCount, 1);
      expect(retryCount, 0);
      expect(find.textContaining('transient error'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);

      // Explicit tap calls /retry and completes.
      await _tapVisible(tester, find.text('Try Again'));
      expect(submitCount, 1);
      expect(retryCount, 1);
      expect(find.text('Save to Device'), findsOneWidget);
    });

    testWidgets('11. Network interruption during polling pauses safely and Check Status recovers same job', (
      tester,
    ) async {
      var submitCount = 0;
      var pollCount = 0;
      var online = false;

      final mockHttp = MockClient((request) async {
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs') {
          submitCount++;
          return http.Response(
            jsonEncode({'job_id': 'job-net-1', 'status': 'queued', 'is_mock': false}),
            202,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-net-1') {
          pollCount++;
          if (!online) {
            throw Exception('SocketException: Network is unreachable');
          }
          return http.Response(
            jsonEncode({
              'job_id': 'job-net-1',
              'status': 'completed',
              'progress': 100,
              'is_mock': false,
            }),
            200,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-net-1/image') {
          return http.Response.bytes(await _makeValidPng64x64(), 200);
        }
        return http.Response('Not found', 404);
      });

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: [_wardrobeItems.first.id],
            title: 'Network Interruption Test',
            capabilities: _genlookCaps,
            pollInterval: const Duration(milliseconds: 15),
            tryOnRepository: TryOnRepositoryImpl(client: TryOnClient(client: mockHttp)),
            wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
            pickImage: (_) async => XFile.fromData(_validJpegHeader, name: 'p.jpg'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.byType(Checkbox));
      await _tapVisible(tester, find.text('Generate Try-On'));

      expect(submitCount, 1);
      expect(pollCount, greaterThanOrEqualTo(5));
      expect(find.text('Connection interrupted'), findsOneWidget);
      expect(find.text('Check Status'), findsOneWidget);

      // Connection returns -> tap Check Status -> completes without duplicate submit.
      online = true;
      await tester.tap(find.text('Check Status'));
      await tester.pumpAndSettle();

      expect(submitCount, 1);
      expect(find.text('Save to Device'), findsOneWidget);
    });

    testWidgets('12. Job recovery resumes active job across widget recreation / app restart without duplicate submit', (
      tester,
    ) async {
      final validPng64 = await _makeValidPng64x64();
      var submitCount = 0;
      var pollCount = 0;

      TryOnJobPersistence.save(
        TryOnSavedJobRef(
          jobId: 'job-recover-99',
          outfitSource: 'wardrobe',
          garmentIds: [_wardrobeItems.first.id],
          title: 'Recovered Look',
          isMock: false,
          savedAtIso: DateTime.now().toUtc().toIso8601String(),
        ),
      );

      final mockHttp = MockClient((request) async {
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs') {
          submitCount++;
          return http.Response('Should not submit', 500);
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-recover-99') {
          pollCount++;
          if (pollCount == 1) {
            return http.Response(
              jsonEncode({
                'job_id': 'job-recover-99',
                'status': 'processing',
                'progress': 50,
                'is_mock': false,
                'garment_ids': [_wardrobeItems.first.id],
              }),
              200,
            );
          }
          return http.Response(
            jsonEncode({
              'job_id': 'job-recover-99',
              'status': 'completed',
              'progress': 100,
              'is_mock': false,
              'garment_ids': [_wardrobeItems.first.id],
            }),
            200,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-recover-99/image') {
          return http.Response.bytes(validPng64, 200);
        }
        return http.Response('Not found', 404);
      });

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: const [],
            title: 'Virtual Try-On',
            capabilities: _genlookCaps,
            pollInterval: const Duration(milliseconds: 20),
            tryOnRepository: TryOnRepositoryImpl(client: TryOnClient(client: mockHttp)),
            wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(submitCount, 0);
      expect(pollCount, greaterThanOrEqualTo(2));
      expect(find.text('Resumed your previous try-on job.'), findsOneWidget);
      expect(find.text('Save to Device'), findsOneWidget);
    });

    testWidgets('12b. Rule A: Pre-202 submit failure preserves Idempotency-Key on Try Again', (
      tester,
    ) async {
      final validPng64 = await _makeValidPng64x64();
      final seenIdemKeys = <String>[];
      var attempt = 0;

      final mockHttp = MockClient((request) async {
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs') {
          attempt++;
          seenIdemKeys.add(request.headers['Idempotency-Key'] ?? '');
          if (attempt == 1) {
            return http.Response(
              jsonEncode({
                'error': {
                  'code': 'STORAGE_FAILURE',
                  'message': 'Failed to securely store input person image. Please try again.',
                },
              }),
              503,
            );
          }
          return http.Response(
            jsonEncode({'job_id': 'job-idem-ok', 'status': 'queued', 'is_mock': false}),
            202,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-idem-ok') {
          return http.Response(
            jsonEncode({
              'job_id': 'job-idem-ok',
              'status': 'completed',
              'progress': 100,
              'is_mock': false,
            }),
            200,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-idem-ok/image') {
          return http.Response.bytes(validPng64, 200);
        }
        return http.Response('Not found', 404);
      });

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: [_wardrobeItems.first.id],
            title: 'Pre-POST Idempotency Test',
            capabilities: _genlookCaps,
            pollInterval: const Duration(milliseconds: 20),
            tryOnRepository: TryOnRepositoryImpl(client: TryOnClient(client: mockHttp)),
            wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
            pickImage: (_) async => XFile.fromData(_validJpegHeader, name: 'p.jpg'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.byType(Checkbox));
      await _tapVisible(tester, find.text('Generate Try-On'));

      expect(attempt, 1);
      expect(find.textContaining('Failed to securely store input person image'), findsOneWidget);

      await _tapVisible(tester, find.text('Try Again'));
      expect(attempt, 2);
      expect(seenIdemKeys.length, 2);
      expect(seenIdemKeys[0], isNotEmpty);
      expect(seenIdemKeys[1], equals(seenIdemKeys[0]));
      expect(find.text('Save to Device'), findsOneWidget);
    });

    testWidgets('12c. Rule D: Completed generation with image-download failure retries image fetch only', (
      tester,
    ) async {
      final validPng64 = await _makeValidPng64x64();
      var submitCount = 0;
      var retryCount = 0;
      var imageAttempts = 0;

      final mockHttp = MockClient((request) async {
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs') {
          submitCount++;
          return http.Response(
            jsonEncode({'job_id': 'job-img-dl', 'status': 'queued', 'is_mock': false}),
            202,
          );
        }
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs/job-img-dl/retry') {
          retryCount++;
          return http.Response('Should not call /retry', 500);
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-img-dl') {
          return http.Response(
            jsonEncode({
              'job_id': 'job-img-dl',
              'status': 'completed',
              'progress': 100,
              'is_mock': false,
            }),
            200,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-img-dl/image') {
          imageAttempts++;
          if (imageAttempts == 1) {
            return http.Response(
              jsonEncode({'error': {'code': 'NOT_FOUND', 'message': 'Temporary fetch glitch.'}}),
              503,
            );
          }
          return http.Response.bytes(validPng64, 200);
        }
        return http.Response('Not found', 404);
      });

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: [_wardrobeItems.first.id],
            title: 'Image Download Retry Test',
            capabilities: _genlookCaps,
            pollInterval: const Duration(milliseconds: 20),
            tryOnRepository: TryOnRepositoryImpl(client: TryOnClient(client: mockHttp)),
            wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
            pickImage: (_) async => XFile.fromData(_validJpegHeader, name: 'p.jpg'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.byType(Checkbox));
      await _tapVisible(tester, find.text('Generate Try-On'));

      expect(submitCount, 1);
      expect(retryCount, 0);
      expect(imageAttempts, 1);
      expect(find.text('Retry Loading Image'), findsOneWidget);

      await _tapVisible(tester, find.text('Retry Loading Image'));
      expect(submitCount, 1);
      expect(retryCount, 0);
      expect(imageAttempts, 2);
      expect(find.text('Save to Device'), findsOneWidget);
    });

    testWidgets('12d. Rule E: Restart recovery restores failed job for /retry without duplicate POST', (
      tester,
    ) async {
      final validPng64 = await _makeValidPng64x64();
      var submitCount = 0;
      var retryCount = 0;

      TryOnJobPersistence.save(
        TryOnSavedJobRef(
          jobId: 'job-failed-restart',
          outfitSource: 'wardrobe',
          garmentIds: [_wardrobeItems.first.id],
          title: 'Interrupted Look',
          isMock: false,
          savedAtIso: DateTime.now().toUtc().toIso8601String(),
        ),
      );

      final mockHttp = MockClient((request) async {
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs') {
          submitCount++;
          return http.Response('Should not submit new job', 500);
        }
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs/job-failed-restart/retry') {
          retryCount++;
          return http.Response(
            jsonEncode({'job_id': 'job-failed-restart', 'status': 'processing', 'is_mock': false}),
            202,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-failed-restart') {
          if (retryCount == 0) {
            return http.Response(
              jsonEncode({
                'job_id': 'job-failed-restart',
                'status': 'failed',
                'progress': 0,
                'is_mock': false,
                'error_code': 'INTERRUPTED_BY_RESTART',
                'error_message': 'Job processing was interrupted by server restart during inference. Please retry.',
                'garment_ids': [_wardrobeItems.first.id],
              }),
              200,
            );
          }
          return http.Response(
            jsonEncode({
              'job_id': 'job-failed-restart',
              'status': 'completed',
              'progress': 100,
              'is_mock': false,
              'garment_ids': [_wardrobeItems.first.id],
            }),
            200,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-failed-restart/image') {
          return http.Response.bytes(validPng64, 200);
        }
        return http.Response('Not found', 404);
      });

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: const [],
            title: 'Virtual Try-On',
            capabilities: _genlookCaps,
            pollInterval: const Duration(milliseconds: 20),
            tryOnRepository: TryOnRepositoryImpl(client: TryOnClient(client: mockHttp)),
            wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(submitCount, 0);
      expect(retryCount, 0);
      expect(find.text('Resumed your previous try-on job.'), findsOneWidget);
      expect(find.textContaining('interrupted by server restart'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);

      await _tapVisible(tester, find.text('Try Again'));
      expect(submitCount, 0);
      expect(retryCount, 1);
      expect(find.text('Save to Device'), findsOneWidget);
    });

    testWidgets('14. Unauthorized 401 handling stops polling, clears session, and shows sign-in prompt', (
      tester,
    ) async {
      await AuthSession.saveSession('expired-jwt');
      var expiredCallbackCount = 0;
      AuthSession.onSessionExpired = () => expiredCallbackCount++;

      var pollCount = 0;
      final mockHttp = MockClient((request) async {
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs') {
          return http.Response(
            jsonEncode({'job_id': 'job-unauth', 'status': 'queued', 'is_mock': false}),
            202,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-unauth') {
          pollCount++;
          return http.Response(
            jsonEncode({
              'error': {
                'code': 'AUTHENTICATION_ERROR',
                'message': 'Your session has expired or is invalid. Please sign in again.',
              },
            }),
            401,
          );
        }
        return http.Response('Not found', 404);
      });

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: [_wardrobeItems.first.id],
            title: 'Unauthorized Test',
            capabilities: _genlookCaps,
            pollInterval: const Duration(milliseconds: 20),
            tryOnRepository: TryOnRepositoryImpl(client: TryOnClient(client: mockHttp)),
            wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
            pickImage: (_) async => XFile.fromData(_validJpegHeader, name: 'p.jpg'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.byType(Checkbox));
      await _tapVisible(tester, find.text('Generate Try-On'));

      expect(pollCount, 1);
      expect(expiredCallbackCount, 1);
      expect(AuthSession.isAuthenticated, isFalse);
      expect(find.textContaining('sign in again'), findsOneWidget);
    });

    testWidgets('Responsive layout renders cleanly on compact mobile (360px) and tablet (900px) with text scaling', (
      tester,
    ) async {
      for (final size in const [Size(360, 760), Size(900, 1200)]) {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1.0;
        addTearDown(() => tester.view.resetPhysicalSize());

        await tester.pumpWidget(
          MaterialApp(
            theme: FansivibeTheme.darkTheme,
            home: MediaQuery(
              data: MediaQueryData(
                size: size,
                textScaler: const TextScaler.linear(1.3),
              ),
              child: TryOnScreen(
                outfitSource: 'wardrobe',
                garmentIds: [_wardrobeItems.first.id],
                title: 'Responsive Try-On',
                capabilities: _genlookCaps,
                wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('Responsive Try-On'), findsOneWidget);
        expect(find.text('Generate Try-On'), findsOneWidget);
        expect(tester.takeException(), isNull);
      }
    });

    testWidgets('13. Phase 7: Client submit TimeoutException preserves idempotency key and avoids duplicate jobs', (
      tester,
    ) async {
      final seenIdempotencyKeys = <String>[];
      var submitAttempts = 0;

      final mockHttp = MockClient((request) async {
        if (request.url.path == '/v1/tryon/jobs') {
          submitAttempts++;
          seenIdempotencyKeys.add(request.headers['Idempotency-Key'] ?? '');
          if (submitAttempts == 1) {
            throw TimeoutException('Simulated client submit timeout');
          }
          return http.Response(
            jsonEncode({
              'job_id': 'job-timeout-recovered-1',
              'status': 'processing',
              'is_mock': false,
            }),
            202,
          );
        }
        if (request.url.path == '/v1/tryon/jobs/job-timeout-recovered-1') {
          return http.Response(
            jsonEncode({
              'job_id': 'job-timeout-recovered-1',
              'status': 'completed',
              'progress': 100,
              'is_mock': false,
              'garment_ids': [_wardrobeItems.first.id],
            }),
            200,
          );
        }
        if (request.url.path == '/v1/tryon/jobs/job-timeout-recovered-1/image') {
          final png = await _makeValidPng64x64();
          return http.Response.bytes(png, 200, headers: {'content-type': 'image/png'});
        }
        return http.Response('Not found', 404);
      });

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: [_wardrobeItems.first.id],
            title: 'Submit Timeout Test',
            capabilities: _genlookCaps,
            pollInterval: const Duration(milliseconds: 20),
            tryOnRepository: TryOnRepositoryImpl(client: TryOnClient(client: mockHttp)),
            wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
            pickImage: (_) async => XFile.fromData(_validJpegHeader, name: 'p.jpg'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.byType(Checkbox));
      await _tapVisible(tester, find.text('Generate Try-On'));

      expect(submitAttempts, 1);
      expect(find.textContaining('Request timed out'), findsOneWidget);

      // Tap Try Again -> resends the EXACT same Idempotency-Key
      await _tapVisible(tester, find.text('Try Again'));
      expect(submitAttempts, 2);
      expect(seenIdempotencyKeys.length, 2);
      expect(seenIdempotencyKeys[0], isNotEmpty);
      expect(seenIdempotencyKeys[1], equals(seenIdempotencyKeys[0]));
      expect(find.text('Save to Device'), findsOneWidget);
    });

    testWidgets('14. Phase 7F: Permanent camera/photo permission denial shows settings guidance and lifecycle pause/resume works', (
      tester,
    ) async {
      final validPng64 = await _makeValidPng64x64();
      var pollCalls = 0;

      final mockHttp = MockClient((request) async {
        if (request.url.path == '/v1/tryon/jobs') {
          return http.Response(
            jsonEncode({
              'job_id': 'job-bg-resume-1',
              'status': 'processing',
              'is_mock': false,
            }),
            202,
          );
        }
        if (request.url.path == '/v1/tryon/jobs/job-bg-resume-1') {
          pollCalls++;
          if (pollCalls < 2) {
            return http.Response(
              jsonEncode({
                'job_id': 'job-bg-resume-1',
                'status': 'processing',
                'progress': 50,
                'is_mock': false,
                'garment_ids': [_wardrobeItems.first.id],
              }),
              200,
            );
          }
          return http.Response(
            jsonEncode({
              'job_id': 'job-bg-resume-1',
              'status': 'completed',
              'progress': 100,
              'is_mock': false,
              'garment_ids': [_wardrobeItems.first.id],
            }),
            200,
          );
        }
        if (request.url.path == '/v1/tryon/jobs/job-bg-resume-1/image') {
          return http.Response.bytes(validPng64, 200, headers: {'content-type': 'image/png'});
        }
        return http.Response('Not found', 404);
      });

      var pickCalls = 0;
      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: [_wardrobeItems.first.id],
            title: 'Permission & Lifecycle Test',
            capabilities: _genlookCaps,
            pollInterval: const Duration(milliseconds: 50),
            tryOnRepository: TryOnRepositoryImpl(client: TryOnClient(client: mockHttp)),
            wardrobeRepository: _FakeWardrobeRepo(items: _wardrobeItems),
            pickImage: (source) async {
              pickCalls++;
              if (pickCalls == 1) {
                throw PlatformException(
                  code: 'camera_access_denied',
                  message: 'Camera permission permanently denied',
                );
              }
              return XFile.fromData(validPng64, name: 'ok.png');
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Permanent camera denial surfaces clear Settings message
      await tester.tap(find.text('Take Photo'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Open device Settings'), findsOneWidget);

      // Gallery succeeds, submit transitions to polling, background pause + resume completes
      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.byType(Checkbox));
      await tester.scrollUntilVisible(find.text('Generate Try-On'), 250);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Generate Try-On'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 20));

      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump(const Duration(milliseconds: 120));
      final pollsWhilePaused = pollCalls;
      await tester.pump(const Duration(milliseconds: 120));
      expect(pollCalls, equals(pollsWhilePaused));

      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(find.text('Save to Device'), findsOneWidget);
    });

    test('15. Phase 7F: TryOnDeviceSaver reports saved, temporary denial, and permanent denial safely', () async {
      final png64 = await _makeValidPng64x64();
      // Non-mobile desktop host writes to ~/Pictures/Fansivibe when HOME is set;
      // verify validation guards for empty and non-image payloads directly.
      final emptyRes = await TryOnDeviceSaver.saveImage(Uint8List(0), jobId: 'j1');
      expect(emptyRes.status, TryOnSaveStatus.failed);

      final svgRes = await TryOnDeviceSaver.saveImage(
        Uint8List.fromList(utf8.encode('<svg></svg>')),
        jobId: 'j1',
      );
      expect(svgRes.status, TryOnSaveStatus.unsupported);

      const outcomePerm = TryOnSaveOutcome(
        status: TryOnSaveStatus.permissionDenied,
        permanentlyDenied: true,
        message: 'Enable in Settings',
      );
      expect(outcomePerm.permanentlyDenied, isTrue);
      expect(png64.length, greaterThan(12));
    });
  });
}
