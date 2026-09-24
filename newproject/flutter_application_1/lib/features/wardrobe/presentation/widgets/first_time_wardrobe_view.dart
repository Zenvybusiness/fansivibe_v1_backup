import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// Custom painter for the gold coat hanger icon matching the PDF reference.
class GoldHangerPainter extends CustomPainter {
  final Color color;

  const GoldHangerPainter({this.color = FansivibeColors.primary});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.4
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    final w = size.width;
    final h = size.height;

    // Top hook: starts at upper right curve, loops down into the hanger apex
    final hookPath = Path();
    hookPath.moveTo(w * 0.58, h * 0.16);
    hookPath.cubicTo(
      w * 0.64, h * 0.04,
      w * 0.44, h * 0.04,
      w * 0.46, h * 0.18,
    );
    hookPath.cubicTo(
      w * 0.48, h * 0.25,
      w * 0.50, h * 0.28,
      w * 0.50, h * 0.35,
    );
    canvas.drawPath(hookPath, paint);

    // Hanger triangular body
    final bodyPath = Path();
    bodyPath.moveTo(w * 0.50, h * 0.35);
    bodyPath.lineTo(w * 0.88, h * 0.62);
    bodyPath.arcToPoint(
      Offset(w * 0.84, h * 0.68),
      radius: const Radius.circular(3),
    );
    bodyPath.lineTo(w * 0.16, h * 0.68);
    bodyPath.arcToPoint(
      Offset(w * 0.12, h * 0.62),
      radius: const Radius.circular(3),
    );
    bodyPath.lineTo(w * 0.50, h * 0.35);
    canvas.drawPath(bodyPath, paint);

    // Bottom horizontal crossbar loop
    final bottomPath = Path();
    bottomPath.moveTo(w * 0.42, h * 0.68);
    bottomPath.lineTo(w * 0.42, h * 0.82);
    bottomPath.lineTo(w * 0.58, h * 0.82);
    bottomPath.lineTo(w * 0.58, h * 0.68);
    canvas.drawPath(bottomPath, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

/// The First-Time / Empty Wardrobe Experience screen for new users in the initial
/// exploration stage with 0 wardrobe items, adhering exactly to the PDF specification.
class FirstTimeWardrobeView extends StatelessWidget {
  final VoidCallback onAddFirstItem;
  final VoidCallback onImportFromPhotos;

  const FirstTimeWardrobeView({
    super.key,
    required this.onAddFirstItem,
    required this.onImportFromPhotos,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480),
        child: SingleChildScrollView(
          physics: const BouncingScrollPhysics(),
          padding: const EdgeInsets.symmetric(
            horizontal: FansivibeSpacing.xl,
            vertical: FansivibeSpacing.xl,
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              const SizedBox(height: FansivibeSpacing.xl),

              // 1. Gold Hanger Icon
              CustomPaint(
                size: const Size(68, 68),
                painter: const GoldHangerPainter(
                  color: FansivibeColors.primary,
                ),
              ),
              const SizedBox(height: FansivibeSpacing.xxl),

              // 2. Editorial Headline: Build your smart wardrobe
              Text(
                'Build your smart\nwardrobe',
                textAlign: TextAlign.center,
                style: FansivibeTypography.headlineMediumWithFamily.copyWith(
                  fontSize: 34,
                  fontWeight: FontWeight.w400,
                  height: 1.18,
                  letterSpacing: -0.3,
                  color: FansivibeColors.onSurface,
                ),
              ),
              const SizedBox(height: FansivibeSpacing.md),

              // 3. Subtitle
              Text(
                'Add your clothes so AI can create\nbetter outfits for you.',
                textAlign: TextAlign.center,
                style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                  fontSize: 16,
                  height: 1.45,
                  color: FansivibeColors.secondary,
                ),
              ),
              const SizedBox(height: 38),

              // 4. Feature Highlights with icons
              _buildFeatureRow(
                icon: Icons.auto_awesome,
                label: 'CREATE COMBINATIONS',
              ),
              const SizedBox(height: FansivibeSpacing.lg),
              _buildFeatureRow(
                icon: Icons.smart_toy_outlined,
                label: 'AI RECOMMENDATIONS',
              ),
              const SizedBox(height: FansivibeSpacing.lg),
              _buildFeatureRow(
                icon: Icons.trending_up_rounded,
                label: 'STYLE SCORE',
              ),
              const SizedBox(height: 48),

              // 5. Primary Action: Add First Item
              SizedBox(
                width: double.infinity,
                height: 56,
                child: ElevatedButton(
                  onPressed: onAddFirstItem,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: FansivibeColors.primary,
                    foregroundColor: FansivibeColors.onPrimary,
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                      borderRadius: FansivibeRadius.fullBorder,
                    ),
                  ),
                  child: Text(
                    'Add First Item',
                    style: FansivibeTypography.titleLargeWithFamily.copyWith(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      color: FansivibeColors.onPrimary,
                      letterSpacing: 0.2,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: FansivibeSpacing.md),

              // 6. Secondary Action: IMPORT FROM PHOTOS
              InkWell(
                onTap: onImportFromPhotos,
                borderRadius: FansivibeRadius.smdBorder,
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: FansivibeSpacing.md,
                    vertical: FansivibeSpacing.sm,
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(
                        Icons.photo_library_outlined,
                        size: 16,
                        color: FansivibeColors.primary,
                      ),
                      const SizedBox(width: FansivibeSpacing.sm),
                      Text(
                        'IMPORT FROM PHOTOS',
                        style: FansivibeTypography.labelMediumWithFamily.copyWith(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 2.2,
                          color: FansivibeColors.primary,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: FansivibeSpacing.xl),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildFeatureRow({
    required IconData icon,
    required String label,
  }) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(
          icon,
          size: 18,
          color: FansivibeColors.primary,
        ),
        const SizedBox(width: FansivibeSpacing.md),
        Text(
          label,
          style: FansivibeTypography.labelMediumWithFamily.copyWith(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            letterSpacing: 2.0,
            color: FansivibeColors.onSurface.withValues(alpha: 0.9),
          ),
        ),
      ],
    );
  }
}
