import 'package:flutter/material.dart';

// ponytail: const map lookup, add entries here instead of new branches.
const _iconsByName = <String, IconData>{
  'lightbulb_outline_rounded': Icons.lightbulb_outline_rounded,
  'trending_up_rounded': Icons.trending_up_rounded,
  'insights_rounded': Icons.insights_rounded,
  'psychology_rounded': Icons.psychology_rounded,
  'auto_awesome_rounded': Icons.auto_awesome_rounded,
  'checkroom_rounded': Icons.checkroom_rounded,
  'person_rounded': Icons.person_rounded,
  'accessibility_rounded': Icons.accessibility_rounded,
  'directions_walk_rounded': Icons.directions_walk_rounded,
  'diamond_rounded': Icons.diamond_rounded,
  'camera_alt_outlined': Icons.camera_alt_outlined,
  'checkroom_outlined': Icons.checkroom_outlined,
  'refresh_rounded': Icons.refresh_rounded,
  'auto_awesome_outlined': Icons.auto_awesome_outlined,
  'event_outlined': Icons.event_outlined,
  'local_fire_department_rounded': Icons.local_fire_department_rounded,
  'emoji_events_rounded': Icons.emoji_events_rounded,
  'star_rounded': Icons.star_rounded,
  'explore_rounded': Icons.explore_rounded,
  'tune_rounded': Icons.tune_rounded,
  'bookmark_rounded': Icons.bookmark_rounded,
  'workspace_premium_rounded': Icons.workspace_premium_rounded,
  'help_outline_rounded': Icons.help_outline_rounded,
  'settings_rounded': Icons.settings_rounded,
  'logout_rounded': Icons.logout_rounded,
};

IconData iconFromName(String name) =>
    _iconsByName[name] ?? Icons.circle_rounded;
