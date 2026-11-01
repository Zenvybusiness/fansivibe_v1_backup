import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/profile/data/user_profile_client.dart';
import 'package:fansivibe/features/profile/data/user_profile_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Contract for backend-authoritative profile hydration.
///
/// PostgreSQL/backend is the canonical authority for persisted profile information.
/// Flutter [LocalStorage] is a cache and transient interaction layer, not an
/// independent canonical profile.
abstract class UserProfileRepository {
  /// Loads the profile from the authoritative backend endpoint `GET /v1/users/me`.
  /// If [forceRefresh] is true, bypasses the in-memory cache.
  Future<UserProfile?> fetchProfile({bool forceRefresh = false});

  /// The currently cached in-memory profile, if any.
  UserProfile? get cachedProfile;

  /// Records an unsynchronized local edit so that subsequent hydrations do
  /// not silently discard pending user input before backend sync.
  void recordPendingEdit({required String field, required dynamic value});

  /// Clears any pending edits.
  void clearPendingEdits();

  /// Gets the map of currently pending unsynchronized edits.
  Map<String, dynamic> get pendingEdits;

  /// Clears all cached profile data and resets request generation tracking.
  void clearCache();

  /// Updates the user's style archetype (e.g. Minimalist, Classic, Streetwear).
  ///
  /// Persists to the canonical backend via `PATCH /v1/users/me` when authenticated.
  /// Returns the updated [UserProfile] on confirmed backend persistence, or null on failure.
  Future<UserProfile?> updateStyleType(String styleType);

  /// Updates one or more application settings toggles.
  ///
  /// Merges into backend settings JSON via `PATCH /v1/users/me` when authenticated.
  /// Returns the updated [UserProfile] on confirmed backend persistence, or null on failure.
  Future<UserProfile?> updateSettings(Map<String, dynamic> settingsPatch);

  /// Updates preferred occasions list.
  ///
  /// Persists to the canonical backend via `PATCH /v1/users/me` when authenticated.
  /// Returns the updated [UserProfile] on confirmed backend persistence, or null on failure.
  Future<UserProfile?> updatePreferredOccasions(List<String> occasions);
}

/// Backend-authoritative implementation of [UserProfileRepository].
class UserProfileRepositoryImpl implements UserProfileRepository {
  UserProfileRepositoryImpl({UserProfileClient? client})
      : _client = client ?? UserProfileClient();

  final UserProfileClient _client;
  UserProfile? _cachedProfile;
  final Map<String, dynamic> _pendingEdits = {};
  int _requestGeneration = 0;

  @override
  UserProfile? get cachedProfile => _cachedProfile;

  @override
  Map<String, dynamic> get pendingEdits => Map.unmodifiable(_pendingEdits);

  @override
  void recordPendingEdit({required String field, required dynamic value}) {
    _pendingEdits[field] = value;
  }

  @override
  void clearPendingEdits() {
    _pendingEdits.clear();
  }

  @override
  void clearCache() {
    _cachedProfile = null;
    _pendingEdits.clear();
    _requestGeneration = 0;
  }

