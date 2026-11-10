import 'dart:async';
import 'package:flutter/material.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_models.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_repository.dart';
import 'package:fansivibe/features/outfit_builder/presentation/widgets/outfit_builder_widgets.dart';
import 'package:fansivibe/features/wardrobe/data/local_wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/widgets/wardrobe_widgets.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

/// Helper function to open the [OutfitSlotSwapSheet] modal bottom sheet.
Future<OutfitRecommendation?> showOutfitSlotSwapSheet({
  required BuildContext context,
  required OutfitRecommendation currentOutfit,
  required OutfitComponent targetComponent,
  required OutfitGenerateRequest request,
  OutfitBuilderRepository? outfitRepository,
  WardrobeRepository? wardrobeRepository,
  Set<String>? pinnedGarmentIds,
}) {
  return showModalBottomSheet<OutfitRecommendation?>(
    context: context,
    isScrollControlled: true,
    backgroundColor: FansivibeColors.surfaceContainerLow,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
    ),
    builder: (sheetContext) => OutfitSlotSwapSheet(
      currentOutfit: currentOutfit,
      targetComponent: targetComponent,
      request: request,
      outfitRepository: outfitRepository,
      wardrobeRepository: wardrobeRepository,
      pinnedGarmentIds: pinnedGarmentIds,
    ),
  );
}

/// Modal bottom sheet allowing users to select an eligible wardrobe replacement
/// for an outfit slot, preview the resulting outfit with recalculated compatibility,
/// and confirm or cancel the swap (Stage 2 P1-1).
class OutfitSlotSwapSheet extends StatefulWidget {
  const OutfitSlotSwapSheet({
    required this.currentOutfit,
    required this.targetComponent,
    required this.request,
    this.outfitRepository,
    this.wardrobeRepository,
    this.pinnedGarmentIds,
    super.key,
  });

  final OutfitRecommendation currentOutfit;
  final OutfitComponent targetComponent;
  final OutfitGenerateRequest request;
  final OutfitBuilderRepository? outfitRepository;
  final WardrobeRepository? wardrobeRepository;
  final Set<String>? pinnedGarmentIds;

  @override
  State<OutfitSlotSwapSheet> createState() => _OutfitSlotSwapSheetState();
}

class _OutfitSlotSwapSheetState extends State<OutfitSlotSwapSheet> {
  late final OutfitBuilderRepository _outfitRepository;
  late final WardrobeRepository _wardrobeRepository;

  bool _loadingCandidates = true;
  String? _candidateError;
  List<WardrobeItemData> _candidates = [];

  WardrobeItemData? _selectedCandidate;
  bool _previewLoading = false;
  String? _previewError;
  OutfitSlotSwapResponse? _previewResponse;

  @override
  void initState() {
    super.initState();
    _outfitRepository =
        widget.outfitRepository ?? OutfitBuilderRepositoryImpl();
    _wardrobeRepository =
        widget.wardrobeRepository ??
        (isGuestUser || !AuthSession.isAuthenticated
            ? LocalWardrobeRepository()
            : WardrobeRepositoryImpl());
    _loadCandidates();
  }

  Future<void> _loadCandidates() async {
    setState(() {
      _loadingCandidates = true;
      _candidateError = null;
    });

    final currentGarmentIds = widget.currentOutfit.components
        .map((c) => c.id)
        .toList();

    try {
      if (isGuestUser || !AuthSession.isAuthenticated) {
        // Guest mode: load strictly from local on-device wardrobe
        final allItems = await _wardrobeRepository.listItems(
          category: widget.targetComponent.category,
        );
        final eligible = allItems
            .where((item) => !currentGarmentIds.contains(item.id))
            .toList();
        if (mounted) {
          setState(() {
            _candidates = eligible;
            _loadingCandidates = false;
          });
        }
        return;
      }

      // Authenticated mode: query backend candidates endpoint
      final apiCandidates = await _outfitRepository.getCandidates(
        slot: widget.targetComponent.category,
        currentGarmentIds: currentGarmentIds,
      );

      if (apiCandidates.isNotEmpty) {
        final mapped = apiCandidates
            .map(
              (c) => WardrobeItemData(
                id: c.id,
                name: c.name,
                category: c.category,
                color: c.color,
                material: c.material,
                isFavorite: c.isFavorite,
                imageRef: c.imageRef != null
                    ? MediaRef.fromJson(c.imageRef!)
                    : null,
                imageUrl: c.imageUrl,
              ),
            )
            .toList();

        if (mounted) {
          setState(() {
            _candidates = mapped;
            _loadingCandidates = false;
          });
        }
        return;
      }

      // Fallback to wardrobe repository listItems for user
      final allItems = await _wardrobeRepository.listItems(
        category: widget.targetComponent.category,
      );
      final eligible = allItems
          .where((item) => !currentGarmentIds.contains(item.id))
          .toList();

      if (mounted) {
        setState(() {
          _candidates = eligible;
          _loadingCandidates = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _candidateError =
              'Unable to load wardrobe alternatives. Please try again.';
          _loadingCandidates = false;
        });
      }
    }
  }

