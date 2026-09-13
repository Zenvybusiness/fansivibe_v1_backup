import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/assistant/presentation/assistant_routes.dart';

void main() {
  group('AssistantRoutes.routeFor — known actions resolve', () {
    test('open_* actions resolve to their destinations', () {
      expect(AssistantRoutes.routeFor('open_outfit'), RouteNames.buildOutfit);
      expect(AssistantRoutes.routeFor('open_hairstyle'), RouteNames.hairstyle);
      expect(AssistantRoutes.routeFor('open_grooming'), RouteNames.grooming);
      expect(AssistantRoutes.routeFor('open_wardrobe'), RouteNames.wardrobe);
      expect(AssistantRoutes.routeFor('open_stylist'), RouteNames.stylist);
      expect(AssistantRoutes.routeFor('open_daily'), RouteNames.dailyOutfit);
      expect(AssistantRoutes.routeFor('open_discover'), RouteNames.discover);
    });

    test('bare action names resolve to their destinations', () {
      expect(AssistantRoutes.routeFor('wardrobe'), RouteNames.wardrobe);
      expect(AssistantRoutes.routeFor('stylist'), RouteNames.stylist);
      expect(AssistantRoutes.routeFor('discover'), RouteNames.discover);
      expect(AssistantRoutes.routeFor('home'), RouteNames.home);
      expect(AssistantRoutes.routeFor('profile'), RouteNames.profile);
      expect(AssistantRoutes.routeFor('daily-outfit'), RouteNames.dailyOutfit);
      expect(AssistantRoutes.routeFor('hairstyle'), RouteNames.hairstyle);
      expect(AssistantRoutes.routeFor('grooming'), RouteNames.grooming);
      expect(AssistantRoutes.routeFor('build-outfit'), RouteNames.buildOutfit);
    });
  });

  group('AssistantRoutes.routeFor — unsupported actions stay unresolved', () {
    test('unknown action returns null (never an unrelated screen)', () {
      expect(AssistantRoutes.routeFor('open_events'), isNull);
      expect(AssistantRoutes.routeFor('open_profile'), isNull);
      expect(AssistantRoutes.routeFor('do_something_new'), isNull);
    });

    test('malformed actions return null', () {
      expect(AssistantRoutes.routeFor('OPEN_OUTFIT'), isNull);
      expect(AssistantRoutes.routeFor(' open_outfit'), isNull);
      expect(AssistantRoutes.routeFor('open_outfit '), isNull);
      expect(AssistantRoutes.routeFor('open-outfit'), isNull);
    });

    test('null and empty actions return null', () {
      expect(AssistantRoutes.routeFor(null), isNull);
      expect(AssistantRoutes.routeFor(''), isNull);
    });
  });

  group('AssistantRoutes.isSupported', () {
    test('known actions are supported', () {
      expect(AssistantRoutes.isSupported('open_outfit'), isTrue);
      expect(AssistantRoutes.isSupported('stylist'), isTrue);
      expect(AssistantRoutes.isSupported('daily-outfit'), isTrue);
    });

    test('unknown, malformed, null, and empty actions are unsupported', () {
      expect(AssistantRoutes.isSupported('open_events'), isFalse);
      expect(AssistantRoutes.isSupported('OPEN_OUTFIT'), isFalse);
      expect(AssistantRoutes.isSupported(null), isFalse);
      expect(AssistantRoutes.isSupported(''), isFalse);
    });
  });
}
