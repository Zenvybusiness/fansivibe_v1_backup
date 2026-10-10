import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/pending_auth_intent.dart';

/// Guest handoff after the Analyze My Style photo step (unauthenticated).
///
/// Shows the limited guest preview when the ephemeral pass returned real
/// observations ([outfitSnapshot] and/or [garmentSnapshot] verbatim from
/// `POST /v1/analysis/{outfit,garment}/ephemeral`), or an honest failure
/// state when it did not. Attributes the backends did not return are
/// omitted — never defaulted or sampled. Full personalized analysis
/// (saved style profile, history, learning recommendations) stays
/// account-only and runs after sign-in. Buttons below preserve their
/// established semantics; camera flow is otherwise untouched.
class YourAnalysisScreen extends StatefulWidget {
  const YourAnalysisScreen({
    super.key,
    this.imageBytes,
    this.outfitSnapshot,
    this.garmentSnapshot,
    this.outfitFailure,
    this.garmentFailure,
  });

  /// In-memory photo bytes for the thumbnail + Try Again replay.
  final Uint8List? imageBytes;

  /// Verbatim `outfit/ephemeral` engine snapshot (face observation), if any.
  final Map<String, dynamic>? outfitSnapshot;

  /// Verbatim `garment/ephemeral` observation snapshot, if any.
  final Map<String, dynamic>? garmentSnapshot;

