import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Server preference sync signature (existing contract:
/// `AssistantClient.syncPreferredOccasion`, additive + idempotent —
/// already-synced codes answer `alreadySynced`, never duplicates).
typedef SyncPreferenceFn =
    Future<PreferenceSyncResult> Function({required String code});

/// Outcome of one guest-data migration attempt.
///
/// Local device data is NEVER mutated here (removal is the caller's job
/// after an explicit user choice): a failed run leaves everything in
/// place, and [migratedLocalIds] feeds the retry ledger so repeats skip
/// already-uploaded items instead of duplicating server rows.
class GuestMigrationResult {
  const GuestMigrationResult({
    required this.migratedItemNames,
    required this.migratedLocalIds,
    required this.failedItemNames,
    required this.skippedItemNames,
    required this.prefsSynced,
    required this.prefsFailed,
  });

  final List<String> migratedItemNames;

  /// Device-local ids successfully created server-side this run.
  final List<String> migratedLocalIds;
  final List<String> failedItemNames;
  final List<String> skippedItemNames;
  final List<String> prefsSynced;
  final List<String> prefsFailed;

  bool get hasFailures =>
      failedItemNames.isNotEmpty || prefsFailed.isNotEmpty;

  bool get movedAnything =>
      migratedItemNames.isNotEmpty || prefsSynced.isNotEmpty;
}

/// Uploads supported guest data into the newly authenticated account.
///
/// Uses ONLY existing backend contracts:
/// - wardrobe: `WardrobeRepository.createItem` (server mints UUIDs;
///   device `local-*` ids are never sent as identities) + `updateItem`
///   for favorites (create carries no favorite flag).
/// - preferences: `syncPreferredOccasion` per code (additive).
///
/// Explicitly NOT transferred (no backend upload contract exists —
/// kept local and documented, never fabricated):
/// face profile (server derives it from real scans), learning signals
/// (M10 sole-writer rules), saved-look title strings (no IDs), style
/// type, vibe, and the legacy analysis blob.
class GuestDataMigration {
  GuestDataMigration({
    required WardrobeRepository wardrobeRepo,
    required SyncPreferenceFn syncPreference,
    required LearningRepository learning,
  }) : _wardrobeRepo = wardrobeRepo,
       _syncPreference = syncPreference,
       _learning = learning;

  final WardrobeRepository _wardrobeRepo;
  final SyncPreferenceFn _syncPreference;
  final LearningRepository _learning;

  static String _tuple(String name, String? category, String? color,
      String? material) {
    return '${name.trim().toLowerCase()}|'
        '${(category ?? '').trim().toLowerCase()}|'
        '${(color ?? '').trim().toLowerCase()}|'
        '${(material ?? '').trim().toLowerCase()}';
  }

  Future<GuestMigrationResult> migrate() async {
    try {
      await _learning.load();
    } catch (_) {
      // Local read failure: fall through with whatever is in memory.
    }

    final migrated = <String>[];
    final migratedIds = <String>[];
    final failed = <String>[];
    final skipped = <String>[];
    final prefsSynced = <String>[];
    final prefsFailed = <String>[];

    final ledger = Set<String>.from(LocalStorage.migratedGuestIds);

    final locals = _learning.wardrobe
        .where((e) => e.id.startsWith('local-'))
        .toList();

    // Best-effort server snapshot for content dedup: an item the user
    // already added manually post-auth must not be uploaded twice.
    // listItems throws on failure — then every item uploads honestly
    // and per-create failures below still guard duplicates on retry
    // via the ledger.
    final serverTuples = <String>{};
    try {
      final existing = await _wardrobeRepo.listItems(pageSize: 100);
      for (final item in existing) {
        serverTuples.add(
          _tuple(item.name, item.category, item.color, item.material),
        );
      }
    } catch (_) {
      // Proceed without the snapshot; the ledger still dedups retries.
    }

    for (final entry in locals) {
      if (ledger.contains(entry.id)) {
        skipped.add(entry.name);
        continue;
      }
      if (serverTuples.contains(
        _tuple(entry.name, entry.category, entry.color, entry.material),
      )) {
        skipped.add(entry.name);
        ledger.add(entry.id);
        LocalStorage.migratedGuestIds = ledger.toList();
        continue;
      }
      try {
        final created = await _wardrobeRepo.createItem(
          name: entry.name,
          category: entry.category,
          color: entry.color,
          material: entry.material,
          imageRef: null, // Guest items are imageless (server-side analysis
          // is account-only); photos never existed to upload.
        );
        if (created == null) {
          failed.add(entry.name);
          continue;
        }
        if (entry.isFavorite) {
          // Favorites ride a second call: create carries no favorite
          // flag. A failed favorite flip keeps the item migrated (the
          // row exists server-side); the star is cosmetic.
          try {
            await _wardrobeRepo.updateItem(
              itemId: created.id,
              isFavorite: true,
            );
          } catch (_) {
            // Item already migrated; favorite loss is not a failure.
          }
        }
        migrated.add(entry.name);
        migratedIds.add(entry.id);
        ledger.add(entry.id);
        LocalStorage.migratedGuestIds = ledger.toList();
      } catch (_) {
        failed.add(entry.name);
      }
    }

    // Prefs ledger (mirrors migratedGuestIds): codes synced by an
    // earlier merge are never re-synced, so a completed choice does not
    // repeat. Failures stay unledgered and are retried next time.
    final syncedLedger = Set<String>.from(LocalStorage.migratedGuestPrefs);
    for (final code in _learning.preferredOccasions) {
      if (syncedLedger.contains(code)) continue;
      try {
        final result = await _syncPreference(code: code);
        if (result == PreferenceSyncResult.synced ||
            result == PreferenceSyncResult.alreadySynced) {
          prefsSynced.add(code);
          syncedLedger.add(code);
          LocalStorage.migratedGuestPrefs = syncedLedger.toList();
        } else {
          prefsFailed.add(code);
        }
      } catch (_) {
        prefsFailed.add(code);
      }
    }

    return GuestMigrationResult(
      migratedItemNames: migrated,
      migratedLocalIds: migratedIds,
      failedItemNames: failed,
      skippedItemNames: skipped,
      prefsSynced: prefsSynced,
      prefsFailed: prefsFailed,
    );
  }
}
