import 'package:flutter/material.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/profile/data/profile_mocks.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

class PreferencesScreen extends StatefulWidget {
  const PreferencesScreen({super.key});

  @override
  State<PreferencesScreen> createState() => _PreferencesScreenState();
}

class _PreferencesScreenState extends State<PreferencesScreen> {
  late LearningService _learningService;
  List<PreferenceOption> _preferences = [];
  String? _lastSavedOccasion;

  @override
  void initState() {
    super.initState();
    _learningService = LearningService.instance;
    _learningService.load().then((_) {
      setState(() {
        _preferences = _buildPreferences();
      });
    });
  }

  List<PreferenceOption> _buildPreferences() {
    final currentOccasions = _learningService.preferredOccasions;
    final allOccasions = <String>['Casual', 'Smart Casual', 'Business', 'Formal', 'Streetwear'];

    // Build occasion focus preference showing current selection
    final occasionOptions = <PreferenceOption>[];
    for (var option in ProfileMockData.stylePreferences
        .where((p) => p.label == 'Occasion Focus')
        .toList()) {
      final isSelected = currentOccasions.contains(option.value);
      occasionOptions.add(
        PreferenceOption(
          label: option.label,
          value: option.value,
          options: option.options,
          selectedIndex:
              isSelected ? allOccasions.indexOf(option.value) : 0,
        ),
      );
    }
    return [occasionOptions.isNotEmpty ? occasionOptions.first : const PreferenceOption(
      label: 'Occasion Focus',
      value: 'Smart Casual',
      options: ['Casual', 'Smart Casual', 'Business', 'Formal', 'Streetwear'],
      selectedIndex: 1,
    )];
  }

  void _onOptionSelected(String value) {
    // Call learning service to persist the preference
    _learningService.addPreferredOccasion(value);
    setState(() {
      _lastSavedOccasion = value;
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Preferences'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
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
                          'Style Preferences',
                          style: theme.textTheme.headlineMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: FansivibeColors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Customize your style profile',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                        ),
                        const SizedBox(height: 24),
                        FansivibeCard(
                          child: Column(
                            children: _preferences
                                .whereType<PreferenceOption>()
                                .expand((pref) => [
                              _PreferenceTile(
                                preference: pref,
                                onOptionSelected: _onOptionSelected,
                              ),
                            ])
                                .toList(),
                          ),
                        ),
                        const SizedBox(height: 32),
                        if (_lastSavedOccasion != null)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 8.0),
                            child: Text(
                              'Saved: $_lastSavedOccasion',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: FansivibeColors.successContainer,
                                fontWeight: FontWeight.w500,
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

class _PreferenceTile extends StatelessWidget {
  const _PreferenceTile({
    required this.preference,
    required this.onOptionSelected,
  });

  final PreferenceOption preference;
  final void Function(String) onOptionSelected;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            preference.label,
            style: theme.textTheme.bodyLarge?.copyWith(
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textPrimary,
            ),
          ),
          const SizedBox(height: 8),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: List.generate(preference.options.length, (i) {
                final isSelected = i == preference.selectedIndex;
                return Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: GestureDetector(
                    onTap: () => onOptionSelected(preference.options[i]),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 8,
                      ),
                      decoration: BoxDecoration(
                        color: isSelected
                            ? FansivibeColors.accentGold
                            : FansivibeColors.accentGold.withValues(alpha: 0.1),
                        borderRadius: FansivibeRadius.baseBorder,
                        border: Border.all(
                          color: isSelected
                              ? FansivibeColors.accentGold
                              : FansivibeColors.accentGold.withValues(
                                  alpha: 0.2,
                                ),
                        ),
                      ),
                      child: Text(
                        preference.options[i],
                        style: theme.textTheme.bodySmall?.copyWith(
                          fontWeight: FontWeight.w600,
                          color: isSelected
                              ? FansivibeColors.background
                              : FansivibeColors.accentGold,
                        ),
                      ),
                    ),
                  ),
                );
              }),
            ),
          ),
        ],
      ),
    );
  }
}
