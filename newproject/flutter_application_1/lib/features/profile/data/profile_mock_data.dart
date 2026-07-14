class ProfileData {
  const ProfileData({
    required this.name,
    required this.username,
    required this.avatarInitials,
    required this.joinDate,
    required this.stylistLevel,
    required this.styleScore,
    required this.globalRank,
    required this.styleProgress,
    required this.styleDna,
    required this.achievements,
    required this.savedLooks,
    required this.menuActions,
  });

  final String name;
  final String username;
  final String avatarInitials;
  final String joinDate;
  final StylistLevelData stylistLevel;
  final int styleScore;
  final GlobalRankData globalRank;
  final StyleProgressData styleProgress;
  final StyleDnaData styleDna;
  final List<AchievementData> achievements;
  final List<SavedLookPreview> savedLooks;
  final List<ProfileMenuAction> menuActions;

  static const ProfileData mock = ProfileData(
    name: 'Alex',
    username: '@alex_styles',
    avatarInitials: 'A',
    joinDate: 'Member since Jan 2026',
    stylistLevel: StylistLevelData(
      label: 'Style Seeker',
      level: 4,
      maxLevel: 10,
    ),
    styleScore: 84,
    globalRank: GlobalRankData(position: 128, total: 12450),
    styleProgress: StyleProgressData(
      current: 3200,
      next: 5000,
      label: 'XP to next level',
    ),
    styleDna: StyleDnaData(
      skinTone: 'Warm Medium',
      faceShape: 'Oval',
      bodyType: 'Athletic',
      styleType: 'Modern Minimalist',
    ),
    achievements: [
      AchievementData(
        iconName: 'local_fire_department',
        label: '7-Day Streak',
        unlocked: true,
      ),
      AchievementData(
        iconName: 'emoji_events',
        label: 'Style Guru',
        unlocked: true,
      ),
      AchievementData(iconName: 'star', label: 'Score 90+', unlocked: true),
      AchievementData(iconName: 'checkroom', label: '20 Looks', unlocked: true),
      AchievementData(iconName: 'explore', label: 'Explorer', unlocked: false),
      AchievementData(
        iconName: 'auto_awesome',
        label: 'Trendsetter',
        unlocked: false,
      ),
    ],
    savedLooks: [
      SavedLookPreview(id: '1', title: 'Modern Minimalist', score: 87),
      SavedLookPreview(id: '2', title: 'Weekend Casual', score: 82),
      SavedLookPreview(id: '3', title: 'Smart Business', score: 91),
      SavedLookPreview(id: '4', title: 'Date Night', score: 85),
    ],
    menuActions: [
      ProfileMenuAction(
        id: 'preferences',
        label: 'Preferences',
        iconName: 'tune_rounded',
      ),
      ProfileMenuAction(
        id: 'saved_looks',
        label: 'Saved Looks',
        iconName: 'bookmark_rounded',
      ),
      ProfileMenuAction(
        id: 'subscription',
        label: 'Subscription',
        iconName: 'workspace_premium_rounded',
      ),
      ProfileMenuAction(
        id: 'support',
        label: 'Support',
        iconName: 'help_outline_rounded',
      ),
      ProfileMenuAction(
        id: 'settings',
        label: 'Settings',
        iconName: 'settings_rounded',
      ),
      ProfileMenuAction(
        id: 'sign_out',
        label: 'Sign Out',
        iconName: 'logout_rounded',
      ),
    ],
  );
}

class StylistLevelData {
  const StylistLevelData({
    required this.label,
    required this.level,
    required this.maxLevel,
  });

  final String label;
  final int level;
  final int maxLevel;
}

class GlobalRankData {
  const GlobalRankData({required this.position, required this.total});

  final int position;
  final int total;
}

class StyleProgressData {
  const StyleProgressData({
    required this.current,
    required this.next,
    required this.label,
  });

  final int current;
  final int next;
  final String label;
}

class StyleDnaData {
  const StyleDnaData({
    required this.skinTone,
    required this.faceShape,
    required this.bodyType,
    required this.styleType,
  });

  final String skinTone;
  final String faceShape;
  final String bodyType;
  final String styleType;
}

class AchievementData {
  const AchievementData({
    required this.iconName,
    required this.label,
    required this.unlocked,
  });

  final String iconName;
  final String label;
  final bool unlocked;
}

class SavedLookPreview {
  const SavedLookPreview({
    required this.id,
    required this.title,
    required this.score,
  });

  final String id;
  final String title;
  final int score;
}

class ProfileMenuAction {
  const ProfileMenuAction({
    required this.id,
    required this.label,
    required this.iconName,
  });

  final String id;
  final String label;
  final String iconName;
}
