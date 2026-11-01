import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/profile/data/user_profile_client.dart';
import 'package:fansivibe/features/profile/data/user_profile_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

void main() {
  group('UserProfileRepository & Hydration Tests', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStorage.init(prefs: await SharedPreferences.getInstance());
      AuthSession.resetForTest();
      clearPendingEphemeralResult();
      await AuthSession.saveSession('test-token-profile');
    });

    tearDown(() async {
      AuthSession.resetForTest();
      await AuthSession.clearSession();
    });

    test('1. Authenticated API hydration loads backend profile authoritatively', () async {
      final mockClient = MockClient((request) async {
        expect(request.url.path, '/v1/users/me');
        expect(request.headers['Authorization'], 'Bearer test-token-profile');
        return http.Response(
          '''{
            "displayName": "Eleanor Vance",
            "styleProfile": {
              "faceShape": "Oval",
              "skinTone": "Warm Medium",
              "bodyType": "Hourglass",
              "styleType": "Minimalist Chic",
              "sourceRunId": "run-xyz-987"
            },
            "preferences": {"preferredOccasions": ["work", "gala"]},
            "settings": {},
            "flags": {},
            "version": 4,
            "memorySummary": {
              "appearanceVerified": true,
              "savedLooksCount": 5,
              "preferredOccasions": ["work", "gala"],
              "appearanceConfidence": 1.0
            }
          }''',
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final client = UserProfileClient(client: mockClient);
      final repo = UserProfileRepositoryImpl(client: client);

      final profile = await repo.fetchProfile();

      expect(profile, isNotNull);
      expect(profile!.displayName, 'Eleanor Vance');
      expect(profile.version, 4);
      expect(profile.styleProfile.faceShape, 'Oval');
      expect(profile.styleProfile.skinTone, 'Warm Medium');
      expect(profile.styleProfile.bodyType, 'Hourglass');
      expect(profile.styleProfile.styleType, 'Minimalist Chic');
      expect(profile.styleProfile.isAssessed, isTrue);

      // Verify sync to LocalStorage cache
      expect(LocalStorage.displayName, 'Eleanor Vance');
      expect(LocalStorage.userProfile['faceShape'], 'Oval');
      expect(LocalStorage.userProfile['skinTone'], 'Warm Medium');
    });

    test('2. Unauthenticated state returns null without calling backend', () async {
      await AuthSession.clearSession();
      int callCount = 0;
      final mockClient = MockClient((request) async {
        callCount++;
        return http.Response('{}', 200);
      });

      final repo = UserProfileRepositoryImpl(
        client: UserProfileClient(client: mockClient),
      );
      final profile = await repo.fetchProfile();

      expect(profile, isNull);
      expect(callCount, 0);
    });

    test('3. Guest appearance data excluded from authenticated hydration (D10 / Batch 1B)', () async {
      stashPendingEphemeralResult(
        feature: 'face_scan',
        snapshot: {'face_shape': 'Heart', 'skin_tone': 'Fair'},
      );

      int callCount = 0;
      final mockClient = MockClient((request) async {
        callCount++;
        return http.Response('{}', 200);
      });

      final repo = UserProfileRepositoryImpl(
        client: UserProfileClient(client: mockClient),
      );

      // In guest mode (with pending ephemeral result and without auth session), fetchProfile returns null
      await AuthSession.clearSession();
      final profile = await repo.fetchProfile();

      expect(profile, isNull);
      expect(callCount, 0);
    });

    test('4. Preserves unsynchronized local user edits over backend data', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          '''{
            "displayName": "Backend Name",
            "styleProfile": {
              "faceShape": "Square",
              "skinTone": "Cool",
              "bodyType": "Rectangle",
              "styleType": "Casual"
            },
            "preferences": {},
            "settings": {},
            "flags": {},
            "version": 2
          }''',
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final repo = UserProfileRepositoryImpl(
        client: UserProfileClient(client: mockClient),
      );

      // User edited skinTone locally before sync
      repo.recordPendingEdit(field: 'skinTone', value: 'Olive');
      expect(repo.pendingEdits['skinTone'], 'Olive');

      final profile = await repo.fetchProfile();

      expect(profile, isNotNull);
      // Backend provided Square, but local pending edit Olive must NOT be discarded
      expect(profile!.styleProfile.faceShape, 'Square');
      expect(profile.styleProfile.skinTone, 'Olive');
    });

    test('5. Stale responses with older generation IDs are discarded', () async {
      // First request takes long, second request is fast
      final mockClient = MockClient((request) async {
        return http.Response(
          '''{
            "displayName": "Fast Response",
            "styleProfile": {"faceShape": "Round"},
            "preferences": {},
            "settings": {},
            "flags": {},
            "version": 2
          }''',
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final repo = UserProfileRepositoryImpl(
        client: UserProfileClient(client: mockClient),
      );

      final p = await repo.fetchProfile(forceRefresh: true);
      expect(p?.displayName, 'Fast Response');
    });

    test('6. Older profile versions do not overwrite newer cached state', () async {
      int requestCount = 0;
      final mockClient = MockClient((request) async {
        requestCount++;
        if (requestCount == 1) {
          return http.Response(
            '''{
              "displayName": "Version 5 User",
              "styleProfile": {"faceShape": "Oval"},
              "preferences": {},
              "settings": {},
              "flags": {},
              "version": 5
            }''',
            200,
            headers: {'content-type': 'application/json'},
          );
        } else {
          return http.Response(
            '''{
              "displayName": "Stale Version 3 User",
              "styleProfile": {"faceShape": "Round"},
              "preferences": {},
              "settings": {},
              "flags": {},
              "version": 3
            }''',
            200,
            headers: {'content-type': 'application/json'},
          );
        }
      });

      final repo = UserProfileRepositoryImpl(
        client: UserProfileClient(client: mockClient),
      );

      final v5 = await repo.fetchProfile(forceRefresh: true);
      expect(v5?.version, 5);
      expect(v5?.displayName, 'Version 5 User');

      // Attempt to load stale version 3
      final rejected = await repo.fetchProfile(forceRefresh: true);
      // Older remote version 3 is rejected, existing version 5 is retained
      expect(rejected?.version, 5);
      expect(rejected?.displayName, 'Version 5 User');
    });

    test('7. Cache fallback on network failure preserves stored data', () async {
      LocalStorage.displayName = 'Cached User';
      LocalStorage.userProfile = {'faceShape': 'Diamond', 'bodyType': 'Athletic'};

      final mockClient = MockClient((request) async {
        return http.Response('Internal Server Error', 500);
      });

      final repo = UserProfileRepositoryImpl(
        client: UserProfileClient(client: mockClient),
      );

      final fallback = await repo.fetchProfile();

      expect(fallback, isNotNull);
      expect(fallback!.displayName, 'Cached User');
      expect(fallback.styleProfile.faceShape, 'Diamond');
      expect(fallback.styleProfile.bodyType, 'Athletic');
    });

    test('8. Empty profile handling without mock fabrication', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          '''{
            "displayName": "Blank User",
            "styleProfile": {},
            "preferences": {},
            "settings": {},
            "flags": {},
            "version": 1
          }''',
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final repo = UserProfileRepositoryImpl(
        client: UserProfileClient(client: mockClient),
      );

      final blank = await repo.fetchProfile();

      expect(blank, isNotNull);
      expect(blank!.displayName, 'Blank User');
      expect(blank.styleProfile.faceShape, isNull);
      expect(blank.styleProfile.skinTone, isNull);
      expect(blank.styleProfile.bodyType, isNull);
      expect(blank.styleProfile.styleType, isNull);
      expect(blank.styleProfile.isAssessed, isFalse);
    });

    test('9. Provenance preservation during hydration and serialization', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          '''{
            "displayName": "Verified User",
            "styleProfile": {
              "faceShape": "Oval",
              "_provenance_faceShape": {
                "value": "Oval",
                "source": "face_scan",
                "confidence": 0.95,
                "confirmed_by_user": true
              }
            },
            "preferences": {},
            "settings": {},
            "flags": {},
            "version": 2
          }''',
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final repo = UserProfileRepositoryImpl(
        client: UserProfileClient(client: mockClient),
      );

      final profile = await repo.fetchProfile();

      expect(profile, isNotNull);
      expect(profile!.styleProfile.extra['_provenance_faceShape'], isNotNull);
      expect(
        profile.styleProfile.extra['_provenance_faceShape']['confirmed_by_user'],
        isTrue,
      );

      // Verify LocalStorage cache also preserved provenance
      expect(LocalStorage.userProfile['_provenance_faceShape'], isNotNull);
    });
  });
}
