class PreferenceOption {
  const PreferenceOption({
    required this.label,
    required this.value,
    required this.options,
    this.selectedIndex = 0,
  });

  final String label;
  final String value;
  final List<String> options;
  final int selectedIndex;
}

class SavedLookDetail {
  const SavedLookDetail({
    required this.id,
    required this.title,
    required this.score,
    required this.date,
    required this.items,
  });

  final String id;
  final String title;
  final int score;
  final String date;
  final List<String> items;
}

class SubscriptionPlan {
  const SubscriptionPlan({
    required this.name,
    required this.price,
    required this.period,
    required this.features,
    required this.isPopular,
  });

  final String name;
  final String price;
  final String period;
  final List<String> features;
  final bool isPopular;
}

class SupportTopic {
  const SupportTopic({
    required this.title,
    required this.description,
    required this.iconName,
  });

  final String title;
  final String description;
  final String iconName;
}

class SettingsItem {
  const SettingsItem({
    required this.label,
    required this.description,
    this.value,
    this.isSwitch = false,
    this.switchValue = false,
  });

  final String label;
  final String description;
  final String? value;
  final bool isSwitch;
  final bool switchValue;
}

abstract final class ProfileMockData {
  static const List<PreferenceOption> stylePreferences = [
    PreferenceOption(
      label: 'Style Vibe',
      value: 'Modern Minimalist',
      options: [
        'Modern Minimalist',
        'Classic Elegance',
        'Street Style',
        'Bohemian',
        'Athleisure',
      ],
      selectedIndex: 0,
    ),
    PreferenceOption(
      label: 'Color Palette',
      value: 'Neutral Tones',
      options: [
        'Neutral Tones',
        'Bold & Vibrant',
        'Pastels',
        'Monochrome',
        'Earth Tones',
      ],
      selectedIndex: 0,
    ),
    PreferenceOption(
      label: 'Fit Preference',
      value: 'Tailored',
      options: ['Slim', 'Tailored', 'Regular', 'Relaxed', 'Oversized'],
      selectedIndex: 1,
    ),
    PreferenceOption(
      label: 'Occasion Focus',
      value: 'Smart Casual',
      options: ['Casual', 'Smart Casual', 'Business', 'Formal', 'Streetwear'],
      selectedIndex: 1,
    ),
  ];

  static const List<SavedLookDetail> savedLooks = [
    SavedLookDetail(
      id: '1',
      title: 'Modern Minimalist',
      score: 87,
      date: 'Saved Jul 12',
      items: ['White Linen Shirt', 'Charcoal Trousers', 'Brown Loafers'],
    ),
    SavedLookDetail(
      id: '2',
      title: 'Weekend Casual',
      score: 82,
      date: 'Saved Jul 10',
      items: ['Crew Neck Tee', 'Denim Jacket', 'White Sneakers'],
    ),
    SavedLookDetail(
      id: '3',
      title: 'Smart Business',
      score: 91,
      date: 'Saved Jul 8',
      items: ['Navy Blazer', 'Light Blue Oxford', 'Khaki Chinos'],
    ),
    SavedLookDetail(
      id: '4',
      title: 'Date Night',
      score: 85,
      date: 'Saved Jul 5',
      items: ['Black Henley', 'Leather Jacket', 'Dark Jeans'],
    ),
    SavedLookDetail(
      id: '5',
      title: 'Summer Breeze',
      score: 78,
      date: 'Saved Jul 3',
      items: ['Linen Button-Down', 'Shorts', 'Espadrilles'],
    ),
    SavedLookDetail(
      id: '6',
      title: 'Office Ready',
      score: 88,
      date: 'Saved Jun 28',
      items: ['Wool Blazer', 'Dress Shirt', 'Dress Pants'],
    ),
  ];

  static const List<SubscriptionPlan> plans = [
    SubscriptionPlan(
      name: 'Free',
      price: '\$0',
      period: '/month',
      features: [
        'Basic style score',
        '3 saved looks',
        'Wardrobe up to 20 items',
        'Standard recommendations',
      ],
      isPopular: false,
    ),
    SubscriptionPlan(
      name: 'Premium',
      price: '\$9.99',
      period: '/month',
      features: [
        'Advanced style analytics',
        'Unlimited saved looks',
        'Unlimited wardrobe items',
        'AI outfit generation',
        'Priority support',
      ],
      isPopular: true,
    ),
    SubscriptionPlan(
      name: 'Elite',
      price: '\$19.99',
      period: '/month',
      features: [
        'Everything in Premium',
        'Personal stylist review',
        'Exclusive style insights',
        'Early access to features',
        'VIP support',
      ],
      isPopular: false,
    ),
  ];

  static const List<SupportTopic> topics = [
    SupportTopic(
      title: 'Getting Started',
      description: 'Learn the basics of Fansivibe',
      iconName: 'rocket_launch_rounded',
    ),
    SupportTopic(
      title: 'Style Score',
      description: 'How your style score is calculated',
      iconName: 'bar_chart_rounded',
    ),
    SupportTopic(
      title: 'Wardrobe Management',
      description: 'Managing your digital wardrobe',
      iconName: 'checkroom_rounded',
    ),
    SupportTopic(
      title: 'Account & Privacy',
      description: 'Manage your account and data',
      iconName: 'security_rounded',
    ),
    SupportTopic(
      title: 'Report a Bug',
      description: 'Let us know about an issue',
      iconName: 'bug_report_rounded',
    ),
    SupportTopic(
      title: 'Contact Us',
      description: 'Get in touch with our team',
      iconName: 'mail_rounded',
    ),
  ];

  static const List<SettingsItem> settingsGroups = [
    SettingsItem(
      label: 'Notifications',
      description: 'Daily style tips, recommendations',
      isSwitch: true,
      switchValue: true,
    ),
    SettingsItem(
      label: 'Sound Effects',
      description: 'App interaction sounds',
      isSwitch: true,
      switchValue: false,
    ),
    SettingsItem(
      label: 'Haptic Feedback',
      description: 'Vibration on interactions',
      isSwitch: true,
      switchValue: true,
    ),
    SettingsItem(
      label: 'Theme',
      description: 'Current appearance',
      value: 'Dark',
    ),
    SettingsItem(
      label: 'Units',
      description: 'Measurement system',
      value: 'Imperial',
    ),
    SettingsItem(
      label: 'Data Saver',
      description: 'Reduce image quality on mobile data',
      isSwitch: true,
      switchValue: false,
    ),
  ];
}
