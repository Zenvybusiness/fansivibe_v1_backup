import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/pending_auth_intent.dart';

/// Guest handoff after the Analyze My Style photo step (unauthenticated).
///
/// No backend analysis runs here: real appearance analysis is account-only
/// (`POST /v1/analysis/hairstyle` behind `get_current_user_id`). This
/// screen therefore shows NO style score, palette, or insights — a
/// fabricated result would pose mock data as analysis. It confirms the
/// photo step is done and routes to account creation (real analysis runs
/// after sign-in) or to guest browsing. Camera flow and buttons below
/// are otherwise untouched.
class YourAnalysisScreen extends StatefulWidget {
  const YourAnalysisScreen({super.key});

  @override
  State<YourAnalysisScreen> createState() => _YourAnalysisScreenState();
}

class _YourAnalysisScreenState extends State<YourAnalysisScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _statusAnim;
  late Animation<double> _ctaAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    );
    _statusAnim = _buildAnim(0.0, 0.5);
    _ctaAnim = _buildAnim(0.4, 1.0);
    _controller.forward();
  }

  Animation<double> _buildAnim(double start, double end) {
    return Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(
        parent: _controller,
        curve: Interval(start, end, curve: Curves.easeOut),
      ),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onSave() {
    // Onboarding conversion: remember that a real account should resume
    // the product journey (default /home) with local progress kept.
    // No analysis payload exists to resume (guest analyses never run),
    // so this stores origin context only — never fabricated results.
    recordPendingAuthIntent(
      PendingAuthIntent(
        action: 'save_progress',
        route: '/home',
        params: const {'source': 'your_analysis'},
        createdAt: DateTime.now(),
      ),
    );
    context.pushNamed(RouteNames.createAccount);
  }

  void _onContinueWithoutAccount() {
    // Guest path: persist locally so a relaunch resumes, then land on
    // the AI Stylist tab. Camera flow and UI above are untouched.
    LocalStorage.onboardingComplete = true;
    LocalStorage.savedLocally = true;
    LocalStorage.analysisCached = true;
    context.goNamed(RouteNames.stylist, extra: {
      'onboarding_complete': true,
      'display_name': null,
      'vibe': null,
      'saved_locally': true,
      'analysis_cached': true,
    });
  }

  void _onRetake() {
    // Fresh capture: a new PhotoCaptureScreen instance holds no image
    // bytes, so the previous photo can never be reused or resubmitted
    // and no stale result survives. goNamed (not pop) is required:
    // popping would land on the AiAnalysis timer, which auto-forwards
    // back here and looks like "Retake opens processing".
    context.goNamed(RouteNames.photoCapture);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: FansivibeColors.surface,
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 24.0;
            final contentMaxWidth = maxWidth > 600 ? 520.0 : double.infinity;

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
                        SizedBox(height: FansivibeSpacing.lg),
                        // Honest state: nothing has been analyzed yet. Real
                        // appearance analysis runs post-auth in Scan flows
                        // via Ollama vision (see analysis endpoints) and
                        // never fabricates scores.
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(FansivibeSpacing.md),
                          decoration: BoxDecoration(
                            color: FansivibeColors.surfaceContainerLow,
                            borderRadius: FansivibeRadius.mdBorder,
                            border: Border.all(
                              color: FansivibeColors.primary.withValues(
                                alpha: 0.25,
                              ),
                            ),
                          ),
                          child: Row(
                            children: [
                              Icon(
                                Icons.info_outline_rounded,
                                size: 18,
                                color: FansivibeColors.primary,
                              ),
                              SizedBox(width: FansivibeSpacing.sm),
                              Expanded(
                                child: Text(
                                  'Photo step complete — your personal analysis runs after you create an account. Nothing has been analyzed yet.',
                                  style: FansivibeTypography.bodyMediumWithFamily
                                      .copyWith(
                                        color: FansivibeColors.secondary,
                                      ),
                                ),
                              ),
                            ],
                          ),
                        ),
                        SizedBox(height: FansivibeSpacing.lg),
                        _buildAnimatedSection(
                          _statusAnim,
                          _buildStatusCard(),
                        ),
                        SizedBox(height: FansivibeSpacing.xl),
                        _buildAnimatedSection(
                          _ctaAnim,
                          Column(
                            children: [
                              FansiButton.primary(
                                label: 'Continue Without Account',
                                icon: Icons.save_rounded,
                                onPressed: _onContinueWithoutAccount,
                              ),
                              SizedBox(height: FansivibeSpacing.sm + 4),
                              FansiButton.tertiary(
                                label: 'Save My Progress',
                                onPressed: _onSave,
                              ),
                              SizedBox(height: FansivibeSpacing.sm + 4),
                              FansiButton.secondary(
                                label: 'Retake Photo',
                                icon: Icons.refresh_rounded,
                                onPressed: _onRetake,
                              ),
                            ],
                          ),
                        ),
                        SizedBox(height: FansivibeSpacing.xxl),
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

  Widget _buildAnimatedSection(Animation<double> anim, Widget child) {
    return AnimatedBuilder(
      animation: anim,
      builder: (context, _) {
        return Opacity(
          opacity: anim.value,
          child: Transform.translate(
            offset: Offset(0, 30 * (1 - anim.value)),
            child: child,
          ),
        );
      },
    );
  }

  /// What happens next — static guidance only, no scores or insights.
  Widget _buildStatusCard() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.mdBorder,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.check_circle_outline_rounded,
                size: 18,
                color: FansivibeColors.primary,
              ),
              SizedBox(width: FansivibeSpacing.sm),
              Flexible(
                child: Text(
                  'Photo ready',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: FansivibeTypography.titleLargeWithFamily.copyWith(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: FansivibeSpacing.md),
          _buildStepRow(
            '1',
            'Create your account to unlock the real AI analysis.',
          ),
          SizedBox(height: FansivibeSpacing.sm),
          _buildStepRow(
            '2',
            'We analyze your photo for face shape and style matches.',
          ),
          SizedBox(height: FansivibeSpacing.sm),
          _buildStepRow(
            '3',
            'Photos without a person visible are rejected — pick one with you in it.',
          ),
        ],
      ),
    );
  }

  Widget _buildStepRow(String number, String text) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 22,
          height: 22,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(
              color: FansivibeColors.primary.withValues(alpha: 0.6),
            ),
          ),
          child: Center(
            child: Text(
              number,
              style: FansivibeTypography.labelSmallWithFamily.copyWith(
                color: FansivibeColors.primary,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ),
        SizedBox(width: FansivibeSpacing.sm),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text(
              text,
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.secondary,
              ),
            ),
          ),
        ),
      ],
    );
  }
}
