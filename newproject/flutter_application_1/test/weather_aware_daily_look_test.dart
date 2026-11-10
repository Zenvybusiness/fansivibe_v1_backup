import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/home/data/home_mock_data.dart';
import 'package:fansivibe/features/home/data/today_look_client.dart';
import 'package:fansivibe/features/home/data/today_look_models.dart';
import 'package:fansivibe/features/home/data/today_look_repository.dart';
import 'package:fansivibe/features/home/presentation/daily_outfit_screen.dart';
import 'package:fansivibe/features/home/presentation/widgets/city_selection_sheet.dart';
import 'package:fansivibe/features/home/presentation/widgets/existing_user_home_widgets.dart';
import 'package:fansivibe/features/profile/data/user_profile_models.dart';
import 'package:fansivibe/features/profile/data/user_profile_repository.dart';
import 'package:fansivibe/features/profile/presentation/settings_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

const String _uuid1 = '78ff3686-c950-4cd6-84c3-7e18d6634dfa';
const String _uuid2 = '4412f646-56a9-4afa-8717-b330da03b3d0';

Map<String, dynamic> _lookWire({
  String title = 'Evening Polish',
  Map<String, dynamic>? weather,
}) => {
  'title': title,
  'occasion': 'work',
  'description': 'Layered neutrals built from owned staples.',
  if (weather != null) 'weather': weather,
  'matchScore': 84,
  'styleScore': 84,
  'components': [
    {
      'id': _uuid1,
      'name': 'Camel Overcoat',
      'category': 'outerwear',
      'color': 'Camel',
      'material': 'Wool',
    },
    {'id': _uuid2, 'name': 'Grey Knit', 'category': 'tops', 'color': 'Grey'},
  ],
  'reasons': ['Picked for a work occasion'],
  'wardrobeContext': {'totalItems': 2, 'matchingItems': 2},
  'alternatives': <Map<String, dynamic>>[],
  'selectedItemIds': [_uuid1, _uuid2],
};

/// Mirrors the actual backend `TodayLookWeather` wire shape: camelCase with
/// absent optionals omitted (`response_model_exclude_none=True`).
Map<String, dynamic> _weatherWire({
  bool applied = true,
  String? condition = 'Moderate rain',
  String? conditionCode = 'rain',
  double? temperatureC = 14.2,
  double? temperatureF = 57.6,
  double? apparentTemperatureC = 13.1,
  double? apparentTemperatureF = 55.6,
  double? precipitationProbability = 80,
  double? precipitationMm = 2.4,
  double? windSpeedKmh = 18,
  bool? isRaining = true,
  String? forecastTimestamp,
  String? city = 'Seattle',
  String? summary = '14°C • Moderate rain in Seattle',
  bool fallback = false,
}) {
  final timestamp =
      forecastTimestamp ??
      DateTime.now()
          .toUtc()
          .subtract(const Duration(minutes: 10))
          .toIso8601String();
  return {
    'applied': applied,
    if (condition != null) 'condition': condition,
    if (conditionCode != null) 'conditionCode': conditionCode,
    if (temperatureC != null) 'temperatureC': temperatureC,
    if (temperatureF != null) 'temperatureF': temperatureF,
    if (apparentTemperatureC != null)
      'apparentTemperatureC': apparentTemperatureC,
    if (apparentTemperatureF != null)
      'apparentTemperatureF': apparentTemperatureF,
    if (precipitationProbability != null)
      'precipitationProbability': precipitationProbability,
    if (precipitationMm != null) 'precipitationMm': precipitationMm,
    if (windSpeedKmh != null) 'windSpeedKmh': windSpeedKmh,
    if (isRaining != null) 'isRaining': isRaining,
    'forecastTimestamp': timestamp,
    if (city != null) 'city': city,
    if (summary != null) 'summary': summary,
    'fallback': fallback,
  };
}

typedef _LookHandler = Future<TodayLookResult> Function(int call, String? city);

class _FakeLookRepository implements TodayLookRepository {
  _FakeLookRepository(this.handler);

  final _LookHandler handler;
  int calls = 0;
  String? lastCity;
  double? lastLatitude;
  double? lastLongitude;

