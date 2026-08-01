import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

Color scoreColorFromDouble(double score) {
  if (score >= 0.9) return FansivibeColors.success;
  if (score >= 0.7) return FansivibeColors.accentGold;
  if (score >= 0.5) return FansivibeColors.warning;
  return FansivibeColors.error;
}
