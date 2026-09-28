import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/features/assistant/data/assistant_client.dart';
import 'package:fansivibe/features/auth/data/guest_data_migration.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/pending_auth_intent.dart';

/// Explicit guest-data choice after successful authentication.
enum GuestDataChoice { merge, keep, discard }

/// Post-auth conversion (Flow 1B): pending-intent return + guest data.
///
/// Shared by register and sign-in success so both doors behave
/// identically: consume the single-use intent, offer Merge/Keep/Discard
/// when transferable guest data exists, migrate on Merge, then navigate
/// to the intent destination (or `/home` when absent/invalid).
///
/// - MERGE: upload supported guest data (wardrobe via
///   `WardrobeRepository.createItem`, preferences via
///   `syncPreferredOccasion`), remove successfully uploaded locals.
/// - KEEP ON DEVICE (and dialog dismiss): upload nothing, delete nothing.
/// - DISCARD (double-confirmed): remove device-local wardrobe + prefs;
///   the account is untouched.
/// - Migration failure: locals preserved, honest error with Retry, the
///   session stays valid, the retry ledger prevents duplicates.
/// - Authenticated screens rebuild from backend repos on navigation, so
///   no manual state refresh is needed; `isGuestUser` flips false purely
///   through `AuthSession` (never a manual flag).
Future<void> handlePostAuthConversion(BuildContext context) async {
  final intent = takePendingAuthIntent();
  final destination = resolvePostAuthDestination(intent);
  try {
    await LearningService.instance.load();
  } catch (_) {
    // Local read failure: proceed with in-memory state; the dialog
    // simply may not appear and navigation still happens.
  }
  if (!context.mounted) return;

  final localIds = _unmigratedLocalIds();
  final prefs = _unmigratedPrefs();
  if (localIds.isEmpty && prefs.isEmpty) {
    _goWithGuidance(context, destination, intent);
    return;
  }

  final choice = await showGuestMergeDialog(
    context,
    itemCount: localIds.length,
    prefCount: prefs.length,
  );
  if (!context.mounted) return;
  switch (choice) {
    case GuestDataChoice.merge:
      await _runMerge(context, destination, intent);
    case GuestDataChoice.discard:
      final confirmed = await showGuestDiscardConfirm(
        context,
        itemCount: localIds.length,
        prefCount: prefs.length,
      );
      if (!context.mounted) return;
      if (confirmed) {
        LearningService.instance.removeLocalItems(localIds.toSet());
        LearningService.instance.clearPreferredOccasions();
        // Device prefs are gone, so their sync ledger is meaningless —
        // without this a re-added code would be skipped as "migrated".
        LocalStorage.migratedGuestPrefs = [];
        _snack(context, 'Device data removed. Your account is unchanged.');
      }
      _goWithGuidance(context, destination, intent);
    case GuestDataChoice.keep:
    case null:
      // Dismissed (back button) defaults to non-destructive Keep.
      _goWithGuidance(context, destination, intent);
  }
}

/// Device-local wardrobe ids still needing upload (already-migrated
/// ledger ids excluded so retries never reprocess them).
List<String> _unmigratedLocalIds() {
  final ledger = Set<String>.from(LocalStorage.migratedGuestIds);
  return LearningService.instance.wardrobe
      .where((e) => e.id.startsWith('local-') && !ledger.contains(e.id))
      .map((e) => e.id)
      .toList();
}

/// Device-local preference codes still needing sync (already-synced
/// ledger codes excluded so a completed merge never re-prompts).
List<String> _unmigratedPrefs() {
  final ledger = Set<String>.from(LocalStorage.migratedGuestPrefs);
  return LearningService.instance.preferredOccasions
      .where((code) => !ledger.contains(code))
      .toList();
}

Future<void> _runMerge(
  BuildContext context,
  String destination,
  PendingAuthIntent? intent,
) async {
  showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (dialogContext) => const Center(
      child: CircularProgressIndicator(),
    ),
  );
  final migration = GuestDataMigration(
    wardrobeRepo: WardrobeRepositoryImpl(),
    syncPreference: AssistantClient().syncPreferredOccasion,
    learning: LearningService.instance,
  );
  // Merge must never block login: an unexpected throw keeps everything
  // local and still lands the user home.
  GuestMigrationResult? result;
  try {
    result = await migration.migrate();
  } catch (_) {
    result = null;
  }
  if (result != null && result.migratedLocalIds.isNotEmpty) {
    // Uploaded rows now live server-side: drop the device copies so
    // they cannot ghost back after a later logout. Failed rows stay.
    LearningService.instance.removeLocalItems(
      result.migratedLocalIds.toSet(),
    );
  }
  if (!context.mounted) return;
  Navigator.of(context, rootNavigator: true).pop();
  if (!context.mounted) return;
  if (result == null) {
    _snack(
      context,
      'Signed in — your device data stays on this device for now.',
    );
    _goWithGuidance(context, destination, intent);
    return;
  }
  if (!result.hasFailures) {
    final moved = result.migratedItemNames.length + result.prefsSynced.length;
    _snack(
      context,
      moved == 0
          ? 'Nothing new to move — your account already has it.'
          : 'Moved $moved item${moved == 1 ? '' : 's'} to your account.',
    );
    _goWithGuidance(context, destination, intent);
    return;
  }
  final retry = await showGuestMigrationResult(context, result);
  if (!context.mounted) return;
  if (retry) {
    // Ledger skips already-uploaded rows: no duplicates on retry.
    await _runMerge(context, destination, intent);
    return;
  }
  _goWithGuidance(context, destination, intent);
}

