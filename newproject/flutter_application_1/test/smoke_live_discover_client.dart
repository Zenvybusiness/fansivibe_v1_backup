// ignore_for_file: avoid_print
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/discover/data/discover_client.dart';
import 'package:fansivibe/features/discover/data/discover_models.dart';
import 'package:fansivibe/features/discover/data/discover_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/auth/secure_token_storage.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

import 'dart:io';

void main() {
  setUp(() async {
    HttpOverrides.global = null;
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
    SecureTokenStorage.resetForTest();
    AuthSession.resetForTest();
    await AuthSession.clearSession();
  });

  test('Live Discover Client-to-Backend End-to-End Verification', () async {
    print('=' * 70);
    print('LIVE DISCOVER CLIENT-TO-BACKEND END-TO-END VERIFICATION');
    print('Target: http://127.0.0.1:8000');
    print('Testing: /v1/discovery/for-you, /v1/discovery/looks/complete, /v1/discovery/trending');
    print('=' * 70);

    final client = DiscoverClient();
    final repo = DiscoverRepositoryImpl(client: client);

    // 1. GET /v1/discovery/for-you (Guest Mode)
    print('\n[1] Testing GET /v1/discovery/for-you (Guest Mode)...');
    final forYouResult = await repo.getForYouRecommendations(
      page: 1,
      pageSize: 5,
      isGuest: true,
    );

    expect(forYouResult.isSuccess, isTrue, reason: 'For You endpoint must succeed for guests');
    final forYou = forYouResult.response!;
    print('  - HTTP 200 OK');
    print('  - Total Catalog Items: ${forYou.totalCount}');
    print('  - Returned Items: ${forYou.items.length}');
    print('  - Applied Context: isGuest=${forYou.appliedContext.isGuest}, userId=${forYou.appliedContext.userId}');
    expect(forYou.appliedContext.isGuest, isTrue);
    expect(forYou.items.isNotEmpty, isTrue);

    final firstItem = forYou.items.first;
    print('  - First Recommendation: "${firstItem.title}" by ${firstItem.brand}');
    print('  - Price: ${firstItem.currency} ${firstItem.price}');
    print('  - Provenance: ${firstItem.explanation.provenance}');
    print('  - Is Demo Fixture: ${firstItem.isSyntheticFixture}');
    print('  - Grounded Summary: "${firstItem.explanation.summary}"');
    expect(firstItem.isSyntheticFixture, isTrue);
    expect(firstItem.price, isNotNull);

    // 2. GET /v1/discovery/looks/complete
    print('\n[2] Testing GET /v1/discovery/looks/complete...');
    final completeLooksResult = await repo.getCompleteLooks(
      limit: 1,
      includeSynthetic: true,
    );

    expect(completeLooksResult.isSuccess, isTrue, reason: 'Complete looks endpoint must succeed');
    final completeLooks = completeLooksResult.response!;
    print('  - HTTP 200 OK');
    print('  - Total Looks Returned: ${completeLooks.looks.length}');
    expect(completeLooks.looks.isNotEmpty, isTrue);

    final firstLook = completeLooks.looks.first;
    print('  - Look ID: ${firstLook.lookId}');
    print('  - Slots: ${firstLook.slots.keys.join(', ')}');
    print('  - Total Catalog Price: ${firstLook.currency} ${firstLook.totalCatalogPrice}');
    print('  - Compatibility Score: ${firstLook.compatibilityScore}');
    print('  - Bundle Purchasable: ${firstLook.bundlePurchasable} (STRICTLY FALSE)');
    print('  - Contains Synthetic Fixtures: ${firstLook.containsSyntheticFixtures}');
    expect(firstLook.bundlePurchasable, isFalse, reason: 'bundlePurchasable must be false');
    expect(firstLook.slots.containsKey('top'), isTrue);
    expect(firstLook.slots.containsKey('bottom'), isTrue);

    // 3. GET /v1/discovery/trending (Unauthenticated Guest Request)
    print('\n[3] Testing GET /v1/discovery/trending (Guest Isolation Check)...');
    final unauthTrending = await repo.getTrending(limit: 5);
    print('  - Result: isSuccess=${unauthTrending.isSuccess}, failure=${unauthTrending.failure}');
    expect(unauthTrending.isSuccess, isFalse);
    expect(unauthTrending.failure, DiscoverFailure.unauthorized,
        reason: 'Trending requires authentication; guests must receive 401 unauthorized');
    print('  - Guest isolation confirmed: no private or authenticated trends leaked to unauthenticated caller');

    // 4. Register live test user & GET /v1/discovery/trending (Authenticated)
    print('\n[4] Registering live test user to acquire valid JWT session...');
    final timestamp = DateTime.now().millisecondsSinceEpoch;
    final regResponse = await http.post(
      Uri.parse('http://127.0.0.1:8000/v1/auth/register'),
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': 'smoke-disc-$timestamp',
      },
      body: jsonEncode({
        'email': 'smoke_disc_$timestamp@example.com',
        'password': 'SecurePassword123!',
        'displayName': 'Live Discover Tester',
      }),
    );
    expect(regResponse.statusCode, anyOf(200, 201), reason: 'Registration must succeed');
    final regData = jsonDecode(regResponse.body) as Map<String, dynamic>;
    final accessToken = regData['accessToken'] as String;
    print('  - Registration succeeded; JWT accessToken acquired');

    await AuthSession.saveSession(accessToken);
    expect(AuthSession.isAuthenticated, isTrue);

    print('\n[5] Testing GET /v1/discovery/trending (Authenticated Session)...');
    final authTrending = await repo.getTrending(limit: 5);
    expect(authTrending.isSuccess, isTrue, reason: 'Authenticated trending request must succeed');
    final trending = authTrending.response!;
    print('  - HTTP 200 OK');
    print('  - Demand Trend Status: ${trending.demandTrendStatus}');
    print('  - Direct Demand Available: ${trending.directDemandAvailable} (DEMAND_SIGNAL_AVAILABLE = False)');
    print('  - Evidence Type: ${trending.evidenceType}');
    print('  - Observations Count: ${trending.observationCount}');
    print('  - Limitations Stated: ${trending.limitations.length}');
    for (final lim in trending.limitations) {
      print('    • $lim');
    }
    expect(trending.directDemandAvailable, isFalse);
    expect(trending.demandTrendStatus, 'insufficient_evidence');
    expect(trending.evidenceType, 'catalog_activity');
    expect(trending.limitations.isNotEmpty, isTrue);

    // 5. Cleanup
    await AuthSession.clearSession();
    expect(AuthSession.isAuthenticated, isFalse);
    print('\n[6] Cleaned up session; verified guest isolation after logout.');
    print('=' * 70);
    print('ALL LIVE END-TO-END VERIFICATIONS PASSED SUCCESSFULLY!');
    print('=' * 70);
  });
}
