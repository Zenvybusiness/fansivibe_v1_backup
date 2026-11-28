import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/features/home/presentation/home_screen.dart';
import 'package:fansivibe/features/home/presentation/widgets/existing_user_home_widgets.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

const bool _runLiveE2E = bool.fromEnvironment(
  'SJ3_LIVE_E2E',
  defaultValue: false,
);

String _formatShortRange(String startIso, String endIso) {
  const months = <int, String>{
    1: 'Jan',
    2: 'Feb',
    3: 'Mar',
    4: 'Apr',
    5: 'May',
    6: 'Jun',
    7: 'Jul',
    8: 'Aug',
    9: 'Sep',
    10: 'Oct',
    11: 'Nov',
    12: 'Dec',
  };
  final s = DateTime.parse(startIso);
  final e = DateTime.parse(endIso);
  if (s.month == e.month) {
    return '${months[s.month]} ${s.day}\u2013${e.day}';
  }
  return '${months[s.month]} ${s.day}\u2013${months[e.month]} ${e.day}';
}

String _isoMonday(DateTime utcInstant) {
  final utcDate = DateTime.utc(
    utcInstant.year,
    utcInstant.month,
    utcInstant.day,
  );
  final monday = utcDate.subtract(Duration(days: utcDate.weekday - 1));
  final y = monday.year.toString().padLeft(4, '0');
  final m = monday.month.toString().padLeft(2, '0');
  final d = monday.day.toString().padLeft(2, '0');
  return '$y-$m-$d';
}

Future<Map<String, dynamic>> _postJson(
  http.Client client,
  String path,
  Map<String, dynamic> body, {
  String? token,
  String? idempotencyKey,
  int expectedStatus = 200,
}) async {
  final headers = <String, String>{'Content-Type': 'application/json'};
  if (token != null) headers['Authorization'] = 'Bearer $token';
  if (idempotencyKey != null) headers['Idempotency-Key'] = idempotencyKey;

  final resp = await client.post(
    Uri.parse('${AppConfig.apiBaseUrl}$path'),
    headers: headers,
    body: jsonEncode(body),
  );
  expect(
    resp.statusCode,
    expectedStatus,
    reason: 'POST $path failed: ${resp.statusCode} ${resp.body}',
  );
  return resp.body.isEmpty
      ? <String, dynamic>{}
      : jsonDecode(resp.body) as Map<String, dynamic>;
}

Future<Map<String, dynamic>> _getJson(
  http.Client client,
  String path, {
  required String token,
  int expectedStatus = 200,
}) async {
  final resp = await client.get(
    Uri.parse('${AppConfig.apiBaseUrl}$path'),
    headers: {'Authorization': 'Bearer $token'},
  );
  expect(
    resp.statusCode,
    expectedStatus,
    reason: 'GET $path failed: ${resp.statusCode} ${resp.body}',
  );
  return jsonDecode(resp.body) as Map<String, dynamic>;
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 6}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