  Future<void> _selectCandidateForPreview(WardrobeItemData candidate) async {
    setState(() {
      _selectedCandidate = candidate;
      _previewLoading = true;
      _previewError = null;
      _previewResponse = null;
    });

    try {
      if (isGuestUser || !AuthSession.isAuthenticated) {
        // Guest mode: compute swap locally without server request
        final updatedComponents = widget.currentOutfit.components.map((c) {
          if (c.id == widget.targetComponent.id) {
            return OutfitComponent(
              id: candidate.id,
              name: candidate.name,
              category: candidate.category,
              color: candidate.color,
              material: candidate.material,
              reason:
                  'Replaced ${widget.targetComponent.name} with your ${candidate.name}',
            );
          }
          return c;
        }).toList();

        final updatedOutfit = OutfitRecommendation(
          title: widget.currentOutfit.title,
          matchScore: widget.currentOutfit.matchScore,
          components: updatedComponents,
          reasons: [
            ...widget.currentOutfit.reasons,
            'Updated with ${candidate.name}',
          ],
          colorHarmony: widget.currentOutfit.colorHarmony,
          bodyFit: widget.currentOutfit.bodyFit,
          occasionMatch: widget.currentOutfit.occasionMatch,
          styleScoreImpact: widget.currentOutfit.styleScoreImpact,
          improvementSuggestion: widget.currentOutfit.improvementSuggestion,
          selectedOccasion: widget.currentOutfit.selectedOccasion,
          selectedMood: widget.currentOutfit.selectedMood,
          selectedColorPalette: widget.currentOutfit.selectedColorPalette,
          snapshot: {
            ...widget.currentOutfit.snapshot,
            'components': updatedComponents.map((c) => c.toJson()).toList(),
          },
        );

        if (mounted) {
          setState(() {
            _previewResponse = OutfitSlotSwapResponse(
              outfit: updatedOutfit,
              replacedSlot: widget.targetComponent.category,
              replacementGarmentId: candidate.id,
              previousGarmentId: widget.targetComponent.id,
              compatibilityScore: updatedOutfit.matchScore,
              previousCompatibilityScore: widget.currentOutfit.matchScore,
              reasons: updatedOutfit.reasons,
            );
            _previewLoading = false;
          });
        }
        return;
      }

      // Authenticated mode: call backend swap-slot endpoint
      final currentIds = widget.currentOutfit.components
          .map((c) => c.id)
          .toList();
      final swapReq = OutfitSlotSwapRequest(
        occasion: widget.request.occasion,
        mood: widget.request.mood,
        fit: widget.request.fit,
        colorPalette: widget.request.colorPalette,
        currentGarmentIds: currentIds,
        slot: widget.targetComponent.category,
        replacementGarmentId: candidate.id,
        pinnedGarmentIds: widget.pinnedGarmentIds?.toList(),
      );

      final response = await _outfitRepository.swapSlot(request: swapReq);

      if (!mounted) return;

      if (response != null) {
        setState(() {
          _previewResponse = response;
          _previewLoading = false;
        });
      } else {
        setState(() {
          _previewError =
              'Compatibility recalculation failed. Please try again.';
          _previewLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _previewError =
              'Failed to preview replacement. Please check your connection.';
          _previewLoading = false;
        });
      }
    }
  }

