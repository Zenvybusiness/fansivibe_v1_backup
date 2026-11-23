import 'dart:async';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_client.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_models.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_repository.dart';
import 'package:fansivibe/features/outfit_builder/presentation/widgets/outfit_builder_widgets.dart';
import 'package:fansivibe/features/outfit_builder/presentation/widgets/outfit_slot_swap_sheet.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';

import 'package:fansivibe/features/wardrobe/presentation/ensemble_wear_confirmation_sheet.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansi_hero_card.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/components/fansi_insight_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

/// Step 3 of the builder flow: renders one backend-derived outfit
/// verbatim (M13, UC-28/29/30).
///
/// The [recommendation] arrives from the generation surface (never
/// mocked here); [request] carries the step-1 prefs so Regenerate can
/// re-derive with the next deterministic seed (`outfit-1`, `outfit-2`,
/// … — same seed repeats the backend result, no randomness introduced).
/// Save uses `POST /v1/outfits/saved` with `sourceContext: "outfit"`,
/// the response snapshot verbatim, and one fresh `Idempotency-Key` per
/// attempt. Wear logging uses `POST /v1/wardrobe/wears` via
/// [WardrobeRepository.logEnsembleWear] with explicit review before confirmation.
class OutfitRecommendationScreen extends StatefulWidget {
  const OutfitRecommendationScreen({
    required this.recommendation,
    required this.request,
    this.candidates,
    this.outfitRepository,
    this.wardrobeRepository,
    super.key,
  });

  /// Backend-derived outfit to render (verbatim server data).
  final OutfitRecommendation recommendation;

  /// Optional list of multiple candidate outfits (Phase 3).
  final List<OutfitCandidate>? candidates;

  /// Step-1 prefs backing Regenerate (ids verbatim).
  final OutfitGenerateRequest request;

  /// Backend outfit source. Defaults to the live repository; tests
  /// inject a fake.
  final OutfitBuilderRepository? outfitRepository;

  /// Backend wardrobe source for wear logging. Defaults to the live repository;
  /// tests inject a fake.
  final WardrobeRepository? wardrobeRepository;

  @override
  State<OutfitRecommendationScreen> createState() =>
      _OutfitRecommendationScreenState();
}

