import 'package:flutter/material.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

/// One garment entry reviewed and confirmed in the ensemble wear sheet.
class EnsembleWearGarment {
  const EnsembleWearGarment({
    required this.id,
    required this.name,
    required this.category,
    this.color,
    this.material,
  });

  final String id;
  final String name;
  final String category;
  final String? color;
  final String? material;
}

/// Helper function to display the [EnsembleWearConfirmationSheet] modal bottom sheet.
Future<WearEventLogResponse?> showEnsembleWearConfirmationSheet({
  required BuildContext context,
  required String outfitTitle,
  required List<EnsembleWearGarment> garments,
  WardrobeRepository? wardrobeRepository,
  ValueChanged<WearEventLogResponse>? onWearLogged,
}) {
  return showModalBottomSheet<WearEventLogResponse?>(
    context: context,
    isScrollControlled: true,
    backgroundColor: FansivibeColors.surfaceContainerLow,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
    ),
    builder: (sheetContext) => EnsembleWearConfirmationSheet(
      outfitTitle: outfitTitle,
      garments: garments,
      wardrobeRepository: wardrobeRepository,
      onWearLogged: onWearLogged,
    ),
  );
}

/// Modal bottom sheet allowing users to review, adjust, and confirm an ensemble
/// wear logging action (Phase 5 of Stage 2 P0-1).
///
/// Adheres strictly to the Digital Atelier design tokens and the D10 Option A
/// guest boundary. Never claims success before backend persistence is confirmed.
class EnsembleWearConfirmationSheet extends StatefulWidget {
  const EnsembleWearConfirmationSheet({
    required this.outfitTitle,
    required this.garments,
    this.wardrobeRepository,
    this.onWearLogged,
    super.key,
  });

  final String outfitTitle;
  final List<EnsembleWearGarment> garments;
  final WardrobeRepository? wardrobeRepository;
  final ValueChanged<WearEventLogResponse>? onWearLogged;

  @override
  State<EnsembleWearConfirmationSheet> createState() =>
      _EnsembleWearConfirmationSheetState();
}

