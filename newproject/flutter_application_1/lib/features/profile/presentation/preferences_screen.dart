import 'package:flutter/material.dart';
import 'package:fansivibe/features/assistant/data/assistant_client.dart';
import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/profile/data/profile_mocks.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

import 'package:fansivibe/features/profile/data/user_profile_models.dart';
import 'package:fansivibe/features/profile/data/user_profile_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

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
  const PreferencesScreen({
    super.key,
    this.preferencesClient,
    this.userProfileRepository,
  });

  /// Injectable for tests; when null the screen owns its own client.
  final AssistantClient? preferencesClient;
  final UserProfileRepository? userProfileRepository;

  @override
  State<PreferencesScreen> createState() => _PreferencesScreenState();
}

class _PreferencesScreenState extends State<PreferencesScreen> {
  late LearningService _learningService;
  late final AssistantClient _client;
  late final UserProfileRepository _userProfileRepo;
  final GlobalKey<FormState> _detailsFormKey = GlobalKey<FormState>();
  final TextEditingController _goalsController = TextEditingController();
  final TextEditingController _dislikesController = TextEditingController();
  final TextEditingController _budgetController = TextEditingController();
  List<PreferenceOption> _preferences = [];
  String? _selectedOccasion;
  String? _selectedArchetype;
  String? _faceShape;
  String? _skinTone;
  String? _bodyType;
  String? _hairType;
  String? _hairDensity;
  String? _maintenancePreference;
  String? _statusMessage;
  bool _syncing = false;
  bool _isError = false;

  static const List<String> _allArchetypes = [
    'Minimalist',
    'Classic',
    'Street Style',
    'Bold',
    'Trendy',
    'Natural',
    'Bohemian',
    'Edgy',
    'Athleisure',
  ];

  static const List<String> _allOccasions = [
    'Casual',
    'Smart Casual',
    'Business',
    'Formal',
    'Streetwear',
  ];

  static const Map<String, String?> _faceShapeOptions = {
    'Not set': null,
    'Oval': 'oval',
    'Round': 'round',
    'Square': 'square',
    'Heart': 'heart',
    'Diamond': 'diamond',
    'Rectangular': 'rectangular',
  };
  static const Map<String, String?> _skinToneOptions = {
    'Not set': null,
    'W00 · Warm 00': 'W00',
    'W01 · Warm 01': 'W01',
    'W02 · Warm 02': 'W02',
    'W03 · Warm 03': 'W03',
    'W04 · Warm 04': 'W04',
    'W05 · Warm 05': 'W05',
    'C00 · Cool 00': 'C00',
    'C01 · Cool 01': 'C01',
    'C02 · Cool 02': 'C02',
    'C03 · Cool 03': 'C03',
    'C04 · Cool 04': 'C04',
    'C05 · Cool 05': 'C05',
  };
  static const Map<String, String?> _bodyTypeOptions = {
    'Not set': null,
    'Slim': 'slim',
    'Average': 'average',
    'Curvy': 'curvy',
    'Plus': 'plus',
  };
  static const Map<String, String?> _hairTypeOptions = {
    'Not set': null,
    'Straight': 'straight',
    'Wavy': 'wavy',
    'Curly': 'curly',
    'Coily': 'coily',
  };
  static const Map<String, String?> _hairDensityOptions = {
    'Not set': null,
    'Sparse': 'sparse',
    'Medium': 'medium',
    'Dense': 'dense',
  };
  static const Map<String, String?> _maintenanceOptions = {
    'Not set': null,
    'Low': 'low',
    'Medium': 'medium',
    'High': 'high',
  };

  @override
  void initState() {
    super.initState();
    _learningService = LearningService.instance;
    _client = widget.preferencesClient ?? AssistantClient();
    _userProfileRepo =
        widget.userProfileRepository ?? UserProfileRepositoryImpl();
    _selectedOccasion = _initialOccasion();
    _selectedArchetype = _initialArchetype();
    _preferences = _buildPreferences();
    _hydrateDetails(_userProfileRepo.cachedProfile);

    _learningService.load().then((_) async {
      if (AuthSession.isAuthenticated || widget.userProfileRepository != null) {
        UserProfile? profile;
        try {
          profile = await _userProfileRepo.fetchProfile();
        } catch (_) {
          // Fallback gracefully
        }
        if (!mounted) return;
        setState(() {
          if (profile?.styleProfile.styleType != null &&
              profile!.styleProfile.styleType!.isNotEmpty) {
            _selectedArchetype = _normalizeArchetype(
              profile.styleProfile.styleType!,
            );
          } else {
            _selectedArchetype = _initialArchetype();
          }
          _selectedOccasion = _initialOccasion();
          _preferences = _buildPreferences();
          _hydrateDetails(profile);
        });
      }
    });
  }