void _goWithGuidance(
  BuildContext context,
  String destination,
  PendingAuthIntent? intent,
) {
  if (intent != null) {
    final message = intent.action == 'save_progress'
        ? 'Account ready — your local progress was kept.'
        : 'Signed in — continue where you left off.';
    _snack(context, message);
  }
  context.go(destination);
}

void _snack(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(message),
      backgroundColor: FansivibeColors.accentGold,
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(
        borderRadius: FansivibeRadius.smdBorder,
      ),
    ),
  );
}

/// Explicit choice dialog. New UI is required by the task; it reuses the
/// existing Digital Atelier tokens and button components only.
Future<GuestDataChoice?> showGuestMergeDialog(
  BuildContext context, {
  required int itemCount,
  required int prefCount,
}) {
  final parts = <String>[];
  if (itemCount > 0) {
    parts.add('$itemCount wardrobe item${itemCount == 1 ? '' : 's'}');
  }
  if (prefCount > 0) {
    parts.add('$prefCount preference${prefCount == 1 ? '' : 's'}');
  }
  return showDialog<GuestDataChoice>(
    context: context,
    barrierDismissible: true,
    builder: (dialogContext) => AlertDialog(
      backgroundColor: FansivibeColors.surfaceContainerLow,
      shape: RoundedRectangleBorder(
        borderRadius: FansivibeRadius.mdBorder,
      ),
      title: Text(
        'Your device has saved data',
        style: FansivibeTypography.titleLargeWithFamily.copyWith(
          color: FansivibeColors.textPrimary,
          fontWeight: FontWeight.w600,
        ),
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'We found ${parts.join(' and ')} saved on this device '
            'while you were browsing as a guest.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.textSecondary,
            ),
          ),
          SizedBox(height: FansivibeSpacing.md),
          FansiButton.primary(
            label: 'Merge into my account',
            icon: Icons.cloud_upload_outlined,
            onPressed: () =>
                Navigator.of(dialogContext).pop(GuestDataChoice.merge),
          ),
          SizedBox(height: FansivibeSpacing.sm),
          FansiButton.secondary(
            label: 'Keep on this device',
            icon: Icons.smartphone_outlined,
            onPressed: () =>
                Navigator.of(dialogContext).pop(GuestDataChoice.keep),
          ),
          SizedBox(height: FansivibeSpacing.sm),
          FansiButton.tertiary(
            label: 'Discard from this device',
            onPressed: () =>
                Navigator.of(dialogContext).pop(GuestDataChoice.discard),
          ),
        ],
      ),
    ),
  );
}

/// Second, explicit confirmation for the destructive choice.
Future<bool> showGuestDiscardConfirm(
  BuildContext context, {
  required int itemCount,
  required int prefCount,
}) async {
  final result = await showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      backgroundColor: FansivibeColors.surfaceContainerLow,
      shape: RoundedRectangleBorder(
        borderRadius: FansivibeRadius.mdBorder,
      ),
      title: Text(
        'Discard device data?',
        style: FansivibeTypography.titleLargeWithFamily.copyWith(
          color: FansivibeColors.textPrimary,
          fontWeight: FontWeight.w600,
        ),
      ),
      content: Text(
        'This removes $itemCount wardrobe item${itemCount == 1 ? '' : 's'}'
        '${prefCount > 0 ? ' and $prefCount preference${prefCount == 1 ? '' : 's'}' : ''} '
        'from this device only. Your account stays exactly as it is.',
        style: FansivibeTypography.bodyMediumWithFamily.copyWith(
          color: FansivibeColors.textSecondary,
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: const Text('Cancel'),
        ),
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: Text(
            'Discard',
            style: TextStyle(color: FansivibeColors.error),
          ),
        ),
      ],
    ),
  );
  return result ?? false;
}

/// Honest partial-failure surface: what moved, what did not, Retry
/// (ledger-safe) or Keep-on-device. True = retry, false = continue.
Future<bool> showGuestMigrationResult(
  BuildContext context,
  GuestMigrationResult result,
) async {
  final failedNames = [
    ...result.failedItemNames,
    ...result.prefsFailed,
  ].take(5).join(', ');
  final outcome = await showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (dialogContext) => AlertDialog(
      backgroundColor: FansivibeColors.surfaceContainerLow,
      shape: RoundedRectangleBorder(
        borderRadius: FansivibeRadius.mdBorder,
      ),
      title: Text(
        'Some items stayed on your device',
        style: FansivibeTypography.titleLargeWithFamily.copyWith(
          color: FansivibeColors.textPrimary,
          fontWeight: FontWeight.w600,
        ),
      ),
      content: Text(
        '${result.migratedItemNames.length + result.prefsSynced.length} moved, '
        '${result.failedItemNames.length + result.prefsFailed.length} could not '
        'be moved ($failedNames). Nothing was deleted — retry or keep them '
        'on this device.',
        style: FansivibeTypography.bodyMediumWithFamily.copyWith(
          color: FansivibeColors.textSecondary,
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: const Text('Keep on device'),
        ),
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: const Text('Retry remaining'),
        ),
      ],
    ),
  );
  return outcome ?? false;
}
