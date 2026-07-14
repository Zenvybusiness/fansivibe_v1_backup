import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_builder_mock_data.dart';
import 'package:fansivibe/features/outfit_builder/presentation/widgets/outfit_builder_widgets.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class BuildOutfitScreen extends StatefulWidget {
  const BuildOutfitScreen({super.key});

  @override
  State<BuildOutfitScreen> createState() => _BuildOutfitScreenState();
}

class _BuildOutfitScreenState extends State<BuildOutfitScreen> {
  String? _selectedOccasion;
  String? _selectedMood;
  String? _selectedFit;
  String? _selectedColorPalette;

  bool get _allSelected =>
      _selectedOccasion != null &&
      _selectedMood != null &&
      _selectedFit != null &&
      _selectedColorPalette != null;

  void _buildOutfit() {
    if (!_allSelected) return;
    context.pushNamed(
      RouteNames.outfitGeneration,
      extra: <String, String>{
        'occasion': _selectedOccasion!,
        'mood': _selectedMood!,
        'fit': _selectedFit!,
        'colorPalette': _selectedColorPalette!,
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Build Outfit'),
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

                        // Header
                        Text(
                          'Create Your Look',
                          style: theme.textTheme.displayLarge?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: FansivibeColors.textPrimary,
                            fontSize: 28,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Tell us your preferences and we\'ll build the perfect outfit',
                          style: theme.textTheme.bodyLarge?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                        ),

                        const SizedBox(height: 28),

                        // Occasion
                        OptionSection(
                          title: 'Occasion',
                          subtitle: 'What\'s the event?',
                          options: BuilderOption.occasionOptions,
                          selectedId: _selectedOccasion,
                          onSelected: (id) =>
                              setState(() => _selectedOccasion = id),
                        ),

                        const SizedBox(height: 24),

                        // Mood
                        OptionSection(
                          title: 'Mood',
                          subtitle: 'What vibe are you going for?',
                          options: BuilderOption.moodOptions,
                          selectedId: _selectedMood,
                          onSelected: (id) =>
                              setState(() => _selectedMood = id),
                        ),

                        const SizedBox(height: 24),

                        // Preferred Fit
                        OptionSection(
                          title: 'Preferred Fit',
                          subtitle: 'How do you like your clothes to fit?',
                          options: BuilderOption.fitOptions,
                          selectedId: _selectedFit,
                          onSelected: (id) => setState(() => _selectedFit = id),
                        ),

                        const SizedBox(height: 24),

                        // Color Palette
                        OptionSection(
                          title: 'Color Palette',
                          subtitle: 'What color direction?',
                          options: BuilderOption.colorPaletteOptions,
                          selectedId: _selectedColorPalette,
                          onSelected: (id) =>
                              setState(() => _selectedColorPalette = id),
                        ),

                        const SizedBox(height: 32),

                        // Build button
                        SizedBox(
                          width: double.infinity,
                          child: FilledButton.icon(
                            onPressed: _allSelected ? _buildOutfit : null,
                            icon: const Icon(
                              Icons.auto_awesome_rounded,
                              size: 20,
                            ),
                            label: const Text('Build My Outfit'),
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
