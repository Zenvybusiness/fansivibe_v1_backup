/// Session-scoped user progress shared across features.
///
/// Persists state across app launches via [LocalStorage].
library;
import 'package:fansivibe/shared/utils/local_storage.dart';

class UserSession {
  UserSession._();

  /// True once a new user has saved their first wardrobe item / completed onboarding.
  static bool get hasSavedWardrobeItem =>
      LocalStorage.onboardingComplete;

  static set hasSavedWardrobeItem(bool value) {
    LocalStorage.onboardingComplete = value;
  }

  /// Display name of the user, if provided during account creation or onboarding.
  static String? get displayName => LocalStorage.displayName;

  static set displayName(String? value) {
    LocalStorage.displayName = value;
  }

  /// Selected style vibe, if user chose one during onboarding.
  static String? get vibe => LocalStorage.vibe;

  static set vibe(String? value) {
    LocalStorage.vibe = value;
  }

  /// Whether the user chose "Continue Without Account" during onboarding.
  static bool get savedLocally => LocalStorage.savedLocally;

  static set savedLocally(bool value) {
    LocalStorage.savedLocally = value;
  }

  /// Whether analysis results were cached during onboarding.
  static bool get analysisCached => LocalStorage.analysisCached;

  static set analysisCached(bool value) {
    LocalStorage.analysisCached = value;
  }
}