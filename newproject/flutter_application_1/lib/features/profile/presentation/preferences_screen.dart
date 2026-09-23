import 'package:flutter/material.dart';
import 'package:fansivibe/features/assistant/data/assistant_client.dart';
import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/profile/data/profile_mocks.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

/// UI label → backend occasion code (P1-2).
///
/// Exact matches against the frozen knowledge occasion vocabulary only
/// (`casual`/`formal`/`business`/`date`/`party`/`travel`/`workout`/`other`/
/// `office` — the codes R36 appends and generation consumes). Labels with
/// no counterpart (`Smart Casual`, `Streetwear`) have no entry: no code is
/// invented for them and they stay local-only (truthfully reported).
const Map<String, String> occasionLabelToCode = {
  'Casual': 'casual',
  'Business': 'business',
  'Formal': 'formal',
};

/// Backend occasion code → UI label (P2-6).
const Map<String, String> occasionCodeToLabel = {
  'casual': 'Casual',
  'business': 'Business',
  'formal': 'Formal',
};

class PreferencesScreen extends StatefulWidget {
  const PreferencesScreen({super.key, this.preferencesClient});

  /// Injectable for tests; when null the screen owns its own client.
  final AssistantClient? preferencesClient;

  @override
  State<PreferencesScreen> createState() => _PreferencesScreenState();
}

class _PreferencesScreenState extends State<PreferencesScreen> {
  late LearningService _learningService;
  late final AssistantClient _client;
  List<PreferenceOption> _preferences = [];
  String? _selectedOccasion;
  String? _statusMessage;
  bool _syncing = false;
  bool _isError = false;

  static const List<String> _allOccasions = [
    'Casual',
    'Smart Casual',
    'Business',
    'Formal',
    'Streetwear',
  ];

  @override
  void initState() {
    super.initState();
    _learningService = LearningService.instance;
    _client = widget.preferencesClient ?? AssistantClient();
    _learningService.load().then((_) {
      if (!mounted) return;
      setState(() {
        _selectedOccasion = _initialOccasion();
        _preferences = _buildPreferences();
      });
    });
  }

  String _initialOccasion() {
    final currentOccasions = _learningService.preferredOccasions;
    for (final occ in currentOccasions.reversed) {
      if (_allOccasions.contains(occ)) {
        return occ;
      }
      final mapped = occasionCodeToLabel[occ];
      if (mapped != null && _allOccasions.contains(mapped)) {
        return mapped;
      }
    }
    return 'Smart Casual';
  }

  List<PreferenceOption> _buildPreferences() {
    final current = _selectedOccasion ?? _initialOccasion();
    final idx = _allOccasions.indexOf(current);
    final selectedIndex = idx >= 0 ? idx : 1;

    final occasionOptions = <PreferenceOption>[];
    for (var option in ProfileMockData.stylePreferences
        .where((p) => p.label == 'Occasion Focus')
        .toList()) {
      occasionOptions.add(
        PreferenceOption(
          label: option.label,
          value: current,
          options: option.options,
          selectedIndex: selectedIndex,
        ),
      );
    }
    return [
      occasionOptions.isNotEmpty
          ? occasionOptions.first
          : PreferenceOption(
              label: 'Occasion Focus',
              value: current,
              options: _allOccasions,
              selectedIndex: selectedIndex,
            ),
    ];
  }

  Future<void> _onOptionSelected(String value) async {
    // While a preference mutation is pending, ignore taps to prevent conflicting
    // duplicate/rapid mutations from creating silently-local state divergence (P2-6).
    if (_syncing) return;

    final code = occasionLabelToCode[value];
    if (code == null) {
      // No backend counterpart exists — nothing truthful to send (P1-2:
      // no invented codes). Local-only, reported as such.
      _learningService.addPreferredOccasion(value);
      setState(() {
        _selectedOccasion = value;
        _preferences = _buildPreferences();
        _isError = false;
        _statusMessage = 'Saved: $value (this device only)';
      });
      return;
    }

    final previousOccasion = _selectedOccasion;

    // Phase 2.1 guests: preferences persist on-device only — the sync
    // call below would 401 without a session, so it is skipped and the
    // status says so honestly instead of rolling back a valid choice.
    if (isGuestUser) {
      _learningService.addPreferredOccasion(value);
      setState(() {
        _selectedOccasion = value;
        _preferences = _buildPreferences();
        _isError = false;
        _statusMessage = 'Saved: $value (this device only)';
      });
      return;
    }

    // Instant-save UX: highlight selected chip immediately and show syncing indicator.
    setState(() {
      _syncing = true;
      _selectedOccasion = value;
      _preferences = _buildPreferences();
      _isError = false;
      _statusMessage = 'Syncing $value…';
    });

    final result = await _client.syncPreferredOccasion(code: code);
    if (!mounted) return;

    switch (result) {
      case PreferenceSyncResult.synced:
        _learningService.addPreferredOccasion(value);
        setState(() {
          _syncing = false;
          _isError = false;
          _statusMessage = 'Synced: $value';
        });
      case PreferenceSyncResult.alreadySynced:
        _learningService.addPreferredOccasion(value);
        setState(() {
          _syncing = false;
          _isError = false;
          _statusMessage = 'Already synced: $value';
        });
      case PreferenceSyncResult.networkError:
        _learningService.addPreferredOccasion(value);
        setState(() {
          _syncing = false;
          _isError = false;
          _statusMessage = 'No connection — saved on this device.';
        });
      case PreferenceSyncResult.unknown:
        _learningService.addPreferredOccasion(value);
        setState(() {
          _syncing = false;
          _isError = false;
          _statusMessage = 'Sync failed — saved on this device.';
        });
      case PreferenceSyncResult.unauthorized:
        // Do not pretend the server accepted the change: roll back selection truthfully.
        setState(() {
          _syncing = false;
          _selectedOccasion = previousOccasion;
          _preferences = _buildPreferences();
          _isError = true;
          _statusMessage = 'Session expired — sign in again to sync.';
        });
      case PreferenceSyncResult.invalidInput:
        setState(() {
          _syncing = false;
          _selectedOccasion = previousOccasion;
          _preferences = _buildPreferences();
          _isError = true;
          _statusMessage = 'Could not sync: unsupported value.';
        });
      case PreferenceSyncResult.rateLimited:
        setState(() {
          _syncing = false;
          _selectedOccasion = previousOccasion;
          _preferences = _buildPreferences();
          _isError = true;
          _statusMessage = 'Too many requests — try again shortly.';
        });
    }
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
                                isSyncing: _syncing,
                              ),
                            ])
                                .toList(),
                          ),
                        ),
                        const SizedBox(height: 32),
                        if (_statusMessage != null)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 8.0),
                            child: Text(
                              _statusMessage!,
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: _syncing
                                    ? FansivibeColors.textSecondary
                                    : _isError
                                        ? FansivibeColors.error
                                        : FansivibeColors.successContainer,
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
    this.isSyncing = false,
  });

  final PreferenceOption preference;
  final void Function(String) onOptionSelected;
  final bool isSyncing;

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
                    onTap: isSyncing
                        ? null
                        : () => onOptionSelected(preference.options[i]),
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
