import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/onboarding/data/onboarding_data.dart';
import 'package:fansivibe/features/onboarding/presentation/widgets/vibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

class VibeSelectScreen extends StatefulWidget {
  const VibeSelectScreen({super.key});

  @override
  State<VibeSelectScreen> createState() => _VibeSelectScreenState();
}

class _VibeSelectScreenState extends State<VibeSelectScreen>
    with SingleTickerProviderStateMixin {
  StyleVibe? _selected;
  bool _photoPath = true;
  bool _vibeRequired = true;

  late AnimationController _animController;
  late Animation<double> _questionAnim;
  late List<Animation<double>> _cardAnims;

  static const _vibeLineOffsets = [
    [Offset(0.2, 0.0), Offset(0.5, 0.0), Offset(0.3, 0.0)],
    [Offset(0.1, 0.3), Offset(0.6, 0.1), Offset(0.4, 0.6)],
    [Offset(0.2, 0.2), Offset(0.5, 0.5), Offset(0.8, 0.8)],
    [Offset(0.0, 0.4), Offset(0.7, 0.0), Offset(0.3, 0.7)],
    [Offset(0.2, 0.1), Offset(0.8, 0.3), Offset(0.5, 0.9)],
    [Offset(0.0, 0.0), Offset(0.9, 0.4), Offset(0.2, 0.8)],
  ];

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    _questionAnim = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(
        parent: _animController,
        curve: const Interval(0.0, 0.3, curve: Curves.easeOut),
      ),
    );
    _cardAnims = List.generate(6, (i) {
      return Tween<double>(begin: 0, end: 1).animate(
        CurvedAnimation(
          parent: _animController,
          curve: Interval(
            0.15 + i * 0.08,
            0.6 + i * 0.05,
            curve: Curves.easeOut,
          ),
        ),
      );
    });
    _animController.forward();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final extra = GoRouterState.of(context).extra as Map<String, dynamic>?;
    if (extra != null) {
      _photoPath = extra['photoPath'] as bool? ?? true;
      // vibeRequired: if false, vibe selection is optional and Continue works without selection
      // if true or absent, vibe selection is required (backward compatible default)
      _vibeRequired = extra['vibeRequired'] as bool? ?? true;
    }
  }

  @override
  void dispose() {
    _animController.dispose();
    super.dispose();
  }

  void _onContinue() {
    if (_photoPath) {
      if (_vibeRequired && _selected == null) {
        // Required but unselected: concise validation, no navigation.
        // (Continue stays tappable so the attempt can surface this
        // message; the dimmed opacity below is the disabled cue.)
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Select a style to continue'),
            backgroundColor: FansivibeColors.surfaceContainerHigh,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(
              borderRadius: FansivibeRadius.smdBorder,
            ),
            duration: const Duration(seconds: 2),
          ),
        );
        return;
      }
      if (_selected != null) {
        // The persisted preference (read by Home/FirstTimeHome/Profile).
        // Deliberately NOT mirrored to LearningService.setStyleType: that
        // records a learning signal, which would flip the new-vs-old Home
        // decision to established for a brand-new user.
        LocalStorage.vibe = _selected!.name;
      }
      context.pushNamed(
        RouteNames.cameraPermission,
        extra: {'vibe': _selected?.name},
      );
    } else {
      // Explore path: answer saved above, land directly on the
      // Discover tab — never through Home first.
      LocalStorage.savedLocally = true;
      if (_selected != null) {
        LocalStorage.vibe = _selected!.name;
      }
      context.goNamed(RouteNames.discover, extra: {'vibe': _selected?.name});
    }
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
                      children: [
                        SizedBox(height: FansivibeSpacing.xl + 8),
                        AnimatedBuilder(
                          animation: _questionAnim,
                          builder: (context, _) {
                            return Opacity(
                              opacity: _questionAnim.value,
                              child: Column(
                                children: [
                                  Text(
                                    'Which style feels\nmost like you?',
                                    textAlign: TextAlign.center,
                                    style: FansivibeTypography
                                        .headlineMediumWithFamily
                                        .copyWith(fontSize: 28, height: 1.2),
                                  ),
                                  SizedBox(height: FansivibeSpacing.sm),
                                  Text(
                                    'Choose one that resonates',
                                    style: FansivibeTypography
                                        .bodyMediumWithFamily
                                        .copyWith(
                                          color: FansivibeColors.secondary,
                                        ),
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                        SizedBox(height: FansivibeSpacing.xl),
                        GridView.count(
                          crossAxisCount: 2,
                          shrinkWrap: true,
                          physics: const NeverScrollableScrollPhysics(),
                          mainAxisSpacing: FansivibeSpacing.md,
                          crossAxisSpacing: FansivibeSpacing.md,
                          childAspectRatio: 0.65,
                          children: List.generate(6, (i) {
                            final vibe = StyleVibe.values[i];
                            return AnimatedBuilder(
                              animation: _cardAnims[i],
                              builder: (context, _) {
                                return Transform.translate(
                                  offset: Offset(
                                    0,
                                    60 * (1 - _cardAnims[i].value),
                                  ),
                                  child: Opacity(
                                    opacity: _cardAnims[i].value,
                                    child: VibeCard(
                                      label: vibe.label,
                                      gradientColors: vibeGradientColors[vibe]!,
                                      lineOffsets: _vibeLineOffsets[i],
                                      isSelected: _selected == vibe,
                                      onTap: () => setState(() {
                                        _selected = (_selected == vibe)
                                            ? null
                                            : vibe;
                                      }),
                                    ),
                                  ),
                                );
                              },
                            );
                          }),
                        ),
                        SizedBox(height: FansivibeSpacing.lg),
                        AnimatedOpacity(
                          opacity: _selected != null ? 1.0 : 0.3,
                          duration: const Duration(milliseconds: 200),
                          child: FansiButton.primary(
                            label: 'Continue',
                            // Always tappable: with no selection on the
                            // required path _onContinue shows the
                            // validation message instead of navigating.
                            // No Skip action exists — selection is
                            // deliberate before continuing.
                            onPressed: _onContinue,
                          ),
                        ),
                        SizedBox(height: FansivibeSpacing.xl),
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