class _OutfitRecommendationScreenState
    extends State<OutfitRecommendationScreen> {
  late final OutfitBuilderRepository _repository;
  late final WardrobeRepository _wardrobeRepository;
  late OutfitRecommendation _rec;
  late List<OutfitCandidate> _candidates;
  int _selectedCandidateIndex = 0;

  bool _regenerating = false;
  int _regenCount = 0;

  bool _saving = false;
  bool _saved = false;
  bool _worn = false;
  final Set<String> _pinnedGarmentIds = <String>{};

  void _handleTogglePin(String garmentId) {
    setState(() {
      if (_pinnedGarmentIds.contains(garmentId)) {
        _pinnedGarmentIds.remove(garmentId);
        _showSnackBar('Piece unpinned');
      } else {
        _pinnedGarmentIds.add(garmentId);
        _showSnackBar('Piece pinned (preserved during swaps)');
      }
    });
  }

  void _selectCandidate(int index) {
    if (index < 0 || index >= _candidates.length) return;
    setState(() {
      _selectedCandidateIndex = index;
      _rec = _candidates[index].toRecommendation();
      _saved = false;
      _worn = false;
    });
  }

  Future<void> _handleReplaceSlot(OutfitComponent component) async {
    if (_pinnedGarmentIds.contains(component.id)) {
      _showSnackBar('This piece is pinned. Unpin it first to replace.');
      return;
    }
    if (_saving || _regenerating) return;

    final updatedOutfit = await showOutfitSlotSwapSheet(
      context: context,
      currentOutfit: _rec,
      targetComponent: component,
      request: widget.request,
      outfitRepository: _repository,
      wardrobeRepository: _wardrobeRepository,
      pinnedGarmentIds: _pinnedGarmentIds,
    );

    if (!mounted || updatedOutfit == null) return;

    setState(() {
      _rec = updatedOutfit;
      if (_selectedCandidateIndex < _candidates.length) {
        _candidates[_selectedCandidateIndex] = updatedOutfit.toCandidate(
          id: _candidates[_selectedCandidateIndex].id,
        );
      }
      _saved = false;
      _worn = false;
    });
    _showSnackBar('Outfit updated with replacement piece');
  }

  @override
  void initState() {
    super.initState();
    _repository = widget.outfitRepository ?? OutfitBuilderRepositoryImpl();
    _wardrobeRepository = widget.wardrobeRepository ?? WardrobeRepositoryImpl();
    _rec = widget.recommendation;
    if (widget.candidates != null && widget.candidates!.isNotEmpty) {
      _candidates = List.from(widget.candidates!);
    } else {
      _candidates = [_rec.toCandidate()];
    }
    _selectedCandidateIndex = 0;
  }

  /// Regenerates via `POST /v1/outfits/compose` or `POST /v1/outfits/generate` with the same prefs and
  /// the next deterministic seed. Guarded while any request is pending;
  /// the UI only updates when the response arrives (never
  /// optimistically). A failed regeneration keeps the current outfit
  /// visible with truthful feedback.
  Future<void> _handleRegenerate() async {
    if (_regenerating || _saving) return;
    setState(() => _regenerating = true);
    _regenCount += 1;

    // Try multi-candidate composition first
    final compResult = await _repository.composeOutfits(
      occasion: widget.request.occasion,
      mood: widget.request.mood,
      fit: widget.request.fit,
      colorPalette: widget.request.colorPalette,
      seed: 'outfit-$_regenCount',
      preferredItemIds: widget.request.preferredItemIds,
    );

    if (!mounted) return;
    if (compResult.available &&
        compResult.composition != null &&
        compResult.composition!.candidates.isNotEmpty) {
      setState(() {
        _candidates = compResult.composition!.candidates;
        _selectedCandidateIndex = 0;
        _rec = _candidates[0].toRecommendation();
        _regenerating = false;
        _saved = false;
        _worn = false;
      });
      return;
    }

    // Fallback to single generateOutfit (for test doubles that only stub generateOutfit)
    final result = await _repository.generateOutfit(
      occasion: widget.request.occasion,
      mood: widget.request.mood,
      fit: widget.request.fit,
      colorPalette: widget.request.colorPalette,
      seed: 'outfit-$_regenCount',
      preferredItemIds: widget.request.preferredItemIds,
    );
    if (!mounted) return;
    if (result.available && result.outfit != null) {
      setState(() {
        _rec = result.outfit!;
        _candidates = [_rec.toCandidate()];
        _selectedCandidateIndex = 0;
        _regenerating = false;
        _saved = false;
        _worn = false;
      });
    } else {
      setState(() => _regenerating = false);
      _showSnackBar(_regenerateErrorMessage(result));
    }
  }

  String _regenerateErrorMessage(OutfitResult result) {
    if (result.noneAvailable) {
      return 'No alternative outfit available right now.';
    }
    switch (result.failure) {
      case OutfitFailure.serviceUnavailable:
        return 'Style service unavailable. Please try again.';
      case OutfitFailure.rateLimited:
        return 'Too many requests. Please wait and try again.';
      case OutfitFailure.networkError:
        return 'Couldn\'t regenerate. Please check your connection.';
      default:
        return 'Couldn\'t regenerate this outfit. Please try again.';
    }
  }

  /// Saves via `POST /v1/outfits/saved` (`sourceContext: "outfit"`,
  /// snapshot verbatim, fresh Idempotency-Key per attempt). Guarded
  /// while any request is pending and disabled once saved, so repeated
  /// taps never duplicate the save. A failed save keeps the outfit
  /// visible with truthful retry feedback. Never logs a wear event.
  Future<void> _handleSave() async {
    if (_saving || _regenerating || _saved) return;
    final title = _rec.title.trim();
    if (title.isEmpty || title.length > 200) {
      _showSnackBar('This outfit can\'t be saved (invalid title).');
      return;
    }
    setState(() => _saving = true);
    final saved = await _repository.saveOutfit(
      title: _rec.title,
      snapshot: _rec.snapshot,
      idempotencyKey: newOutfitBuilderIdempotencyKey(),
    );
    if (!mounted) return;
    setState(() => _saving = false);
    if (saved != null) {
      setState(() => _saved = true);
      _showSnackBar('Outfit saved');
    } else {
      _showSnackBar('Couldn\'t save this outfit. Please try again.');
    }
  }

  /// Opens the ensemble wear confirmation sheet to review and persist
  /// this recommended outfit as worn (Phase 4 of Stage 2 P0-1).
  Future<void> _handleLogWear() async {
    if (isGuestUser || !AuthSession.isAuthenticated) {
      promptGuestSignIn(
        context,
        action: 'Sign in to log wears. Browsing stays free.',
      );
      return;
    }
    if (_saving || _regenerating || _worn) return;

    final garments = _rec.components
        .map(
          (c) => EnsembleWearGarment(
            id: c.id,
            name: c.name,
            category: c.category,
            color: c.color,
            material: c.material,
          ),
        )
        .toList();

    if (garments.isEmpty) {
      _showSnackBar('Cannot log wear: outfit contains no garments.');
      return;
    }

    final response = await showEnsembleWearConfirmationSheet(
      context: context,
      outfitTitle: _rec.title,
      garments: garments,
      wardrobeRepository: _wardrobeRepository,
    );

    if (!mounted || response == null) return;

    setState(() {
      _worn = true;
    });

    unawaited(_wardrobeRepository.getWearSummary());

    _showSnackBar(
      response.created
          ? 'Ensemble recorded in wear history'
          : 'Ensemble already recorded for today',
    );
  }

  void _showSnackBar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.smdBorder),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final rec = _rec;
    final busy = _regenerating || _saving;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Your Outfit'),
        leading: IconButton(
          icon: Icon(
            Icons.arrow_back_rounded,
            color: FansivibeColors.textPrimary,
          ),
          onPressed: () => Navigator.of(context).pop(),
        ),
        actions: [
          IconButton(
            key: const Key('btn_view_saved_outfits_nav'),
            icon: const Icon(
              Icons.bookmark_outline_rounded,
              color: FansivibeColors.accentGold,
            ),
            tooltip: 'Saved Outfits',
            onPressed: () => context.pushNamed(RouteNames.profileSavedLooks),
          ),
        ],
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 20.0;
            final contentMaxWidth = maxWidth > 600 ? 560.0 : double.infinity;
            final activeCand = _selectedCandidateIndex < _candidates.length
                ? _candidates[_selectedCandidateIndex]
                : null;

            return SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              child: Center(
                child: ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: contentMaxWidth),
                  child: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: horizontalPadding,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SizedBox(height: 8),

                        // Multiple Candidates Selector
                        _buildCandidateSelector(context),

                        // Header hero card
                        FansiHeroCard(
                          eyebrow: 'OUTFIT RECOMMENDATION',
                          image: FansiImageWell(
                            icon: Icons.checkroom_rounded,
                            color: FansivibeColors.accentGold,
                          ),
                          title: rec.title,
                          subtitle:
                              '${rec.selectedOccasion} \u2022 ${rec.selectedMood} \u2022 ${rec.selectedColorPalette}',
                        ),
                        const SizedBox(height: 24),

                        // Match Score
                        Center(
                          child: ScoreCircle(
                            score: rec.matchScore,
                            label: 'Match Score',
                          ),
                        ),
                        const SizedBox(height: 16),

                        // Documented score breakdown calculation
                        if (activeCand?.scoreBreakdown != null) ...[
                          ScoreBreakdownCard(
                            breakdown: activeCand!.scoreBreakdown!,
                          ),
                          const SizedBox(height: 24),
                        ],

                        // Outfit Components
                        _buildComponentsSection(context, rec),
                        const SizedBox(height: 24),

                        // Missing pieces / suggested additions
                        if (activeCand != null &&
                            activeCand.missingPieces.isNotEmpty) ...[
                          MissingPiecesSection(
                            missingPieces: activeCand.missingPieces,
                          ),
                          const SizedBox(height: 24),
                        ],

                        // Recommendation Reasons
                        _buildReasonsSection(context, rec),
                        const SizedBox(height: 24),

                        // Styling Rationale & Tips
                        if (activeCand != null) ...[
                          _buildStylingRationaleSection(context, activeCand),
                          const SizedBox(height: 24),
                          _buildStylingTipsSection(context, activeCand),
                          const SizedBox(height: 24),
                        ],

                        // Metrics
                        _buildMetricsSection(context, rec),
                        const SizedBox(height: 24),

                        // Ensemble Match impact
                        _buildImpactCard(context, rec),
                        const SizedBox(height: 12),

                        // Improvement suggestion
                        _buildImprovementCard(context, rec),
                        const SizedBox(height: 28),

                        // Actions
                        _buildActions(context, busy: busy),
                        const SizedBox(height: 32),
                      ],
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildCandidateSelector(BuildContext context) {
    if (_candidates.length <= 1) return const SizedBox.shrink();
    return Container(
      margin: const EdgeInsets.only(bottom: 20),
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.2),
        ),
      ),
      child: Row(
        children: List.generate(_candidates.length, (index) {
          final isSelected = index == _selectedCandidateIndex;
          final cand = _candidates[index];
          final pct = (cand.matchScore * 100).round();
          return Expanded(
            child: InkWell(
              key: Key('candidate_tab_$index'),
              onTap: () => _selectCandidate(index),
              borderRadius: BorderRadius.circular(10),
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 8),
                decoration: BoxDecoration(
                  color: isSelected
                      ? FansivibeColors.accentGold.withValues(alpha: 0.15)
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(10),
                  border: isSelected
                      ? Border.all(
                          color: FansivibeColors.accentGold.withValues(alpha: 0.6),
                        )
                      : null,
                ),
                child: Column(
                  children: [
                    Text(
                      'Look ${index + 1}',
                      style: TextStyle(
                        color: isSelected
                            ? FansivibeColors.accentGold
                            : FansivibeColors.textSecondary,
                        fontWeight:
                            isSelected ? FontWeight.bold : FontWeight.w500,
                        fontSize: 13,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '$pct% match',
                      style: TextStyle(
                        color: isSelected
                            ? FansivibeColors.textPrimary
                            : FansivibeColors.textSecondary.withValues(alpha: 0.6),
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        }),
      ),
    );
  }

  Widget _buildStylingRationaleSection(
    BuildContext context,
    OutfitCandidate cand,
  ) {
    if (cand.stylingRationale.isEmpty) return const SizedBox.shrink();
    return FansiInsightCard(
      icon: Icons.lightbulb_rounded,
      title: 'Styling Rationale',
      body: cand.stylingRationale,
      accentColor: FansivibeColors.accentGold,
    );
  }

  Widget _buildStylingTipsSection(
    BuildContext context,
    OutfitCandidate cand,
  ) {
    if (cand.stylingTips.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(
              Icons.style_outlined,
              size: 20,
              color: FansivibeColors.accentGold,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                'Practical Styling Tips',
                style: theme.textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.textPrimary,
                  fontSize: 20,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        ...cand.stylingTips.map(
          (tip) => Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(
                  Icons.arrow_right_rounded,
                  size: 20,
                  color: FansivibeColors.accentGold,
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    tip,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: FansivibeColors.textSecondary,
                      height: 1.4,
                      fontSize: 13,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildImpactCard(BuildContext context, OutfitRecommendation rec) {
    return FansiInsightCard(
      icon: Icons.check_circle_outline_rounded,
      title: 'Ensemble Match',
      body: rec.styleScoreImpact,
      accentColor: FansivibeColors.accentGold,
    );
  }

  Widget _buildImprovementCard(BuildContext context, OutfitRecommendation rec) {
    return FansiInsightCard(
      icon: Icons.lightbulb_outline_rounded,
      title: 'Improvement Suggestion',
      body: rec.improvementSuggestion,
      accentColor: FansivibeColors.warning,
    );
  }

  Widget _buildComponentsSection(
    BuildContext context,
    OutfitRecommendation rec,
  ) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Outfit Components',
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
            fontSize: 22,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          '${rec.components.length} curated pieces',
          style: theme.textTheme.bodyMedium?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
        ),
        const SizedBox(height: 14),
        ...rec.components.map(
          (component) => OutfitComponentCard(
            component: component,
            isPinned: _pinnedGarmentIds.contains(component.id),
            onTogglePin: () => _handleTogglePin(component.id),
            onReplace: () => _handleReplaceSlot(component),
          ),
        ),
      ],
    );
  }

  Widget _buildReasonsSection(BuildContext context, OutfitRecommendation rec) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Why This Look Works',
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
            fontSize: 22,
          ),
        ),
        const SizedBox(height: 14),
        if (rec.reasons.isEmpty)
          Text(
            'No grounded explanation available.',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: FansivibeColors.textSecondary,
              height: 1.5,
            ),
          ),
        ...rec.reasons.asMap().entries.map(
          (entry) => Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${entry.key + 1}.',
                  style: theme.textTheme.bodyLarge?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.accentGold,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    entry.value,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: FansivibeColors.textPrimary,
                      height: 1.5,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildMetricsSection(BuildContext context, OutfitRecommendation rec) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        MetricCard(
          icon: Icons.palette_outlined,
          title: 'Color Harmony',
          description: rec.colorHarmony,
          accentColor: FansivibeColors.accentGold,
        ),
        MetricCard(
          icon: Icons.accessibility_new_rounded,
          title: 'Body Fit',
          description: rec.bodyFit,
          accentColor: FansivibeColors.accentGold,
        ),
        MetricCard(
          icon: Icons.event_outlined,
          title: 'Occasion Match',
          description: rec.occasionMatch,
          accentColor: FansivibeColors.success,
        ),
      ],
    );
  }

  Widget _buildActions(BuildContext context, {required bool busy}) {
    return Column(
      children: [
        FansiButton.primary(
          label: _saved ? 'Saved' : (_saving ? 'Saving…' : 'Save Outfit'),
          icon: Icons.favorite_rounded,
          onPressed: busy || _saved ? null : _handleSave,
        ),
        const SizedBox(height: 12),
        FansiButton.secondary(
          label: _worn ? 'Worn Today' : 'Log Wear Today',
          icon: _worn ? Icons.check_circle_rounded : Icons.checkroom_rounded,
          onPressed: busy || _worn ? null : _handleLogWear,
        ),
        const SizedBox(height: 12),
        FansiButton.secondary(
          label: _regenerating ? 'Regenerating…' : 'Regenerate',
          icon: Icons.refresh_rounded,
          onPressed: busy ? null : _handleRegenerate,
        ),
        const SizedBox(height: 12),
        FansiButton.secondary(
          label: 'View Saved Outfits',
          icon: Icons.bookmark_outline_rounded,
          onPressed: () => context.pushNamed(RouteNames.profileSavedLooks),
        ),
        const SizedBox(height: 12),
        // Stage F0 mock try-on preview (Path B): component UUIDs travel
        // as labels only — test data, never genuine AI output.
        FansiButton.secondary(
          label: 'Try On (Test Preview)',
          icon: Icons.visibility_outlined,
          onPressed: busy
              ? null
              : () => context.pushNamed(
                  RouteNames.tryOn,
                  extra: {
                    'outfitSource': 'outfit',
                    'garmentIds': [for (final c in _rec.components) c.id],
                    'title': _rec.title,
                  },
                ),
        ),
      ],
    );
  }
}
