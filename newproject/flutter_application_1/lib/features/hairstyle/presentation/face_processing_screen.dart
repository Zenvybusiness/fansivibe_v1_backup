import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/domain/hairstyle_service.dart';
import 'package:fansivibe/features/hairstyle/presentation/widgets/hairstyle_widgets.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

class FaceProcessingScreen extends StatefulWidget {
  const FaceProcessingScreen({
    super.key,
    this.service,
    this.imageBytes,
    this.imageFilename,
    this.imageContentType,
    this.angleFront,
    this.angleFrontName,
    this.angleLeft,
    this.angleLeftName,
    this.angleRight,
    this.angleRightName,
  });

  /// Injectable for tests; when null the screen owns a real [HairstyleService].
  final HairstyleService? service;

  /// Real scan image held in memory by the scan screen (never persisted,
  /// never logged). When null the existing profile-only path is used.
  final Uint8List? imageBytes;
  final String? imageFilename;
  final String? imageContentType;

  /// Guided multi-angle captures (FRONT/LEFT/RIGHT, in-memory only).
  /// When all three are present they take the multi-angle path; every
  /// view is analyzed and none is discarded (see face_scan_votes.dart).
  final Uint8List? angleFront;
  final String? angleFrontName;
  final Uint8List? angleLeft;
  final String? angleLeftName;
  final Uint8List? angleRight;
  final String? angleRightName;

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
      _service = HairstyleService()..attachLearning(LearningService.instance);
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
    // Phase 2 guests: hairstyle analysis (POST /v1/analysis/hairstyle)
    // is account-only — never submit. The build below renders the
    // sign-in prompt instead.
    if (isGuestUser) {
      setState(() {});
      return;
    }
    // Guided multi-angle path: every captured view is analyzed through
    // the existing endpoint and aggregated deterministically.
    if (widget.angleFront != null &&
        widget.angleLeft != null &&
        widget.angleRight != null) {
      final multi = await _service.runMultiAngleAnalysis(
        frontBytes: widget.angleFront!,
        frontName: widget.angleFrontName,
        leftBytes: widget.angleLeft!,
        leftName: widget.angleLeftName,
        rightBytes: widget.angleRight!,
        rightName: widget.angleRightName,
      );
      if (!mounted) return;
      // Null/failed multi-angle stays on the honest error state (with
      // retry) — mock content is never forwarded as a real analysis.
      if (multi == null || _service.analysisError != null) {
        setState(() {});
        return;
      }
      LearningService.instance.setFace(
        FaceProfile(
          faceShape: multi.faceShape,
          skinTone: multi.skinTone,
          bodyType: null,
          styleType: multi.styleDna.isNotEmpty
              ? multi.styleDna.split('•').first
              : '',
        ),
      );
      _navigateToResult(multi);
      return;
    }
    final result = await _service.runAnalysis(
      imageBytes: widget.imageBytes,
      imageFilename: widget.imageFilename,
      imageContentType: widget.imageContentType,
    );
    if (!mounted) return;
    // A genuine backend failure (`status=failed`) surfaces an honest error
    // state instead of silently navigating to the offline mock (required
    // error state; only this component changed).
    if (_service.analysisError != null) {
      setState(() {});
      return;
    }
    // Persist the face profile ONLY when the analysis resolved from a real
    // backend result — never from the offline mock fallback (G-11). This
    // keeps cold-start users who complete a real scan on the path to a valid
    // face profile without ever storing mock-derived attributes as if real.
    // A mock resolution (offline/unreachable/skip) forwards null so the
    // result screen renders its explicit error state — mock content is
    // never posed as a real analysis.
    if (!_service.isMockResult) {
      LearningService.instance.setFace(
        FaceProfile(
          faceShape: result.faceShape,
          skinTone: result.skinTone,
          bodyType: null,
          styleType: result.styleDna.isNotEmpty ? result.styleDna.split('•').first : '',
        ),
      );
      _navigateToResult(result);
    } else {
      _navigateToResult(null);
    }
  }

  void _navigateToResult(HairstyleAnalysisResult? result) {
    if (_navigated) return;
    _navigated = true;
    context.replaceNamed(RouteNames.hairstyleResult, extra: result);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    // Phase 2 guests: honest sign-in prompt — the analysis submit in
    // _start never fired, so no 401 and no polling.
    if (isGuestUser) {
      return Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        appBar: AppBar(
          title: const Text('Analyzing Face'),
          leading: IconButton(
            icon: const Icon(
              Icons.arrow_back_rounded,
              color: FansivibeColors.textPrimary,
            ),
            onPressed: () => Navigator.of(context).pop(),
          ),
        ),
        body: const SafeArea(
          child: SingleChildScrollView(
            physics: BouncingScrollPhysics(),
            child: Padding(
              padding: EdgeInsets.all(20),
              child: GuestSignInCard(
                title: 'Hairstyle Analysis',
                message:
                    'Hairstyle analysis lives in your account. Sign in to analyze your photo — browsing stays free.',
              ),
            ),
          ),
        ),
      );
    }
    final completedStages = _service.completedStageCount;
    final totalStages = HairstyleService.totalStages;
    final allComplete = completedStages >= totalStages;
    final errorMessage = _service.analysisError;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: Text(
          errorMessage != null
              ? 'Analysis Failed'
              : allComplete
              ? 'Analysis Complete'
              : 'Analyzing Face',
        ),
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
                              color: errorMessage != null
                                  ? FansivibeColors.error.withValues(alpha: 0.3)
                                  : allComplete
                                  ? FansivibeColors.success.withValues(
                                      alpha: 0.3,
                                    )
                                  : FansivibeColors.accentGold.withValues(
                                      alpha: 0.3,
                                    ),
                            ),
                          ),
                          child: Center(
                            child: errorMessage != null
                                ? Icon(
                                    Icons.error_outline_rounded,
                                    size: 64,
                                    color: FansivibeColors.error,
                                  )
                                : allComplete
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

                        if (errorMessage != null) ...[
                          Text(
                            'Something went wrong',
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.w600,
                              color: FansivibeColors.textPrimary,
                            ),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            errorMessage,
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
                            onPressed: () {
                              setState(() {});
                              _start();
                            },
                          ),
                        ] else ...[
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
                        ],

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
