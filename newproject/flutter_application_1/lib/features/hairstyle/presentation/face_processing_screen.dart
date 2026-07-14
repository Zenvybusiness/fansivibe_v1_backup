import 'dart:async';
import 'package:flutter/material.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/presentation/hairstyle_result_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/widgets/hairstyle_widgets.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class FaceProcessingScreen extends StatefulWidget {
  const FaceProcessingScreen({super.key});

  @override
  State<FaceProcessingScreen> createState() => _FaceProcessingScreenState();
}

class _FaceProcessingScreenState extends State<FaceProcessingScreen> {
  int _currentStageIndex = 0;
  final List<bool> _completedStages = [];
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _completedStages.addAll(
      List.filled(HairstyleProcessingStage.mockStages.length, false),
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
    if (_currentStageIndex >= HairstyleProcessingStage.mockStages.length) {
      _navigateToResult();
      return;
    }

    final stage = HairstyleProcessingStage.mockStages[_currentStageIndex];
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
    Navigator.of(context).pushReplacement<void, void>(
      MaterialPageRoute<void>(builder: (_) => const HairstyleResultScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final allComplete =
        _currentStageIndex >= HairstyleProcessingStage.mockStages.length;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: Text(allComplete ? 'Analysis Complete' : 'Analyzing Face'),
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

                        ...HairstyleProcessingStage.mockStages
                            .asMap()
                            .entries
                            .map((entry) {
                              final index = entry.key;
                              final stage = entry.value;
                              return HairstyleStageIndicator(
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