  @override
  void dispose() {
    _goalsController.dispose();
    _dislikesController.dispose();
    _budgetController.dispose();
    super.dispose();
  }

  static String _normalizeArchetype(String val) {
    final lower = val.trim().toLowerCase();
    if (lower.contains('minimal')) return 'Minimalist';
    if (lower.contains('classic')) return 'Classic';
    if (lower.contains('street')) return 'Street Style';
    if (lower.contains('bold')) return 'Bold';
    if (lower.contains('trend')) return 'Trendy';
    if (lower.contains('natural')) return 'Natural';
    if (lower.contains('bohem')) return 'Bohemian';
    if (lower.contains('edgy')) return 'Edgy';
    if (lower.contains('athleis') || lower.contains('sport')) {
      return 'Athleisure';
    }
    for (final arch in _allArchetypes) {
      if (arch.toLowerCase() == lower) return arch;
    }
    return val;
  }

  static String? _normalizeCode(String? value, Map<String, String?> options) {
    if (value == null || value.trim().isEmpty) return null;
    final lower = value.trim().toLowerCase();
    final canonical = lower == 'rectangle' ? 'rectangular' : lower;
    for (final option in options.values) {
      if (option != null && option.toLowerCase() == canonical) return option;
    }
    return value.trim();
  }

  static Map<String, String?> _optionsWithCurrent(
    Map<String, String?> options,
    String? value,
  ) {
    final result = Map<String, String?>.from(options);
    if (value != null && !options.values.contains(value)) {
      result['$value (existing)'] = value;
    }
    return result;
  }

  void _hydrateDetails(UserProfile? profile) {
    final style = profile?.styleProfile;
    if (style != null) {
      _faceShape = _normalizeCode(style.faceShape, _faceShapeOptions);
      _skinTone = _normalizeCode(style.skinTone, _skinToneOptions);
      _bodyType = _normalizeCode(style.bodyType, _bodyTypeOptions);
      _hairType = _normalizeCode(style.hairType, _hairTypeOptions);
      _hairDensity = _normalizeCode(style.hairDensity, _hairDensityOptions);
    }
    final prefs = profile?.preferences ?? const <String, dynamic>{};
    _maintenancePreference = _normalizeCode(
      prefs['maintenancePreference'] as String? ??
          prefs['maintenance_preference'] as String?,
      _maintenanceOptions,
    );
    _goalsController.text =
        (prefs['appearanceGoals'] ?? prefs['appearance_goals'] ?? '')
            .toString();
    _dislikesController.text = (prefs['dislikes'] ?? '').toString();
    final budget = prefs['maxBudget'] ?? prefs['max_budget'];
    _budgetController.text = budget is num ? budget.toString() : '';
  }

  Future<void> _saveDetails() async {
    if (!(_detailsFormKey.currentState?.validate() ?? false)) return;
    final budgetText = _budgetController.text.trim();
    final budget = budgetText.isEmpty ? null : double.tryParse(budgetText);
    final stylePatch = <String, dynamic>{
      'faceShape': _faceShape,
      'skinTone': _skinTone,
      'bodyType': _bodyType,
      'hairType': _hairType,
      'hairDensity': _hairDensity,
    };
    final preferencePatch = <String, dynamic>{
      'appearanceGoals': _goalsController.text.trim().isEmpty
          ? null
          : _goalsController.text.trim(),
      'dislikes': _dislikesController.text.trim().isEmpty
          ? null
          : _dislikesController.text.trim(),
      'maintenancePreference': _maintenancePreference,
      'maxBudget': budget,
    };

    if (isGuestUser || !AuthSession.isAuthenticated) {
      await _userProfileRepo.updateStyleAttributes(stylePatch);
      await _userProfileRepo.updatePreferenceFields(preferencePatch);
      if (!mounted) return;
      setState(() {
        _isError = false;
        _statusMessage = 'Saved: profile details (this device only)';
      });
      return;
    }

    setState(() {
      _syncing = true;
      _isError = false;
      _statusMessage = 'Syncing profile details…';
    });
    final styleUpdated = await _userProfileRepo.updateStyleAttributes(
      stylePatch,
    );
    final preferencesUpdated = await _userProfileRepo.updatePreferenceFields(
      preferencePatch,
    );
    if (!mounted) return;
    setState(() {
      _syncing = false;
      _isError = styleUpdated == null || preferencesUpdated == null;
      _statusMessage = _isError
          ? 'Sync failed — could not update profile details.'
          : 'Synced: profile details';
    });
  }

