import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/grooming/data/grooming_mock_data.dart'
    hide GroomingAnalysisResult;
import 'package:fansivibe/features/grooming/data/grooming_models.dart'
    show GroomingAnalysisResult;
import 'package:fansivibe/features/grooming/presentation/widgets/grooming_widgets.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

class GroomingInputScreen extends StatefulWidget {
  const GroomingInputScreen({super.key});

  @override
  State<GroomingInputScreen> createState() => _GroomingInputScreenState();
}

class _GroomingInputScreenState extends State<GroomingInputScreen> {
  String? _selectedFaceShape;
  String? _selectedBeardStyle;
  String? _selectedDensity;
  String? _selectedColor;

  @override
  void initState() {
    super.initState();
  }

  void _analyze() {
    // Guests run the synchronous ephemeral analysis (D-01) over the
    // request profile collected below — the same processing navigation
    // as the authenticated path. Account gating happens only at Save.
    // Every field is user-chosen: never invent defaults (no silent 'oval').
    if (_selectedFaceShape == null ||
        _selectedBeardStyle == null ||
        _selectedDensity == null ||
        _selectedColor == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Select your face shape, beard style, density and color to continue.',
          ),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }
    final faceShape = _selectedFaceShape!;
    final beardStyle = _selectedBeardStyle!;
    final density = _selectedDensity!;
    final color = _selectedColor!;

    context.pushNamed(
      RouteNames.groomingProcessing,
      extra: <String, String>{
        'faceShape': faceShape,
        'beardStyle': beardStyle,
        'beardDensity': density,
        'beardColor': color,
      },
    );
  }

  /// Resume banner for the stashed guest result (D-01): explicit View
  /// restores the exact snapshot for replay, Dismiss clears the slot.
  /// Renders only when this feature's snapshot is stashed.
  Widget _buildPendingResultBanner(BuildContext context) {
    final pending = peekPendingEphemeralResult();
    if (pending == null || pending.feature != EphemeralFeature.grooming) {
      return const SizedBox.shrink();
    }
    final snapshot = pending.snapshot;
    return Column(
      children: [
        PendingEphemeralResultBanner(
          title: 'Your grooming analysis is saved',
          message:
              'Your recent guest analysis is on this device. View it any time — sign in to save it to your profile.',
          onView: () {
            try {
              final result = GroomingAnalysisResult.fromSnapshot(snapshot);
              if (!context.mounted) return;
              context.pushNamed(RouteNames.groomingResult, extra: result);
            } catch (_) {
              clearPendingEphemeralResult();
              if (!context.mounted) return;
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text(
                    'The saved result was unreadable. Please run a new analysis.',
                  ),
                  behavior: SnackBarBehavior.floating,
                ),
              );
            }
          },
          onDismiss: () {
            clearPendingEphemeralResult();
            if (mounted) setState(() {});
          },
        ),
        const SizedBox(height: 12),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Beard / Glasses'),
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
                        const SizedBox(height: 8),

                        _buildPendingResultBanner(context),

                        Text(
                          'Grooming Profile',
                          style: theme.textTheme.displayLarge?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: FansivibeColors.textPrimary,
                            fontSize: 28,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Tell us about your features for personalized grooming suggestions',
                          style: theme.textTheme.bodyLarge?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                        ),

                        const SizedBox(height: 28),

                        GroomingOptionSection(
                          title: 'Face Shape',
                          subtitle: 'What is your face shape?',
                          options: GroomingOption.faceShapeOptions,
                          selectedId: _selectedFaceShape,
                          onSelected: (id) =>
                              setState(() => _selectedFaceShape = id),
                        ),

                        const SizedBox(height: 24),

                        GroomingOptionSection(
                          title: 'Beard Style',
                          subtitle: 'Which style interests you?',
                          options: GroomingOption.beardStyleOptions,
                          selectedId: _selectedBeardStyle,
                          onSelected: (id) =>
                              setState(() => _selectedBeardStyle = id),
                        ),

                        const SizedBox(height: 24),

                        GroomingOptionSection(
                          title: 'Beard Density',
                          subtitle: 'How thick is your facial hair?',
                          options: GroomingOption.densityOptions,
                          selectedId: _selectedDensity,
                          onSelected: (id) =>
                              setState(() => _selectedDensity = id),
                        ),

                        const SizedBox(height: 24),

                        GroomingOptionSection(
                          title: 'Beard Color',
                          subtitle: 'What is your facial hair color?',
                          options: GroomingOption.colorOptions,
                          selectedId: _selectedColor,
                          onSelected: (id) =>
                              setState(() => _selectedColor = id),
                        ),

                        const SizedBox(height: 32),

                        FansiButton.primary(
                          label: 'Analyze Style',
                          icon: Icons.auto_awesome_rounded,
                          onPressed: _analyze,
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