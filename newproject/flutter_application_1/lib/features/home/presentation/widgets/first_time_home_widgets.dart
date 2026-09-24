import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// Curated look recommendation model for first-time users.
class FirstTimeCuratedLook {
  final String title;
  final List<String> items;
  final String reasoning;
  final String vibe;

  const FirstTimeCuratedLook({
    required this.title,
    required this.items,
    required this.reasoning,
    required this.vibe,
  });
}

const _streetwearLook = FirstTimeCuratedLook(
  title: 'Relaxed Streetwear',
  items: [
    'Oversized Denim Jacket',
    'White Fitted Tee',
    'Dark Straight Jeans',
    'Clean Low Sneakers',
  ],
  reasoning:
      'Built around your preference for relaxed fits and effortless urban '
      'aesthetics. Harmonized color balance rated for early morning warmth.',
  vibe: 'streetwear',
);

const _minimalistLook = FirstTimeCuratedLook(
  title: 'Modern Minimalist',
  items: [
    'Unstructured Charcoal Blazer',
    'Merino Wool Crewneck',
    'Tapered Black Trousers',
    'Clean Low Sneakers',
  ],
  reasoning:
      'Built around your preference for clean lines and intentional simplicity. '
      'Monochromatic tonal balance designed for effortless elegance.',
  vibe: 'minimalist',
);

const _classicLook = FirstTimeCuratedLook(
  title: 'Timeless Tailored',
  items: [
    'Navy Wool Overcoat',
    'Crisp Oxford Shirt',
    'Tailored Chinos',
    'Leather Chelsea Boots',
  ],
  reasoning:
      'Built around your preference for refined silhouettes and investment pieces. '
      'Structured tailoring proportioned for timeless confidence.',
  vibe: 'classic',
);

const _boldLook = FirstTimeCuratedLook(
  title: 'Statement Contrast',
  items: [
    'Structured Colorblock Jacket',
    'Textured Knit Tee',
    'Wide-Leg Pleated Pants',
    'Chunky Derby Shoes',
  ],
  reasoning:
      'Built around your preference for strong colors and confident presence. '
      'High-contrast layering crafted to make a bold first impression.',
  vibe: 'bold',
);

const _naturalLook = FirstTimeCuratedLook(
  title: 'Earth & Texture',
  items: [
    'Linen Overshirt',
    'Organic Cotton Slub Tee',
    'Relaxed Olive Cargoes',
    'Suede Minimalist Runners',
  ],
  reasoning:
      'Built around your preference for tactile textures and relaxed earth tones. '
      'Breathable layering balanced for effortless comfort.',
  vibe: 'natural',
);

const _edgyLook = FirstTimeCuratedLook(
  title: 'Dark Monochrome',
  items: [
    'Asymmetric Biker Jacket',
    'Distressed Charcoal Longline Tee',
    'Slim Raw Denim',
    'Matte Combat Boots',
  ],
  reasoning:
      'Built around your preference for unconventional cuts and artistic dark aesthetics. '
      'Angular silhouette crafted with architectural drape.',
  vibe: 'edgy',
);

