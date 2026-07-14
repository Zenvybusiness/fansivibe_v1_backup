import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

Color scoreColorFromDouble(double score) {
  if (score >= 0.9) return const Color(0xFF4CAF50);
  if (score >= 0.7) return FansivibeColors.accentGold;
  if (score >= 0.5) return const Color(0xFFFF9800);
  return const Color(0xFFF44336);
}
