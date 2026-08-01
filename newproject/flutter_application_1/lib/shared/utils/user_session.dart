/// Session-scoped user progress shared across features.
///
/// No persistence or state management exists in this app, so cross-feature
/// signals that gate first-visit flows live here as simple flags.
class UserSession {
  UserSession._();

  /// True once a new user has saved their first wardrobe item.
  static bool hasSavedWardrobeItem = false;
}
