import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/profile/data/saved_looks_models.dart';
import 'package:fansivibe/features/profile/data/saved_looks_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/ensemble_wear_confirmation_sheet.dart';
import 'package:fansivibe/features/wardrobe/presentation/widgets/wardrobe_widgets.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/components/fansi_badge.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

/// Dedicated Saved Look Detail Screen (Stage 2 P1-2).
///
/// Displays the complete ensemble, hydrated garments with actual thumbnails,
/// snapshot attributes, clear archived garment indicators, active wardrobe
/// navigation, and direct Log Wear Today action reusing the P0-1 workflow.
class SavedLookDetailsScreen extends StatefulWidget {
  const SavedLookDetailsScreen({
    this.look,
    this.savedLooksRepository,
    this.wardrobeRepository,
    super.key,
  });

  /// The saved look to display.
  final SavedLookItem? look;

  /// Optional repository override for tests.
  final SavedLooksRepository? savedLooksRepository;

  /// Optional wardrobe repository override for wear logging.
  final WardrobeRepository? wardrobeRepository;

  @override
  State<SavedLookDetailsScreen> createState() => _SavedLookDetailsScreenState();
}

class _SavedLookDetailsScreenState extends State<SavedLookDetailsScreen> {
  late final SavedLooksRepository _savedLooksRepository;
  late final WardrobeRepository _wardrobeRepository;

  bool _isDeleting = false;
  bool _isWornToday = false;

  @override
  void initState() {
    super.initState();
    _savedLooksRepository =
        widget.savedLooksRepository ?? SavedLooksRepositoryImpl();
    _wardrobeRepository = widget.wardrobeRepository ?? WardrobeRepositoryImpl();
  }

  int? _computeScore(SavedLookItem look) {
    final raw = look.snapshot['matchScore'];
    if (raw is num) {
      final val = raw.toDouble();
      return (val <= 1.0 ? val * 100 : val).round();
    }
    return null;
  }

  String get _eyebrow {
    return switch (widget.look?.sourceContext) {
      'grooming' => 'GROOMING LOOK',
      'hairstyle' => 'HAIRSTYLE LOOK',
      'outfit' => 'OUTFIT LOOK',
      _ => 'SAVED LOOK',
    };
  }