  @override
  Future<UserProfile?> fetchProfile({bool forceRefresh = false}) async {
    // 1. Unauthenticated state or guest:
    // Guest appearance data must NOT become authenticated profile data (D10 / Batch 1B).
    if (!AuthSession.isAuthenticated || isGuestUser) {
      return null;
    }

    // 2. Return memory cache if available and not forced to refresh.
    if (!forceRefresh && _cachedProfile != null) {
      return _applyPendingEdits(_cachedProfile!);
    }

    // Increment generation ID to prevent stale asynchronous responses from
    // overwriting newer state.
    final generation = ++_requestGeneration;

    try {
      final remoteProfile = await _client.getProfile();

      // Stale response protection: if another request was initiated, discard this response.
      if (generation != _requestGeneration) {
        debugPrint(
          'UserProfileRepository: Discarding stale response (gen $generation < $_requestGeneration)',
        );
        return _cachedProfile != null ? _applyPendingEdits(_cachedProfile!) : null;
      }

      if (remoteProfile != null) {
        // Version protection: do not let an older profile version overwrite a newer one.
        if (_cachedProfile != null && remoteProfile.version < _cachedProfile!.version) {
          debugPrint(
            'UserProfileRepository: Discarding older version (${remoteProfile.version} < ${_cachedProfile!.version})',
          );
          return _applyPendingEdits(_cachedProfile!);
        }

        _cachedProfile = remoteProfile;
        _syncToLocalStorage(remoteProfile);
        return _applyPendingEdits(remoteProfile);
      }
    } catch (e) {
      debugPrint('UserProfileRepository: fetchProfile error: $e');
    }

    // 3. Fallback on network failure: return cached profile or LocalStorage cache.
    if (_cachedProfile != null) {
      return _applyPendingEdits(_cachedProfile!);
    }

    final fallback = _readFromLocalStorage();
    if (fallback != null) {
      _cachedProfile = fallback;
      return _applyPendingEdits(fallback);
    }

    return null;
  }

  UserProfile _applyPendingEdits(UserProfile profile) {
    if (_pendingEdits.isEmpty) return profile;

    var style = profile.styleProfile;
    var name = profile.displayName;

    if (_pendingEdits.containsKey('displayName')) {
      name = _pendingEdits['displayName'] as String? ?? name;
    }
    if (_pendingEdits.containsKey('faceShape')) {
      style = style.copyWith(faceShape: _pendingEdits['faceShape'] as String?);
    }
    if (_pendingEdits.containsKey('skinTone')) {
      style = style.copyWith(skinTone: _pendingEdits['skinTone'] as String?);
    }
    if (_pendingEdits.containsKey('bodyType')) {
      style = style.copyWith(bodyType: _pendingEdits['bodyType'] as String?);
    }
    if (_pendingEdits.containsKey('styleType')) {
      style = style.copyWith(styleType: _pendingEdits['styleType'] as String?);
    }

    return profile.copyWith(
      displayName: name,
      styleProfile: style,
    );
  }

  @override
  Future<UserProfile?> updateStyleType(String styleType) async {
    final cleanStyle = styleType.trim();
    if (cleanStyle.isEmpty) return null;

    if (!AuthSession.isAuthenticated || isGuestUser) {
      LearningService.instance.setStyleType(cleanStyle);
      LocalStorage.vibe = cleanStyle;
      final currentMap = Map<String, dynamic>.from(LocalStorage.userProfile);
      currentMap['styleType'] = cleanStyle;
      LocalStorage.userProfile = currentMap;
      if (_cachedProfile != null) {
        final updatedStyle = _cachedProfile!.styleProfile.copyWith(styleType: cleanStyle);
        _cachedProfile = _cachedProfile!.copyWith(styleProfile: updatedStyle);
        return _cachedProfile;
      }
      return UserProfile(
        displayName: LocalStorage.displayName ?? '',
        styleProfile: UserStyleProfile(styleType: cleanStyle),
        version: 1,
      );
    }

    try {
      final updated = await _client.updateProfile(styleType: cleanStyle);
      if (updated != null) {
        _cachedProfile = updated;
        _syncToLocalStorage(updated);
        return updated;
      }
    } catch (e) {
      debugPrint('UserProfileRepositoryImpl: updateStyleType error: $e');
    }
    return null;
  }

