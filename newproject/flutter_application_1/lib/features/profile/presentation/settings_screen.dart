import 'package:flutter/material.dart';
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
  });

  final UserProfileRepository? userProfileRepository;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late UserProfileRepository _userProfileRepo;
  late List<SettingsItem> _items;

  @override
  void initState() {
    super.initState();
    _userProfileRepo = widget.userProfileRepository ?? UserProfileRepositoryImpl();
    _items = _buildItems(LocalStorage.settings);

    _userProfileRepo.fetchProfile().then((profile) {
      if (!mounted || profile == null) return;
      setState(() {
        _items = _buildItems(profile.settings);
      });
    });
  }

  List<SettingsItem> _buildItems(Map<String, dynamic> settings) {
    return ProfileMockData.settingsGroups.map((s) {
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
  const _SettingsTile({required this.item, this.onToggle});

  final SettingsItem item;
  final ValueChanged<bool>? onToggle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
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
    );
  }
}
