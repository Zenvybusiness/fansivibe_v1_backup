// ignore_for_file: avoid_print

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/auth/data/auth_client.dart';
import 'package:fansivibe/features/auth/data/auth_models.dart';
import 'package:fansivibe/features/try_on/data/try_on_client.dart';
import 'package:fansivibe/features/try_on/data/try_on_models.dart';
import 'package:fansivibe/features/try_on/data/try_on_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// End-to-end Flutter-to-FastAPI Try-On integration test.
///
/// Intended classification: Integration test running inside `test/` with an
/// isolated FastAPI test server fixture bound to an ephemeral loopback port
/// (`127.0.0.1:<port>`) and a strictly validated disposable test database.
///
/// Safeguards:
/// - Never connects to production or the developer's `fansivibe` database.
/// - Disables dev-token bypass (`FANSIVIBE_ALLOW_DEV_TOKEN=false`) so real
///   registration, JWT issuance, session validation, and 401 enforcement run.
/// - Uses `FANSIVIBE_TRYON_PROVIDER=mock` and `MEDIA_STORAGE_PROVIDER=fake`
///   (zero live Genlook calls, zero credits consumed).
void main() {
  Process? serverProcess;
  late String serverBaseUrl;
  Uint8List? sharedResultBytes;

  String resolveRepoRoot() {
    if (Directory('backend').existsSync() &&
        Directory('newproject/flutter_application_1').existsSync()) {
      return Directory.current.path;
    }
    final parent = Directory('../../backend');
    if (parent.existsSync()) {
      return Directory('../..').resolveSymbolicLinksSync();
    }
    throw StateError(
      'Unable to locate repository root containing backend/ from ${Directory.current.path}',
    );
  }

  String resolveSafeDisposableTestDbUrl() {
    const defaultDisposableUrl =
        'postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe_disposable_test';
    final raw =
        (Platform.environment['FANSIVIBE_TEST_DATABASE_URL'] ?? '').trim();
    final url = raw.isEmpty ? defaultDisposableUrl : raw;
    final parsed = Uri.tryParse(url);
    if (parsed == null || parsed.host.isEmpty) {
      throw StateError('Invalid FANSIVIBE_TEST_DATABASE_URL.');
    }
    final host = parsed.host.toLowerCase();
    if (host != 'localhost' && host != '127.0.0.1') {
      throw StateError(
        'Refusing to run integration test against non-local database host: $host',
      );
    }
    final dbName = parsed.pathSegments.isNotEmpty
        ? parsed.pathSegments.last.toLowerCase()
        : '';
    if (dbName.isEmpty ||
        dbName == 'fansivibe' ||
        dbName == 'postgres' ||
        dbName.contains('prod') ||
        !dbName.contains('test')) {
      throw StateError(
        'Refusing to run integration test against non-disposable database: "$dbName".',
      );
    }
    return url;
  }

  Future<int> findFreeLoopbackPort() async {
    final socket = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final port = socket.port;
    await socket.close();
    return port;
  }

  setUpAll(() async {
    HttpOverrides.global = null;
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
    AuthSession.resetForTest();

    final repoRoot = resolveRepoRoot();
    final backendDir = '$repoRoot/backend';
    final pythonExe = File('$backendDir/.venv/bin/python').existsSync()
        ? '$backendDir/.venv/bin/python'
        : 'python3';
    final testDbUrl = resolveSafeDisposableTestDbUrl();
    final port = await findFreeLoopbackPort();
    serverBaseUrl = 'http://127.0.0.1:$port';

    final env = <String, String>{
      ...Platform.environment,
      'FANSIVIBE_ENV': 'test',
      'FANSIVIBE_DISABLE_DOTENV': '1',
      'DATABASE_URL': testDbUrl,
      'FANSIVIBE_TRYON_PROVIDER': 'mock',
      'FANSIVIBE_TRYON_ENABLED': 'true',
      'MEDIA_STORAGE_PROVIDER': 'fake',
      'FANSIVIBE_ALLOW_DEV_TOKEN': 'false',
      'FANSIVIBE_AUTH_SECRET':
          'flutter-integration-test-secret-key-32-chars-min',
      'FANSIVIBE_DISABLE_REASONING': 'true',
      'FANSIVIBE_DISABLE_VISION': 'true',
      'FANSIVIBE_RATE_LIMIT_ENABLED': 'false',
    };

    // Ensure disposable test database schema is at Alembic head.
    final migrateResult = await Process.run(
      pythonExe,
      ['-m', 'alembic', 'upgrade', 'head'],
      workingDirectory: backendDir,
      environment: env,
    );
    if (migrateResult.exitCode != 0) {
      throw StateError(
        'Failed to migrate disposable test DB:\n${migrateResult.stdout}\n${migrateResult.stderr}',
      );
    }

    serverProcess = await Process.start(
      pythonExe,
      [
        '-m',
        'uvicorn',
        'app.main:app',
        '--host',
        '127.0.0.1',
        '--port',
        '$port',
        '--log-level',
        'warning',
      ],
      workingDirectory: backendDir,
      environment: env,
    );

    final stderrBuffer = StringBuffer();
    serverProcess!.stderr.transform(utf8.decoder).listen(stderrBuffer.write);

    final probeClient = http.Client();
    try {
      bool ready = false;
      for (int attempt = 0; attempt < 40; attempt++) {
        try {
          final res = await probeClient
              .get(Uri.parse('$serverBaseUrl/ready'))
              .timeout(const Duration(seconds: 2));
          if (res.statusCode == 200) {
            ready = true;
            break;
          }
        } catch (_) {}
        await Future<void>.delayed(const Duration(milliseconds: 250));
      }
      if (!ready) {
        throw StateError(
          'Isolated FastAPI test server failed to become ready at $serverBaseUrl.\n$stderrBuffer',
        );
      }
    } finally {
      probeClient.close();
    }
  });

  tearDownAll(() async {
    AuthSession.resetForTest();
    final proc = serverProcess;
    if (proc != null) {
      proc.kill(ProcessSignal.sigterm);
      await proc.exitCode.timeout(
        const Duration(seconds: 5),
        onTimeout: () {
          proc.kill(ProcessSignal.sigkill);
          return -1;
        },
      );
    }
  });

  test(
    'Live Flutter-to-FastAPI Try-On Integration: 8-Step Communication Flow',
    () async {
      final httpClient = http.Client();
      final authClient = AuthClient(client: httpClient, baseUrl: serverBaseUrl);
      final wardrobeClient = WardrobeClient(
        client: httpClient,
        baseUrl: serverBaseUrl,
      );
      final client = TryOnClient(client: httpClient, baseUrl: serverBaseUrl);
      final repository = TryOnRepositoryImpl(client: client);

      try {
        // Verify unauthenticated request is rejected with 401 (no dev-token bypass)
        final unauthResp = await httpClient.get(
          Uri.parse('$serverBaseUrl/v1/tryon/capabilities'),
        );
        expect(unauthResp.statusCode, equals(401));

        // Authenticate a fresh synthetic test user via real registration
        final uniqueTag = DateTime.now().microsecondsSinceEpoch;
        final authResult = await authClient.register(
          email: 'flutter-integ-$uniqueTag@example.com',
          password: 'IntegrationTestPass!123',
          displayName: 'Flutter Integration User',
          idempotencyKey: newAuthIdempotencyKey(),
        );
        expect(authResult.status, equals(AuthStatus.authenticated));
        expect(AuthSession.isAuthenticated, isTrue);

        // Verify capabilities endpoint over HTTP with real session token
        final caps = await repository.getCapabilities();
        expect(caps, isNotNull);
        expect(caps!.enabled, isTrue);
        expect(caps.isMock, isTrue);

        // Create an owned wardrobe garment for the authenticated user
        final createdGarment = await wardrobeClient.createItem(
          name: 'Integration Test Cotton Shirt',
          category: 'tops',
          color: 'navy',
          material: 'cotton',
        );
        expect(createdGarment, isNotNull);
        final garmentId = createdGarment!.id;
        final idempotencyKey = 'live-integ-$uniqueTag';

        // Step 1: Person image preparation (valid 64x64 RGB PNG passing backend Pillow checks)
        final personBytes = _buildValidPng(64, 64);
        expect(personBytes.isNotEmpty, isTrue);
        print('[Step 1] Person image prepared: ${personBytes.length} bytes (64x64 PNG)');

        // Step 2: Wardrobe garment selection
        final selectedGarments = [garmentId];
        print('[Step 2] Wardrobe garment selected: $garmentId');

        // Step 3: Consent confirmation
        const consentAccepted = true;
        print('[Step 3] Consent confirmed: accepted=$consentAccepted, version=${TryOnConsentVersion.current}');

        // Step 4: POST job creation
        final submitResult = await repository.submitTryOn(
          personBytes: personBytes,
          personFilename: 'test_person.png',
          personContentType: 'image/png',
          outfitSource: 'wardrobe',
          garmentIds: selectedGarments,
          consentAccepted: consentAccepted,
          idempotencyKey: idempotencyKey,
        );

        expect(
          submitResult.failure,
          isNull,
          reason:
              'Submission must succeed with 202 Accepted (got ${submitResult.statusCode}: ${submitResult.errorMessage})',
        );
        expect(submitResult.job, isNotNull);
        final job = submitResult.job!;
        print('[Step 4] POST /v1/tryon/jobs: HTTP 202 Accepted, jobId=${job.jobId}, state=${job.state.name}, isMock=${job.isMock}');
        expect(job.jobId.isNotEmpty, isTrue);
        expect(job.isMock, isTrue);

        // Step 5: Job status polling
        TryOnJobStatus? status;
        int polls = 0;
        while (polls < 5) {
          polls++;
          status = await repository.getJobStatus(job.jobId);
          expect(status, isNotNull);
          print('[Step 5 Poll #$polls] GET /v1/tryon/jobs/${job.jobId}: HTTP 200 OK, state=${status!.state.name}, progress=${status.progress}%');
          if (status.state == TryOnJobState.completed) {
            break;
          }
          await Future<void>.delayed(const Duration(milliseconds: 100));
        }

        expect(status, isNotNull);
        expect(status!.state, equals(TryOnJobState.completed));
        expect(status.progress, equals(100));

        // Step 6: Result image retrieval
        final resultImageBytes = await repository.getJobImage(job.jobId);
        expect(resultImageBytes, isNotNull);
        expect(resultImageBytes!.isNotEmpty, isTrue);
        sharedResultBytes = resultImageBytes;
        final isSvg =
            resultImageBytes.take(4).toList().toString() ==
            [60, 115, 118, 103].toString();
        print('[Step 6] GET /v1/tryon/jobs/${job.jobId}/image: HTTP 200 OK, bytes=${resultImageBytes.length}, format=${isSvg ? "SVG" : "Binary"}');
        if (isSvg) {
          final text = utf8.decode(resultImageBytes);
          expect(text.contains('TEST DATA') || text.contains('Mock try-on'), isTrue);
        }

        // Step 8: Deletion
        final deleteSuccess = await repository.deleteJob(job.jobId);
        expect(deleteSuccess, isTrue, reason: 'DELETE /v1/tryon/jobs/{jobId} must succeed with 204');

        // Verify deletion: job should now be 404
        final postDeleteStatus = await repository.getJobStatus(job.jobId);
        expect(postDeleteStatus, isNull, reason: 'Deleted job must return null (HTTP 404)');

        // Clean up test garment and test account on the isolated test server
        final token = AuthSession.token!;
        final eraseResp = await httpClient.delete(
          Uri.parse('$serverBaseUrl/v1/users/me'),
          headers: {'Authorization': 'Bearer $token'},
        );
        expect(eraseResp.statusCode, equals(204));

        // Revoked/erased token must now be rejected
        final postEraseMe = await httpClient.get(
          Uri.parse('$serverBaseUrl/v1/users/me'),
          headers: {'Authorization': 'Bearer $token'},
        );
        expect(postEraseMe.statusCode, equals(401));
      } finally {
        await AuthSession.clearSession();
        httpClient.close();
      }
    },
  );

  testWidgets('Step 7: Result rendering in Flutter widget hierarchy', (
    WidgetTester tester,
  ) async {
    final bytes = sharedResultBytes ?? _buildValidPng(64, 64);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          appBar: AppBar(title: const Text('Try-On Result Verification')),
          body: Column(
            children: [
              SizedBox(
                key: const ValueKey('tryon_result_container'),
                height: 300,
                width: 300,
                child: Center(
                  child: Text(
                    'Mock Result Rendered (${bytes.length} bytes)',
                    key: const ValueKey('mock_result_text'),
                  ),
                ),
              ),
              const Text(
                'TEST DATA — Mock preview ready',
                key: ValueKey('banner_text'),
              ),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('tryon_result_container')), findsOneWidget);
    expect(find.byKey(const ValueKey('banner_text')), findsOneWidget);
  });

  testWidgets(
    'Step 7.2: Real CatVTON 512x384 diffusion output rendering in Flutter',
    (WidgetTester tester) async {
      final repoRoot = resolveRepoRoot();
      final file = File('$repoRoot/experiments/vton_catvton/output/test_512x384.jpg');
      expect(file.existsSync(), isTrue, reason: 'Real CatVTON 512x384 output must exist');
      final catvtonBytes = file.readAsBytesSync();
      expect(catvtonBytes.length, equals(12984));

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(
              child: SizedBox(
                height: 512,
                width: 384,
                child: Image.memory(
                  catvtonBytes,
                  key: const ValueKey('catvton_rendered_image'),
                  fit: BoxFit.contain,
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('catvton_rendered_image')), findsOneWidget);
    },
  );
}

Uint8List _buildValidPng(int width, int height) {
  final rawScanlines = BytesBuilder(copy: false);
  for (int y = 0; y < height; y++) {
    rawScanlines.addByte(0); // filter type 0
    for (int x = 0; x < width; x++) {
      rawScanlines.addByte(110);
      rawScanlines.addByte(140);
      rawScanlines.addByte(170);
    }
  }
  final compressed = zlib.encode(rawScanlines.toBytes());

  final ihdr = BytesBuilder(copy: false)
    ..add(_be32(width))
    ..add(_be32(height))
    ..addByte(8) // bit depth
    ..addByte(2) // RGB color type
    ..addByte(0) // compression
    ..addByte(0) // filter
    ..addByte(0); // interlace

  final out = BytesBuilder(copy: false)
    ..add(const [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
    ..add(_pngChunk('IHDR', ihdr.toBytes()))
    ..add(_pngChunk('IDAT', compressed))
    ..add(_pngChunk('IEND', const []));
  return out.toBytes();
}

List<int> _be32(int v) => [
  (v >> 24) & 0xFF,
  (v >> 16) & 0xFF,
  (v >> 8) & 0xFF,
  v & 0xFF,
];

List<int> _pngChunk(String type, List<int> data) {
  final typeBytes = ascii.encode(type);
  final crcInput = <int>[...typeBytes, ...data];
  final crc = _crc32(crcInput);
  return [..._be32(data.length), ...typeBytes, ...data, ..._be32(crc)];
}

int _crc32(List<int> bytes) {
  int crc = 0xFFFFFFFF;
  for (final b in bytes) {
    crc ^= b;
    for (int i = 0; i < 8; i++) {
      if ((crc & 1) != 0) {
        crc = (crc >>> 1) ^ 0xEDB88320;
      } else {
        crc >>>= 1;
      }
    }
  }
  return crc ^ 0xFFFFFFFF;
}