  @override
  Future<TodayLookResult> getTodayLook({
    String? city,
    double? latitude,
    double? longitude,
  }) {
    calls += 1;
    lastCity = city;
    lastLatitude = latitude;
    lastLongitude = longitude;
    return handler(calls, city);
  }

  @override
  Future<TodayLookResult> regenerateTodayLook({
    String? seed,
    String? city,
    double? latitude,
    double? longitude,
  }) async => const TodayLookResult.noneAvailable();

  @override
  Future<SavedTodayLook?> saveTodayLook({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async => null;
}

class _FakeProfileRepository implements UserProfileRepository {
  _FakeProfileRepository({this.profile, this.failUpdates = false});

  UserProfile? profile;
  bool failUpdates;
  final List<Map<String, dynamic>> settingsUpdates = [];
  final Map<String, dynamic> _pendingEdits = {};

  @override
  UserProfile? get cachedProfile => profile;

  @override
  Future<UserProfile?> fetchProfile({bool forceRefresh = false}) async =>
      profile;

  @override
  void recordPendingEdit({required String field, required dynamic value}) {
    _pendingEdits[field] = value;
  }

  @override
  void clearPendingEdits() => _pendingEdits.clear();

  @override
  Map<String, dynamic> get pendingEdits => Map.unmodifiable(_pendingEdits);

  @override
  void clearCache() => profile = null;

  @override
  Future<UserProfile?> updateStyleType(String styleType) async => profile;

  @override
  Future<UserProfile?> updateSettings(
    Map<String, dynamic> settingsPatch,
  ) async {
    if (failUpdates) return null;
    settingsUpdates.add(settingsPatch);
    final merged = Map<String, dynamic>.from(profile?.settings ?? {})
      ..addAll(settingsPatch);
    profile =
        (profile ??
                UserProfile(
                  displayName: 'Test User',
                  styleProfile: const UserStyleProfile(),
                  version: 1,
                ))
            .copyWith(settings: merged);
    return profile;
  }

  @override
  Future<UserProfile?> updatePreferredOccasions(List<String> occasions) async =>
      profile;
}

Widget _dailyApp(TodayLookRepository repository, {TextScaler? textScaler}) {
  return MaterialApp(
    theme: ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: FansivibeColors.background,
      colorScheme: const ColorScheme.dark(surface: FansivibeColors.surface),
    ),
    home: Builder(
      builder: (context) {
        final screen = DailyOutfitScreen(todayLookRepository: repository);
        if (textScaler == null) return screen;
        return MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: textScaler),
          child: screen,
        );
      },
    ),
  );
}