  Future<void> _handleLogWearToday() async {
    final look = widget.look;
    if (look == null) return;

    if (isGuestUser || !AuthSession.isAuthenticated) {
      promptGuestSignIn(
        context,
        action: 'Sign in to log wears. Browsing stays free.',
      );
      return;
    }

    final activeGarments =
        look.items?.where((item) => !item.isArchived).toList() ?? [];

    if (activeGarments.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Cannot log wear: all ensemble pieces have been archived.',
          ),
        ),
      );
      return;
    }

    final ensembleGarments = activeGarments
        .map(
          (g) => EnsembleWearGarment(
            id: g.id,
            name: g.name,
            category: g.category,
            color: g.color,
            material: g.material,
          ),
        )
        .toList();

    final result = await showEnsembleWearConfirmationSheet(
      context: context,
      outfitTitle: look.title.isNotEmpty ? look.title : 'Saved Ensemble',
      garments: ensembleGarments,
      wardrobeRepository: _wardrobeRepository,
    );

    if (result != null && mounted) {
      setState(() {
        _isWornToday = true;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Look successfully logged as worn today!'),
          backgroundColor: FansivibeColors.accentGold,
        ),
      );
    }
  }

  Future<void> _handleDelete() async {
    final look = widget.look;
    if (look == null || _isDeleting) return;

    setState(() => _isDeleting = true);
    final outcome = await _savedLooksRepository.deleteSavedLook(id: look.id);
    if (!mounted) return;

    if (outcome != null) {
      if (Navigator.of(context).canPop()) {
        Navigator.of(context).pop(true);
      }
    } else {
      setState(() => _isDeleting = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Could not remove saved look. Please retry.'),
        ),
      );
    }
  }

  void _onGarmentTap(HydratedGarmentItem garment) {
    if (garment.isArchived) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('This piece was removed from your wardrobe.'),
          duration: Duration(seconds: 2),
        ),
      );
      return;
    }

    context.pushNamed(RouteNames.wardrobeItemDetails, extra: garment.id);
  }

  Widget _buildGarmentCard(HydratedGarmentItem garment) {
    return Container(
      margin: const EdgeInsets.only(bottom: FansivibeSpacing.md),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.mdBorder,
        border: Border.all(
          color: garment.isArchived
              ? FansivibeColors.outlineVariant.withValues(alpha: 0.3)
              : Colors.transparent,
        ),
      ),
      child: Material(
        color: Colors.transparent,
        borderRadius: FansivibeRadius.mdBorder,
        child: InkWell(
          borderRadius: FansivibeRadius.mdBorder,
          onTap: () => _onGarmentTap(garment),
          child: Padding(
            padding: const EdgeInsets.all(FansivibeSpacing.md),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ClipRRect(
                  borderRadius: FansivibeRadius.smBorder,
                  child: SizedBox(
                    width: 72,
                    height: 72,
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        WardrobeItemImage(
                          item: garment.toWardrobeItemData(),
                          iconSize: 28,
                        ),
                        if (garment.isArchived)
                          Container(
                            color: FansivibeColors.surface.withValues(
                              alpha: 0.45,
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: FansivibeSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              garment.name,
                              style: FansivibeTypography.bodyLargeWithFamily
                                  .copyWith(
                                    color: garment.isArchived
                                        ? FansivibeColors.textSecondary
                                        : FansivibeColors.textPrimary,
                                    fontWeight: FontWeight.w600,
                                  ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          if (garment.isFavorite) ...[
                            const SizedBox(width: 6),
                            const Icon(
                              Icons.favorite_rounded,
                              size: 16,
                              color: FansivibeColors.accentGold,
                            ),
                          ],
                        ],
                      ),
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          Text(
                            garment.category.toUpperCase(),
                            style: FansivibeTypography.labelSmallWithFamily
                                .copyWith(
                                  color: FansivibeColors.textSecondary,
                                  letterSpacing: 0.8,
                                ),
                          ),
                          if (garment.color.isNotEmpty) ...[
                            Text(
                              ' • ',
                              style: FansivibeTypography.labelSmallWithFamily
                                  .copyWith(
                                    color: FansivibeColors.textSecondary
                                        .withValues(alpha: 0.6),
                                  ),
                            ),
                            Text(
                              garment.color,
                              style: FansivibeTypography.labelSmallWithFamily
                                  .copyWith(
                                    color: FansivibeColors.textSecondary,
                                  ),
                            ),
                          ],
                          if (garment.material != null &&
                              garment.material!.isNotEmpty) ...[
                            Text(
                              ' • ',
                              style: FansivibeTypography.labelSmallWithFamily
                                  .copyWith(
                                    color: FansivibeColors.textSecondary
                                        .withValues(alpha: 0.6),
                                  ),
                            ),
                            Text(
                              garment.material!,
                              style: FansivibeTypography.labelSmallWithFamily
                                  .copyWith(
                                    color: FansivibeColors.textSecondary,
                                  ),
                            ),
                          ],
                        ],
                      ),
                      if (garment.reason != null &&
                          garment.reason!.isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Text(
                          garment.reason!,
                          style: FansivibeTypography.bodyMediumWithFamily
                              .copyWith(
                                fontSize: 12,
                                color: FansivibeColors.textSecondary,
                                fontStyle: FontStyle.italic,
                              ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                      if (garment.isArchived) ...[
                        const SizedBox(height: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: FansivibeSpacing.sm,
                            vertical: 3,
                          ),
                          decoration: BoxDecoration(
                            color: FansivibeColors.accentGold.withValues(
                              alpha: 0.15,
                            ),
                            borderRadius: FansivibeRadius.xsBorder,
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(
                                Icons.archive_outlined,
                                size: 12,
                                color: FansivibeColors.accentGold,
                              ),
                              const SizedBox(width: 4),
                              Text(
                                'Archived piece (no longer in wardrobe)',
                                style: FansivibeTypography.labelSmallWithFamily
                                    .copyWith(
                                      color: FansivibeColors.accentGold,
                                      fontWeight: FontWeight.w600,
                                    ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                if (!garment.isArchived) ...[
                  const SizedBox(width: FansivibeSpacing.sm),
                  Icon(
                    Icons.chevron_right_rounded,
                    color: FansivibeColors.textSecondary.withValues(alpha: 0.6),
                    size: 20,
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final look = widget.look;
    if (look == null) {
      return Scaffold(
        backgroundColor: FansivibeColors.surface,
        appBar: AppBar(
          backgroundColor: FansivibeColors.surface,
          elevation: 0,
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_rounded),
            onPressed: () => Navigator.of(context).pop(),
          ),
        ),
        body: const Center(child: Text('Saved look details not available.')),
      );
    }

    final score = _computeScore(look);
    final items = look.items ?? const [];
    final reasons =
        (look.snapshot['reasons'] as List<dynamic>?)
            ?.map((e) => e.toString())
            .toList() ??
        const [];
    final occasion =
        look.snapshot['occasionMatch'] as String? ??
        look.snapshot['occasion'] as String?;
    final colorHarmony = look.snapshot['colorHarmony'] as String?;

    final activeGarments = items.where((g) => !g.isArchived).toList();
    final canLogWear = activeGarments.isNotEmpty && !_isWornToday;

    return Scaffold(
      backgroundColor: FansivibeColors.surface,
      appBar: AppBar(
        backgroundColor: FansivibeColors.surface,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Text(
          _eyebrow,
          style: FansivibeTypography.labelMediumWithFamily.copyWith(
            color: FansivibeColors.textSecondary,
            letterSpacing: 1.2,
          ),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.delete_outline_rounded),
            tooltip: 'Remove Look',
            onPressed: _isDeleting ? null : _handleDelete,
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(
          horizontal: FansivibeSpacing.lg,
          vertical: FansivibeSpacing.md,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Title & Score Header
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        look.title.isNotEmpty ? look.title : 'Untitled Look',
                        style: FansivibeTypography.headlineMediumWithFamily,
                      ),
                      if (look.sourceRunId != null) ...[
                        const SizedBox(height: 4),
                        Text(
                          'From run ${look.sourceRunId}',
                          style: FansivibeTypography.bodyMediumWithFamily
                              .copyWith(
                                fontSize: 12,
                                color: FansivibeColors.textSecondary,
                              ),
                        ),
                      ],
                    ],
                  ),
                ),
                if (score != null) ...[
                  const SizedBox(width: FansivibeSpacing.md),
                  FansiBadge(score: score),
                ],
              ],
            ),
            const SizedBox(height: FansivibeSpacing.lg),

            // Style notes / Occasion chips
            if (occasion != null || colorHarmony != null) ...[
              Wrap(
                spacing: FansivibeSpacing.sm,
                runSpacing: FansivibeSpacing.sm,
                children: [
                  if (occasion != null)
                    Chip(
                      backgroundColor: FansivibeColors.surfaceContainerLow,
                      label: Text(
                        occasion,
                        style: FansivibeTypography.labelMediumWithFamily
                            .copyWith(color: FansivibeColors.textPrimary),
                      ),
                      side: BorderSide.none,
                    ),
                  if (colorHarmony != null)
                    Chip(
                      backgroundColor: FansivibeColors.surfaceContainerLow,
                      label: Text(
                        colorHarmony,
                        style: FansivibeTypography.labelMediumWithFamily
                            .copyWith(color: FansivibeColors.textPrimary),
                      ),
                      side: BorderSide.none,
                    ),
                ],
              ),
              const SizedBox(height: FansivibeSpacing.lg),
            ],

            // Reasons section
            if (reasons.isNotEmpty) ...[
              Container(
                padding: const EdgeInsets.all(FansivibeSpacing.md),
                decoration: BoxDecoration(
                  color: FansivibeColors.surfaceContainerLowest,
                  borderRadius: FansivibeRadius.mdBorder,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'WHY THIS WORKS',
                      style: FansivibeTypography.labelSmallWithFamily.copyWith(
                        color: FansivibeColors.accentGold,
                        letterSpacing: 1.0,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: FansivibeSpacing.sm),
                    for (final reason in reasons)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 4),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '• ',
                              style: FansivibeTypography.bodyMediumWithFamily
                                  .copyWith(color: FansivibeColors.accentGold),
                            ),
                            Expanded(
                              child: Text(
                                reason,
                                style: FansivibeTypography.bodyMediumWithFamily
                                    .copyWith(
                                      color: FansivibeColors.textSecondary,
                                      height: 1.4,
                                    ),
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: FansivibeSpacing.xl),
            ],

            // Garments Header
            Row(
              children: [
                Text(
                  'Ensemble Pieces',
                  style: FansivibeTypography.titleLargeWithFamily,
                ),
                const SizedBox(width: FansivibeSpacing.sm),
                Text(
                  '(${items.length})',
                  style: FansivibeTypography.titleLargeWithFamily.copyWith(
                    color: FansivibeColors.textSecondary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: FansivibeSpacing.md),

            // Garments List
            if (items.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(
                  vertical: FansivibeSpacing.lg,
                ),
                child: Text(
                  'No garment items recorded in this saved look.',
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.textSecondary,
                  ),
                ),
              )
            else
              for (final garment in items) _buildGarmentCard(garment),

            const SizedBox(height: FansivibeSpacing.xl),

            // Actions
            if (look.sourceContext == 'outfit' ||
                look.sourceContext == 'daily') ...[
              FansiButton.primary(
                label: _isWornToday ? 'Worn Today ✓' : 'Log Wear Today',
                icon: Icons.checkroom_rounded,
                onPressed: canLogWear ? _handleLogWearToday : null,
              ),
              const SizedBox(height: FansivibeSpacing.md),
            ],

            FansiButton.tertiary(
              label: _isDeleting ? 'Removing…' : 'Remove from Saved Looks',
              onPressed: _isDeleting ? null : _handleDelete,
            ),
            const SizedBox(height: FansivibeSpacing.xxl),
          ],
        ),
      ),
    );
  }
}
