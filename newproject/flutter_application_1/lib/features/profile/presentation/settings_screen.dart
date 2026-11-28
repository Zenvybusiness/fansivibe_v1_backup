import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/auth/data/auth_repository.dart';
import 'package:fansivibe/features/home/presentation/widgets/city_selection_sheet.dart';
import 'package:fansivibe/features/profile/data/profile_mocks.dart';
import 'package:fansivibe/features/profile/data/user_profile_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

const Map<String, String> _settingLabelToKey = {
  'Notifications': 'notifications',
  'Sound Effects': 'soundEffects',
  'Haptic Feedback': 'hapticFeedback',
  'Data Saver': 'dataSaver',
};

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({
    super.key,
    this.userProfileRepository,
    this.authRepository,
  });

  final UserProfileRepository? userProfileRepository;
  final AuthRepository? authRepository;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late UserProfileRepository _userProfileRepo;
  late AuthRepository _authRepo;
  late List<SettingsItem> _items;
  Map<String, dynamic> _currentSettings = {};
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _userProfileRepo =
        widget.userProfileRepository ?? UserProfileRepositoryImpl();
    _authRepo = widget.authRepository ?? AuthRepositoryImpl();
    _currentSettings = Map<String, dynamic>.from(LocalStorage.settings);
    _items = _buildItems(_currentSettings);

    _userProfileRepo.fetchProfile().then((profile) {
      if (!mounted || profile == null) return;
      setState(() {
        _currentSettings = Map<String, dynamic>.from(profile.settings);
        _items = _buildItems(profile.settings);
      });
    });
  }

  String _resolveSavedCity(Map<String, dynamic> settings) {
    // Authenticated users read the profile settings they just hydrated;
    // device-local state is only authoritative for guests.
    final isAuthenticated = AuthSession.isAuthenticated && !isGuestUser;
    if (!isAuthenticated) {
      final local = LocalStorage.weatherCity;
      if (local != null) return local;
    }
    return _cityFromSettings(settings) ?? 'Not set';
  }

  static String? _cityFromSettings(Map<String, dynamic> settings) {
    final loc =
        settings['weather_location'] ??
        settings['weatherLocation'] ??
        settings['location'];
    if (loc is Map) {
      final city = loc['city'] ?? loc['cityName'] ?? loc['name'];
      if (city != null && city.toString().trim().isNotEmpty) {
        return city.toString().trim();
      }
    }
    final flat = settings['weatherCity'];
    if (flat is String && flat.trim().isNotEmpty) return flat.trim();
    return null;
  }

  List<SettingsItem> _buildItems(Map<String, dynamic> settings) {
    final list = ProfileMockData.settingsGroups.map((s) {
      if (!s.isSwitch) return s;
      final key = _settingLabelToKey[s.label];
      final val = (key != null && settings.containsKey(key))
          ? (settings[key] as bool? ?? s.switchValue)
          : s.switchValue;
      return SettingsItem(
        label: s.label,
        description: s.description,
        value: s.value,
        isSwitch: s.isSwitch,
        switchValue: val,
      );
    }).toList();

    // Weather Location item
    list.add(
      SettingsItem(
        label: 'Weather Location',
        description: 'City for weather-aware recommendations',
        value: _resolveSavedCity(settings),
        isSwitch: false,
      ),
    );

    return list;
  }

  Future<void> _onToggle(int index, bool val) async {
    final item = _items[index];
    final key = _settingLabelToKey[item.label];
    if (key == null) return;

    final oldVal = item.switchValue;
    setState(() {
      _items[index] = SettingsItem(
        label: item.label,
        description: item.description,
        value: item.value,
        isSwitch: item.isSwitch,
        switchValue: val,
      );
    });

    if (!AuthSession.isAuthenticated || isGuestUser) {
      final updated = Map<String, dynamic>.from(LocalStorage.settings);
      updated[key] = val;
      LocalStorage.settings = updated;
      return;
    }

    try {
      final res = await _userProfileRepo.updateSettings({key: val});
      if (!mounted) return;
      if (res == null) {
        setState(() {
          _items[index] = SettingsItem(
            label: item.label,
            description: item.description,
            value: item.value,
            isSwitch: item.isSwitch,
            switchValue: oldVal,
          );
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Failed to update setting. Please try again.'),
            backgroundColor: FansivibeColors.error,
          ),
        );
      }
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _items[index] = SettingsItem(
          label: item.label,
          description: item.description,
          value: item.value,
          isSwitch: item.isSwitch,
          switchValue: oldVal,
        );
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Failed to update setting. Please try again.'),
          backgroundColor: FansivibeColors.error,
        ),
      );
    }
  }

  Future<void> _onSelectCity() async {
    final isAuthenticatedUser = AuthSession.isAuthenticated && !isGuestUser;
    final currentCity = _resolveSavedCity(_currentSettings);
    final selectedCity = await showCitySelectionSheet(
      context,
      currentCity: currentCity == 'Not set' ? null : currentCity,
    );
    if (selectedCity == null) return;

    final cleanCity = selectedCity.trim();
    final newCityVal = cleanCity.isEmpty ? null : cleanCity;

    if (!isAuthenticatedUser) {
      _applyCityLocally(newCityVal);
      if (!mounted) return;
      _refreshCityTile(Map<String, dynamic>.from(LocalStorage.settings));
      LocalStorage.notifyWeatherLocationChanged();
      _showCityFeedback(
        newCityVal != null
            ? 'Weather city saved on this device'
            : 'Weather city cleared',
        error: false,
      );
      return;
    }

    // Persist through the approved preferences flow first; the local cache
    // (and mounted look surfaces) only change after confirmed backend save.
    try {
      final res = await _userProfileRepo.updateSettings({
        'weather_location': newCityVal != null ? {'city': newCityVal} : null,
      });
      if (!mounted) return;
      if (res == null) {
        _showCityFeedback(
          'Failed to update weather city. Please try again.',
          error: true,
        );
        return;
      }

      _applyCityLocally(newCityVal);
      final updated = Map<String, dynamic>.from(res.settings);
      if (newCityVal != null) {
        updated['weather_location'] = {'city': newCityVal};
        updated['weatherCity'] = newCityVal;
      } else {
        updated.remove('weather_location');
        updated.remove('weatherCity');
      }
      _refreshCityTile(updated);
      LocalStorage.notifyWeatherLocationChanged();
      _showCityFeedback(
        newCityVal != null
            ? 'Weather city updated to $newCityVal'
            : 'Weather city cleared',
        error: false,
      );
    } catch (_) {
      if (!mounted) return;
      _showCityFeedback(
        'Failed to update weather city. Please try again.',
        error: true,
      );
    }
  }

  /// Mirrors the saved city into device storage without touching unrelated
  /// settings keys.
  void _applyCityLocally(String? city) {
    LocalStorage.weatherCity = city;
    final updated = Map<String, dynamic>.from(LocalStorage.settings);
    if (city != null) {
      updated['weather_location'] = {'city': city};
      updated['weatherCity'] = city;
    } else {
      updated.remove('weather_location');
      updated.remove('weatherCity');
    }
    LocalStorage.settings = updated;
  }

  void _refreshCityTile(Map<String, dynamic> settings) {
    setState(() {
      _currentSettings = settings;
      _items = _buildItems(settings);
    });
  }

  void _showCityFeedback(String message, {required bool error}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: error
            ? FansivibeColors.error
            : FansivibeColors.primary,
      ),
    );
  }

  Future<void> _handleSignOut() async {
    if (_busy) return;
    setState(() => _busy = true);
    await _authRepo.logout();
    if (!mounted) return;
    setState(() => _busy = false);
    try {
      context.goNamed(RouteNames.entry);
    } catch (_) {}
  }

  Future<void> _showDeleteConfirmation() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => const _DeleteAccountDialog(),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _busy = true);
    final deleted = await _userProfileRepo.deleteAccount();
    if (!mounted) return;
    setState(() => _busy = false);
    if (!deleted) {
      _showCityFeedback(
        'Account deletion failed. Please try again.',
        error: true,
      );
      return;
    }
    await AuthSession.clearSession();
    if (!mounted) return;
    try {
      context.goNamed(RouteNames.entry);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Settings'),
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
                          'App Settings',
                          style: theme.textTheme.headlineMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: FansivibeColors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Customize your experience',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                        ),
                        const SizedBox(height: 24),
                        FansivibeCard(
                          child: Column(
                            children: List.generate(_items.length, (i) {
                              final item = _items[i];
                              return Column(
                                children: [
                                  _SettingsTile(
                                    item: item,
                                    onToggle: item.isSwitch
                                        ? (val) => _onToggle(i, val)
                                        : null,
                                    onTap: item.label == 'Weather Location'
                                        ? _onSelectCity
                                        : null,
                                  ),
                                  if (i < _items.length - 1)
                                    Divider(
                                      height: 1,
                                      color: FansivibeColors.accentGold
                                          .withValues(alpha: 0.1),
                                      indent: 0,
                                    ),
                                ],
                              );
                            }),
                          ),
                        ),
                        if (AuthSession.isAuthenticated && !isGuestUser) ...[
                          const SizedBox(height: 24),
                          Text(
                            'Account',
                            style: theme.textTheme.titleLarge?.copyWith(
                              fontWeight: FontWeight.w600,
                              color: FansivibeColors.textPrimary,
                            ),
                          ),
                          const SizedBox(height: 12),
                          FansivibeCard(
                            child: Column(
                              children: [
                                ListTile(
                                  leading: const Icon(Icons.logout_rounded),
                                  title: const Text('Sign Out'),
                                  onTap: _busy ? null : _handleSignOut,
                                ),
                                Divider(
                                  height: 1,
                                  color: FansivibeColors.accentGold.withValues(
                                    alpha: 0.1,
                                  ),
                                ),
                                ListTile(
                                  leading: Icon(
                                    Icons.delete_forever_rounded,
                                    color: FansivibeColors.error,
                                  ),
                                  title: Text(
                                    'Delete Account',
                                    style: TextStyle(
                                      color: FansivibeColors.error,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  subtitle: const Text(
                                    'Permanently erase your account and data',
                                  ),
                                  onTap: _busy ? null : _showDeleteConfirmation,
                                ),
                              ],
                            ),
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

class _SettingsTile extends StatelessWidget {
  const _SettingsTile({required this.item, this.onToggle, this.onTap});

  final SettingsItem item;
  final ValueChanged<bool>? onToggle;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return InkWell(
      onTap: item.isSwitch ? null : onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.label,
                    style: theme.textTheme.bodyLarge?.copyWith(
                      fontWeight: FontWeight.w500,
                      color: FansivibeColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    item.description,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: FansivibeColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
            if (item.isSwitch)
              Switch(
                value: item.switchValue,
                onChanged: onToggle,
                activeTrackColor: FansivibeColors.accentGold.withValues(
                  alpha: 0.3,
                ),
              )
            else
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (item.value != null)
                    Text(
                      item.value!,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: FansivibeColors.textSecondary,
                      ),
                    ),
                  const SizedBox(width: 4),
                  Icon(
                    Icons.chevron_right_rounded,
                    size: 20,
                    color: FansivibeColors.textSecondary,
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

class _DeleteAccountDialog extends StatefulWidget {
  const _DeleteAccountDialog();

  @override
  State<_DeleteAccountDialog> createState() => _DeleteAccountDialogState();
}

class _DeleteAccountDialogState extends State<_DeleteAccountDialog> {
  final TextEditingController _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Delete account?'),
      content: SizedBox(
        width: 320,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'This permanently erases your account and saved data. Type DELETE to confirm.',
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _controller,
                autofocus: true,
                onChanged: (_) => setState(() {}),
                decoration: const InputDecoration(
                  labelText: 'Type DELETE',
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        TextButton(
          onPressed: _controller.text == 'DELETE'
              ? () => Navigator.of(context).pop(true)
              : null,
          child: const Text('Delete account'),
        ),
      ],
    );
  }
}