FirstTimeCuratedLook getCuratedLookForVibe(String? vibeKey) {
  if (vibeKey != null) {
    final normalized = vibeKey.trim().toLowerCase();
    if (normalized.contains('minimal')) return _minimalistLook;
    if (normalized.contains('classic')) return _classicLook;
    if (normalized.contains('bold')) return _boldLook;
    if (normalized.contains('natural')) return _naturalLook;
    if (normalized.contains('edgy')) return _edgyLook;
    if (normalized.contains('trend') || normalized.contains('street')) {
      return _streetwearLook;
    }
  }
  return _streetwearLook;
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. BRANDING & GREETING HEADER
// ─────────────────────────────────────────────────────────────────────────────

class FirstTimeHeader extends StatelessWidget {
  final String? displayName;

  const FirstTimeHeader({super.key, this.displayName});

  String _formatGreeting() {
    final hour = DateTime.now().hour;
    if (hour < 12) return 'Good Morning';
    if (hour < 17) return 'Good Afternoon';
    return 'Good Evening';
  }

  @override
  Widget build(BuildContext context) {
    final greetingPrefix = _formatGreeting();
    final name = displayName?.trim();
    final greetingText = (name != null && name.isNotEmpty)
        ? '$greetingPrefix, $name'
        : greetingPrefix;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Top navigation/branding row
        Wrap(
          alignment: WrapAlignment.spaceBetween,
          crossAxisAlignment: WrapCrossAlignment.center,
          runSpacing: 8,
          children: [
            Text(
              'F A N S I V I B E',
              style: FansivibeTypography.labelMediumWithFamily.copyWith(
                color: FansivibeColors.onSurface.withValues(alpha: 0.9),
                letterSpacing: 3.0,
                fontSize: 11.5,
                fontWeight: FontWeight.w600,
              ),
            ),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Notification bell with badge dot
                Semantics(
                  button: true,
                  label: 'Notifications',
                  child: InkWell(
                    onTap: () {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: const Text('No new notifications'),
                          backgroundColor:
                              FansivibeColors.surfaceContainerHighest,
                          behavior: SnackBarBehavior.floating,
                          shape: RoundedRectangleBorder(
                            borderRadius: FansivibeRadius.smBorder,
                          ),
                          duration: const Duration(seconds: 2),
                        ),
                      );
                    },
                    borderRadius: BorderRadius.circular(20),
                    child: Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: FansivibeColors.surfaceContainerLow,
                        border: Border.all(
                          color: Colors.white.withValues(alpha: 0.08),
                        ),
                      ),
                      child: Stack(
                        alignment: Alignment.center,
                        children: [
                          Icon(
                            Icons.notifications_none_rounded,
                            size: 19,
                            color: FansivibeColors.onSurface.withValues(
                              alpha: 0.9,
                            ),
                          ),
                          Positioned(
                            top: 8,
                            right: 9,
                            child: Container(
                              width: 6,
                              height: 6,
                              decoration: const BoxDecoration(
                                color: FansivibeColors.primary,
                                shape: BoxShape.circle,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                // Profile Avatar Button
                Semantics(
                  button: true,
                  label: 'Profile',
                  child: InkWell(
                    onTap: () => context.goNamed(RouteNames.profile),
                    borderRadius: BorderRadius.circular(20),
                    child: Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: FansivibeColors.primary.withValues(alpha: 0.15),
                        border: Border.all(
                          color: FansivibeColors.primary.withValues(alpha: 0.4),
                          width: 1.2,
                        ),
                      ),
                      child: ClipOval(
                        child: Image.asset(
                          'assets/images/profile_avatar.png',
                          width: 36,
                          height: 36,
                          fit: BoxFit.cover,
                          errorBuilder: (context, error, stackTrace) => Center(
                            child: Text(
                              (name != null && name.isNotEmpty)
                                  ? name[0].toUpperCase()
                                  : 'A',
                              style:
                                  FansivibeTypography.titleLargeWithFamily.copyWith(
                                fontSize: 14,
                                fontWeight: FontWeight.w700,
                                color: FansivibeColors.primary,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
        const SizedBox(height: 22),
        // Greeting Headline
        Text(
          greetingText,
          style: FansivibeTypography.displayLargeWithFamily.copyWith(
            fontSize: 30,
            fontWeight: FontWeight.w400,
            color: FansivibeColors.onSurface,
            height: 1.15,
            letterSpacing: -0.3,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          "Let's build your style\nprofile.",
          style: FansivibeTypography.bodyLargeWithFamily.copyWith(
            fontSize: 15,
            color: FansivibeColors.secondary,
            height: 1.35,
          ),
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. TODAY'S LOOK CARD & FASHION EDITORIAL VISUAL
// ─────────────────────────────────────────────────────────────────────────────

class TodaysLookCard extends StatelessWidget {
  final FirstTimeCuratedLook look;
  final VoidCallback onTryLook;
  final VoidCallback onChangeStyle;

  const TodaysLookCard({
    super.key,
    required this.look,
    required this.onTryLook,
    required this.onChangeStyle,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: const Color(0xFF181716),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.07),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.45),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Badges Row
          Wrap(
            alignment: WrapAlignment.spaceBetween,
            crossAxisAlignment: WrapCrossAlignment.center,
            runSpacing: 6,
            children: [
              // Left: • TODAY'S LOOK
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 5,
                ),
                decoration: BoxDecoration(
                  color: const Color(0xFF262420).withValues(alpha: 0.9),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.08),
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 6,
                      height: 6,
                      decoration: const BoxDecoration(
                        color: Color(0xFFE3C373),
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      "TODAY'S LOOK",
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.95),
                        fontSize: 9.5,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 1.5,
                      ),
                    ),
                  ],
                ),
              ),
              // Right: INITIAL LOOK
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 5,
                ),
                decoration: BoxDecoration(
                  color: const Color(0xFF262420).withValues(alpha: 0.9),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.08),
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(
                      Icons.verified_outlined,
                      size: 12,
                      color: Color(0xFFE3C373),
                    ),
                    const SizedBox(width: 4),
                    Text(
                      'INITIAL LOOK',
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.95),
                        fontSize: 9.5,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 1.5,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),

          // Main Outfit Visual (approx 65% visual ratio)
          ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: SizedBox(
              width: double.infinity,
              height: 290,
              child: EditorialOutfitVisual(vibe: look.vibe),
            ),
          ),
          const SizedBox(height: 16),

          // Content section (approx 35% ratio)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'CURATED RECOMMENDATION',
                  style: FansivibeTypography.labelSmallWithFamily.copyWith(
                    color: FansivibeColors.primary,
                    letterSpacing: 2.2,
                    fontSize: 10.5,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  look.title,
                  style: FansivibeTypography.headlineMediumWithFamily.copyWith(
                    fontSize: 24,
                    fontWeight: FontWeight.w500,
                    color: FansivibeColors.onSurface,
                    height: 1.2,
                  ),
                ),
                const SizedBox(height: 12),

                // Tags (2x2 or wrapping pills)
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final item in look.items)
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 7,
                        ),
                        decoration: BoxDecoration(
                          color: const Color(0xFF222120),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(
                            color: Colors.white.withValues(alpha: 0.06),
                            width: 0.8,
                          ),
                        ),
                        child: Text(
                          item,
                          style: TextStyle(
                            color: const Color(0xFFE5E2E1),
                            fontSize: 11.5,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 14),

                // Reasoning Text
                Text(
                  look.reasoning,
                  style: TextStyle(
                    color: const Color(0xFF9E9E9E),
                    fontSize: 12.5,
                    height: 1.48,
                  ),
                ),
                const SizedBox(height: 18),

                // Action Buttons Row: TRY THIS LOOK / CHANGE STYLE
                Row(
                  children: [
                    // Primary Action: TRY THIS LOOK
                    Expanded(
                      child: SizedBox(
                        height: 44,
                        child: ElevatedButton.icon(
                          onPressed: onTryLook,
                          icon: const Icon(
                            Icons.checkroom_rounded,
                            size: 16,
                            color: Color(0xFF141414),
                          ),
                          label: const Text(
                            'TRY THIS LOOK',
                            style: TextStyle(
                              color: Color(0xFF141414),
                              fontWeight: FontWeight.w800,
                              fontSize: 11,
                              letterSpacing: 1.0,
                            ),
                          ),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: FansivibeColors.primary,
                            elevation: 0,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(24),
                            ),
                            padding: const EdgeInsets.symmetric(horizontal: 10),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    // Secondary Action: CHANGE STYLE
                    Expanded(
                      child: SizedBox(
                        height: 44,
                        child: OutlinedButton.icon(
                          onPressed: onChangeStyle,
                          icon: const Icon(
                            Icons.swap_horiz_rounded,
                            size: 16,
                            color: Colors.white,
                          ),
                          label: const Text(
                            'CHANGE STYLE',
                            style: TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                              fontSize: 11,
                              letterSpacing: 1.0,
                            ),
                          ),
                          style: OutlinedButton.styleFrom(
                            backgroundColor: const Color(0xFF242322),
                            side: BorderSide(
                              color: Colors.white.withValues(alpha: 0.12),
                            ),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(24),
                            ),
                            padding: const EdgeInsets.symmetric(horizontal: 10),
                          ),
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
    );
  }
}

/// Stylized luxury fashion editorial visual presentation that renders the exact
/// visual architecture from Homes.pdf, with resilient fallback to Atelier illustration.
class EditorialOutfitVisual extends StatelessWidget {
  final String vibe;

  const EditorialOutfitVisual({super.key, required this.vibe});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF181716),
      ),
      child: Stack(
        fit: StackFit.expand,
        children: [
          // 1. High-fashion editorial photography matching Homes.pdf
          Image.asset(
            'assets/images/editorial_look_streetwear.jpg',
            fit: BoxFit.cover,
            alignment: const Alignment(0, -0.4),
            errorBuilder: (context, error, stackTrace) => _buildFallbackVisual(),
          ),
          // 2. Subtle top vignette for badge contrast
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            height: 60,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.black.withValues(alpha: 0.5),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),
          // 3. Smooth bottom gradient blending into the card content
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            height: 90,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.transparent,
                    const Color(0xFF181716).withValues(alpha: 0.9),
                    const Color(0xFF181716),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFallbackVisual() {
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Color(0xFF1F1D1B),
            Color(0xFF151413),
            Color(0xFF0F0E0E),
          ],
        ),
      ),
      child: Stack(
        fit: StackFit.expand,
        children: [
          Positioned(
            top: 40,
            left: 0,
            right: 0,
            bottom: 0,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  center: const Alignment(0, -0.2),
                  radius: 0.85,
                  colors: [
                    FansivibeColors.primary.withValues(alpha: 0.09),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),
          CustomPaint(
            painter: _AtelierOutfitPainter(vibe: vibe),
          ),
          Positioned(
            top: 14,
            left: 14,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.45),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(
                  color: Colors.white.withValues(alpha: 0.08),
                ),
              ),
              child: Text(
                'FANSIVIBE ATELIER // SPEC 01',
                style: TextStyle(
                  color: FansivibeColors.primary.withValues(alpha: 0.85),
                  fontSize: 8.5,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.6,
                ),
              ),
            ),
          ),
          Positioned(
            bottom: 12,
            right: 14,
            child: Text(
              'PROPORTION MATCH: 94%',
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.35),
                fontSize: 8.5,
                fontWeight: FontWeight.w600,
                letterSpacing: 1.5,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _AtelierOutfitPainter extends CustomPainter {
  final String vibe;

  _AtelierOutfitPainter({required this.vibe});

  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final cy = size.height / 2;

    // Subtle background architectural vertical gridlines
    final gridPaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.035)
      ..strokeWidth = 1.0;
    canvas.drawLine(Offset(cx - 70, 0), Offset(cx - 70, size.height), gridPaint);
    canvas.drawLine(Offset(cx + 70, 0), Offset(cx + 70, size.height), gridPaint);
    canvas.drawLine(Offset(0, cy + 20), Offset(size.width, cy + 20), gridPaint);

    // 1. Head & Neck
    final skinPaint = Paint()
      ..color = const Color(0xFFC49E7C).withValues(alpha: 0.85)
      ..style = PaintingStyle.fill;
    // Head oval
    canvas.drawOval(
      Rect.fromCenter(center: Offset(cx, 44), width: 26, height: 32),
      skinPaint,
    );
    // Neck
    final neckRect = Rect.fromCenter(center: Offset(cx, 64), width: 14, height: 16);
    canvas.drawRect(neckRect, skinPaint);

    // 2. White Fitted Tee (chest base)
    final teePaint = Paint()
      ..color = const Color(0xFFF0EFEB)
      ..style = PaintingStyle.fill;
    final teePath = Path()
      ..moveTo(cx - 16, 68)
      ..lineTo(cx + 16, 68)
      ..lineTo(cx + 20, 140)
      ..lineTo(cx - 20, 140)
      ..close();
    canvas.drawPath(teePath, teePaint);

    // 3. Jacket (Over the tee) - Denim/Tailored Outerwear
    final jacketColor = switch (vibe.toLowerCase()) {
      'minimalist' => const Color(0xFF262628),
      'classic' => const Color(0xFF1B263B),
      'bold' => const Color(0xFF3D2635),
      'natural' => const Color(0xFF333D29),
      'edgy' => const Color(0xFF1C1C1E),
      _ => const Color(0xFF2C3E50), // Streetwear Indigo Denim
    };

    final jacketPaint = Paint()
      ..color = jacketColor
      ..style = PaintingStyle.fill;

    // Torso jacket path (left flap, right flap)
    final leftJacket = Path()
      ..moveTo(cx - 14, 66)
      ..lineTo(cx - 52, 84)
      ..lineTo(cx - 44, 155)
      ..lineTo(cx - 12, 152)
      ..lineTo(cx - 12, 76)
      ..close();
    canvas.drawPath(leftJacket, jacketPaint);

    final rightJacket = Path()
      ..moveTo(cx + 14, 66)
      ..lineTo(cx + 52, 84)
      ..lineTo(cx + 44, 155)
      ..lineTo(cx + 12, 152)
      ..lineTo(cx + 12, 76)
      ..close();
    canvas.drawPath(rightJacket, jacketPaint);

    // Sleeves
    final sleevePaint = Paint()
      ..color = jacketColor.withValues(alpha: 0.95)
      ..style = PaintingStyle.fill;
    final leftSleeve = Path()
      ..moveTo(cx - 52, 84)
      ..lineTo(cx - 62, 145)
      ..lineTo(cx - 46, 148)
      ..lineTo(cx - 42, 98)
      ..close();
    canvas.drawPath(leftSleeve, sleevePaint);

    final rightSleeve = Path()
      ..moveTo(cx + 52, 84)
      ..lineTo(cx + 62, 145)
      ..lineTo(cx + 46, 148)
      ..lineTo(cx + 42, 98)
      ..close();
    canvas.drawPath(rightSleeve, sleevePaint);

    // Jacket details: collar & pockets
    final seamPaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.18)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.0;
    canvas.drawLine(Offset(cx - 14, 66), Offset(cx - 30, 96), seamPaint);
    canvas.drawLine(Offset(cx + 14, 66), Offset(cx + 30, 96), seamPaint);
    // Chest pockets
    canvas.drawRect(Rect.fromLTWH(cx - 38, 100, 16, 14), seamPaint);
    canvas.drawRect(Rect.fromLTWH(cx + 22, 100, 16, 14), seamPaint);

    // 4. Straight Jeans / Trousers
    final pantsColor = const Color(0xFF181A22);
    final pantsPaint = Paint()
      ..color = pantsColor
      ..style = PaintingStyle.fill;

    final pantsPath = Path()
      ..moveTo(cx - 24, 152)
      ..lineTo(cx + 24, 152)
      ..lineTo(cx + 26, 235)
      ..lineTo(cx + 6, 235)
      ..lineTo(cx + 2, 178)
      ..lineTo(cx - 2, 178)
      ..lineTo(cx - 6, 235)
      ..lineTo(cx - 26, 235)
      ..close();
    canvas.drawPath(pantsPath, pantsPaint);

    // Inseam line
    canvas.drawLine(Offset(cx, 176), Offset(cx, 235), seamPaint);

    // 5. Clean Low Sneakers
    final shoePaint = Paint()
      ..color = const Color(0xFFF2F0EB)
      ..style = PaintingStyle.fill;
    // Left shoe
    final leftShoe = RRect.fromRectAndRadius(
      Rect.fromLTWH(cx - 28, 236, 20, 12),
      const Radius.circular(4),
    );
    canvas.drawRRect(leftShoe, shoePaint);
    // Right shoe
    final rightShoe = RRect.fromRectAndRadius(
      Rect.fromLTWH(cx + 8, 236, 20, 12),
      const Radius.circular(4),
    );
    canvas.drawRRect(rightShoe, shoePaint);
  }

  @override
  bool shouldRepaint(covariant _AtelierOutfitPainter oldDelegate) =>
      oldDelegate.vibe != vibe;
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. SCAN MY OUTFIT ACTION BANNER
// ─────────────────────────────────────────────────────────────────────────────

class ScanOutfitBanner extends StatelessWidget {
  final VoidCallback onScan;

  const ScanOutfitBanner({super.key, required this.onScan});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Semantics(
          button: true,
          label: 'Scan My Outfit',
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: onScan,
              borderRadius: BorderRadius.circular(28),
              child: Container(
                width: double.infinity,
                height: 52,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [
                      Color(0xFFE8C882),
                      Color(0xFFD6B05F),
                      Color(0xFFC49B44),
                    ],
                    begin: Alignment.centerLeft,
                    end: Alignment.centerRight,
                  ),
                  borderRadius: BorderRadius.circular(28),
                  boxShadow: [
                    BoxShadow(
                      color: FansivibeColors.primary.withValues(alpha: 0.22),
                      blurRadius: 18,
                      offset: const Offset(0, 6),
                    ),
                  ],
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(
                      Icons.filter_center_focus_rounded,
                      size: 20,
                      color: Colors.black,
                    ),
                    const SizedBox(width: 8),
                    const Text(
                      'SCAN MY OUTFIT',
                      style: TextStyle(
                        color: Colors.black,
                        fontWeight: FontWeight.w800,
                        fontSize: 13,
                        letterSpacing: 1.5,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'GET INSTANT AI FEEDBACK IN UNDER 2 SECONDS',
          style: TextStyle(
            color: const Color(0xFF8A8580),
            fontSize: 9.5,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.8,
          ),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. STYLE SCORE CARD
// ─────────────────────────────────────────────────────────────────────────────

class StyleScoreCard extends StatelessWidget {
  final VoidCallback onReadyTap;

  const StyleScoreCard({super.key, required this.onReadyTap});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: const Color(0xFF181716),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.07),
          width: 1,
        ),
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header: STYLE SCORE • Baseline | (i) Uncalibrated
          Wrap(
            alignment: WrapAlignment.spaceBetween,
            crossAxisAlignment: WrapCrossAlignment.center,
            runSpacing: 4,
            children: [
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    'STYLE SCORE',
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.95),
                      fontSize: 10.5,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.2,
                    ),
                  ),
                  const SizedBox(width: 4),
                  Container(
                    width: 3,
                    height: 3,
                    decoration: const BoxDecoration(
                      color: Color(0xFF8A8580),
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 4),
                  const Text(
                    'Baseline',
                    style: TextStyle(
                      color: Color(0xFF8A8580),
                      fontSize: 10.5,
                      fontWeight: FontWeight.w400,
                    ),
                  ),
                ],
              ),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: const [
                  Icon(
                    Icons.info_outline_rounded,
                    size: 12,
                    color: Color(0xFF8A8580),
                  ),
                  SizedBox(width: 4),
                  Text(
                    'Uncalibrated',
                    style: TextStyle(
                      color: Color(0xFF8A8580),
                      fontSize: 10.5,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 16),

          // Main body row
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              // Left Column
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.baseline,
                      textBaseline: TextBaseline.alphabetic,
                      children: [
                        Text(
                          '0',
                          style: FansivibeTypography.displayLargeWithFamily
                              .copyWith(
                            fontSize: 44,
                            fontWeight: FontWeight.w400,
                            color: Colors.white,
                            height: 1.0,
                          ),
                        ),
                        const SizedBox(width: 8),
                        const Expanded(
                          child: Text(
                            'Your score starts here',
                            style: TextStyle(
                              fontSize: 13.5,
                              fontWeight: FontWeight.w400,
                              color: Color(0xFFC6C6CB),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Scan an outfit to see how your look matches your personal style preferences.',
                      style: TextStyle(
                        fontSize: 12,
                        color: Color(0xFF8A8580),
                        height: 1.45,
                      ),
                    ),
                    const SizedBox(height: 14),
                    // Streak label
                    Row(
                      children: const [
                        Icon(
                          Icons.schedule_rounded,
                          size: 14,
                          color: Color(0xFF8A8580),
                        ),
                        SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            '0 days (First scan activates streak)',
                            style: TextStyle(
                              fontSize: 11,
                              color: Color(0xFF8A8580),
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 14),
              // Right Column: Circular Dotted Dial with chevron and READY
              Semantics(
                button: true,
                label: 'Scan outfit to calibrate score',
                child: InkWell(
                  onTap: onReadyTap,
                  borderRadius: BorderRadius.circular(38),
                  child: SizedBox(
                    width: 76,
                    height: 76,
                    child: CustomPaint(
                      painter: _DottedDialPainter(),
                      child: Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(
                              Icons.chevron_right_rounded,
                              size: 24,
                              color: Color(0xFFE3C373),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              'READY',
                              style: TextStyle(
                                color: const Color(0xFFE3C373),
                                fontSize: 8.5,
                                fontWeight: FontWeight.w800,
                                letterSpacing: 1.5,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _DottedDialPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final cy = size.height / 2;
    final radius = (size.width / 2) - 4;

    const numDots = 20;
    final dotPaint = Paint()
      ..color = const Color(0xFFE3C373).withValues(alpha: 0.35)
      ..style = PaintingStyle.fill;

    for (int i = 0; i < numDots; i++) {
      final angle = (i * 2 * math.pi) / numDots;
      final x = cx + radius * math.cos(angle);
      final y = cy + radius * math.sin(angle);
      canvas.drawCircle(Offset(x, y), 1.6, dotPaint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. AI STYLIST DISCOVERY SECTION
// ─────────────────────────────────────────────────────────────────────────────

class AiStylistDiscoverySection extends StatelessWidget {
  final VoidCallback onScanOutfit;
  final VoidCallback onFindHairstyle;
  final VoidCallback onBuildWardrobe;

  const AiStylistDiscoverySection({
    super.key,
    required this.onScanOutfit,
    required this.onFindHairstyle,
    required this.onBuildWardrobe,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Want to discover more about your style?',
          style: FansivibeTypography.titleLargeWithFamily.copyWith(
            fontSize: 17,
            fontWeight: FontWeight.w600,
            color: Colors.white,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          'Your AI Stylist can help you understand your look, hair, and overall style.',
          style: TextStyle(
            fontSize: 13,
            color: const Color(0xFF8A8580),
            height: 1.45,
          ),
        ),
        const SizedBox(height: 16),

        // Action 1: Scan My Outfit
        _buildDiscoveryTile(
          context: context,
          icon: Icons.camera_alt_outlined,
          title: 'Scan My Outfit',
          subtitle: 'Get your first AI style breakdown & score',
          onTap: onScanOutfit,
        ),
        const SizedBox(height: 10),

        // Action 2: Find My Hairstyle
        _buildDiscoveryTile(
          context: context,
          icon: Icons.content_cut_rounded,
          title: 'Find My Hairstyle',
          subtitle: 'Discover cuts matching your face shape & vibe',
          onTap: onFindHairstyle,
        ),
        const SizedBox(height: 10),

        // Action 3: Build My Wardrobe
        _buildDiscoveryTile(
          context: context,
          icon: Icons.door_sliding_outlined,
          title: 'Build My Wardrobe',
          subtitle: 'Digitize favorite items for seamless layering',
          onTap: onBuildWardrobe,
        ),
      ],
    );
  }

  Widget _buildDiscoveryTile({
    required BuildContext context,
    required IconData icon,
    required String title,
    required String subtitle,
    required VoidCallback onTap,
  }) {
    return Semantics(
      button: true,
      label: title,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(16),
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            decoration: BoxDecoration(
              color: const Color(0xFF181716),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: Colors.white.withValues(alpha: 0.06),
                width: 1,
              ),
            ),
            child: Row(
              children: [
                // Icon square pill
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: const Color(0xFF222120),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: Colors.white.withValues(alpha: 0.06),
                    ),
                  ),
                  child: Icon(
                    icon,
                    size: 20,
                    color: Colors.white.withValues(alpha: 0.95),
                  ),
                ),
                const SizedBox(width: 14),
                // Text Column
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        subtitle,
                        style: TextStyle(
                          color: const Color(0xFF8A8580),
                          fontSize: 12,
                          height: 1.3,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                const Icon(
                  Icons.chevron_right_rounded,
                  size: 20,
                  color: Color(0xFF666666),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 6. STYLE JOURNEY / AI INSIGHT CARD
// ─────────────────────────────────────────────────────────────────────────────

class StyleJourneyCard extends StatelessWidget {
  final bool hasPreferencesSelected;
  final bool hasOutfitScanned;
  final bool hasWardrobeItem;

  const StyleJourneyCard({
    super.key,
    required this.hasPreferencesSelected,
    this.hasOutfitScanned = false,
    this.hasWardrobeItem = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: const Color(0xFF181716),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.07),
          width: 1,
        ),
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header: ⚡ AI INSIGHT | Your Style Journey
          Wrap(
            alignment: WrapAlignment.spaceBetween,
            crossAxisAlignment: WrapCrossAlignment.center,
            runSpacing: 4,
            children: [
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(
                    Icons.bolt_rounded,
                    size: 15,
                    color: Color(0xFFE3C373),
                  ),
                  const SizedBox(width: 4),
                  Text(
                    'AI INSIGHT',
                    style: TextStyle(
                      color: const Color(0xFFE3C373),
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.5,
                    ),
                  ),
                ],
              ),
              Text(
                'Your Style Journey',
                style: TextStyle(
                  color: const Color(0xFF8A8580),
                  fontSize: 11,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),

          // Insight explanation body
          const Text(
            'Complete your first outfit scan to unlock personalized style insights. '
            'Fansivibe learns from your daily fits and refines your aesthetic over time.',
            style: TextStyle(
              color: Color(0xFFC6C6CB),
              fontSize: 13,
              height: 1.5,
            ),
          ),
          const SizedBox(height: 20),

          // 4-Step Checklist
          _buildStepItem(
            stepNumber: 1,
            label: hasPreferencesSelected
                ? 'Style preferences selected'
                : 'Select style preferences',
            isCompleted: hasPreferencesSelected,
          ),
          const SizedBox(height: 12),
          _buildStepItem(
            stepNumber: 2,
            label: hasOutfitScanned ? 'First outfit scanned' : 'First outfit scan',
            isCompleted: hasOutfitScanned,
          ),
          const SizedBox(height: 12),
          _buildStepItem(
            stepNumber: 3,
            label: hasWardrobeItem
                ? 'First wardrobe item added'
                : 'First wardrobe item added',
            isCompleted: hasWardrobeItem,
          ),
          const SizedBox(height: 12),
          _buildStepItem(
            stepNumber: 4,
            label: 'Unlock dynamic score & trend radar',
            isCompleted: false,
          ),
        ],
      ),
    );
  }

  Widget _buildStepItem({
    required int stepNumber,
    required String label,
    required bool isCompleted,
  }) {
    return Row(
      children: [
        // Indicator circle
        Container(
          width: 22,
          height: 22,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: isCompleted
                ? const Color(0xFF2C281F)
                : const Color(0xFF222120),
            border: Border.all(
              color: isCompleted
                  ? const Color(0xFFE3C373).withValues(alpha: 0.6)
                  : Colors.white.withValues(alpha: 0.12),
              width: 1,
            ),
          ),
          child: Center(
            child: isCompleted
                ? const Icon(
                    Icons.check_rounded,
                    size: 13,
                    color: Color(0xFFE3C373),
                  )
                : Text(
                    '$stepNumber',
                    style: TextStyle(
                      color: const Color(0xFF8A8580),
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
          ),
        ),
        const SizedBox(width: 12),
        // Step text
        Expanded(
          child: Text(
            label,
            style: TextStyle(
              color: isCompleted
                  ? const Color(0xFFE5E2E1)
                  : const Color(0xFF8A8580),
              fontSize: 13,
              fontWeight: isCompleted ? FontWeight.w500 : FontWeight.w400,
            ),
          ),
        ),
      ],
    );
  }
}
