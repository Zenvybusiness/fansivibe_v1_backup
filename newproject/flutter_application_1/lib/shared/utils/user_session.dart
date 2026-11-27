import 'package:flutter/foundation.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

class UserSession {
  UserSession._();

  /// Reactive notifier that fires whenever wardrobe item presence changes.
  static final ValueNotifier<bool> savedWardrobeItemNotifier =
      ValueNotifier<bool>(LocalStorage.hasSavedWardrobeItem);

  /// Reactive notifier that fires whenever the authenticated saved-looks
  /// collection changes (saved or deleted from Home, Daily Outfit, or Saved Looks).
  static final ValueNotifier<int> savedLooksVersion = ValueNotifier<int>(0);

  /// Notifies mounted listeners that persisted saved looks changed.
  static void notifySavedLooksChanged() {
    savedLooksVersion.value++;
  }

  /// Reactive notifier that fires whenever the authenticated events
  /// collection changes (created, updated, or deleted).
  static final ValueNotifier<int> eventsVersion = ValueNotifier<int>(0);

  /// Notifies mounted listeners that persisted events changed.
  static void notifyEventsChanged() {
    eventsVersion.value++;
  }

  /// True once a user has saved their first wardrobe item.
  static bool get hasSavedWardrobeItem => LocalStorage.hasSavedWardrobeItem;

  static set hasSavedWardrobeItem(bool value) {
    LocalStorage.hasSavedWardrobeItem = value;
    savedWardrobeItemNotifier.value = value;
  }

  /// True if the user is a returning user who logged in with an existing account.
  static bool get isReturningUser => LocalStorage.isReturningUser;

  static set isReturningUser(bool value) {
    LocalStorage.isReturningUser = value;
  }

  /// Whether the user is currently classified as a new user in the initial exploration stage.
  static bool get isNewUserInInitialExploration {
    if (isReturningUser) return false;
    if (hasSavedWardrobeItem) return false;
    if (LocalStorage.savedLookIds.isNotEmpty) return false;
    try {
      if (LearningService.instance.signals.isNotEmpty) return false;
      if (LearningService.instance.savedLooks.isNotEmpty) return false;
    } catch (_) {}
    final hasOnboarding =
        LocalStorage.onboardingComplete ||
        LocalStorage.vibe != null ||
        LocalStorage.savedLocally;
    return hasOnboarding;
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
}
