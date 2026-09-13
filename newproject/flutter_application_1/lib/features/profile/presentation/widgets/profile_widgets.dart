import 'package:flutter/material.dart';
import 'package:fansivibe/features/profile/data/profile_mock_data.dart';
import 'package:fansivibe/shared/components/fansi_insight_card.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';

class ProfileHeader extends StatelessWidget {
  const ProfileHeader({required this.data, super.key});

  final ProfileData data;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      children: [
        CircleAvatar(
          radius: 44,
          backgroundColor: FansivibeColors.accentGold.withValues(alpha: 0.2),
          child: Text(
            data.avatarInitials,
            style: theme.textTheme.displayLarge?.copyWith(
              color: FansivibeColors.accentGold,
              fontWeight: FontWeight.bold,
              fontSize: 36,
            ),
          ),
        ),
        const SizedBox(height: 16),
        Text(
          data.name,
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.bold,
            color: FansivibeColors.textPrimary,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          data.username,
          style: theme.textTheme.bodyMedium?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          data.joinDate,
          style: theme.textTheme.bodySmall?.copyWith(
            color: FansivibeColors.textSecondary.withValues(alpha: 0.7),
          ),
        ),
      ],
    );
  }
}

class ProfileHeroCard extends StatelessWidget {
  const ProfileHeroCard({required this.data, this.styleScore, super.key});

  final ProfileData data;

  /// Backend style score (M10-C, STEP 19.16). Null while loading or when
  /// unavailable renders an honest placeholder — never the mock value.
  final int? styleScore;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final xpProgress = (data.styleProgress.current / data.styleProgress.next)
        .clamp(0.0, 1.0);

