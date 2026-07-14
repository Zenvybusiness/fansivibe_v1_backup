import 'dart:async';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/grooming/data/grooming_mock_data.dart';
import 'package:fansivibe/features/grooming/presentation/widgets/grooming_widgets.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class GroomingProcessingScreen extends StatefulWidget {
  const GroomingProcessingScreen({
    required this.faceShape,
    required this.beardStyle,
    required this.beardDensity,
    required this.beardColor,
    super.key,
  });

  final String faceShape;
  final String beardStyle;
  final String beardDensity;
  final String beardColor;

  @override
  State<GroomingProcessingScreen> createState() =>
      _GroomingProcessingScreenState();
}

class _GroomingProcessingScreenState extends State<GroomingProcessingScreen> {
  int _currentStageIndex = 0;
  final List<bool> _completedStages = [];
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _completedStages.addAll(
      List.filled(GroomingProcessingStage.mockStages.length, false),
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
    if (_currentStageIndex >= GroomingProcessingStage.mockStages.length) {
      _navigateToResult();
      return;
    }

    final stage = GroomingProcessingStage.mockStages[_currentStageIndex];
    _timer = Timer(stage.duration, () {
      if (!mounted) return;
      setState(() {
        _completedStages[_currentStageIndex] = true;
        _currentStageIndex++;
      });
      _processNextStage();
    });
  }

  void _navigateToResult() {
    if (!mounted) return;
    context.replaceNamed(
      RouteNames.groomingResult,
      extra: <String, String>{
        'faceShape': widget.faceShape,
        'beardStyle': widget.beardStyle,
        'beardDensity': widget.beardDensity,
        'beardColor': widget.beardColor,
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final allComplete =
        _currentStageIndex >= GroomingProcessingStage.mockStages.length;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: Text(allComplete ? 'Analysis Complete' : 'Analyzing Features'),
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
                                ? Icon(
                                    Icons.check_circle_rounded,
                                    size: 64,
                                    color: const Color(0xFF4CAF50),
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

                        ...GroomingProcessingStage.mockStages
                            .asMap()
                            .entries
                            .map((entry) {
                              final index = entry.key;
                              final stage = entry.value;
                              return GroomingStageIndicator(
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
                              onPressed: _navigateToResult,
                              icon: const Icon(
                                Icons.visibility_rounded,
                                size: 20,
                              ),
                              label: const Text('View Recommendations'),
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
}
