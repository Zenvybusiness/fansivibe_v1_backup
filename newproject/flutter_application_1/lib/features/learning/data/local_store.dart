import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/learning/data/models.dart';

/// Persists the on-device user model as a single JSON blob.
///
/// Uses `shared_preferences` — lightweight and available on every device. If
/// storage is unavailable (e.g. headless tests) it degrades to in-memory so
/// the app never crashes; the model just isn't written.
class LocalStore {
  LocalStore();

  static const String _modelKey = 'fansivibe.user_model.v1';

  Future<String?> readRaw() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(_modelKey);
    } catch (error) {
      debugPrint('LocalStore read unavailable: $error');
      return null;
    }
  }

  Future<void> writeRaw(String encoded) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_modelKey, encoded);
    } catch (error) {
      debugPrint('LocalStore write unavailable: $error');
    }
  }

  Future<UserModel?> load() async {
    final raw = await readRaw();
    if (raw == null || raw.isEmpty) return null;
    try {
      return UserModel.decode(raw);
    } catch (error) {
      debugPrint('LocalStore decode failed, using defaults: $error');
      return null;
    }
  }

  Future<void> save(UserModel model) => writeRaw(model.encode());
}