  @override
  Future<UserProfile?> updateSettings(Map<String, dynamic> settingsPatch) async {
    if (settingsPatch.isEmpty) return _cachedProfile;

    if (!AuthSession.isAuthenticated || isGuestUser) {
      final current = Map<String, dynamic>.from(LocalStorage.settings);
      current.addAll(settingsPatch);
      LocalStorage.settings = current;
      if (_cachedProfile != null) {
        final updatedSettings = Map<String, dynamic>.from(_cachedProfile!.settings)..addAll(settingsPatch);
        _cachedProfile = _cachedProfile!.copyWith(settings: updatedSettings);
        return _cachedProfile;
      }
      return UserProfile(
        displayName: LocalStorage.displayName ?? '',
        styleProfile: const UserStyleProfile(),
        settings: current,
        version: 1,
      );
    }

    try {
      final updated = await _client.updateProfile(settings: settingsPatch);
      if (updated != null) {
        _cachedProfile = updated;
        _syncToLocalStorage(updated);
        return updated;
      }
    } catch (e) {
      debugPrint('UserProfileRepositoryImpl: updateSettings error: $e');
    }
    return null;
  }

  @override
  Future<UserProfile?> updatePreferredOccasions(List<String> occasions) async {
    if (!AuthSession.isAuthenticated || isGuestUser) {
      LearningService.instance.replacePreferredOccasions(occasions);
      if (_cachedProfile != null) {
        final updatedPrefs = Map<String, dynamic>.from(_cachedProfile!.preferences);
        updatedPrefs['preferredOccasions'] = occasions;
        _cachedProfile = _cachedProfile!.copyWith(preferences: updatedPrefs);
        return _cachedProfile;
      }
      return null;
    }

    try {
      final updated = await _client.updateProfile(preferredOccasions: occasions);
      if (updated != null) {
        _cachedProfile = updated;
        _syncToLocalStorage(updated);
        LearningService.instance.replacePreferredOccasions(occasions);
        return updated;
      }
    } catch (e) {
      debugPrint('UserProfileRepositoryImpl: updatePreferredOccasions error: $e');
    }
    return null;
  }

  void _syncToLocalStorage(UserProfile profile) {
    if (profile.displayName.isNotEmpty) {
      LocalStorage.displayName = profile.displayName;
    }

    final currentMap = Map<String, dynamic>.from(LocalStorage.userProfile);

    final style = profile.styleProfile;
    if (style.faceShape != null) currentMap['faceShape'] = style.faceShape;
    if (style.skinTone != null) currentMap['skinTone'] = style.skinTone;
    if (style.bodyType != null) currentMap['bodyType'] = style.bodyType;
    if (style.styleType != null && style.styleType!.isNotEmpty) {
      currentMap['styleType'] = style.styleType;
      LocalStorage.vibe = style.styleType;
      LearningService.instance.setStyleType(style.styleType!);
    }
    if (style.sourceRunId != null) currentMap['sourceRunId'] = style.sourceRunId;

    // Preserve Batch 1A provenance keys.
    style.extra.forEach((k, v) {
      if (k.startsWith('_provenance_')) {
        currentMap[k] = v;
      }
    });

    LocalStorage.userProfile = currentMap;

    // Sync settings to LocalStorage as well
    if (profile.settings.isNotEmpty) {
      final currentSettings = Map<String, dynamic>.from(LocalStorage.settings);
      currentSettings.addAll(profile.settings);
      LocalStorage.settings = currentSettings;
    }

    // Sync preferredOccasions if present
    final occs = profile.preferences['preferredOccasions'] ?? profile.preferences['preferred_occasions'];
    if (occs is List) {
      final parsed = occs.map((e) => e.toString()).toList();
      LearningService.instance.replacePreferredOccasions(parsed);
    }
  }

  UserProfile? _readFromLocalStorage() {
    final map = LocalStorage.userProfile;
    final name = LocalStorage.displayName ?? '';
    final localSettings = LocalStorage.settings;
    if (map.isEmpty && name.isEmpty && localSettings.isEmpty) return null;

    final style = UserStyleProfile.fromJson(map);
    return UserProfile(
      displayName: name,
      styleProfile: style,
      settings: localSettings,
      version: 1,
    );
  }
}
