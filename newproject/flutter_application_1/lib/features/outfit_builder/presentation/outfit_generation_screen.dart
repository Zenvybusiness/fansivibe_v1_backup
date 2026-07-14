import 'dart:async';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_builder_mock_data.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class OutfitGenerationScreen extends StatefulWidget {
  const OutfitGenerationScreen({
    required this.occasion,
    required this.mood,
    required this.fit,
    required this.colorPalette,
    super.key,
  });

  final String occasion;
  final String mood;
  final String fit;
  final String colorPalette;

  @override
  State<OutfitGenerationScreen> createState() => _OutfitGenerationScreenState();
}

class _OutfitGenerationScreenState extends State<OutfitGenerationScreen> {
  int _currentStageIndex = 0;
  final List<bool> _completedStages = [];
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _completedStages.addAll(
      List.filled(GenerationStage.mockStages.length, false),
    );
    _startProcessing();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _startProcessing() {
    _processNextStage();
  }

  void _processNextStage() {
    if (_currentStageIndex >= GenerationStage.mockStages.length) {
      _navigateToRecommendation();
      return;
    }

    final stage = GenerationStage.mockStages[_currentStageIndex];
    _timer = Timer(stage.duration, () {
      if (!mounted) return;
      setState(() {
        _completedStages[_currentStageIndex] = true;
        _currentStageIndex++;
      });
      _processNextStage();
    });
  }

  void _navigateToRecommendation() {
    if (!mounted) return;
    context.replaceNamed(RouteNames.outfitRecommendation);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final allComplete = _currentStageIndex >= GenerationStage.mockStages.length;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: Text(allComplete ? 'Generation Complete' : 'Building Outfit'),
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
                    child: Column(
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
                              color: allComplete
                                  ? const Color(
                                      0xFF4CAF50,
                                    ).withValues(alpha: 0.3)
                                  : FansivibeColors.accentGold.withValues(
                                      alpha: 0.3,
                                    ),
                            ),
                          ),
                          child: Center(
                            child: allComplete
                                ? const Icon(
                                    Icons.check_circle_rounded,
                                    size: 64,
                                    color: Color(0xFF4CAF50),
                                  )
                                : SizedBox(
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

                        // Processing stages
                        ...GenerationStage.mockStages.asMap().entries.map((
                          entry,
                        ) {
                          final index = entry.key;
                          final stage = entry.value;
                          return _buildStageIndicator(
                            stage: stage,
                            isActive: index == _currentStageIndex,
                            isComplete: _completedStages[index],
                          );
                        }),

                        const SizedBox(height: 40),

                        if (allComplete)
                          SizedBox(
                            width: double.infinity,
                            child: FilledButton.icon(
                              onPressed: _navigateToRecommendation,
                              icon: const Icon(
                                Icons.visibility_rounded,
                                size: 20,
                              ),
                              label: const Text('View Recommendation'),
                              style: FilledButton.styleFrom(
                                backgroundColor: FansivibeColors.accentGold,
                                foregroundColor: FansivibeColors.background,
                                padding: const EdgeInsets.symmetric(
                                  vertical: 16,
                                ),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(16),
                                ),
                                elevation: 4,
                                shadowColor: FansivibeColors.accentGold
                                    .withValues(alpha: 0.3),
                              ),
                            ),
                          ),

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

  Widget _buildSelectionSummary(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.15),
        ),
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
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
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

  Widget _buildStageIndicator({
    required GenerationStage stage,
    required bool isActive,
    required bool isComplete,
  }) {
    final theme = Theme.of(context);
    final Color iconColor;
    final Widget icon;

    if (isComplete) {
      iconColor = const Color(0xFF4CAF50);
      icon = Icon(Icons.check_circle_rounded, size: 22, color: iconColor);
    } else if (isActive) {
      iconColor = FansivibeColors.accentGold;
      icon = SizedBox(
        width: 22,
        height: 22,
        child: CircularProgressIndicator(
          strokeWidth: 2.5,
          valueColor: AlwaysStoppedAnimation<Color>(iconColor),
        ),
      );
    } else {
      iconColor = FansivibeColors.textSecondary.withValues(alpha: 0.3);
      icon = Icon(
        Icons.radio_button_unchecked_rounded,
        size: 22,
        color: iconColor,
      );
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          icon,
          const SizedBox(width: 14),
          Expanded(
            child: Text(
              stage.label,
              style: theme.textTheme.bodyLarge?.copyWith(
                color: isComplete
                    ? FansivibeColors.textPrimary
                    : isActive
                    ? FansivibeColors.textPrimary
                    : FansivibeColors.textSecondary.withValues(alpha: 0.4),
                fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }

  String _labelForId(List<BuilderOption> options, String id) {
    return options.firstWhere((o) => o.id == id).label;
  }
}