  Widget _detailDropdown({
    required String label,
    required String? value,
    required Map<String, String?> options,
    required ValueChanged<String?> onChanged,
  }) {
    final items = _optionsWithCurrent(options, value);
    return DropdownButtonFormField<String?>(
      key: ValueKey('profileDetail_${label.replaceAll(' ', '')}'),
      initialValue: value,
      isExpanded: true,
      items: [
        for (final entry in items.entries)
          DropdownMenuItem<String?>(
            value: entry.value,
            child: Text(entry.key, overflow: TextOverflow.ellipsis),
          ),
      ],
      onChanged: _syncing ? null : onChanged,
      decoration: InputDecoration(
        labelText: label,
        filled: true,
        fillColor: FansivibeColors.surface,
        border: OutlineInputBorder(borderRadius: FansivibeRadius.baseBorder),
      ),
      dropdownColor: FansivibeColors.surface,
    );
  }

  String _initialArchetype([UserProfile? profile]) {
    final fromProfile =
        profile?.styleProfile.styleType ??
        _userProfileRepo.cachedProfile?.styleProfile.styleType;
    if (fromProfile != null && fromProfile.isNotEmpty) {
      return _normalizeArchetype(fromProfile);
    }
    final fromLearning = _learningService.styleType;
    if (fromLearning != null && fromLearning.isNotEmpty) {
      return _normalizeArchetype(fromLearning);
    }
    final fromStorage = LocalStorage.vibe;
    if (fromStorage != null && fromStorage.isNotEmpty) {
      return _normalizeArchetype(fromStorage);
    }
    return _allArchetypes.first;
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
    final currentArchetype = _selectedArchetype ?? _initialArchetype();
    final archetypeIdx = _allArchetypes.indexOf(currentArchetype);
    final selectedArchetypeIndex = archetypeIdx >= 0 ? archetypeIdx : 0;

    final currentOccasion = _selectedOccasion ?? _initialOccasion();
    final occasionIdx = _allOccasions.indexOf(currentOccasion);
    final selectedOccasionIndex = occasionIdx >= 0 ? occasionIdx : 1;

    return [
      PreferenceOption(
        label: 'Style Archetype',
        value: currentArchetype,
        options: _allArchetypes,
        selectedIndex: selectedArchetypeIndex,
      ),
      PreferenceOption(
        label: 'Occasion Focus',
        value: currentOccasion,
        options: _allOccasions,
        selectedIndex: selectedOccasionIndex,
      ),
    ];
  }

  Future<void> _onArchetypeSelected(String value) async {
    if (_syncing) return;

    final normalized = _normalizeArchetype(value);
    final previousArchetype = _selectedArchetype;

    if (isGuestUser || !AuthSession.isAuthenticated) {
      _learningService.setStyleType(normalized);
      LocalStorage.vibe = normalized;
      setState(() {
        _selectedArchetype = normalized;
        _preferences = _buildPreferences();
        _isError = false;
        _statusMessage = 'Saved: $normalized (this device only)';
      });
      return;
    }

    setState(() {
      _syncing = true;
      _selectedArchetype = normalized;
      _preferences = _buildPreferences();
      _isError = false;
      _statusMessage = 'Syncing $normalized…';
    });

    final updated = await _userProfileRepo.updateStyleType(normalized);
    if (!mounted) return;

    if (updated != null) {
      _learningService.setStyleType(normalized);
      LocalStorage.vibe = normalized;
      setState(() {
        _syncing = false;
        _isError = false;
        _statusMessage = 'Synced: $normalized';
      });
    } else {
      setState(() {
        _syncing = false;
        _selectedArchetype = previousArchetype;
        _preferences = _buildPreferences();
        _isError = true;
        _statusMessage = 'Sync failed — could not update style archetype.';
      });
    }
  }