  void _confirmReplacement() {
    if (_previewResponse != null) {
      Navigator.of(context).pop(_previewResponse!.outfit);
    }
  }

  void _cancelPreview() {
    setState(() {
      _selectedCandidate = null;
      _previewResponse = null;
      _previewError = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isPreviewMode = _selectedCandidate != null;

    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.85,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const SizedBox(height: 12),
            Center(
              child: Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(
                  color: FansivibeColors.textSecondary.withValues(alpha: 0.3),
                  borderRadius: FansivibeRadius.fullBorder,
                ),
              ),
            ),
            const SizedBox(height: 16),
            Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: FansivibeSpacing.lg,
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          isPreviewMode
                              ? 'Preview Component Swap'
                              : 'Replace ${widget.targetComponent.name}',
                          style: theme.textTheme.headlineSmall?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: FansivibeColors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          isPreviewMode
                              ? 'Review compatibility before confirming'
                              : 'Select an alternative from your wardrobe (${widget.targetComponent.category})',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(
                      Icons.close_rounded,
                      color: FansivibeColors.textSecondary,
                    ),
                    onPressed: () => Navigator.of(context).pop(null),
                  ),
                ],
              ),
            ),
            const Divider(
              color: FansivibeColors.surfaceContainerHigh,
              height: 24,
            ),
            Expanded(
              child: isPreviewMode
                  ? _buildPreviewView(theme)
                  : _buildCandidatesView(theme),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCandidatesView(ThemeData theme) {
    if (_loadingCandidates) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32.0),
          child: CircularProgressIndicator(color: FansivibeColors.accentGold),
        ),
      );
    }

    if (_candidateError != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.error_outline_rounded,
                color: FansivibeColors.error,
                size: 40,
              ),
              const SizedBox(height: 12),
              Text(
                _candidateError!,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              FansiButton.secondary(
                label: 'Retry',
                onPressed: _loadCandidates,
                expanded: false,
              ),
            ],
          ),
        ),
      );
    }

    if (_candidates.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.checkroom_outlined,
                size: 48,
                color: FansivibeColors.accentGold.withValues(alpha: 0.6),
              ),
              const SizedBox(height: 16),
              Text(
                'No alternative ${widget.targetComponent.category} found',
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.textPrimary,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'You don\'t have other ${widget.targetComponent.category} pieces in your wardrobe to replace this slot.',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),
              FansiButton.secondary(
                label: 'Close',
                onPressed: () => Navigator.of(context).pop(null),
                expanded: false,
              ),
            ],
          ),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.symmetric(
        horizontal: FansivibeSpacing.lg,
        vertical: 8,
      ),
      itemCount: _candidates.length,
      itemBuilder: (context, index) {
        final item = _candidates[index];
        return _buildCandidateCard(item, theme);
      },
    );
  }

  Widget _buildCandidateCard(WardrobeItemData item, ThemeData theme) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: FansivibeRadius.smdBorder,
        border: Border.all(
          color: FansivibeColors.textSecondary.withValues(alpha: 0.15),
        ),
      ),
      child: InkWell(
        borderRadius: FansivibeRadius.smdBorder,
        onTap: () => _selectCandidateForPreview(item),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              ClipRRect(
                borderRadius: FansivibeRadius.smBorder,
                child: SizedBox(
                  width: 60,
                  height: 60,
                  child: WardrobeItemImage(item: item, iconSize: 28),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            item.name,
                            style: theme.textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.w600,
                              color: FansivibeColors.textPrimary,
                            ),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        if (item.isFavorite)
                          const Icon(
                            Icons.favorite_rounded,
                            size: 14,
                            color: FansivibeColors.primary,
                          ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${item.color}${item.material != null ? ' \u2022 ${item.material}' : ''}',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: FansivibeColors.textSecondary,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              FansiButton.secondary(
                label: 'Preview',
                onPressed: () => _selectCandidateForPreview(item),
                expanded: false,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPreviewView(ThemeData theme) {
    if (_previewLoading) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(color: FansivibeColors.accentGold),
            const SizedBox(height: 16),
            Text(
              'Recalculating outfit compatibility…',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
            ),
          ],
        ),
      );
    }

    if (_previewError != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.error_outline_rounded,
                color: FansivibeColors.error,
                size: 40,
              ),
              const SizedBox(height: 12),
              Text(
                _previewError!,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  FansiButton.secondary(
                    label: 'Back',
                    onPressed: _cancelPreview,
                    expanded: false,
                  ),
                  const SizedBox(width: 12),
                  FansiButton.primary(
                    label: 'Retry',
                    onPressed: () =>
                        _selectCandidateForPreview(_selectedCandidate!),
                    expanded: false,
                  ),
                ],
              ),
            ],
          ),
        ),
      );
    }

    final resp = _previewResponse;
    if (resp == null) return const SizedBox.shrink();

    final prevScorePercent = resp.previousCompatibilityScore != null
        ? (resp.previousCompatibilityScore! * 100).round()
        : null;
    final newScorePercent = (resp.compatibilityScore * 100).round();

    return SingleChildScrollView(
      physics: const BouncingScrollPhysics(),
      padding: const EdgeInsets.symmetric(
        horizontal: FansivibeSpacing.lg,
        vertical: 8,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Before / After comparison card
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: FansivibeColors.surface,
              borderRadius: FansivibeRadius.smdBorder,
              border: Border.all(
                color: FansivibeColors.accentGold.withValues(alpha: 0.3),
              ),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'CURRENT',
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: FansivibeColors.textSecondary,
                          letterSpacing: 1.1,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        widget.targetComponent.name,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          fontWeight: FontWeight.w500,
                          color: FansivibeColors.textPrimary,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                      Text(
                        widget.targetComponent.color,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: FansivibeColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: Icon(
                    Icons.arrow_forward_rounded,
                    color: FansivibeColors.accentGold,
                    size: 24,
                  ),
                ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'REPLACEMENT',
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: FansivibeColors.accentGold,
                          letterSpacing: 1.1,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        _selectedCandidate!.name,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          fontWeight: FontWeight.w600,
                          color: FansivibeColors.textPrimary,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                      Text(
                        _selectedCandidate!.color,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: FansivibeColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // Compatibility Score Card
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: FansivibeColors.surface,
              borderRadius: FansivibeRadius.smdBorder,
            ),
            child: Row(
              children: [
                ScoreCircle(
                  score: resp.compatibilityScore,
                  label: 'Match Score',
                ),
                const SizedBox(width: 18),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Recalculated Compatibility',
                        style: theme.textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w600,
                          color: FansivibeColors.textPrimary,
                        ),
                      ),
                      const SizedBox(height: 4),
                      if (prevScorePercent != null)
                        Text(
                          newScorePercent >= prevScorePercent
                              ? 'Compatibility improves by ${newScorePercent - prevScorePercent}%'
                              : 'Compatibility changes from $prevScorePercent% to $newScorePercent%',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: newScorePercent >= prevScorePercent
                                ? FansivibeColors.success
                                : FansivibeColors.textSecondary,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      const SizedBox(height: 4),
                      Text(
                        resp.outfit.occasionMatch,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: FansivibeColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // Updated Reasons
          if (resp.reasons.isNotEmpty) ...[
            Text(
              'Updated Outfit Harmony',
              style: theme.textTheme.titleSmall?.copyWith(
                fontWeight: FontWeight.w600,
                color: FansivibeColors.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            ...resp.reasons
                .take(3)
                .map(
                  (r) => Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(
                          Icons.check_circle_rounded,
                          size: 16,
                          color: FansivibeColors.accentGold,
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            r,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: FansivibeColors.textPrimary,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
          ],

          const SizedBox(height: 24),

          // Confirm / Change Buttons
          FansiButton.primary(
            label: 'Confirm Replacement',
            icon: Icons.check_rounded,
            onPressed: _confirmReplacement,
          ),
          const SizedBox(height: 10),
          FansiButton.secondary(
            label: 'Choose Different Item',
            icon: Icons.swap_horiz_rounded,
            onPressed: _cancelPreview,
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}