class _EnsembleWearConfirmationSheetState
    extends State<EnsembleWearConfirmationSheet> {
  late final WardrobeRepository _repository;
  late final Set<String> _selectedIds;
  String? _idempotencyKey;

  bool _isSubmitting = false;
  WearEventLogResponse? _successResponse;
  String? _errorMessage;

  static final RegExp _uuidPattern = RegExp(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
    r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$',
  );

  @override
  void initState() {
    super.initState();
    _repository = widget.wardrobeRepository ?? WardrobeRepositoryImpl();
    // Pre-select all genuine wardrobe UUIDs
    _selectedIds = widget.garments
        .where((g) => _uuidPattern.hasMatch(g.id.trim()))
        .map((g) => g.id.trim())
        .toSet();
    _idempotencyKey = newWearIdempotencyKey();
  }

  void _toggleGarment(String id) {
    if (_isSubmitting || _successResponse != null) return;
    setState(() {
      if (_selectedIds.contains(id)) {
        _selectedIds.remove(id);
      } else {
        _selectedIds.add(id);
      }
    });
  }

  Future<void> _handleConfirmWear() async {
    // 1. Guard against guest attempts
    if (!AuthSession.isAuthenticated || isGuestUser) {
      if (mounted) {
        promptGuestSignIn(
          context,
          action: 'Sign in to log wears. Browsing stays free.',
        );
      }
      return;
    }

    if (_isSubmitting || _selectedIds.isEmpty) return;

    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });

    final key = _idempotencyKey ??= newWearIdempotencyKey();

    WearEventLogResponse? response;
    try {
      response = await _repository.logEnsembleWear(
        itemIds: _selectedIds.toList(),
        idempotencyKey: key,
      );
    } catch (_) {
      response = null;
    }

    if (!mounted) return;

    if (response != null) {
      setState(() {
        _isSubmitting = false;
        _successResponse = response;
        _errorMessage = null;
      });
      widget.onWearLogged?.call(response);
    } else {
      setState(() {
        _isSubmitting = false;
        _errorMessage =
            "Couldn't record wear. Check your connection and try again.";
      });
    }
  }

  IconData _categoryIcon(String category) {
    switch (category.toLowerCase()) {
      case 'outerwear':
        return Icons.checkroom_rounded;
      case 'tops':
        return Icons.person_rounded;
      case 'bottoms':
        return Icons.accessibility_rounded;
      case 'footwear':
        return Icons.directions_walk_rounded;
      case 'accessories':
        return Icons.diamond_rounded;
      default:
        return Icons.category_rounded;
    }
  }

  @override
  Widget build(BuildContext context) {
    final mediaQuery = MediaQuery.of(context);
    final maxHeight = mediaQuery.size.height * 0.85;

    return Semantics(
      container: true,
      label: 'Ensemble Wear Confirmation',
      child: Container(
        key: const Key('ensemble_wear_sheet'),
        constraints: BoxConstraints(maxHeight: maxHeight),
        decoration: BoxDecoration(
          color: FansivibeColors.surfaceContainerLow,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 12),
              // Drag Handle
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: FansivibeColors.outlineVariant,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // Content Body
              Expanded(
                child: SingleChildScrollView(
                  physics: const BouncingScrollPhysics(),
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: _buildBody(context),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_successResponse != null) {
      return _buildSuccessView(context, _successResponse!);
    }
    if (_isSubmitting) {
      return _buildLoadingView(context);
    }
    if (_errorMessage != null) {
      return _buildErrorView(context, _errorMessage!);
    }
    return _buildReviewView(context);
  }

  Widget _buildReviewView(BuildContext context) {
    final validGarments = widget.garments
        .where((g) => _uuidPattern.hasMatch(g.id.trim()))
        .toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Eyebrow
        Text(
          'RECORD ENSEMBLE WEAR',
          style: FansivibeTypography.labelSmallWithFamily.copyWith(
            color: FansivibeColors.accentGold,
            letterSpacing: 2.0,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 6),
        // Title
        Text(
          widget.outfitTitle,
          style: TextStyle(
            fontFamily: FansivibeTypography.displayFamily,
            fontSize: 22,
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
          ),
        ),
        const SizedBox(height: 6),
        // Subtitle
        Text(
          'Review the garments you are wearing today. Deselect any piece you swapped or left out.',
          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
            color: FansivibeColors.textSecondary,
            height: 1.4,
          ),
        ),
        const SizedBox(height: 18),

        // Garment count badge
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: FansivibeColors.surfaceContainerHigh,
            borderRadius: BorderRadius.circular(FansivibeRadius.sm),
            border: Border.all(
              color: FansivibeColors.accentGold.withValues(alpha: 0.25),
              width: 1,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.checkroom_rounded,
                size: 16,
                color: FansivibeColors.accentGold,
              ),
              const SizedBox(width: 8),
              Text(
                '${_selectedIds.length} of ${validGarments.length} garments selected',
                style: FansivibeTypography.labelMediumWithFamily.copyWith(
                  color: FansivibeColors.textPrimary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),

        if (validGarments.isEmpty)
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: FansivibeColors.surfaceContainerHigh,
              borderRadius: BorderRadius.circular(FansivibeRadius.sm),
            ),
            child: Row(
              children: [
                Icon(
                  Icons.info_outline_rounded,
                  color: FansivibeColors.warning,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'No owned wardrobe garments found in this outfit.',
                    style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                      color: FansivibeColors.textPrimary,
                    ),
                  ),
                ),
              ],
            ),
          )
        else
          // Garments List
          ListView.separated(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: validGarments.length,
            separatorBuilder: (_, __) => const SizedBox(height: 10),
            itemBuilder: (context, index) {
              final garment = validGarments[index];
              final isSelected = _selectedIds.contains(garment.id.trim());

              final details = [
                garment.category.toUpperCase(),
                if (garment.color != null && garment.color!.isNotEmpty)
                  garment.color!,
                if (garment.material != null && garment.material!.isNotEmpty)
                  garment.material!,
              ].join(' \u2022 ');

              return InkWell(
                key: Key('garment_item_${garment.id}'),
                onTap: () => _toggleGarment(garment.id.trim()),
                borderRadius: BorderRadius.circular(FansivibeRadius.sm),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 12,
                  ),
                  decoration: BoxDecoration(
                    color: isSelected
                        ? FansivibeColors.surfaceContainerHigh
                        : FansivibeColors.surfaceContainerLowest,
                    borderRadius: BorderRadius.circular(FansivibeRadius.sm),
                    border: Border.all(
                      color: isSelected
                          ? FansivibeColors.accentGold.withValues(alpha: 0.4)
                          : FansivibeColors.outlineVariant.withValues(alpha: 0.15),
                      width: 1,
                    ),
                  ),
                  child: Row(
                    children: [
                      // Thumbnail icon well (Digital Atelier 65/35 visual motif)
                      Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          color: isSelected
                              ? FansivibeColors.accentGold.withValues(alpha: 0.15)
                              : FansivibeColors.surfaceContainerLow,
                          borderRadius: BorderRadius.circular(
                            FansivibeRadius.xs,
                          ),
                        ),
                        child: Icon(
                          _categoryIcon(garment.category),
                          color: isSelected
                              ? FansivibeColors.accentGold
                              : FansivibeColors.textSecondary,
                          size: 22,
                        ),
                      ),
                      const SizedBox(width: 14),
                      // Garment Info
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              garment.name,
                              style: FansivibeTypography.titleLargeWithFamily
                                  .copyWith(
                                fontSize: 16,
                                color: isSelected
                                    ? FansivibeColors.textPrimary
                                    : FansivibeColors.textSecondary,
                                fontWeight: FontWeight.w600,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                            const SizedBox(height: 3),
                            Text(
                              details,
                              style: FansivibeTypography.labelSmallWithFamily
                                  .copyWith(
                                color: FansivibeColors.textSecondary,
                                fontSize: 11,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      // Toggle indicator
                      IconButton(
                        key: Key('garment_toggle_${garment.id}'),
                        icon: Icon(
                          isSelected
                              ? Icons.check_circle_rounded
                              : Icons.radio_button_unchecked_rounded,
                          color: isSelected
                              ? FansivibeColors.accentGold
                              : FansivibeColors.outlineVariant,
                          size: 24,
                        ),
                        onPressed: () => _toggleGarment(garment.id.trim()),
                        tooltip: isSelected ? 'Remove from wear' : 'Include in wear',
                      ),
                    ],
                  ),
                ),
              );
            },
          ),

        const SizedBox(height: 24),

        // Actions
        FansiButton.primary(
          key: const Key('confirm_wear_button'),
          label: _selectedIds.isEmpty
              ? 'Select At Least One Item'
              : 'Confirm Wear (${_selectedIds.length})',
          icon: Icons.checkroom_rounded,
          onPressed: _selectedIds.isEmpty ? null : _handleConfirmWear,
        ),
        const SizedBox(height: 10),
        FansiButton.secondary(
          key: const Key('cancel_wear_button'),
          label: 'Cancel',
          onPressed: () => Navigator.of(context).pop(),
        ),
        const SizedBox(height: 16),
      ],
    );
  }

  Widget _buildLoadingView(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 40),
        child: Column(
          key: const Key('wear_loading_indicator'),
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(
              valueColor: AlwaysStoppedAnimation<Color>(
                FansivibeColors.accentGold,
              ),
            ),
            const SizedBox(height: 24),
            Text(
              'Recording Outfit Wear…',
              style: TextStyle(
                fontFamily: FansivibeTypography.displayFamily,
                fontSize: 20,
                fontWeight: FontWeight.w600,
                color: FansivibeColors.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Updating your wardrobe rotation and wear history.',
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.textSecondary,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSuccessView(
    BuildContext context,
    WearEventLogResponse response,
  ) {
    final count = response.wears.length;
    final message = response.created
        ? 'Your ensemble has been saved to your wardrobe wear history.'
        : 'This ensemble was already recorded for today (idempotent replay).';

    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 24),
        child: Column(
          key: const Key('wear_success_view'),
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                color: FansivibeColors.accentGold.withValues(alpha: 0.15),
                shape: BoxShape.circle,
              ),
              child: Icon(
                Icons.check_circle_rounded,
                color: FansivibeColors.accentGold,
                size: 40,
              ),
            ),
            const SizedBox(height: 20),
            Text(
              'Outfit Recorded!',
              style: TextStyle(
                fontFamily: FansivibeTypography.displayFamily,
                fontSize: 24,
                fontWeight: FontWeight.w600,
                color: FansivibeColors.textPrimary,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              message,
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.textSecondary,
                height: 1.4,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              decoration: BoxDecoration(
                color: FansivibeColors.surfaceContainerHigh,
                borderRadius: BorderRadius.circular(FansivibeRadius.sm),
              ),
              child: Text(
                '$count ${count == 1 ? "garment" : "garments"} updated in rotation',
                style: FansivibeTypography.labelMediumWithFamily.copyWith(
                  color: FansivibeColors.accentGold,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            const SizedBox(height: 28),
            FansiButton.primary(
              key: const Key('wear_success_done_button'),
              label: 'Done',
              icon: Icons.check_rounded,
              onPressed: () => Navigator.of(context).pop(response),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorView(BuildContext context, String message) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 24),
        child: Column(
          key: const Key('wear_error_view'),
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                color: FansivibeColors.error.withValues(alpha: 0.15),
                shape: BoxShape.circle,
              ),
              child: Icon(
                Icons.error_outline_rounded,
                color: FansivibeColors.error,
                size: 32,
              ),
            ),
            const SizedBox(height: 20),
            Text(
              "Couldn't Record Wear",
              style: TextStyle(
                fontFamily: FansivibeTypography.displayFamily,
                fontSize: 20,
                fontWeight: FontWeight.w600,
                color: FansivibeColors.textPrimary,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              message,
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.textSecondary,
                height: 1.4,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            FansiButton.primary(
              key: const Key('wear_error_retry_button'),
              label: 'Try Again',
              icon: Icons.refresh_rounded,
              onPressed: _handleConfirmWear,
            ),
            const SizedBox(height: 10),
            FansiButton.secondary(
              label: 'Dismiss',
              onPressed: () => Navigator.of(context).pop(),
            ),
          ],
        ),
      ),
    );
  }
}