Future<void> _pumpDaily(
  WidgetTester tester,
  TodayLookRepository repository, {
  TextScaler? textScaler,
}) async {
  await tester.pumpWidget(_dailyApp(repository, textScaler: textScaler));
  await tester.pumpAndSettle();
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    LocalStorage.savedLocally = false;
  });

  group('A. TodayLookWeather model', () {
    test('deserializes the full backend weather object', () {
      final look = TodayLook.fromJson(_lookWire(weather: _weatherWire()));
      final weather = look.weather!;

      expect(weather.applied, isTrue);
      expect(weather.condition, 'Moderate rain');
      expect(weather.conditionCode, 'rain');
      expect(weather.temperatureC, 14.2);
      expect(weather.temperatureF, 57.6);
      expect(weather.apparentTemperatureC, 13.1);
      expect(weather.apparentTemperatureF, 55.6);
      expect(weather.precipitationProbability, 80);
      expect(weather.precipitationMm, 2.4);
      expect(weather.windSpeedKmh, 18);
      expect(weather.isRaining, isTrue);
      expect(weather.forecastTimestamp, isNotNull);
      expect(weather.city, 'Seattle');
      expect(weather.summary, '14°C • Moderate rain in Seattle');
      expect(weather.fallback, isFalse);
      expect(look.snapshot['weather'], isNotNull);
    });

    test('weather absent is normal and preserves the look', () {
      final look = TodayLook.fromJson(_lookWire());

      expect(look.weather, isNull);
      expect(look.title, 'Evening Polish');
      expect(look.components, hasLength(2));
    });

    test('individual weather fields may be absent', () {
      final look = TodayLook.fromJson(
        _lookWire(weather: {'applied': true, 'city': 'Oslo'}),
      );
      final weather = look.weather!;

      expect(weather.applied, isTrue);
      expect(weather.city, 'Oslo');
      expect(weather.condition, isNull);
      expect(weather.conditionCode, isNull);
      expect(weather.temperatureC, isNull);
      expect(weather.temperatureF, isNull);
      expect(weather.precipitationProbability, isNull);
      expect(weather.summary, isNull);
      expect(weather.forecastTimestamp, isNull);
      expect(weather.fallback, isFalse);
    });

    test('missing applied is not an unsupported influence claim', () {
      final look = TodayLook.fromJson(
        _lookWire(weather: {'city': 'Oslo', 'temperatureC': 4.0}),
      );

      expect(look.weather!.applied, isFalse);
    });
  });

  group('B. client city parameters', () {
    test('GET propagates city and omits absent city', () async {
      late Uri seen;
      final client = TodayLookClient(
        client: MockClient((request) async {
          seen = request.url;
          return http.Response(jsonEncode(_lookWire()), 200);
        }),
      );

      await client.getTodayLook(city: 'Seattle');
      expect(seen.queryParameters, {'city': 'Seattle'});

      await client.getTodayLook();
      expect(seen.queryParameters, isEmpty);
    });

    test('POST propagates seed, city, and coarse coordinates', () async {
      late Uri seen;
      final client = TodayLookClient(
        client: MockClient((request) async {
          seen = request.url;
          return http.Response(jsonEncode(_lookWire()), 200);
        }),
      );

      await client.regenerateTodayLook(
        seed: 'look-2',
        city: 'Tokyo',
        latitude: 35.68,
        longitude: 139.69,
      );

      expect(seen.queryParameters, {
        'seed': 'look-2',
        'city': 'Tokyo',
        'lat': '35.68',
        'lon': '139.69',
      });
    });
  });

  group('C. repository city boundary', () {
    Future<Uri> capture(
      TodayLookRepositoryImpl repository, {
      String? city,
    }) async {
      final result = await repository.getTodayLook(city: city);
      expect(result.available, isTrue);
      return _capturedUri!;
    }

    test('guest stored city travels as a query parameter', () async {
      LocalStorage.savedLocally = true;
      LocalStorage.weatherCity = 'Paris';
      final repository = TodayLookRepositoryImpl(
        client: TodayLookClient(
          client: MockClient((request) async {
            _capturedUri = request.url;
            return http.Response(jsonEncode(_lookWire()), 200);
          }),
        ),
      );

      final uri = await capture(repository);

      expect(uri.queryParameters['city'], 'Paris');
    });

    test('authenticated request does not leak a device-local city', () async {
      await AuthSession.saveSession('tok-test');
      LocalStorage.weatherCity = 'Paris';
      final repository = TodayLookRepositoryImpl(
        client: TodayLookClient(
          client: MockClient((request) async {
            _capturedUri = request.url;
            return http.Response(jsonEncode(_lookWire()), 200);
          }),
        ),
      );

      final uri = await capture(repository);

      expect(uri.queryParameters.containsKey('city'), isFalse);
    });

    test(
      'explicit city still propagates for an authenticated request',
      () async {
        await AuthSession.saveSession('tok-test');
        final repository = TodayLookRepositoryImpl(
          client: TodayLookClient(
            client: MockClient((request) async {
              _capturedUri = request.url;
              return http.Response(jsonEncode(_lookWire()), 200);
            }),
          ),
        );

        final uri = await capture(repository, city: 'Tokyo');

        expect(uri.queryParameters['city'], 'Tokyo');
      },
    );

    test('missing city sends no city parameter', () async {
      LocalStorage.savedLocally = true;
      final repository = TodayLookRepositoryImpl(
        client: TodayLookClient(
          client: MockClient((request) async {
            _capturedUri = request.url;
            return http.Response(jsonEncode(_lookWire()), 200);
          }),
        ),
      );

      final uri = await capture(repository);

      expect(uri.queryParameters.containsKey('city'), isFalse);
    });

    test('weather city getter reads backend-synced settings', () {
      LocalStorage.settings = {
        'weather_location': {'city': 'Berlin'},
      };

      expect(LocalStorage.weatherCity, 'Berlin');
    });
  });

  group('D. DailyOutfitScreen weather UI', () {
    testWidgets('weather available shows summary, rain, and influence', (
      tester,
    ) async {
      final repo = _FakeLookRepository(
        (_, __) async => TodayLookResult.available(
          TodayLook.fromJson(_lookWire(weather: _weatherWire())),
        ),
      );

      await _pumpDaily(tester, repo);

      expect(find.text('WEATHER CONTEXT'), findsOneWidget);
      expect(find.text('14°C • Moderate rain in Seattle'), findsOneWidget);
      expect(find.text('80% chance of rain'), findsOneWidget);
      expect(
        find.text('Weather considered in today\'s recommendation.'),
        findsOneWidget,
      );
      expect(find.textContaining('Forecast updated'), findsOneWidget);
      expect(find.text('Evening Polish'), findsOneWidget);
    });

    testWidgets('applied false shows weather without an influence claim', (
      tester,
    ) async {
      final repo = _FakeLookRepository(
        (_, __) async => TodayLookResult.available(
          TodayLook.fromJson(_lookWire(weather: _weatherWire(applied: false))),
        ),
      );

      await _pumpDaily(tester, repo);

      expect(find.text('14°C • Moderate rain in Seattle'), findsOneWidget);
      expect(
        find.text('Weather considered in today\'s recommendation.'),
        findsNothing,
      );
    });

    testWidgets(
      'weather unavailable keeps the normal look and no placeholders',
      (tester) async {
        LocalStorage.weatherCity = 'Seattle';
        final repo = _FakeLookRepository(
          (_, __) async =>
              TodayLookResult.available(TodayLook.fromJson(_lookWire())),
        );

        await _pumpDaily(tester, repo);

        expect(find.text('WEATHER CONTEXT'), findsNothing);
        expect(find.textContaining('°C'), findsNothing);
        expect(find.textContaining('chance of rain'), findsNothing);
        expect(
          find.textContaining('No city selected for weather'),
          findsNothing,
        );
        expect(find.text('Evening Polish'), findsOneWidget);
        expect(find.text('The Ensemble'), findsOneWidget);
      },
    );

    testWidgets('no city selected shows a settings prompt, not an error', (
      tester,
    ) async {
      final repo = _FakeLookRepository(
        (_, __) async =>
            TodayLookResult.available(TodayLook.fromJson(_lookWire())),
      );

      await _pumpDaily(tester, repo);

      expect(
        find.textContaining('No city selected for weather'),
        findsOneWidget,
      );
      expect(find.text('Choose City'), findsOneWidget);
      expect(find.text('Try Again'), findsNothing);
      expect(find.text('Evening Polish'), findsOneWidget);
    });

    testWidgets('missing temperature and precipitation render safely', (
      tester,
    ) async {
      final repo = _FakeLookRepository(
        (_, __) async => TodayLookResult.available(
          TodayLook.fromJson(
            _lookWire(
              weather: _weatherWire(
                condition: 'Cloudy',
                conditionCode: 'cloudy',
                temperatureC: null,
                temperatureF: null,
                apparentTemperatureC: null,
                apparentTemperatureF: null,
                precipitationProbability: null,
                precipitationMm: null,
                isRaining: false,
                city: 'Oslo',
                summary: null,
              ),
            ),
          ),
        ),
      );

      await _pumpDaily(tester, repo);

      expect(find.text('Cloudy in Oslo'), findsOneWidget);
      expect(find.textContaining('°C'), findsNothing);
      expect(find.textContaining('°F'), findsNothing);
      expect(find.textContaining('chance of rain'), findsNothing);
      expect(
        find.text('Weather considered in today\'s recommendation.'),
        findsOneWidget,
      );
    });

    testWidgets('empty weather object does not render placeholder UI', (
      tester,
    ) async {
      LocalStorage.weatherCity = 'Seattle';
      final repo = _FakeLookRepository(
        (_, __) async => TodayLookResult.available(
          TodayLook.fromJson(_lookWire(weather: <String, dynamic>{})),
        ),
      );

      await _pumpDaily(tester, repo);

      expect(find.text('WEATHER CONTEXT'), findsNothing);
      expect(find.textContaining('No city selected for weather'), findsNothing);
    });

    testWidgets('loading state renders the existing indicator', (tester) async {
      final completer = Completer<TodayLookResult>();
      final repo = _FakeLookRepository((_, __) => completer.future);

      await tester.pumpWidget(_dailyApp(repo));
      await tester.pump();

      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      completer.complete(
        TodayLookResult.available(TodayLook.fromJson(_lookWire())),
      );
      await tester.pumpAndSettle();
      expect(find.text('Evening Polish'), findsOneWidget);
    });

    testWidgets('API error renders the existing retry state', (tester) async {
      final repo = _FakeLookRepository(
        (_, __) async =>
            const TodayLookResult.failure(TodayLookFailure.networkError),
      );

      await _pumpDaily(tester, repo);

      expect(find.text('Couldn\'t load today\'s look'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);
      expect(find.text('WEATHER CONTEXT'), findsNothing);
    });

    testWidgets('location change drops stale weather and refetches', (
      tester,
    ) async {
      final second = Completer<TodayLookResult>();
      final repo = _FakeLookRepository((call, __) {
        if (call == 1) {
          return Future.value(
            TodayLookResult.available(
              TodayLook.fromJson(_lookWire(weather: _weatherWire())),
            ),
          );
        }
        return second.future;
      });

      await _pumpDaily(tester, repo);
      expect(find.text('14°C • Moderate rain in Seattle'), findsOneWidget);

      LocalStorage.notifyWeatherLocationChanged();
      await tester.pump();

      expect(repo.calls, 2);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(find.text('14°C • Moderate rain in Seattle'), findsNothing);

      second.complete(
        TodayLookResult.available(
          TodayLook.fromJson(
            _lookWire(
              title: 'Fresh City Look',
              weather: _weatherWire(
                condition: 'Clear sky',
                conditionCode: 'clear',
                temperatureC: 22,
                temperatureF: 71.6,
                precipitationProbability: 0,
                isRaining: false,
                city: 'Tokyo',
                summary: '22°C • Clear sky in Tokyo',
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Fresh City Look'), findsOneWidget);
      expect(find.text('22°C • Clear sky in Tokyo'), findsOneWidget);
      expect(find.text('14°C • Moderate rain in Seattle'), findsNothing);
    });

    testWidgets('long city name and scaled text do not overflow at 320px', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(320, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final longCity =
          'Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch';
      final repo = _FakeLookRepository(
        (_, __) async => TodayLookResult.available(
          TodayLook.fromJson(
            _lookWire(
              weather: _weatherWire(
                city: longCity,
                summary:
                    '14°C • Moderate rain in $longCity with a long advisory line',
              ),
            ),
          ),
        ),
      );

      await _pumpDaily(tester, repo, textScaler: const TextScaler.linear(1.3));

      expect(find.text('WEATHER CONTEXT'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group('E. Home hero weather display', () {
    testWidgets('weather summary replaces the static time label', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: ExistingUserHeroCard(
                data: TodaysLookData.mock.copyWith(
                  weather: '14°C • Moderate rain in Seattle',
                ),
              ),
            ),
          ),
        ),
      );

      expect(find.text('14°C • Moderate rain in Seattle'), findsOneWidget);
      expect(find.text('08:00 AM'), findsNothing);
    });

    testWidgets('empty weather keeps the standard hero header', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: ExistingUserHeroCard(
                data: TodaysLookData.mock.copyWith(weather: ''),
              ),
            ),
          ),
        ),
      );

      expect(find.text('08:00 AM'), findsOneWidget);
      expect(find.textContaining('Moderate rain'), findsNothing);
    });
  });

  group('F. Settings city selection', () {
    testWidgets('authenticated update sends only weather_location and '
        'preserves unrelated settings', (tester) async {
      await AuthSession.saveSession('tok-test');
      final repo = _FakeProfileRepository(
        profile: UserProfile(
          displayName: 'Test User',
          styleProfile: const UserStyleProfile(),
          settings: const {
            'notifications': false,
            'soundEffects': true,
            'weather_location': {'city': 'Paris'},
          },
          version: 1,
        ),
      );
      final before = LocalStorage.weatherLocationVersion.value;

      await tester.pumpWidget(
        MaterialApp(home: SettingsScreen(userProfileRepository: repo)),
      );
      await tester.pumpAndSettle();
      expect(find.text('Paris'), findsOneWidget);

      await tester.ensureVisible(find.text('Weather Location'));
      await tester.tap(find.text('Weather Location'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Tokyo'));
      await tester.pumpAndSettle();

      expect(repo.settingsUpdates, hasLength(1));
      expect(repo.settingsUpdates.single, {
        'weather_location': {'city': 'Tokyo'},
      });
      expect(repo.cachedProfile?.settings['notifications'], isFalse);
      expect(repo.cachedProfile?.settings['soundEffects'], isTrue);
      expect(LocalStorage.weatherCity, 'Tokyo');
      expect(LocalStorage.settings['weather_location'], {'city': 'Tokyo'});
      expect(LocalStorage.weatherLocationVersion.value, before + 1);
      expect(find.text('Weather city updated to Tokyo'), findsOneWidget);
    });

    testWidgets('authenticated failure leaves the saved city unchanged', (
      tester,
    ) async {
      await AuthSession.saveSession('tok-test');
      final repo = _FakeProfileRepository(
        profile: UserProfile(
          displayName: 'Test User',
          styleProfile: const UserStyleProfile(),
          settings: const {
            'notifications': true,
            'weather_location': {'city': 'Paris'},
          },
          version: 1,
        ),
        failUpdates: true,
      );
      final before = LocalStorage.weatherLocationVersion.value;

      await tester.pumpWidget(
        MaterialApp(home: SettingsScreen(userProfileRepository: repo)),
      );
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Weather Location'));
      await tester.tap(find.text('Weather Location'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Tokyo'));
      await tester.pumpAndSettle();

      expect(repo.settingsUpdates, isEmpty);
      expect(repo.cachedProfile?.settings['weather_location'], {
        'city': 'Paris',
      });
      expect(find.text('Paris'), findsOneWidget);
      expect(LocalStorage.weatherLocationVersion.value, before);
      expect(
        find.text('Failed to update weather city. Please try again.'),
        findsOneWidget,
      );
    });

    testWidgets('guest city persists locally without a backend update', (
      tester,
    ) async {
      await AuthSession.clearSession();
      LocalStorage.savedLocally = true;
      expect(isGuestUser, isTrue);
      final repo = _FakeProfileRepository();
      final before = LocalStorage.weatherLocationVersion.value;

      await tester.pumpWidget(
        MaterialApp(home: SettingsScreen(userProfileRepository: repo)),
      );
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Weather Location'));
      await tester.tap(find.text('Weather Location'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Seattle'));
      await tester.pumpAndSettle();

      expect(repo.settingsUpdates, isEmpty);
      expect(LocalStorage.weatherCity, 'Seattle');
      expect(LocalStorage.settings['weather_location'], {'city': 'Seattle'});
      expect(LocalStorage.settings['weatherCity'], 'Seattle');
      expect(LocalStorage.weatherLocationVersion.value, before + 1);
      expect(find.text('Weather city saved on this device'), findsOneWidget);
    });

    testWidgets('city sheet only offers backend-resolvable cities', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => TextButton(
                onPressed: () => showCitySelectionSheet(context),
                child: const Text('Open'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();

      expect(find.text('SUPPORTED CITIES'), findsOneWidget);
      expect(find.text('Seattle'), findsOneWidget);
      expect(find.text('Set'), findsNothing);
    });
  });
}

/// Captured URL shared by the repository capture helper above.
Uri? _capturedUri;
