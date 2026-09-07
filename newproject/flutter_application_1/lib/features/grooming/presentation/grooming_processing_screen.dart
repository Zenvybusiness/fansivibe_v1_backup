
import 'package:flutter/material.dart';
import 'package:fansivibe/features/grooming/data/grooming_mock_data.dart';
import 'package:fansivibe/features/grooming/data/grooming_service.dart';
import 'package:fansivibe/features/grooming/presentation/widgets/grooming_widgets.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class GroomingProcessingScreen extends StatefulWidget {
  const GroomingProcessingScreen({
    required this.faceShape,
    required this.beardStyle,
    required this.beardDensity,
    required this.beardColor,
    this.service,
    super.key,
  });

  final String faceShape;
  final String beardStyle;
  final String beardDensity;
  final String beardColor;

  /// Injectable for tests; when null the service automatically attaches
  /// [LearningService.instance] so the analysis uses the user's stored face
  /// profile instead of falling back to the offline mock result.
  final GroomingService? service;

  @override
  State<GroomingProcessingScreen> createState() =>
      _GroomingProcessingScreenState();
}

class _GroomingProcessingScreenState extends State<GroomingProcessingScreen> {
  late final GroomingService _service;

  @override
  void initState() {
    super.initState();
    final provided = widget.service;
    if (provided != null) {
      _service = provided;
    } else {
      _service = GroomingService()..attachLearning(LearningService.instance);
    }
  }

  @override
  void dispose() {
    _service.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isProcessing = _service.isProcessing;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: isProcessing
            ? const Text('Analyzing Features')
            : const Text('Analysis Complete'),
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
                              color: isProcessing
                                  ? FansivibeColors.accentGold.withValues(
                                      alpha: 0.3,
                                    )
                                  : FansivibeColors.success.withValues(
                                      alpha: 0.3,
                                    ),
                            ),
                          ),
                          child: isProcessing
                              ? const Center(
                                  child: CircularProgressIndicator(
                                    strokeWidth: 4,
                                    valueColor: AlwaysStoppedAnimation<Color>(
                                      FansivibeColors.accentGold,
                                    ),
                                  ),
                                )
                              : const Center(
                                  child: Icon(
                                    Icons.check_circle_rounded,
                                    size: 64,
                                    color: FansivibeColors.success,
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
                                isActive: index == 0,
                                isComplete: true,
                              );
                        }),

                        const SizedBox(height: 40),

                        if (isProcessing)
                          FansiButton.primary(
                            label: 'View Results',
                            icon: Icons.check_circle_outline,
                            onPressed: () {},
                          )
                        else
                          FansiButton.primary(
                            label: 'View Results',
                            icon: Icons.check_circle_outline,
                            onPressed: () {},
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