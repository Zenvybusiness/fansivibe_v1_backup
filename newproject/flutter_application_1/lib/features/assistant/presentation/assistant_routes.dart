import 'package:fansivibe/app/router/route_names.dart';

/// Maps assistant route requests to the app's own route names.
///
/// The AI never navigates by itself — it returns a route identifier and the
/// client executes it through the existing go_router.
abstract final class AssistantRoutes {
  static String routeFor(String? action) {
    return switch (action) {
      'open_outfit' => RouteNames.buildOutfit,
      'open_hairstyle' => RouteNames.hairstyle,
      'open_grooming' => RouteNames.grooming,
      'open_wardrobe' => RouteNames.wardrobe,
      'open_stylist' => RouteNames.stylist,
      'open_daily' => RouteNames.dailyOutfit,
      'open_discover' => RouteNames.discover,
      'wardrobe' => RouteNames.wardrobe,
      'stylist' => RouteNames.stylist,
      'discover' => RouteNames.discover,
      'home' => RouteNames.home,
      'profile' => RouteNames.profile,
      'daily-outfit' => RouteNames.dailyOutfit,
      'hairstyle' => RouteNames.hairstyle,
      'grooming' => RouteNames.grooming,
      'build-outfit' => RouteNames.buildOutfit,
      _ => RouteNames.stylist,
    };
  }
}
