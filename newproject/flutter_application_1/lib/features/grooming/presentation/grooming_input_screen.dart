import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/grooming/data/grooming_mock_data.dart';
import 'package:fansivibe/features/grooming/presentation/widgets/grooming_widgets.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

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

  bool get _allSelected =>
      _selectedFaceShape != null &&
      _selectedBeardStyle != null &&
      _selectedDensity != null &&
      _selectedColor != null;

  String _labelForId(String id, List<GroomingOption> options) {
    return options.firstWhere((o) => o.id == id).label;
  }

  void _analyze() {
    if (!_allSelected) return;
    context.pushNamed(
      RouteNames.groomingProcessing,
      extra: <String, String>{
        'faceShape': _labelForId(
          _selectedFaceShape!,
          GroomingOption.faceShapeOptions,
        ),
        'beardStyle': _labelForId(
          _selectedBeardStyle!,
          GroomingOption.beardStyleOptions,
        ),
        'beardDensity': _labelForId(
          _selectedDensity!,
          GroomingOption.densityOptions,
        ),
        'beardColor': _labelForId(_selectedColor!, GroomingOption.colorOptions),
      },
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

                        SizedBox(
                          width: double.infinity,
                          child: FilledButton.icon(
                            onPressed: _allSelected ? _analyze : null,
                            icon: const Icon(
                              Icons.auto_awesome_rounded,
                              size: 20,
                            ),
                            label: const Text('Analyze Features'),
                            style: FilledButton.styleFrom(
                              backgroundColor: FansivibeColors.accentGold,
                              foregroundColor: FansivibeColors.background,
                              disabledBackgroundColor: FansivibeColors
                                  .accentGold
                                  .withValues(alpha: 0.3),
                              disabledForegroundColor:
                                  FansivibeColors.textSecondary,
                              padding: const EdgeInsets.symmetric(vertical: 16),
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