  /// Typed failure reasons (e.g. `no_face_detected`, `rate_limited`),
  /// surfaced only when the matching snapshot is absent.
  final String? outfitFailure;
  final String? garmentFailure;

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
    LocalStorage.onboardingPhotoCaptured = true;
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
    // and no stale result survives. The stashed preview is discarded with
    // the photo (a retake supersedes it). goNamed (not pop) is required:
    // popping would land on the AiAnalysis pass, which would re-forward
    // the discarded photo's result back here.
    clearPendingEphemeralResult();
    context.goNamed(RouteNames.photoCapture);
  }

  void _onCreateAccount() {
    // Preview conversion: same resume path as Save My Progress (default
    // /home with local progress kept via the post-auth merge dialog).
    // The stashed outfit snapshot (if any) travels device-locally for a
    // later Save → sign-in replay; nothing auto-POSTs after login.
    recordPendingAuthIntent(
      PendingAuthIntent(
        action: 'save_progress',
        route: '/home',
        params: const {'source': 'guest_preview'},
        createdAt: DateTime.now(),
      ),
    );
    context.pushNamed(RouteNames.createAccount);
  }

  void _onTryAgain() {
    // Retry re-runs the live ephemeral pass with the same bytes (a fresh
    // analysis, never a cached result). Without bytes, fall back to a
    // fresh capture.
    final bytes = widget.imageBytes;
    if (bytes == null || bytes.isEmpty) {
      _onRetake();
      return;
    }
    context.pushNamed(
      RouteNames.aiAnalysis,
      extra: <String, dynamic>{'imageBytes': bytes},
    );
  }

  bool get _hasPreview =>
      widget.outfitSnapshot != null || widget.garmentSnapshot != null;

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
                        // Honest state: with a preview this ran on the guest
                        // photo via the ephemeral endpoints; without one,
                        // nothing has been analyzed yet. Full personalized
                        // analysis runs post-auth and never fabricates.
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
                                  _hasPreview
                                      ? 'Guest preview ready — this first look ran on your photo. Create an account for the full personalized analysis.'
                                      : 'Photo step complete — your personal analysis runs after you create an account. Nothing has been analyzed yet.',
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
                        if (_hasPreview) ...[
                          _buildAnimatedSection(
                            _statusAnim,
                            _buildPreviewCard(),
                          ),
                          SizedBox(height: FansivibeSpacing.lg),
                        ] else if (widget.outfitFailure != null ||
                            widget.garmentFailure != null) ...[
                          _buildAnimatedSection(
                            _statusAnim,
                            _buildFailureCard(),
                          ),
                          SizedBox(height: FansivibeSpacing.lg),
                        ],
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
                                label: 'Create Account',
                                icon: Icons.person_add_rounded,
                                onPressed: _onCreateAccount,
                              ),
                              SizedBox(height: FansivibeSpacing.sm + 4),
                              FansiButton.secondary(
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

  /// Limited guest preview: the uploaded photo plus only the observations
  /// the ephemeral pass actually returned. Null or empty attributes are
  /// omitted (never defaulted), with a plain note where a section found
  /// nothing measurable.
  Widget _buildPreviewCard() {
    final garment =
        widget.garmentSnapshot?.cast<String, dynamic>();
    final outfit = widget.outfitSnapshot?.cast<String, dynamic>();
    final appearance =
        outfit?['appearance'] as Map<String, dynamic>?;
    final faceShape = appearance?['faceShape'] as String?;
    final recommendations =
        outfit?['recommendations'] as Map<String, dynamic>?;
    final top = recommendations?['top'] as Map<String, dynamic>?;
    final confidence = (outfit?['confidence'] as num?)?.toDouble();
    final needsMoreData = outfit?['needs_more_data'] as bool? ?? false;

    final facts = <MapEntry<String, IconData>>[];
    void addFact(String? value, String label, IconData icon) {
      if (value != null && value.trim().isNotEmpty) {
        facts.add(MapEntry('$label: ${_pretty(value)}', icon));
      }
    }

    addFact(
      garment?['category'] as String?,
      'Garment',
      Icons.checkroom_outlined,
    );
    addFact(garment?['color'] as String?, 'Color', Icons.palette_outlined);
    addFact(
      garment?['pattern'] as String?,
      'Pattern',
      Icons.layers_outlined,
    );
    addFact(
      garment?['material'] as String?,
      'Material',
      Icons.texture_outlined,
    );
    addFact(garment?['style'] as String?, 'Style', Icons.style_outlined);
    addFact(garment?['fit'] as String?, 'Fit', Icons.straighten_outlined);
    final hasGarmentFacts = facts.isNotEmpty;
    addFact(faceShape, 'Face shape', Icons.face_outlined);

    final topName = top?['name'] as String?;
    final topReasons = top?['reasons'] as List?;
    final topReason =
        topReasons != null && topReasons.isNotEmpty
            ? topReasons.first.toString()
            : null;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.mdBorder,
        border: Border.all(
          color: FansivibeColors.primary.withValues(alpha: 0.25),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Your Style Preview',
            style: FansivibeTypography.titleLargeWithFamily.copyWith(
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
          SizedBox(height: FansivibeSpacing.sm),
          Text(
            'A first look from this photo only — not the full analysis.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              fontSize: 13,
            ),
          ),
          if (widget.imageBytes != null && widget.imageBytes!.isNotEmpty) ...[
            SizedBox(height: FansivibeSpacing.md),
            ClipRRect(
              borderRadius: FansivibeRadius.baseBorder,
              child: Image.memory(
                widget.imageBytes!,
                height: 180,
                width: double.infinity,
                fit: BoxFit.cover,
                gaplessPlayback: true,
                errorBuilder: (_, _, _) => const SizedBox.shrink(),
              ),
            ),
          ],
          SizedBox(height: FansivibeSpacing.md),
          for (final fact in facts) _buildFactRow(fact.key, fact.value),
          if (garment == null || !hasGarmentFacts)
            _buildFactRow(
              'No clear outfit details in this photo.',
              Icons.info_outline_rounded,
              muted: true,
            ),
          if (faceShape == null || faceShape.trim().isEmpty)
            _buildFactRow(
              "Face shape wasn't measurable in this photo.",
              Icons.info_outline_rounded,
              muted: true,
            ),
          if (topName != null && topName.trim().isNotEmpty) ...[
            SizedBox(height: FansivibeSpacing.sm),
            _buildFactRow(
              'Styling direction: ${_pretty(topName)}',
              Icons.auto_awesome_outlined,
            ),
            if (topReason != null && topReason.trim().isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(left: 26, top: 2),
                child: Text(
                  topReason,
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.secondary,
                    fontSize: 13,
                  ),
                ),
              ),
          ],
          if (confidence != null) ...[
            SizedBox(height: FansivibeSpacing.sm),
            _buildFactRow(
              'Analysis confidence: ${(confidence * 100).round()}%'
              '${needsMoreData ? ' — early preview, more photos sharpen this after you join' : ''}',
              Icons.trending_up_rounded,
              muted: true,
            ),
          ],
          SizedBox(height: FansivibeSpacing.sm),
          Text(
            'Create an account to unlock the full personalized analysis: a saved style profile, analysis history, and recommendations that learn from your saves.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              fontSize: 13,
            ),
          ),
        ],
      ),
    );
  }

  /// Honest failure: names the typed reason, offers retry with the same
  /// bytes (a fresh analysis) or a retake. Never a success state.
  Widget _buildFailureCard() {
    final reason = widget.outfitFailure ?? widget.garmentFailure;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      decoration: BoxDecoration(
        color: FansivibeColors.error.withValues(alpha: 0.08),
        borderRadius: FansivibeRadius.mdBorder,
        border: Border.all(
          color: FansivibeColors.error.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.error_outline_rounded,
                size: 18,
                color: FansivibeColors.error,
              ),
              SizedBox(width: FansivibeSpacing.sm),
              Flexible(
                child: Text(
                  'Preview unavailable',
                  style: FansivibeTypography.titleLargeWithFamily.copyWith(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: FansivibeSpacing.sm),
          Text(
            _previewFailureMessage(reason),
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
            ),
          ),
          SizedBox(height: FansivibeSpacing.md),
          FansiButton.secondary(
            label: 'Try Again',
            icon: Icons.refresh_rounded,
            onPressed: _onTryAgain,
          ),
        ],
      ),
    );
  }

  /// Maps a typed ephemeral failure reason to user-facing copy (mirrors the
  /// Scan flow's mapping; unknown shapes degrade to a generic retry).
  String _previewFailureMessage(String? reason) {
    switch (reason) {
      case 'no_face_detected':
        return 'No face was clearly visible in that photo. Retake with your face in frame, or try another photo.';
      case 'no_garment_detected':
        return 'No clear outfit was visible in that photo. Retake showing what you are wearing.';
      case 'ambiguous_subject':
        return 'That photo was hard to read. Retake with one clear subject.';
      case 'low_confidence':
        return "The analysis wasn't confident enough in that photo. Retake in better light.";
      case 'rate_limited':
        return 'Too many requests — please wait a moment and try again.';
      case 'service_unavailable':
      case 'unreachable':
        return 'The analysis service is unavailable. Check your connection and try again.';
      case 'empty_image':
        return "That photo couldn't be read. Please try another.";
      default:
        if (reason != null &&
            reason.isNotEmpty &&
            reason != 'request_failed') {
          return 'Analysis failed ($reason). Please try again.';
        }
        return 'Analysis failed. Please try again.';
    }
  }

  /// Display-case for a raw model value (codes like `tops` read naturally).
  String _pretty(String raw) {
    final words = raw.replaceAll('_', ' ').trim();
    if (words.isEmpty) return words;
    return words[0].toUpperCase() + words.substring(1);
  }

  Widget _buildFactRow(String text, IconData icon, {bool muted = false}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            icon,
            size: 16,
            color: muted
                ? FansivibeColors.secondary
                : FansivibeColors.primary,
          ),
          SizedBox(width: FansivibeSpacing.sm),
          Expanded(
            child: Text(
              text,
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: muted
                    ? FansivibeColors.secondary
                    : FansivibeColors.textPrimary,
                fontWeight: muted ? FontWeight.w400 : FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
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
