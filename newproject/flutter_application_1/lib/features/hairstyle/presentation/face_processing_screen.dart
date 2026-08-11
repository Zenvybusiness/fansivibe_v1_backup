import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/domain/hairstyle_service.dart';
import 'package:fansivibe/features/hairstyle/presentation/widgets/hairstyle_widgets.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class FaceProcessingScreen extends StatefulWidget {
  const FaceProcessingScreen({super.key, this.service});

  /// Injectable for tests; when null the screen owns a real [HairstyleService].
  final HairstyleService? service;

  @override
  State<FaceProcessingScreen> createState() => _FaceProcessingScreenState();
}

class _FaceProcessingScreenState extends State<FaceProcessingScreen> {
  late final HairstyleService _service;
  bool _ownsService = false;
  bool _navigated = false;

  @override
  void initState() {
    super.initState();
    final provided = widget.service;
    if (provided != null) {
      _service = provided;
    } else {
      _service = HairstyleService();
      _ownsService = true;
    }
    _service.addListener(_onServiceChanged);
    _start();
  }

  @override
  void dispose() {
    _service.removeListener(_onServiceChanged);
    if (_ownsService) {
      _service.dispose();
    }
    super.dispose();
  }

  void _onServiceChanged() {
    if (!mounted) return;
    setState(() {});
  }

  Future<void> _start() async {
    final result = await _service.runAnalysis();
    if (!mounted) return;
    _navigateToResult(result);
  }

  void _navigateToResult(HairstyleAnalysisResult? result) {
    if (_navigated) return;
    _navigated = true;
    context.replaceNamed(RouteNames.hairstyleResult, extra: result);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final completedStages = _service.completedStageCount;
    final totalStages = HairstyleService.totalStages;
    final allComplete = completedStages >= totalStages;

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
                                  ? FansivibeColors.success.withValues(
                                      alpha: 0.3,
                                    )
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
                                    color: FansivibeColors.success,
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
                                isActive: index == completedStages,
                                isComplete: index < completedStages,
                              );
                            }),

                        const SizedBox(height: 40),

                        if (allComplete)
                          FansiButton.primary(
                            label: 'View Results',
                            icon: Icons.check_circle_outline,
                            onPressed: _navigated
                                ? null
                                : () => _navigateToResult(_service.result),
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