  Future<void> _onOccasionSelected(String value) => _onOptionSelected(value);

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
                            children: [
                              for (int i = 0; i < _preferences.length; i++) ...[
                                _PreferenceTile(
                                  preference: _preferences[i],
                                  onOptionSelected: (val) {
                                    if (_preferences[i].label ==
                                        'Occasion Focus') {
                                      _onOccasionSelected(val);
                                    } else {
                                      _onArchetypeSelected(val);
                                    }
                                  },
                                  isSyncing: _syncing,
                                ),
                                if (i < _preferences.length - 1)
                                  Divider(
                                    height: 1,
                                    color: FansivibeColors.accentGold
                                        .withValues(alpha: 0.1),
                                  ),
                              ],
                            ],
                          ),
                        ),
                        const SizedBox(height: 24),
                        Text(
                          'Appearance & Preferences',
                          style: theme.textTheme.titleLarge?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: FansivibeColors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Set the details your stylist uses to tailor recommendations.',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                        ),
                        const SizedBox(height: 12),
                        FansivibeCard(
                          child: Form(
                            key: _detailsFormKey,
                            child: Padding(
                              padding: const EdgeInsets.all(16),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  _detailDropdown(
                                    label: 'Face shape',
                                    value: _faceShape,
                                    options: _faceShapeOptions,
                                    onChanged: (value) =>
                                        setState(() => _faceShape = value),
                                  ),
                                  const SizedBox(height: 12),
                                  _detailDropdown(
                                    label: 'Skin tone',
                                    value: _skinTone,
                                    options: _skinToneOptions,
                                    onChanged: (value) =>
                                        setState(() => _skinTone = value),
                                  ),
                                  const SizedBox(height: 12),
                                  _detailDropdown(
                                    label: 'Body type',
                                    value: _bodyType,
                                    options: _bodyTypeOptions,
                                    onChanged: (value) =>
                                        setState(() => _bodyType = value),
                                  ),
                                  const SizedBox(height: 12),
                                  _detailDropdown(
                                    label: 'Hair type',
                                    value: _hairType,
                                    options: _hairTypeOptions,
                                    onChanged: (value) =>
                                        setState(() => _hairType = value),
                                  ),
                                  const SizedBox(height: 12),
                                  _detailDropdown(
                                    label: 'Hair density',
                                    value: _hairDensity,
                                    options: _hairDensityOptions,
                                    onChanged: (value) =>
                                        setState(() => _hairDensity = value),
                                  ),
                                  const SizedBox(height: 12),
                                  TextFormField(
                                    key: const ValueKey(
                                      'profileDetail_appearanceGoals',
                                    ),
                                    controller: _goalsController,
                                    maxLength: 500,
                                    maxLines: 2,
                                    decoration: const InputDecoration(
                                      labelText: 'Appearance goals',
                                      hintText:
                                          'What would you like to refine?',
                                      border: OutlineInputBorder(),
                                    ),
                                  ),
                                  const SizedBox(height: 12),
                                  TextFormField(
                                    key: const ValueKey(
                                      'profileDetail_dislikes',
                                    ),
                                    controller: _dislikesController,
                                    maxLength: 500,
                                    maxLines: 2,
                                    decoration: const InputDecoration(
                                      labelText: 'Dislikes',
                                      hintText: 'Anything you want to avoid?',
                                      border: OutlineInputBorder(),
                                    ),
                                  ),
                                  const SizedBox(height: 12),
                                  _detailDropdown(
                                    label: 'Maintenance',
                                    value: _maintenancePreference,
                                    options: _maintenanceOptions,
                                    onChanged: (value) => setState(
                                      () => _maintenancePreference = value,
                                    ),
                                  ),
                                  const SizedBox(height: 12),
                                  TextFormField(
                                    key: const ValueKey(
                                      'profileDetail_maxBudget',
                                    ),
                                    controller: _budgetController,
                                    keyboardType: TextInputType.number,
                                    decoration: const InputDecoration(
                                      labelText: 'Budget limit',
                                      hintText: 'e.g. 5000',
                                      border: OutlineInputBorder(),
                                    ),
                                    validator: (value) {
                                      final raw = value?.trim() ?? '';
                                      if (raw.isEmpty) return null;
                                      final amount = double.tryParse(raw);
                                      if (amount == null ||
                                          amount < 0 ||
                                          amount > 1000000) {
                                        return 'Enter an amount between 0 and 1,000,000.';
                                      }
                                      return null;
                                    },
                                  ),
                                  const SizedBox(height: 16),
                                  ElevatedButton.icon(
                                    onPressed: _syncing ? null : _saveDetails,
                                    icon: const Icon(Icons.save_rounded),
                                    label: Text(
                                      _syncing
                                          ? 'Saving…'
                                          : 'Save profile details',
                                    ),
                                    style: ElevatedButton.styleFrom(
                                      backgroundColor:
                                          FansivibeColors.accentGold,
                                      foregroundColor:
                                          FansivibeColors.background,
                                      shape: RoundedRectangleBorder(
                                        borderRadius:
                                            FansivibeRadius.baseBorder,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
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
