import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_builder_mock_data.dart'
    hide OutfitComponent, OutfitRecommendation;
import 'package:fansivibe/features/outfit_builder/outfit_builder.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

/// Step 2 of the builder flow: derives one outfit from the step-1
/// preferences via the M13 backend (#41 `POST /v1/outfits/generate`).
///
/// The stage list below is static process copy (what the derivation
/// does), never timed fake progress: a single request runs on entry and
/// the screen forwards on its response. 200 auto-forwards the verbatim
/// recommendation (plus the request prefs for regenerate) to the
/// recommendation surface; 204 renders an honest empty state; any
/// failure renders an error with retry. Nothing here fabricates an
/// outfit, and no wardrobe/event fetch happens in this layer — the
/// backend owns all data.
class OutfitGenerationScreen extends StatefulWidget {
  const OutfitGenerationScreen({
    required this.occasion,
    required this.mood,
    required this.fit,
    required this.colorPalette,
    this.outfitRepository,
    super.key,
  });

  final String occasion;
  final String mood;
  final String fit;
  final String colorPalette;

  /// Backend outfit source. Defaults to the live repository; tests
  /// inject a fake.
  final OutfitBuilderRepository? outfitRepository;

  @override
  State<OutfitGenerationScreen> createState() => _OutfitGenerationScreenState();
}

class _OutfitGenerationScreenState extends State<OutfitGenerationScreen> {
  late final OutfitBuilderRepository _repository;
  Future<OutfitResult>? _generationFuture;
  bool _forwarded = false;

  @override
  void initState() {
    super.initState();
    _repository = widget.outfitRepository ?? OutfitBuilderRepositoryImpl();
    _generate();
  }

  void _generate() {
    setState(() {
      _forwarded = false;
      _generationFuture = _repository.generateOutfit(
        occasion: widget.occasion,
        mood: widget.mood,
        fit: widget.fit,
        colorPalette: widget.colorPalette,
      );
    });
  }

