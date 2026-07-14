import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/features/outfit_scan/data/outfit_scan_mock_data.dart';

class CameraPreviewPlaceholder extends StatelessWidget {
  const CameraPreviewPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      height: 280,
      width: double.infinity,
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Stack(
        fit: StackFit.expand,
        children: [
          Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.camera_alt_rounded,
                  size: 64,
                  color: FansivibeColors.accentGold.withValues(alpha: 0.4),
                ),
                const SizedBox(height: 12),
                Text(
                  'Camera Preview',
                  style: theme.textTheme.bodyLarge?.copyWith(
                    color: FansivibeColors.textSecondary,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'Point your camera at your outfit',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: FansivibeColors.textSecondary.withValues(alpha: 0.7),
                  ),
                ),
              ],
            ),
          ),
          Positioned(
            top: 12,
            right: 12,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: FansivibeColors.accentGold.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: FansivibeColors.accentGold.withValues(alpha: 0.4),
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: 8,
                    height: 8,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation<Color>(
                        FansivibeColors.accentGold,
                      ),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    'AI Analysis Active',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: FansivibeColors.accentGold,
                      fontWeight: FontWeight.w600,
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class CheckIndicator extends StatelessWidget {
  const CheckIndicator({
    required this.label,
    required this.isPassing,
    super.key,
  });

  final String label;
  final bool isPassing;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = isPassing
        ? const Color(0xFF4CAF50)
        : FansivibeColors.textSecondary.withValues(alpha: 0.5);

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          isPassing
              ? Icons.check_circle_rounded
              : Icons.hourglass_empty_rounded,
          size: 14,
          color: color,
        ),
        const SizedBox(width: 6),
        Text(
          label,
          style: theme.textTheme.bodySmall?.copyWith(
            color: color,
            fontWeight: isPassing ? FontWeight.w500 : FontWeight.normal,
          ),
        ),
      ],
    );
  }
}

class ProcessingStageIndicator extends StatelessWidget {
  const ProcessingStageIndicator({
    required this.stage,
    required this.isActive,
    required this.isComplete,
    super.key,
  });

  final ProcessingStage stage;
  final bool isActive;
  final bool isComplete;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final Color iconColor;
    final Widget icon;

    if (isComplete) {
      iconColor = const Color(0xFF4CAF50);
      icon = Icon(Icons.check_circle_rounded, size: 22, color: iconColor);
    } else if (isActive) {
      iconColor = FansivibeColors.accentGold;
      icon = SizedBox(
        width: 22,
        height: 22,
        child: CircularProgressIndicator(
          strokeWidth: 2.5,
          valueColor: AlwaysStoppedAnimation<Color>(iconColor),
        ),
      );
    } else {
      iconColor = FansivibeColors.textSecondary.withValues(alpha: 0.3);
      icon = Icon(
        Icons.radio_button_unchecked_rounded,
        size: 22,
        color: iconColor,
      );
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          icon,
          const SizedBox(width: 14),
          Expanded(
            child: Text(
              stage.label,
              style: theme.textTheme.bodyLarge?.copyWith(
                color: isComplete
                    ? FansivibeColors.textPrimary
                    : isActive
                    ? FansivibeColors.textPrimary
                    : FansivibeColors.textSecondary.withValues(alpha: 0.4),
                fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

class AnalysisSectionCard extends StatelessWidget {
  const AnalysisSectionCard({required this.section, super.key});

  final AnalysisSection section;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scoreColor = _getScoreColor(section.score);

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: scoreColor.withValues(alpha: 0.2), width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  section.label,
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.textPrimary,
                  ),
                ),
              ),
              if (section.score != null) ...[
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: scoreColor.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                      color: scoreColor.withValues(alpha: 0.3),
                    ),
                  ),
                  child: Text(
                    '${(section.score! * 100).round()}%',
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: scoreColor,
                      fontFamily: 'sans-serif',
                    ),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 12),
          Text(
            section.description,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: FansivibeColors.textPrimary,
              height: 1.6,
            ),
          ),
          if (section.detail != null) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Icon(Icons.info_outline_rounded, size: 14, color: scoreColor),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    section.detail!,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: scoreColor,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Color _getScoreColor(double? score) {
    if (score == null) return FansivibeColors.accentGold;
    if (score >= 0.9) return const Color(0xFF4CAF50);
    if (score >= 0.8) return FansivibeColors.accentGold;
    if (score >= 0.7) return const Color(0xFFFF9800);
    return const Color(0xFFF44336);
  }
}

class DetectedItemChip extends StatelessWidget {
  const DetectedItemChip({required this.item, super.key});

  final DetectedClothingItem item;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.15),
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: FansivibeColors.accentGold.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(
              _categoryIcon(item.category),
              size: 20,
              color: FansivibeColors.accentGold,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.name,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w500,
                    color: FansivibeColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 2),
                Row(
                  children: [
                    Text(
                      item.category,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: FansivibeColors.textSecondary,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color: _parseColor(item.color),
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: FansivibeColors.textSecondary.withValues(
                            alpha: 0.3,
                          ),
                          width: 1,
                        ),
                      ),
                    ),
                    const SizedBox(width: 4),
                    Text(
                      item.color,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: FansivibeColors.textSecondary,
                      ),
                    ),
                    if (item.material != null) ...[
                      const SizedBox(width: 8),
                      Text(
                        item.material!,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: FansivibeColors.textSecondary.withValues(
                            alpha: 0.7,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  IconData _categoryIcon(String category) {
    switch (category.toLowerCase()) {
      case 'outerwear':
        return Icons.checkroom_rounded;
      case 'tops':
        return Icons.person_rounded;
      case 'bottoms':
        return Icons.accessibility_rounded;
      case 'footwear':
        return Icons.directions_walk_rounded;
      case 'accessories':
        return Icons.diamond_rounded;
      default:
        return Icons.category_rounded;
    }
  }

  Color _parseColor(String colorName) {
    switch (colorName.toLowerCase()) {
      case 'charcoal':
      case 'black':
        return const Color(0xFF2C2C2C);
      case 'off-white':
      case 'white':
        return const Color(0xFFF0F0F0);
      case 'navy':
      case 'blue':
        return const Color(0xFF1A237E);
      case 'brown':
        return const Color(0xFF5D4037);
      case 'gray':
      case 'grey':
        return const Color(0xFF757575);
      case 'beige':
        return const Color(0xFFD7C8A8);
      default:
        return FansivibeColors.accentGold;
    }
  }
}