    return FansivibeCard(
      child: Column(
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 32,
                backgroundColor: FansivibeColors.accentGold.withValues(
                  alpha: 0.15,
                ),
                child: Text(
                  data.avatarInitials,
                  style: theme.textTheme.displayLarge?.copyWith(
                    color: FansivibeColors.accentGold,
                    fontWeight: FontWeight.bold,
                    fontSize: 28,
                  ),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      data.name,
                      style: theme.textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: FansivibeColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      data.username,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: FansivibeColors.textSecondary,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        Icon(
                          Icons.auto_awesome_rounded,
                          size: 14,
                          color: FansivibeColors.accentGold,
                        ),
                        const SizedBox(width: 6),
                        Flexible(
                          child: Text(
                            data.stylistLevel.label,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: FansivibeColors.accentGold,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: FansivibeColors.accentGold.withValues(
                              alpha: 0.12,
                            ),
                            borderRadius: FansivibeRadius.fullBorder,
                          ),
                          child: Text(
                            'Lvl ${data.stylistLevel.level}',
                            style: theme.textTheme.bodySmall?.copyWith(
                              fontWeight: FontWeight.w700,
                              color: FansivibeColors.accentGold,
                              fontFamily: 'sans-serif',
                              fontSize: 11,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Flexible(
                    child: Text(
                      data.styleProgress.label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: FansivibeColors.textSecondary,
                        fontSize: 11,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Flexible(
                    child: Text(
                      '${data.styleProgress.current} / ${data.styleProgress.next}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodySmall?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: FansivibeColors.accentGold,
                        fontFamily: 'sans-serif',
                        fontSize: 11,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              ClipRRect(
                borderRadius: FansivibeRadius.smBorder,
                child: LinearProgressIndicator(
                  value: xpProgress,
                  minHeight: 8,
                  backgroundColor: FansivibeColors.accentGold.withValues(
                    alpha: 0.1,
                  ),
                  valueColor: AlwaysStoppedAnimation<Color>(
                    FansivibeColors.accentGold,
                  ),
                  borderRadius: FansivibeRadius.smBorder,
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          Row(
            children: [
              Expanded(
                child: Container(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  decoration: BoxDecoration(
                    color: FansivibeColors.surfaceContainerLow,
                    borderRadius: FansivibeRadius.smBorder,
                  ),
                  child: Column(
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.star_rounded,
                            size: 16,
                            color: FansivibeColors.accentGold,
                          ),
                          const SizedBox(width: 4),
                          Flexible(
                            child: Text(
                              styleScore?.toString() ?? '–',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: theme.textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.bold,
                                color: FansivibeColors.textPrimary,
                                fontFamily: 'sans-serif',
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 2),
                      Text(
                        'Style Score',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: FansivibeColors.textSecondary,
                          fontSize: 11,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Container(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  decoration: BoxDecoration(
                    color: FansivibeColors.surfaceContainerLow,
                    borderRadius: FansivibeRadius.smBorder,
                  ),
                  child: Column(
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.leaderboard_rounded,
                            size: 16,
                            color: FansivibeColors.accentGold,
                          ),
                          const SizedBox(width: 4),
                          Flexible(
                            child: Text(
                              '#${data.globalRank.position}',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: theme.textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.bold,
                                color: FansivibeColors.textPrimary,
                                fontFamily: 'sans-serif',
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 2),
                      Text(
                        'Global Rank',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: FansivibeColors.textSecondary,
                          fontSize: 11,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Center(
            child: Text(
              data.joinDate,
              style: theme.textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textSecondary.withValues(alpha: 0.6),
                fontSize: 11,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class StylistLevelBadge extends StatelessWidget {
  const StylistLevelBadge({required this.data, super.key});

  final StylistLevelData data;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final progress = data.level / data.maxLevel;

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          Icons.auto_awesome_rounded,
          size: 18,
          color: FansivibeColors.accentGold,
        ),
        const SizedBox(width: 8),
        Text(
          data.label,
          style: theme.textTheme.bodyMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.accentGold,
          ),
        ),
        const SizedBox(width: 8),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(
            color: FansivibeColors.accentGold.withValues(alpha: 0.15),
            borderRadius: FansivibeRadius.smdBorder,
          ),
          child: Text(
            'Lvl ${data.level}',
            style: theme.textTheme.bodySmall?.copyWith(
              fontWeight: FontWeight.w700,
              color: FansivibeColors.accentGold,
              fontFamily: 'sans-serif',
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 60,
          height: 6,
          child: ClipRRect(
            borderRadius: FansivibeRadius.xsBorder,
            child: LinearProgressIndicator(
              value: progress,
              backgroundColor: FansivibeColors.accentGold.withValues(
                alpha: 0.1,
              ),
              valueColor: AlwaysStoppedAnimation<Color>(
                FansivibeColors.accentGold,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class ProfileStatRow extends StatelessWidget {
  const ProfileStatRow({required this.score, required this.rank, super.key});

  final int score;
  final GlobalRankData rank;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _buildStat(
            context,
            icon: Icons.star_rounded,
            value: '$score',
            label: 'Style Score',
          ),
        ),
        Container(
          width: 1,
          height: 40,
          color: FansivibeColors.accentGold.withValues(alpha: 0.2),
        ),
        Expanded(
          child: _buildStat(
            context,
            icon: Icons.leaderboard_rounded,
            value: '#${rank.position}',
            label: 'Global Rank',
          ),
        ),
      ],
    );
  }

  Widget _buildStat(
    BuildContext context, {
    required IconData icon,
    required String value,
    required String label,
  }) {
    final theme = Theme.of(context);

    return Column(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 18, color: FansivibeColors.accentGold),
            const SizedBox(width: 6),
            Text(
              value,
              style: theme.textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.bold,
                color: FansivibeColors.textPrimary,
                fontFamily: 'sans-serif',
              ),
            ),
          ],
        ),
        const SizedBox(height: 2),
        Text(
          label,
          style: theme.textTheme.bodySmall?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
        ),
      ],
    );
  }
}

class StyleProgressIndicator extends StatelessWidget {
  const StyleProgressIndicator({required this.data, super.key});

  final StyleProgressData data;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final progress = (data.current / data.next).clamp(0.0, 1.0);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Flexible(
              child: Text(
                data.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
              ),
            ),
            const SizedBox(width: 8),
            Flexible(
              child: Text(
                '${data.current} / ${data.next}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.accentGold,
                  fontFamily: 'sans-serif',
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        ClipRRect(
          borderRadius: FansivibeRadius.xsBorder,
          child: LinearProgressIndicator(
            value: progress,
            minHeight: 10,
            backgroundColor: FansivibeColors.accentGold.withValues(alpha: 0.1),
            valueColor: AlwaysStoppedAnimation<Color>(
              FansivibeColors.accentGold,
            ),
            borderRadius: FansivibeRadius.xsBorder,
          ),
        ),
      ],
    );
  }
}

class AchievementGrid extends StatelessWidget {
  const AchievementGrid({required this.achievements, super.key});

  final List<AchievementData> achievements;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: achievements.map((a) {
        final isUnlocked = a.unlocked;
        return SizedBox(
          width: 80,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 52,
                height: 52,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: isUnlocked
                      ? FansivibeColors.accentGold.withValues(alpha: 0.2)
                      : FansivibeColors.surface,
                  border: Border.all(
                    color: isUnlocked
                        ? FansivibeColors.accentGold.withValues(alpha: 0.5)
                        : FansivibeColors.accentGold.withValues(alpha: 0.1),
                  ),
                ),
                child: Icon(
                  _getIconData(a.iconName),
                  size: 22,
                  color: isUnlocked
                      ? FansivibeColors.accentGold
                      : FansivibeColors.textSecondary.withValues(alpha: 0.4),
                ),
              ),
              const SizedBox(height: 6),
              Text(
                a.label,
                style: theme.textTheme.bodySmall?.copyWith(
                  fontSize: 11,
                  color: isUnlocked
                      ? FansivibeColors.textPrimary
                      : FansivibeColors.textSecondary.withValues(alpha: 0.5),
                ),
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        );
      }).toList(),
    );
  }

  IconData _getIconData(String name) {
    switch (name) {
      case 'local_fire_department':
        return Icons.local_fire_department_rounded;
      case 'emoji_events':
        return Icons.emoji_events_rounded;
      case 'star':
        return Icons.star_rounded;
      case 'checkroom':
        return Icons.checkroom_rounded;
      case 'explore':
        return Icons.explore_rounded;
      case 'auto_awesome':
        return Icons.auto_awesome_rounded;
      default:
        return Icons.circle_rounded;
    }
  }
}

class AchievementBar extends StatelessWidget {
  const AchievementBar({required this.achievements, super.key});

  final List<AchievementData> achievements;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final unlocked = achievements.where((a) => a.unlocked).length;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(
              Icons.emoji_events_rounded,
              size: 18,
              color: FansivibeColors.accentGold,
            ),
            const SizedBox(width: 8),
            Flexible(
              child: Text(
                'Achievements',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.textPrimary,
                ),
              ),
            ),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                color: FansivibeColors.accentGold.withValues(alpha: 0.1),
                borderRadius: FansivibeRadius.fullBorder,
              ),
              child: Text(
                '$unlocked/${achievements.length}',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.accentGold,
                  fontWeight: FontWeight.w600,
                  fontSize: 11,
                  fontFamily: 'sans-serif',
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 14),
        SizedBox(
          height: 72,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: achievements.length,
            separatorBuilder: (_, __) => const SizedBox(width: 12),
            itemBuilder: (context, index) {
              final a = achievements[index];
              final isUnlocked = a.unlocked;

              return Column(
                children: [
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: isUnlocked
                          ? FansivibeColors.accentGold.withValues(alpha: 0.18)
                          : FansivibeColors.surface,
                      border: Border.all(
                        color: isUnlocked
                            ? FansivibeColors.accentGold.withValues(alpha: 0.45)
                            : FansivibeColors.accentGold.withValues(
                                alpha: 0.08,
                              ),
                      ),
                    ),
                    child: Icon(
                      _iconFromName(a.iconName),
                      size: 20,
                      color: isUnlocked
                          ? FansivibeColors.accentGold
                          : FansivibeColors.textSecondary.withValues(
                              alpha: 0.35,
                            ),
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    a.label,
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontSize: 10,
                      color: isUnlocked
                          ? FansivibeColors.textPrimary
                          : FansivibeColors.textSecondary.withValues(
                              alpha: 0.5,
                            ),
                    ),
                  ),
                ],
              );
            },
          ),
        ),
      ],
    );
  }

  IconData _iconFromName(String name) {
    switch (name) {
      case 'local_fire_department':
        return Icons.local_fire_department_rounded;
      case 'emoji_events':
        return Icons.emoji_events_rounded;
      case 'star':
        return Icons.star_rounded;
      case 'checkroom':
        return Icons.checkroom_rounded;
      case 'explore':
        return Icons.explore_rounded;
      case 'auto_awesome':
        return Icons.auto_awesome_rounded;
      default:
        return Icons.circle_rounded;
    }
  }
}

class SavedLooksRow extends StatelessWidget {
  const SavedLooksRow({required this.looks, super.key});

  final List<SavedLookPreview> looks;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SizedBox(
      height: 100,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: looks.length,
        separatorBuilder: (_, __) => const SizedBox(width: 12),
        itemBuilder: (context, index) {
          final look = looks[index];
          return _buildLookTile(context, look, theme);
        },
      ),
    );
  }

  Widget _buildLookTile(
    BuildContext context,
    SavedLookPreview look,
    ThemeData theme,
  ) {
    Color scoreColor;
    if (look.score >= 90) {
      scoreColor = FansivibeColors.success;
    } else if (look.score >= 80) {
      scoreColor = FansivibeColors.accentGold;
    } else {
      scoreColor = FansivibeColors.warning;
    }

    return Container(
      width: 130,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.smdBorder,
      ),
      child: FittedBox(
        fit: BoxFit.scaleDown,
        alignment: Alignment.topLeft,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: FansivibeColors.accentGold.withValues(alpha: 0.15),
                borderRadius: FansivibeRadius.smBorder,
              ),
              child: Icon(
                Icons.checkroom_rounded,
                size: 18,
                color: FansivibeColors.accentGold,
              ),
            ),
            SizedBox(height: FansivibeSpacing.xs),
            Text(
              look.title,
              style: theme.textTheme.bodySmall?.copyWith(
                fontWeight: FontWeight.w600,
                color: FansivibeColors.textPrimary,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            const SizedBox(height: 2),
            Row(
              children: [
                Icon(Icons.star_rounded, size: 12, color: scoreColor),
                const SizedBox(width: 4),
                Text(
                  '${look.score}',
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: scoreColor,
                    fontFamily: 'sans-serif',
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class StyleDnaCard extends StatelessWidget {
  const StyleDnaCard({required this.data, super.key});

  final StyleDnaData data;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildDnaInsight(
          context,
          Icons.palette_rounded,
          'Skin Tone',
          data.skinTone,
        ),
        const SizedBox(height: 10),
        _buildDnaInsight(
          context,
          Icons.face_rounded,
          'Face Shape',
          data.faceShape,
        ),
        const SizedBox(height: 10),
        _buildDnaInsight(
          context,
          Icons.accessibility_rounded,
          'Body Type',
          data.bodyType,
        ),
        const SizedBox(height: 10),
        _buildDnaInsight(
          context,
          Icons.style_rounded,
          'Style Type',
          data.styleType,
        ),
      ],
    );
  }

  Widget _buildDnaInsight(
    BuildContext context,
    IconData icon,
    String label,
    String value,
  ) {
    return FansiInsightCard(
      icon: icon,
      title: label,
      body: value,
      accentColor: FansivibeColors.accentGold,
    );
  }
}

class ProfileMenuCard extends StatelessWidget {
  const ProfileMenuCard({required this.action, this.onTap, super.key});

  final ProfileMenuAction action;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDestructive = action.id == 'sign_out';

    return InkWell(
      onTap: onTap,
      borderRadius: FansivibeRadius.smdBorder,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 4),
        child: Row(
          children: [
            Icon(
              _getIconData(action.iconName),
              size: 22,
              color: isDestructive
                  ? FansivibeColors.error
                  : FansivibeColors.accentGold,
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Text(
                action.label,
                style: theme.textTheme.bodyLarge?.copyWith(
                  fontWeight: FontWeight.w500,
                  color: isDestructive
                      ? FansivibeColors.error
                      : FansivibeColors.textPrimary,
                ),
              ),
            ),
            Icon(
              Icons.chevron_right_rounded,
              size: 20,
              color: FansivibeColors.textSecondary,
            ),
          ],
        ),
      ),
    );
  }

  IconData _getIconData(String name) {
    switch (name) {
      case 'tune_rounded':
        return Icons.tune_rounded;
      case 'bookmark_rounded':
        return Icons.bookmark_rounded;
      case 'workspace_premium_rounded':
        return Icons.workspace_premium_rounded;
      case 'help_outline_rounded':
        return Icons.help_outline_rounded;
      case 'settings_rounded':
        return Icons.settings_rounded;
      case 'logout_rounded':
        return Icons.logout_rounded;
      default:
        return Icons.circle_rounded;
    }
  }
}
