import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

class VibeCard extends StatelessWidget {
  final String label;
  final List<Color> gradientColors;
  final List<Offset> lineOffsets;
  final bool isSelected;
  final VoidCallback onTap;

  const VibeCard({
    required this.label,
    required this.gradientColors,
    required this.lineOffsets,
    required this.isSelected,
    required this.onTap,
    super.key,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOut,
        decoration: BoxDecoration(
          color: FansivibeColors.surfaceContainer,
          borderRadius: FansivibeRadius.mdBorder,
          border: Border.all(
            color: isSelected ? FansivibeColors.primary : Colors.transparent,
            width: isSelected ? 2 : 0,
          ),
          boxShadow: isSelected
              ? [
                  BoxShadow(
                    color: FansivibeColors.primary.withValues(alpha: 0.15),
                    blurRadius: 16,
                    spreadRadius: 1,
                  ),
                ]
              : null,
        ),
        child: Column(
          children: [
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.vertical(
                  top: Radius.circular(FansivibeRadius.md - 1),
                ),
                child: Container(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: gradientColors,
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                  ),
                  child: CustomPaint(
                    painter: _LinePainter(
                      lines: lineOffsets,
                      color: Colors.white.withValues(alpha: 0.08),
                    ),
                  ),
                ),
              ),
            ),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(
                horizontal: FansivibeSpacing.sm + 4,
                vertical: FansivibeSpacing.sm + 4,
              ),
              decoration: BoxDecoration(
                color: isSelected
                    ? FansivibeColors.primary.withValues(alpha: 0.08)
                    : Colors.transparent,
                borderRadius: BorderRadius.only(
                  bottomLeft: Radius.circular(FansivibeRadius.md),
                  bottomRight: Radius.circular(FansivibeRadius.md),
                ),
              ),
              child: Text(
                label,
                style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                  color: isSelected
                      ? FansivibeColors.primary
                      : FansivibeColors.onSurface,
                  fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                ),
                textAlign: TextAlign.center,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LinePainter extends CustomPainter {
  final List<Offset> lines;
  final Color color;

  _LinePainter({required this.lines, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;

    for (final offset in lines) {
      canvas.drawLine(
        Offset(offset.dx * size.width, 0),
        Offset(offset.dy * size.width, size.height),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_LinePainter oldDelegate) =>
      lines != oldDelegate.lines || color != oldDelegate.color;
}
