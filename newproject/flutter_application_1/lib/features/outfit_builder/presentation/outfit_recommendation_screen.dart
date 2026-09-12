import 'package:flutter/material.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_client.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_models.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_repository.dart';
import 'package:fansivibe/features/outfit_builder/presentation/widgets/outfit_builder_widgets.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansi_hero_card.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/components/fansi_insight_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

/// Step 3 of the builder flow: renders one backend-derived outfit
/// verbatim (M13, UC-28/29/30).
///
/// The [recommendation] arrives from the generation surface (never
/// mocked here); [request] carries the step-1 prefs so Regenerate can
/// re-derive with the next deterministic seed (`outfit-1`, `outfit-2`,
/// … — same seed repeats the backend result, no randomness introduced).
/// Save uses `POST /v1/outfits/saved` with `sourceContext: "outfit"`,
/// the response snapshot verbatim, and one fresh `Idempotency-Key` per
/// attempt. Saving never logs a wear event — there is no wear call
/// anywhere in this file.
class OutfitRecommendationScreen extends StatefulWidget {
  const OutfitRecommendationScreen({
    required this.recommendation,
    required this.request,
    this.outfitRepository,
    super.key,
  });

  /// Backend-derived outfit to render (verbatim server data).
  final OutfitRecommendation recommendation;

  /// Step-1 prefs backing Regenerate (ids verbatim).
  final OutfitGenerateRequest request;

  /// Backend outfit source. Defaults to the live repository; tests
  /// inject a fake.
  final OutfitBuilderRepository? outfitRepository;

  @override
  State<OutfitRecommendationScreen> createState() =>
      _OutfitRecommendationScreenState();
}

class _OutfitRecommendationScreenState
    extends State<OutfitRecommendationScreen> {
  late final OutfitBuilderRepository _repository;
  late OutfitRecommendation _rec;

  bool _regenerating = false;
  int _regenCount = 0;

  bool _saving = false;
  bool _saved = false;

  @override
  void initState() {
    super.initState();
    _repository = widget.outfitRepository ?? OutfitBuilderRepositoryImpl();
    _rec = widget.recommendation;
  }

  /// Regenerates via `POST /v1/outfits/generate` with the same prefs and
  /// the next deterministic seed. Guarded while any request is pending;
  /// the UI only updates when the response arrives (never
  /// optimistically). A failed regeneration keeps the current outfit
  /// visible with truthful feedback.
  Future<void> _handleRegenerate() async {
    if (_regenerating || _saving) return;
    setState(() => _regenerating = true);
    _regenCount += 1;
    final result = await _repository.generateOutfit(
      occasion: widget.request.occasion,
      mood: widget.request.mood,
      fit: widget.request.fit,
      colorPalette: widget.request.colorPalette,
      seed: 'outfit-$_regenCount',
    );
    if (!mounted) return;
    if (result.available) {
      setState(() {
        _rec = result.outfit!;
        _regenerating = false;
        _saved = false;
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
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 20.0;
            final contentMaxWidth = maxWidth > 600 ? 560.0 : double.infinity;

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
                        const SizedBox(height: 24),

                        // Outfit Components
                        _buildComponentsSection(context, rec),
                        const SizedBox(height: 24),

                        // Recommendation Reasons
                        _buildReasonsSection(context, rec),
                        const SizedBox(height: 24),

                        // Metrics
                        _buildMetricsSection(context, rec),
                        const SizedBox(height: 24),

                        // Style Score impact
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

  Widget _buildImpactCard(BuildContext context, OutfitRecommendation rec) {
    return FansiInsightCard(
      icon: Icons.trending_up_rounded,
      title: 'Style Score Impact',
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
            onReplace: () {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('Replace ${component.name} coming soon'),
                  backgroundColor: FansivibeColors.accentGold,
                  behavior: SnackBarBehavior.floating,
                  shape: RoundedRectangleBorder(
                    borderRadius: FansivibeRadius.smdBorder,
                  ),
                ),
              );
            },
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
          label: _regenerating ? 'Regenerating…' : 'Regenerate',
          icon: Icons.refresh_rounded,
          onPressed: busy ? null : _handleRegenerate,
        ),
      ],
    );
  }
}