  void _forward(OutfitRecommendation outfit) {
    if (_forwarded || !mounted) return;
    _forwarded = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.replaceNamed(
        RouteNames.outfitRecommendation,
        extra: <String, dynamic>{
          'recommendation': outfit.snapshot,
          'request': <String, String>{
            'occasion': widget.occasion,
            'mood': widget.mood,
            'fit': widget.fit,
            'colorPalette': widget.colorPalette,
          },
        },
      );
    });
  }

  String _failureMessage(OutfitFailure? failure) {
    switch (failure) {
      case OutfitFailure.unauthorized:
        return 'Please sign in again to build an outfit.';
      case OutfitFailure.invalidInput:
        return 'Those preferences look invalid. Please go back and reselect.';
      case OutfitFailure.rateLimited:
        return 'Too many requests. Please wait and try again.';
      case OutfitFailure.serviceUnavailable:
        return 'Style service unavailable. Please try again.';
      case OutfitFailure.networkError:
        return 'Please check your connection and try again.';
      default:
        return 'Something went wrong. Please try again.';
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Building Outfit'),
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
            final contentMaxWidth = maxWidth > 600 ? 440.0 : double.infinity;

            return SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              child: Center(
                child: ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: contentMaxWidth),
                  child: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: horizontalPadding,
                    ),
                    child: FutureBuilder<OutfitResult>(
                      future: _generationFuture,
                      builder: (context, snapshot) {
                        if (snapshot.connectionState ==
                            ConnectionState.waiting) {
                          return _buildLoading(context);
                        }
                        final result = snapshot.data;
                        if (result != null && result.available) {
                          _forward(result.outfit!);
                          return _buildForwarding(context);
                        }
                        if (result != null && result.noneAvailable) {
                          return _buildEmpty(context);
                        }
                        return _buildError(context, result?.failure);
                      },
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

  Widget _buildLoading(BuildContext context) {
    return Column(
      children: [
        const SizedBox(height: 40),

        // Visual indicator
        Container(
          width: 160,
          height: 160,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: FansivibeColors.surface,
            border: Border.all(
              color: FansivibeColors.accentGold.withValues(alpha: 0.3),
            ),
          ),
          child: const Center(
            child: SizedBox(
              width: 48,
              height: 48,
              child: CircularProgressIndicator(
                strokeWidth: 4,
                valueColor: AlwaysStoppedAnimation<Color>(
                  FansivibeColors.accentGold,
                ),
              ),
            ),
          ),
        ),

        const SizedBox(height: 40),

        // Selection summary
        _buildSelectionSummary(context),

        const SizedBox(height: 28),

        // Processing stages (static process copy — no timed fake progress)
        ...GenerationStage.mockStages.map(
          (stage) => _buildStageIndicator(stage: stage),
        ),

        const SizedBox(height: 32),
      ],
    );
  }

  Widget _buildForwarding(BuildContext context) {
    return Column(
      children: [
        const SizedBox(height: 40),
        Container(
          width: 160,
          height: 160,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: FansivibeColors.surface,
            border: Border.all(
              color: FansivibeColors.success.withValues(alpha: 0.3),
            ),
          ),
          child: const Center(
            child: Icon(
              Icons.check_circle_rounded,
              size: 64,
              color: FansivibeColors.success,
            ),
          ),
        ),
        const SizedBox(height: 24),
        Text(
          'Generation Complete',
          style: Theme.of(context).textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
          ),
        ),
        const SizedBox(height: 32),
      ],
    );
  }

  Widget _buildEmpty(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      children: [
        const SizedBox(height: 40),
        const Icon(
          Icons.checkroom_outlined,
          size: 64,
          color: FansivibeColors.textSecondary,
        ),
        const SizedBox(height: 24),
        Text(
          'No matching outfit',
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'Your wardrobe doesn\'t have the pieces for this combination yet. '
          'Add wardrobe items to unlock outfit generation.',
          textAlign: TextAlign.center,
          style: theme.textTheme.bodyMedium?.copyWith(
            color: FansivibeColors.textSecondary,
            height: 1.5,
          ),
        ),
        const SizedBox(height: 24),
        _buildSelectionSummary(context),
        const SizedBox(height: 24),
        FansiButton.secondary(
          label: 'Try Again',
          icon: Icons.refresh_rounded,
          onPressed: _generate,
        ),
        const SizedBox(height: 32),
      ],
    );
  }

  Widget _buildError(BuildContext context, OutfitFailure? failure) {
    final theme = Theme.of(context);
    return Column(
      children: [
        const SizedBox(height: 40),
        const Icon(
          Icons.error_outline_rounded,
          size: 64,
          color: FansivibeColors.textSecondary,
        ),
        const SizedBox(height: 24),
        Text(
          'Couldn\'t build your outfit',
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          _failureMessage(failure),
          textAlign: TextAlign.center,
          style: theme.textTheme.bodyMedium?.copyWith(
            color: FansivibeColors.textSecondary,
            height: 1.5,
          ),
        ),
        const SizedBox(height: 24),
        FansiButton.secondary(
          label: 'Try Again',
          icon: Icons.refresh_rounded,
          onPressed: _generate,
        ),
        const SizedBox(height: 32),
      ],
    );
  }

  Widget _buildSelectionSummary(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.baseBorder,
      ),
      child: Column(
        children: [
          Text(
            'Your Preferences',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: FansivibeColors.textSecondary,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 16,
            runSpacing: 12,
            alignment: WrapAlignment.center,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              _buildPreferenceChip(
                context,
                _labelForId(BuilderOption.occasionOptions, widget.occasion),
                Icons.event_outlined,
              ),
              _buildPreferenceChip(
                context,
                _labelForId(BuilderOption.moodOptions, widget.mood),
                Icons.explore_outlined,
              ),
              _buildPreferenceChip(
                context,
                _labelForId(BuilderOption.fitOptions, widget.fit),
                Icons.tune_rounded,
              ),
              _buildPreferenceChip(
                context,
                _labelForId(
                  BuilderOption.colorPaletteOptions,
                  widget.colorPalette,
                ),
                Icons.palette_outlined,
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildPreferenceChip(
    BuildContext context,
    String label,
    IconData icon,
  ) {
    final theme = Theme.of(context);

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 18, color: FansivibeColors.accentGold),
        const SizedBox(height: 4),
        Text(
          label,
          style: theme.textTheme.bodySmall?.copyWith(
            color: FansivibeColors.textPrimary,
            fontSize: 11,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }

  Widget _buildStageIndicator({required GenerationStage stage}) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Icon(
            Icons.radio_button_unchecked_rounded,
            size: 22,
            color: FansivibeColors.textSecondary.withValues(alpha: 0.3),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Text(
              stage.label,
              style: theme.textTheme.bodyLarge?.copyWith(
                color: FansivibeColors.textSecondary.withValues(alpha: 0.4),
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }

  String _labelForId(List<BuilderOption> options, String id) {
    // Prefs always come from the step-1 picker ids; unknown ids fall back
    // to the raw id instead of crashing the flow.
    for (final option in options) {
      if (option.id == id) return option.label;
    }
    return id;
  }
}