Future<void> _pumpUntil(
  WidgetTester tester,
  bool Function() condition, {
  required String reason,
  int attempts = 40,
}) async {
  for (var i = 0; i < attempts; i++) {
    await _pumpFrames(tester, count: 1);
    if (condition()) return;
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 250)),
    );
  }
  fail('Timed out waiting for $reason');
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    LearningService.instance.resetForTest();
    AuthSession.resetForTest();
  });

  tearDown(() async {
    HttpOverrides.global = null;
    LearningService.instance.resetForTest();
    AuthSession.resetForTest();
    await AuthSession.clearSession();
  });

  testWidgets(
    'SJ3 live backend-to-Flutter Home UI end-to-end verification',
    skip: !_runLiveE2E,
    (WidgetTester tester) async {
      late http.Client rawClient;
      late String token1;
      late String email1;
      late String password1;
      late String token2;
      late Map<String, dynamic> backendHistory1;
      late Map<String, dynamic> backendSummary1;
      late Map<String, dynamic> backendHistory2;

      await tester.runAsync(() async {
        // Allow real loopback HTTP in testWidgets when SJ3_LIVE_E2E=true.
        HttpOverrides.global = null;
        rawClient = http.Client();

        final runId = DateTime.now().microsecondsSinceEpoch;
        email1 = 'sj3-flutter-u1-$runId@example.com';
        password1 = 'FansivibeSJ3!Pass1';

        // 1. Register User 1
        final reg1 = await _postJson(
          rawClient,
          '/v1/auth/register',
          {
            'email': email1,
            'password': password1,
            'displayName': 'SJ3 Flutter User 1',
          },
          idempotencyKey: 'sj3-fl-reg1-$runId',
          expectedStatus: 201,
        );
        token1 = reg1['accessToken'] as String;

        // 2. Seed valid learning activity: 5 wardrobe items + 2 saved looks
        for (var i = 0; i < 5; i++) {
          await _postJson(
            rawClient,
            '/v1/wardrobe/items',
            {'name': 'SJ3 Top $i', 'category': 'tops', 'color': 'black'},
            token: token1,
            expectedStatus: 201,
          );
        }
        for (var i = 0; i < 2; i++) {
          await _postJson(
            rawClient,
            '/v1/looks/today/save',
            {
              'title': 'SJ3 Look $i',
              'sourceContext': 'daily',
              'snapshot': {'kind': 'daily', 'i': i},
            },
            token: token1,
            idempotencyKey: 'sj3-fl-save-$runId-$i',
            expectedStatus: 201,
          );
        }

        // 3. Record previous week snapshot via SJ1 endpoint
        final nowUtc = DateTime.now().toUtc();
        final prevMonday = _isoMonday(nowUtc.subtract(const Duration(days: 7)));
        final snap1 = await _postJson(
          rawClient,
          '/v1/learning/journey/snapshots',
          {'weekStart': prevMonday},
          token: token1,
          expectedStatus: 200,
        );
        expect(snap1['created'], isTrue);
        expect((snap1['snapshot'] as Map)['styleScore'], 69);

        // Add 3 more wardrobe items in current week so current = 72 (+3 vs 69)
        for (var i = 0; i < 3; i++) {
          await _postJson(
            rawClient,
            '/v1/wardrobe/items',
            {'name': 'SJ3 Bottom $i', 'category': 'bottoms', 'color': 'navy'},
            token: token1,
            expectedStatus: 201,
          );
        }

        // 4. Fetch GET /v1/learning/journey/history & /v1/learning/summary
        backendHistory1 = await _getJson(
          rawClient,
          '/v1/learning/journey/history',
          token: token1,
        );
        backendSummary1 = await _getJson(
          rawClient,
          '/v1/learning/summary',
          token: token1,
        );

        expect(backendHistory1['hasHistory'], isTrue);
        expect((backendHistory1['currentWeek'] as Map)['styleScore'], 72);
        expect((backendHistory1['previousWeek'] as Map)['styleScore'], 69);
        expect(
          (backendHistory1['bestHistoricalWeek'] as Map)['styleScore'],
          69,
        );
        expect((backendHistory1['comparison'] as Map)['scoreDelta'], 3);
        expect((backendHistory1['comparison'] as Map)['currentWeekRank'], 1);
        expect((backendHistory1['comparison'] as Map)['totalRankedWeeks'], 2);
        expect(backendSummary1['styleScore'], 72);
        expect(backendSummary1['streak'], greaterThanOrEqualTo(1));

        // Save User 1 session for Flutter HomeScreen
        await AuthSession.saveSession(token1);
      });

      // 6. Open Home and verify Flutter UI renders exact backend values
      await tester.runAsync(() async {
        await tester.pumpWidget(
          MaterialApp(theme: ThemeData.dark(), home: const HomeScreen()),
        );
        await Future<void>.delayed(const Duration(milliseconds: 1200));
      });
      await _pumpUntil(
        tester,
        () => find.byType(ExistingUserStyleJourney).evaluate().isNotEmpty,
        reason: 'ExistingUserStyleJourney after live backend fetch',
      );

      final curWeek = backendHistory1['currentWeek'] as Map<String, dynamic>;
      final prevWeek = backendHistory1['previousWeek'] as Map<String, dynamic>;
      final bestWeek =
          backendHistory1['bestHistoricalWeek'] as Map<String, dynamic>;
      final comp = backendHistory1['comparison'] as Map<String, dynamic>;

      final curScore = curWeek['styleScore'] as int;
      final prevScore = prevWeek['styleScore'] as int;
      final delta = comp['scoreDelta'] as int;
      final rank = comp['currentWeekRank'] as int;
      final totalRanked = comp['totalRankedWeeks'] as int;
      final bestScore = bestWeek['styleScore'] as int;
      final styledDays = curWeek['styledDaysCount'] as int;
      final signals = curWeek['signalsCount'] as int;
      final curRange = _formatShortRange(
        curWeek['weekStart'] as String,
        curWeek['weekEnd'] as String,
      );
      final prevRange = _formatShortRange(
        prevWeek['weekStart'] as String,
        prevWeek['weekEnd'] as String,
      );
      final bestRange = _formatShortRange(
        bestWeek['weekStart'] as String,
        bestWeek['weekEnd'] as String,
      );

      await tester.ensureVisible(find.byType(ExistingUserStyleJourney));
      await tester.pump();

      expect(find.byType(ExistingUserStyleJourney), findsOneWidget);
      expect(find.text('$curScore'), findsWidgets);
      expect(find.text('Week of $curRange'), findsOneWidget);
      expect(find.text('Last week ($prevRange): $prevScore'), findsOneWidget);
      expect(find.text('+$delta pts vs last week'), findsOneWidget);
      expect(find.text('Rank #$rank of $totalRanked weeks'), findsOneWidget);
      expect(
        find.text('Personal best: $bestScore ($bestRange)'),
        findsOneWidget,
      );
      expect(
        find.text(
          '$styledDays/7 styled days • $signals style actions this week',
        ),
        findsOneWidget,
      );

      // 7 & 8. New user with 1 current-week item (established home, NO history)
      // sees empty history state and zero data from User 1
      await tester.runAsync(() async {
        final runId2 = DateTime.now().microsecondsSinceEpoch;
        final reg2 = await _postJson(
          rawClient,
          '/v1/auth/register',
          {
            'email': 'sj3-flutter-u2-$runId2@example.com',
            'password': 'FansivibeSJ3!Pass2',
            'displayName': 'SJ3 New User',
          },
          idempotencyKey: 'sj3-fl-reg2-$runId2',
          expectedStatus: 201,
        );
        token2 = reg2['accessToken'] as String;

        // Add 1 wardrobe item so User 2 enters established Home with empty history
        await _postJson(
          rawClient,
          '/v1/wardrobe/items',
          {'name': 'SJ3 U2 Tee', 'category': 'tops', 'color': 'white'},
          token: token2,
          expectedStatus: 201,
        );

        backendHistory2 = await _getJson(
          rawClient,
          '/v1/learning/journey/history',
          token: token2,
        );
        expect(backendHistory2['hasHistory'], isFalse);
        expect(backendHistory2['previousWeek'], isNull);
        expect(backendHistory2['bestHistoricalWeek'], isNull);

        await AuthSession.saveSession(token2);
      });
      await _pumpUntil(
        tester,
        () => find
            .text(
              'First week in progress — past weeks and personal bests will appear here once recorded.',
            )
            .evaluate()
            .isNotEmpty,
        reason: 'new-user empty history state',
      );

      await tester.ensureVisible(find.byType(ExistingUserStyleJourney));
      await tester.pump();

      expect(find.text('Rank #1 of 1 week'), findsOneWidget);
      expect(
        find.text(
          'First week in progress — past weeks and personal bests will appear here once recorded.',
        ),
        findsOneWidget,
      );
      expect(find.text('+$delta pts vs last week'), findsNothing);

      // 9. Verify auth expiry (logout User 1 -> 401 clears AuthSession)
      // and re-login refresh restores User 1 history
      await tester.runAsync(() async {
        await AuthSession.saveSession(token1);
      });

      final refreshBtn = find.byKey(const Key('style_journey_refresh_button'));
      await _pumpUntil(
        tester,
        () => refreshBtn.evaluate().isNotEmpty,
        reason: 'style journey refresh button for User 1',
      );

      await tester.runAsync(() async {
        // Revoke token1 on the backend
        await _postJson(
          rawClient,
          '/v1/auth/logout',
          {},
          token: token1,
          expectedStatus: 204,
        );
      });

      // Trigger Style Journey refresh with revoked token1
      await tester.ensureVisible(refreshBtn);
      await tester.pump();
      await tester.runAsync(() async {
        await tester.tap(refreshBtn);
        await Future<void>.delayed(const Duration(milliseconds: 800));
      });
      await _pumpUntil(
        tester,
        () => !AuthSession.isAuthenticated,
        reason: 'auth expiry after revoked token refresh',
      );

      expect(AuthSession.isAuthenticated, isFalse);

      // Re-authenticate User 1 and verify recovery
      await tester.runAsync(() async {
        final login1 = await _postJson(rawClient, '/v1/auth/login', {
          'email': email1,
          'password': password1,
        }, expectedStatus: 200);
        final freshToken = login1['accessToken'] as String;
        await AuthSession.saveSession(freshToken);
        rawClient.close();
      });
      await _pumpUntil(
        tester,
        () => find.text('+$delta pts vs last week').evaluate().isNotEmpty,
        reason: 'User 1 history after re-authentication',
      );

      expect(AuthSession.isAuthenticated, isTrue);
      await tester.ensureVisible(find.byType(ExistingUserStyleJourney));
      await tester.pump();
      expect(find.text('+$delta pts vs last week'), findsOneWidget);
    },
  );
}
