import 'package:flutter/material.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show WardrobeItemData;
import 'package:fansivibe/features/profile/data/saved_looks_models.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// Design system tokens strictly locked to the Fansivibe Digital Atelier specification.
abstract final class _AtelierColors {
  static const background = Color(0xFF131313);
  static const surfaceLow = Color(0xFF1C1B1B);
  static const surfaceStandard = Color(0xFF201F1F);
  static const surfaceHigh = Color(0xFF2A2A2A);
  static const surfaceFloating = Color(0xFF353534);

  static const textPrimary = Color(0xFFE5E2E1);
  static const textSecondary = Color(0xFFCFC5B3);

  static const goldPrimary = Color(0xFFE3C373);
  static const goldDarkText = Color(0xFF3E2E00);

  static const subtleOutline = Color(0xFF4C4638);
}

/// Circular score gauge painter that renders a luxury atelier ring without resembling a fitness ring.
class AtelierScoreGaugePainter extends CustomPainter {
  final double progress; // 0.0 to 1.0

  AtelierScoreGaugePainter({required this.progress});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = (size.width - 6) / 2;

    // Track paint
    final trackPaint = Paint()
      ..color = _AtelierColors.surfaceFloating.withValues(alpha: 0.35)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3.0;
    canvas.drawCircle(center, radius, trackPaint);

    // Active progress arc in champagne gold
    final activePaint = Paint()
      ..color = _AtelierColors.goldPrimary
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 3.5;

    const startAngle = -3.141592653589793 / 2;
    final sweepAngle = 2 * 3.141592653589793 * progress.clamp(0.0, 1.0);
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      startAngle,
      sweepAngle,
      false,
      activePaint,
    );
  }

  @override
  bool shouldRepaint(covariant AtelierScoreGaugePainter oldDelegate) =>
      oldDelegate.progress != progress;
}

// ---------------------------------------------------------------------------
// 1. BRAND BAR (Top Bar with Wordmark, Bell, Avatar thumbnail)
// ---------------------------------------------------------------------------

class EstablishedBrandBar extends StatelessWidget {
  final VoidCallback? onNotificationsTap;
  final VoidCallback? onAvatarTap;
  final String? avatarInitials;

  const EstablishedBrandBar({
    super.key,
    this.onNotificationsTap,
    this.onAvatarTap,
    this.avatarInitials,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8.0),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // Wordmark
          const Text(
            'FANSIVIBE',
            style: TextStyle(
              fontFamily: FansivibeTypography.textFamily,
              fontSize: 12.5,
              fontWeight: FontWeight.w700,
              letterSpacing: 3.4,
              color: _AtelierColors.textPrimary,
            ),
          ),
          // Actions
          Row(
            children: [
              IconButton(
                onPressed: onNotificationsTap,
                splashRadius: 20,
                constraints: const BoxConstraints(minWidth: 38, minHeight: 38),
                padding: EdgeInsets.zero,
                icon: Stack(
                  clipBehavior: Clip.none,
                  children: [
                    const Icon(
                      Icons.notifications_none_rounded,
                      color: _AtelierColors.textPrimary,
                      size: 22,
                    ),
                    Positioned(
                      top: 1,
                      right: 1,
                      child: Container(
                        width: 6.5,
                        height: 6.5,
                        decoration: const BoxDecoration(
                          color: _AtelierColors.goldPrimary,
                          shape: BoxShape.circle,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              GestureDetector(
                onTap: onAvatarTap,
                child: Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: _AtelierColors.goldPrimary.withValues(alpha: 0.5),
                      width: 1.2,
                    ),
                    color: _AtelierColors.surfaceHigh,
                  ),
                  child: Center(
                    child: Text(
                      avatarInitials ?? 'AR',
                      style: const TextStyle(
                        fontFamily: FansivibeTypography.textFamily,
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: _AtelierColors.goldPrimary,
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

// ---------------------------------------------------------------------------
// 2. PROFILE HERO (Avatar, Name, Handle, Style Level Badge, Chips, Actions)
// ---------------------------------------------------------------------------

class EstablishedProfileHero extends StatelessWidget {
  final String displayName;
  final String username;
  final String? initials;
  final String styleLevel;
  final String globalRankPercentile;
  final List<String> styleIdentityChips;
  final VoidCallback onEditProfile;
  final VoidCallback onShare;

  const EstablishedProfileHero({
    super.key,
    required this.displayName,
    required this.username,
    this.initials,
    this.styleLevel = 'ADVANCED',
    this.globalRankPercentile = 'TOP 8% GLOBAL',
    required this.styleIdentityChips,
    required this.onEditProfile,
    required this.onShare,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        const SizedBox(height: 12),

        // Rounded Rect Avatar with Gold Halo & Corner Badge
        Center(
          child: Stack(
            clipBehavior: Clip.none,
            children: [
              Container(
                width: 96,
                height: 96,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(22),
                  color: _AtelierColors.surfaceStandard,
                  border: Border.all(
                    color: _AtelierColors.goldPrimary.withValues(alpha: 0.45),
                    width: 1.5,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: _AtelierColors.goldPrimary.withValues(alpha: 0.12),
                      blurRadius: 20,
                      spreadRadius: 2,
                    ),
                  ],
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(20),
                  child: Image.asset(
                    'assets/images/profile_avatar.png',
                    fit: BoxFit.cover,
                    errorBuilder: (context, error, stackTrace) {
                      return Center(
                        child: Text(
                          initials ?? 'AR',
                          style: const TextStyle(
                            fontFamily: FansivibeTypography.displayFamily,
                            fontSize: 34,
                            fontStyle: FontStyle.italic,
                            color: _AtelierColors.goldPrimary,
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ),
              // Corner Gold Badge
              Positioned(
                bottom: -4,
                right: -4,
                child: Container(
                  width: 24,
                  height: 24,
                  decoration: BoxDecoration(
                    color: _AtelierColors.goldPrimary,
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: _AtelierColors.background,
                      width: 2.0,
                    ),
                  ),
                  child: const Center(
                    child: Icon(
                      Icons.auto_awesome,
                      size: 13,
                      color: _AtelierColors.goldDarkText,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 16),

        // User Display Name in Editorial Serif
        Text(
          displayName,
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontFamily: FansivibeTypography.displayFamily,
            fontSize: 28,
            fontWeight: FontWeight.w400,
            letterSpacing: 0.4,
            color: _AtelierColors.textPrimary,
          ),
        ),

        const SizedBox(height: 4),

        // Handle
        Text(
          username.startsWith('@') ? username : '@$username',
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontFamily: FansivibeTypography.textFamily,
            fontSize: 12.5,
            fontWeight: FontWeight.w500,
            letterSpacing: 0.6,
            color: _AtelierColors.textSecondary,
          ),
        ),

        const SizedBox(height: 12),

        // Style Level Pill Badge
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
          decoration: BoxDecoration(
            color: _AtelierColors.surfaceLow,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: _AtelierColors.subtleOutline.withValues(alpha: 0.35),
              width: 1.0,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.auto_awesome,
                size: 11,
                color: _AtelierColors.goldPrimary,
              ),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  'STYLE LEVEL: $styleLevel  •  $globalRankPercentile',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontFamily: FansivibeTypography.textFamily,
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.2,
                    color: _AtelierColors.goldPrimary,
                  ),
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 12),

        // Style Identity Chips
        Wrap(
          alignment: WrapAlignment.center,
          spacing: 8,
          runSpacing: 8,
          children: styleIdentityChips.map((tag) {
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
              decoration: BoxDecoration(
                color: _AtelierColors.surfaceLow,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: _AtelierColors.subtleOutline.withValues(alpha: 0.25),
                  width: 1.0,
                ),
              ),
              child: Text(
                tag.toUpperCase(),
                style: const TextStyle(
                  fontFamily: FansivibeTypography.textFamily,
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.0,
                  color: _AtelierColors.textPrimary,
                ),
              ),
            );
          }).toList(),
        ),

        const SizedBox(height: 18),

        // Edit Profile & Share Action Buttons
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            InkWell(
              onTap: onEditProfile,
              borderRadius: BorderRadius.circular(20),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8.5),
                decoration: BoxDecoration(
                  color: _AtelierColors.surfaceHigh,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(
                    color: _AtelierColors.subtleOutline.withValues(alpha: 0.3),
                    width: 1.0,
                  ),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.edit_outlined,
                      size: 14,
                      color: _AtelierColors.goldPrimary,
                    ),
                    SizedBox(width: 8),
                    Text(
                      'Edit Profile',
                      style: TextStyle(
                        fontFamily: FansivibeTypography.textFamily,
                        fontSize: 12.5,
                        fontWeight: FontWeight.w500,
                        color: _AtelierColors.textPrimary,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(width: 14),
            InkWell(
              onTap: onShare,
              borderRadius: BorderRadius.circular(20),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8.5),
                decoration: BoxDecoration(
                  color: _AtelierColors.surfaceHigh,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(
                    color: _AtelierColors.subtleOutline.withValues(alpha: 0.3),
                    width: 1.0,
                  ),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.ios_share_rounded,
                      size: 14,
                      color: _AtelierColors.textPrimary,
                    ),
                    SizedBox(width: 8),
                    Text(
                      'Share',
                      style: TextStyle(
                        fontFamily: FansivibeTypography.textFamily,
                        fontSize: 12.5,
                        fontWeight: FontWeight.w500,
                        color: _AtelierColors.textPrimary,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// 3. PRIMARY ARCHETYPE CARD
// ---------------------------------------------------------------------------

class EstablishedPrimaryArchetypeCard extends StatelessWidget {
  final String title;
  final String subtitle;
  final String description;
  final List<String> tags;
  final VoidCallback? onShare;

  const EstablishedPrimaryArchetypeCard({
    super.key,
    required this.title,
    required this.subtitle,
    required this.description,
    required this.tags,
    this.onShare,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: _AtelierColors.surfaceLow,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: _AtelierColors.subtleOutline.withValues(alpha: 0.22),
          width: 1.0,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'PRIMARY ARCHETYPE',
                style: TextStyle(
                  fontFamily: FansivibeTypography.textFamily,
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 2.0,
                  color: _AtelierColors.textSecondary,
                ),
              ),
              if (onShare != null)
                GestureDetector(
                  onTap: onShare,
                  child: const Icon(
                    Icons.ios_share_rounded,
                    size: 15,
                    color: _AtelierColors.textSecondary,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            title,
            style: const TextStyle(
              fontFamily: FansivibeTypography.displayFamily,
              fontSize: 22,
              fontWeight: FontWeight.w400,
              color: _AtelierColors.textPrimary,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            '$subtitle — $description',
            style: const TextStyle(
              fontFamily: FansivibeTypography.textFamily,
              fontSize: 13,
              height: 1.45,
              fontWeight: FontWeight.w400,
              color: _AtelierColors.textSecondary,
            ),
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: tags.map((tag) {
              return Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: _AtelierColors.surfaceHigh,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: _AtelierColors.subtleOutline.withValues(alpha: 0.2),
                    width: 1.0,
                  ),
                ),
                child: Text(
                  tag.toUpperCase(),
                  style: const TextStyle(
                    fontFamily: FansivibeTypography.textFamily,
                    fontSize: 9.5,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 1.0,
                    color: _AtelierColors.textPrimary,
                  ),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 4. STYLE INTELLIGENCE (Style Score & Global Rank Cards)
// ---------------------------------------------------------------------------

class EstablishedStyleIntelligence extends StatelessWidget {
  final int styleScore;
  final String deltaText;
  final String? globalRank;
  final String? rankPercentile;
  final String rankSubtitle;

  const EstablishedStyleIntelligence({
    super.key,
    required this.styleScore,
    this.deltaText = '+4.0',
    this.globalRank = '#2,481',
    this.rankPercentile = 'TOP 8% GLOBAL',
    this.rankSubtitle = 'Calculated across 31k active members',
  });

  @override
  Widget build(BuildContext context) {
    final showRank = globalRank != null && globalRank!.isNotEmpty;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              'STYLE INTELLIGENCE',
              style: TextStyle(
                fontFamily: FansivibeTypography.textFamily,
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 2.0,
                color: _AtelierColors.textPrimary,
              ),
            ),
            Row(
              children: [
                Icon(
                  Icons.auto_awesome,
                  size: 11,
                  color: _AtelierColors.goldPrimary,
                ),
                SizedBox(width: 4),
                Text(
                  'ATELIER CALIBRATED',
                  style: TextStyle(
                    fontFamily: FansivibeTypography.textFamily,
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.2,
                    color: _AtelierColors.goldPrimary,
                  ),
                ),
              ],
            ),
          ],
        ),
        const SizedBox(height: 14),
        Row(
          children: [
            // Left Card: Style Score
            Expanded(
              child: Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: _AtelierColors.surfaceLow,
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(
                    color: _AtelierColors.subtleOutline.withValues(alpha: 0.2),
                    width: 1.0,
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'STYLE SCORE',
                          style: TextStyle(
                            fontFamily: FansivibeTypography.textFamily,
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 1.2,
                            color: _AtelierColors.textSecondary,
                          ),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: _AtelierColors.surfaceHigh,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(
                            deltaText,
                            style: const TextStyle(
                              fontFamily: FansivibeTypography.textFamily,
                              fontSize: 9.5,
                              fontWeight: FontWeight.w700,
                              color: _AtelierColors.goldPrimary,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.baseline,
                          textBaseline: TextBaseline.alphabetic,
                          children: [
                            Text(
                              styleScore.toString(),
                              style: const TextStyle(
                                fontFamily: FansivibeTypography.displayFamily,
                                fontSize: 32,
                                fontWeight: FontWeight.w400,
                                color: _AtelierColors.textPrimary,
                              ),
                            ),
                            const SizedBox(width: 4),
                            const Text(
                              '/ 100',
                              style: TextStyle(
                                fontFamily: FansivibeTypography.textFamily,
                                fontSize: 12,
                                color: _AtelierColors.textSecondary,
                              ),
                            ),
                          ],
                        ),
                        // Circular Gauge
                        SizedBox(
                          width: 36,
                          height: 36,
                          child: CustomPaint(
                            painter: AtelierScoreGaugePainter(
                              progress: (styleScore / 100).clamp(0.0, 1.0),
                            ),
                            child: const Center(
                              child: Icon(
                                Icons.auto_awesome,
                                size: 12,
                                color: _AtelierColors.goldPrimary,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    const Text(
                      'Consistency-based precision',
                      style: TextStyle(
                        fontFamily: FansivibeTypography.textFamily,
                        fontSize: 10.5,
                        color: _AtelierColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
            ),

            if (showRank) ...[
              const SizedBox(width: 12),
              // Right Card: Global Rank
              Expanded(
                child: Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: _AtelierColors.surfaceLow,
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(
                      color: _AtelierColors.subtleOutline.withValues(alpha: 0.2),
                      width: 1.0,
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'GLOBAL RANK',
                            style: TextStyle(
                              fontFamily: FansivibeTypography.textFamily,
                              fontSize: 10,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 1.2,
                              color: _AtelierColors.textSecondary,
                            ),
                          ),
                          Icon(
                            Icons.public_rounded,
                            size: 15,
                            color: _AtelierColors.goldPrimary,
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      Text(
                        globalRank!,
                        style: const TextStyle(
                          fontFamily: FansivibeTypography.displayFamily,
                          fontSize: 24,
                          fontWeight: FontWeight.w400,
                          color: _AtelierColors.textPrimary,
                        ),
                      ),
                      if (rankPercentile != null) ...[
                        const SizedBox(height: 2),
                        Text(
                          rankPercentile!,
                          style: const TextStyle(
                            fontFamily: FansivibeTypography.textFamily,
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 0.8,
                            color: _AtelierColors.goldPrimary,
                          ),
                        ),
                      ],
                      const SizedBox(height: 6),
                      Text(
                        rankSubtitle,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontFamily: FansivibeTypography.textFamily,
                          fontSize: 10.5,
                          color: _AtelierColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// 5. STYLE PROGRESS (TRAJECTORY) CARD
// ---------------------------------------------------------------------------

class EstablishedTrajectoryCard extends StatelessWidget {
  final int currentScore;
  final int consistencyPercentage;

  const EstablishedTrajectoryCard({
    super.key,
    required this.currentScore,
    this.consistencyPercentage = 94,
  });

  @override
  Widget build(BuildContext context) {
    // 4 progression data points (scaled gracefully based on currentScore)
    final w1 = (currentScore - 12).clamp(60, 100);
    final w2 = (currentScore - 8).clamp(60, 100);
    final w3 = (currentScore - 4).clamp(60, 100);
    final now = currentScore;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: _AtelierColors.surfaceLow,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: _AtelierColors.subtleOutline.withValues(alpha: 0.2),
          width: 1.0,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'TRAJECTORY',
                      style: TextStyle(
                        fontFamily: FansivibeTypography.textFamily,
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 2.0,
                        color: _AtelierColors.goldPrimary,
                      ),
                    ),
                    SizedBox(height: 4),
                    Text(
                      '30-Day Evolution',
                      style: TextStyle(
                        fontFamily: FansivibeTypography.displayFamily,
                        fontSize: 16,
                        fontWeight: FontWeight.w400,
                        color: _AtelierColors.textPrimary,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: _AtelierColors.surfaceHigh,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  'Consistency: $consistencyPercentage%',
                  style: const TextStyle(
                    fontFamily: FansivibeTypography.textFamily,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: _AtelierColors.goldPrimary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),

          // 4-Column Bar Chart
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              _buildProgressColumn(score: w1, label: 'W1', isCurrent: false),
              _buildProgressColumn(score: w2, label: 'W2', isCurrent: false),
              _buildProgressColumn(score: w3, label: 'W3', isCurrent: false),
              _buildProgressColumn(score: now, label: 'Now', isCurrent: true),
            ],
          ),

          const SizedBox(height: 16),

          // Summary Note
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(
                Icons.auto_awesome,
                size: 13,
                color: _AtelierColors.goldPrimary,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Your style consistency is improving. Keep exploring and saving to refine your signature aesthetic.',
                  style: const TextStyle(
                    fontFamily: FansivibeTypography.textFamily,
                    fontSize: 12,
                    height: 1.45,
                    color: _AtelierColors.textSecondary,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildProgressColumn({
    required int score,
    required String label,
    required bool isCurrent,
  }) {
    final heightRatio = ((score - 50) / 50.0).clamp(0.35, 1.0);
    final barHeight = 44.0 + (heightRatio * 46.0);

    return Column(
      children: [
        Text(
          score.toString(),
          style: TextStyle(
            fontFamily: FansivibeTypography.textFamily,
            fontSize: 11,
            fontWeight: isCurrent ? FontWeight.w700 : FontWeight.w500,
            color: isCurrent ? _AtelierColors.goldPrimary : _AtelierColors.textSecondary,
          ),
        ),
        const SizedBox(height: 6),
        Container(
          width: 58,
          height: barHeight,
          decoration: BoxDecoration(
            color: isCurrent ? _AtelierColors.goldPrimary : _AtelierColors.surfaceHigh,
            borderRadius: BorderRadius.circular(10),
            boxShadow: isCurrent
                ? [
                    BoxShadow(
                      color: _AtelierColors.goldPrimary.withValues(alpha: 0.25),
                      blurRadius: 10,
                      spreadRadius: 1,
                    ),
                  ]
                : null,
          ),
          child: isCurrent
              ? const Center(
                  child: Icon(
                    Icons.check,
                    size: 14,
                    color: _AtelierColors.goldDarkText,
                  ),
                )
              : null,
        ),
        const SizedBox(height: 8),
        Text(
          label,
          style: TextStyle(
            fontFamily: FansivibeTypography.textFamily,
            fontSize: 10.5,
            fontWeight: isCurrent ? FontWeight.w700 : FontWeight.w500,
            color: isCurrent ? _AtelierColors.goldPrimary : _AtelierColors.textSecondary,
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// 6. CURATED WARDROBE SECTION (Rail + Summary Categories)
// ---------------------------------------------------------------------------

class EstablishedCuratedWardrobe extends StatelessWidget {
  final int totalCount;
  final List<WardrobeItemData> items;
  final VoidCallback onViewAll;
  final Map<String, int> categoryCounts;

  const EstablishedCuratedWardrobe({
    super.key,
    required this.totalCount,
    required this.items,
    required this.onViewAll,
    required this.categoryCounts,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Header
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Curated Wardrobe',
                    style: TextStyle(
                      fontFamily: FansivibeTypography.displayFamily,
                      fontSize: 22,
                      fontWeight: FontWeight.w400,
                      color: _AtelierColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    '$totalCount Cataloged Pieces',
                    style: const TextStyle(
                      fontFamily: FansivibeTypography.textFamily,
                      fontSize: 12,
                      color: _AtelierColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            InkWell(
              onTap: onViewAll,
              child: const Padding(
                padding: EdgeInsets.symmetric(vertical: 4.0),
                child: Text(
                  'VIEW ALL →',
                  style: TextStyle(
                    fontFamily: FansivibeTypography.textFamily,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.2,
                    color: _AtelierColors.goldPrimary,
                  ),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),

        // Horizontal Product / Clothing Rail
        SizedBox(
          height: 225,
          child: items.isEmpty
              ? _buildEmptyWardrobePlaceholder()
              : ListView.separated(
                  scrollDirection: Axis.horizontal,
                  physics: const BouncingScrollPhysics(),
                  itemCount: items.length > 8 ? 8 : items.length,
                  separatorBuilder: (_, __) => const SizedBox(width: 14),
                  itemBuilder: (context, index) {
                    final item = items[index];
                    return _buildWardrobeItemCard(item);
                  },
                ),
        ),

        const SizedBox(height: 14),

        // Compact Category Summary Row
        Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: _AtelierColors.surfaceLow,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
              color: _AtelierColors.subtleOutline.withValues(alpha: 0.18),
              width: 1.0,
            ),
          ),
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                _buildCategoryStat('TOPS', categoryCounts['tops'] ?? 64),
                _buildDotSeparator(),
                _buildCategoryStat('BOTTOMS', categoryCounts['bottoms'] ?? 42),
                _buildDotSeparator(),
                _buildCategoryStat('OUTERWEAR', categoryCounts['outerwear'] ?? 28),
                _buildDotSeparator(),
                _buildCategoryStat('SHOES', categoryCounts['footwear'] ?? 31),
                _buildDotSeparator(),
                _buildCategoryStat('ACCESSORIES', categoryCounts['accessories'] ?? 83),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildCategoryStat(String name, int count) {
    return Text(
      '$name $count',
      style: const TextStyle(
        fontFamily: FansivibeTypography.textFamily,
        fontSize: 11,
        fontWeight: FontWeight.w600,
        letterSpacing: 1.0,
        color: _AtelierColors.textSecondary,
      ),
    );
  }

  Widget _buildDotSeparator() {
    return const Padding(
      padding: EdgeInsets.symmetric(horizontal: 10),
      child: Text(
        '•',
        style: TextStyle(
          color: _AtelierColors.goldPrimary,
          fontSize: 12,
        ),
      ),
    );
  }

  Widget _buildWardrobeItemCard(WardrobeItemData item) {
    // Visual asset resolution per category
    String assetImage = 'assets/images/discover_item_wool_coat.jpg';
    if (item.category.toLowerCase().contains('top')) {
      assetImage = 'assets/images/discover_cat_clothing.jpg';
    } else if (item.category.toLowerCase().contains('footwear') ||
        item.category.toLowerCase().contains('shoe')) {
      assetImage = 'assets/images/discover_item_samba.jpg';
    } else if (item.category.toLowerCase().contains('access')) {
      assetImage = 'assets/images/discover_cat_accessories.jpg';
    }

    return Container(
      width: 138,
      decoration: BoxDecoration(
        color: _AtelierColors.surfaceLow,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: _AtelierColors.subtleOutline.withValues(alpha: 0.2),
          width: 1.0,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 65% Image Area
          Expanded(
            flex: 65,
            child: ClipRRect(
              borderRadius: const BorderRadius.vertical(top: Radius.circular(15)),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Image.asset(
                    assetImage,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => Container(
                      color: _AtelierColors.surfaceStandard,
                      child: const Center(
                        child: Icon(
                          Icons.checkroom_rounded,
                          color: _AtelierColors.goldPrimary,
                          size: 28,
                        ),
                      ),
                    ),
                  ),
                  // Subtle top gradient
                  Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.bottomCenter,
                        end: Alignment.topCenter,
                        colors: [
                          _AtelierColors.surfaceLow.withValues(alpha: 0.6),
                          Colors.transparent,
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          // 35% Content Area
          Expanded(
            flex: 35,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    item.category.toUpperCase(),
                    style: const TextStyle(
                      fontFamily: FansivibeTypography.textFamily,
                      fontSize: 8.5,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.0,
                      color: _AtelierColors.goldPrimary,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    item.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontFamily: FansivibeTypography.displayFamily,
                      fontSize: 12.5,
                      fontWeight: FontWeight.w400,
                      color: _AtelierColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    item.color,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontFamily: FansivibeTypography.textFamily,
                      fontSize: 10,
                      color: _AtelierColors.textSecondary,
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

  Widget _buildEmptyWardrobePlaceholder() {
    return Container(
      decoration: BoxDecoration(
        color: _AtelierColors.surfaceLow,
        borderRadius: BorderRadius.circular(16),
      ),
      child: const Center(
        child: Text(
          'No wardrobe items yet',
          style: TextStyle(color: _AtelierColors.textSecondary),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 7. WARDROBE INTELLIGENCE (ATELIER SYNTHESIS)
// ---------------------------------------------------------------------------

class EstablishedWardrobeSynthesis extends StatelessWidget {
  final String synthesisQuote;
  final VoidCallback onDiscoverComplementary;

  const EstablishedWardrobeSynthesis({
    super.key,
    required this.synthesisQuote,
    required this.onDiscoverComplementary,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: _AtelierColors.surfaceLow,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: _AtelierColors.subtleOutline.withValues(alpha: 0.22),
          width: 1.0,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(
                Icons.lightbulb_outline_rounded,
                size: 15,
                color: _AtelierColors.goldPrimary,
              ),
              SizedBox(width: 8),
              Text(
                'ATELIER SYNTHESIS',
                style: TextStyle(
                  fontFamily: FansivibeTypography.textFamily,
                  fontSize: 10.5,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 2.0,
                  color: _AtelierColors.goldPrimary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            synthesisQuote,
            style: const TextStyle(
              fontFamily: FansivibeTypography.textFamily,
              fontSize: 13.5,
              height: 1.48,
              color: _AtelierColors.textPrimary,
            ),
          ),
          const SizedBox(height: 14),
          InkWell(
            onTap: onDiscoverComplementary,
            child: const Text(
              'DISCOVER COMPLEMENTARY PIECES →',
              style: TextStyle(
                fontFamily: FansivibeTypography.textFamily,
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.2,
                color: _AtelierColors.goldPrimary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 8. SAVED LOOKS SECTION (2-Column Editorial Grid)
// ---------------------------------------------------------------------------

class EstablishedSavedLooks extends StatelessWidget {
  final List<SavedLookItem> looks;
  final VoidCallback onArchivedEnsembles;

  const EstablishedSavedLooks({
    super.key,
    required this.looks,
    required this.onArchivedEnsembles,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            const Expanded(
              child: Text(
                'Saved Looks',
                style: TextStyle(
                  fontFamily: FansivibeTypography.displayFamily,
                  fontSize: 22,
                  fontWeight: FontWeight.w400,
                  color: _AtelierColors.textPrimary,
                ),
              ),
            ),
            const SizedBox(width: 8),
            InkWell(
              onTap: onArchivedEnsembles,
              child: const Padding(
                padding: EdgeInsets.symmetric(vertical: 4.0),
                child: Text(
                  'Archived Ensembles →',
                  style: TextStyle(
                    fontFamily: FansivibeTypography.textFamily,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.0,
                    color: _AtelierColors.goldPrimary,
                  ),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        // 2-Column Grid
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: _buildLookCard(
                title: looks.isNotEmpty ? looks[0].title : 'Modern Minimal Evening',
                subtitle: 'Smart Casual • Gallery',
                imageAsset: 'assets/images/discover_look_urban_minimal.jpg',
                onTap: onArchivedEnsembles,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: _buildLookCard(
                title: looks.length > 1 ? looks[1].title : 'Structured Autumn Layers',
                subtitle: 'Casual Tailoring • Street',
                imageAsset: 'assets/images/discover_look_modern_classics.jpg',
                onTap: onArchivedEnsembles,
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildLookCard({
    required String title,
    required String subtitle,
    required String imageAsset,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 250,
        decoration: BoxDecoration(
          color: _AtelierColors.surfaceLow,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(
            color: _AtelierColors.subtleOutline.withValues(alpha: 0.2),
            width: 1.0,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 65% Image
            Expanded(
              flex: 65,
              child: ClipRRect(
                borderRadius: const BorderRadius.vertical(top: Radius.circular(17)),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    Image.asset(
                      imageAsset,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => Container(
                        color: _AtelierColors.surfaceStandard,
                        child: const Icon(
                          Icons.style_rounded,
                          color: _AtelierColors.goldPrimary,
                        ),
                      ),
                    ),
                    Positioned(
                      top: 10,
                      right: 10,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3.5),
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.65),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                            color: _AtelierColors.goldPrimary.withValues(alpha: 0.4),
                            width: 0.8,
                          ),
                        ),
                        child: const Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.auto_awesome,
                              size: 9,
                              color: _AtelierColors.goldPrimary,
                            ),
                            SizedBox(width: 3),
                            Text(
                              'SAVED',
                              style: TextStyle(
                                fontFamily: FansivibeTypography.textFamily,
                                fontSize: 8.5,
                                fontWeight: FontWeight.w700,
                                letterSpacing: 1.0,
                                color: _AtelierColors.goldPrimary,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            // 35% Content
            Expanded(
              flex: 35,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontFamily: FansivibeTypography.displayFamily,
                        fontSize: 13.5,
                        fontWeight: FontWeight.w400,
                        color: _AtelierColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      subtitle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontFamily: FansivibeTypography.textFamily,
                        fontSize: 11,
                        color: _AtelierColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 9. CURATED WISHLIST (Product-oriented luxury commerce row)
// ---------------------------------------------------------------------------

class EstablishedCuratedWishlist extends StatelessWidget {
  final VoidCallback onEntireAcquisition;
  final void Function(String productTitle) onShopProduct;

  const EstablishedCuratedWishlist({
    super.key,
    required this.onEntireAcquisition,
    required this.onShopProduct,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            const Expanded(
              child: Text(
                'Curated Wishlist',
                style: TextStyle(
                  fontFamily: FansivibeTypography.displayFamily,
                  fontSize: 22,
                  fontWeight: FontWeight.w400,
                  color: _AtelierColors.textPrimary,
                ),
              ),
            ),
            const SizedBox(width: 8),
            InkWell(
              onTap: onEntireAcquisition,
              child: const Padding(
                padding: EdgeInsets.symmetric(vertical: 4.0),
                child: Text(
                  'Entire Acquisition →',
                  style: TextStyle(
                    fontFamily: FansivibeTypography.textFamily,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.0,
                    color: _AtelierColors.textSecondary,
                  ),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        _buildProductRow(
          brand: 'STUDIO NICHOLSON',
          title: 'Water-Repellent Cotton Trench Coat',
          price: '₹48,000',
          imageAsset: 'assets/images/discover_item_wool_coat.jpg',
        ),
        const SizedBox(height: 12),
        _buildProductRow(
          brand: 'LEMAIRE',
          title: 'Padded Leather Derby Shoes',
          price: '₹36,500',
          imageAsset: 'assets/images/discover_item_samba.jpg',
        ),
      ],
    );
  }

  Widget _buildProductRow({
    required String brand,
    required String title,
    required String price,
    required String imageAsset,
  }) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: _AtelierColors.surfaceLow,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: _AtelierColors.subtleOutline.withValues(alpha: 0.2),
          width: 1.0,
        ),
      ),
      child: Row(
        children: [
          // Thumbnail image
          ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: SizedBox(
              width: 58,
              height: 58,
              child: Image.asset(
                imageAsset,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => Container(
                  color: _AtelierColors.surfaceStandard,
                  child: const Icon(
                    Icons.shopping_bag_outlined,
                    color: _AtelierColors.goldPrimary,
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(width: 14),
          // Product details
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  brand,
                  style: const TextStyle(
                    fontFamily: FansivibeTypography.textFamily,
                    fontSize: 9.5,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.2,
                    color: _AtelierColors.textSecondary,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontFamily: FansivibeTypography.textFamily,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                    color: _AtelierColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  price,
                  style: const TextStyle(
                    fontFamily: FansivibeTypography.textFamily,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: _AtelierColors.goldPrimary,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          // Shop CTA
          InkWell(
            onTap: () => onShopProduct(title),
            borderRadius: BorderRadius.circular(16),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
              decoration: BoxDecoration(
                color: _AtelierColors.surfaceHigh,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: _AtelierColors.subtleOutline.withValues(alpha: 0.3),
                  width: 1.0,
                ),
              ),
              child: const Text(
                'SHOP →',
                style: TextStyle(
                  fontFamily: FansivibeTypography.textFamily,
                  fontSize: 10.5,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.0,
                  color: _AtelierColors.textPrimary,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 10. STYLE DNA PROFILE (4-Part Dimension Grid)
// ---------------------------------------------------------------------------

class EstablishedStyleDnaProfile extends StatelessWidget {
  final String colorPalette;
  final String silhouette;
  final String occasions;
  final String anchor;
  final VoidCallback onDimensionsTap;

  const EstablishedStyleDnaProfile({
    super.key,
    this.colorPalette = 'Neutral & Earth',
    this.silhouette = 'Relaxed Tailoring',
    this.occasions = 'Smart Casual',
    this.anchor = 'Modern Minimal',
    required this.onDimensionsTap,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            const Expanded(
              child: Text(
                'Style DNA Profile',
                style: TextStyle(
                  fontFamily: FansivibeTypography.displayFamily,
                  fontSize: 22,
                  fontWeight: FontWeight.w400,
                  color: _AtelierColors.textPrimary,
                ),
              ),
            ),
            const SizedBox(width: 8),
            InkWell(
              onTap: onDimensionsTap,
              child: const Padding(
                padding: EdgeInsets.symmetric(vertical: 4.0),
                child: Text(
                  'Signature Dimensions →',
                  style: TextStyle(
                    fontFamily: FansivibeTypography.textFamily,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.0,
                    color: _AtelierColors.textSecondary,
                  ),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        // 2x2 Grid
        Row(
          children: [
            Expanded(
              child: _buildDnaCard(
                label: 'COLOR PALETTE',
                value: colorPalette,
                subtitle: 'Warm Undertones & Ivory',
                showColorDots: true,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _buildDnaCard(
                label: 'SILHOUETTE',
                value: silhouette,
                subtitle: 'Fluid lines with structure',
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: _buildDnaCard(
                label: 'KEY OCCASIONS',
                value: occasions,
                subtitle: 'Gallery • Evening Dining',
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _buildDnaCard(
                label: 'AESTHETIC ANCHOR',
                value: anchor,
                subtitle: 'High tonal discipline',
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildDnaCard({
    required String label,
    required String value,
    required String subtitle,
    bool showColorDots = false,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _AtelierColors.surfaceLow,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: _AtelierColors.subtleOutline.withValues(alpha: 0.2),
          width: 1.0,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontFamily: FansivibeTypography.textFamily,
              fontSize: 9.5,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.2,
              color: _AtelierColors.textSecondary,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            value,
            style: const TextStyle(
              fontFamily: FansivibeTypography.displayFamily,
              fontSize: 15,
              fontWeight: FontWeight.w400,
              color: _AtelierColors.textPrimary,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            subtitle,
            style: const TextStyle(
              fontFamily: FansivibeTypography.textFamily,
              fontSize: 10.5,
              color: _AtelierColors.textSecondary,
            ),
          ),
          if (showColorDots) ...[
            const SizedBox(height: 8),
            Row(
              children: [
                _buildDot(const Color(0xFFE5E2E1)),
                const SizedBox(width: 6),
                _buildDot(_AtelierColors.goldPrimary),
                const SizedBox(width: 6),
                _buildDot(const Color(0xFF353534)),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildDot(Color color) {
    return Container(
      width: 10,
      height: 10,
      decoration: BoxDecoration(
        color: color,
        shape: BoxShape.circle,
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.2),
          width: 0.5,
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 11. AI STYLE OBSERVATION CARD
// ---------------------------------------------------------------------------

class EstablishedAiObservation extends StatelessWidget {
  final String observationText;
  final VoidCallback onExploreEditions;

  const EstablishedAiObservation({
    super.key,
    required this.observationText,
    required this.onExploreEditions,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: _AtelierColors.surfaceLow,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: _AtelierColors.goldPrimary.withValues(alpha: 0.2),
          width: 1.0,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(
                Icons.auto_awesome,
                size: 13,
                color: _AtelierColors.goldPrimary,
              ),
              SizedBox(width: 7),
              Text(
                '✦ ATELIER ENGINE OBSERVATION',
                style: TextStyle(
                  fontFamily: FansivibeTypography.textFamily,
                  fontSize: 10.5,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.8,
                  color: _AtelierColors.goldPrimary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            '"$observationText"',
            style: const TextStyle(
              fontFamily: FansivibeTypography.displayFamily,
              fontSize: 14,
              fontStyle: FontStyle.italic,
              height: 1.5,
              color: _AtelierColors.textPrimary,
            ),
          ),
          const SizedBox(height: 14),
          InkWell(
            onTap: onExploreEditions,
            child: const Text(
              'EXPLORE CURATED EDITIONS →',
              style: TextStyle(
                fontFamily: FansivibeTypography.textFamily,
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.2,
                color: _AtelierColors.goldPrimary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 12. CURATORIAL MILESTONES & STREAK
// ---------------------------------------------------------------------------

class EstablishedCuratorialMilestones extends StatelessWidget {
  final int unlockedCount;
  final int totalCount;
  final int streakDays;

  const EstablishedCuratorialMilestones({
    super.key,
    this.unlockedCount = 6,
    this.totalCount = 12,
    this.streakDays = 12,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            const Expanded(
              child: Text(
                'Curatorial Milestones',
                style: TextStyle(
                  fontFamily: FansivibeTypography.displayFamily,
                  fontSize: 22,
                  fontWeight: FontWeight.w400,
                  color: _AtelierColors.textPrimary,
                ),
              ),
            ),
            const SizedBox(width: 8),
            Text(
              '$unlockedCount of $totalCount Unlocked',
              style: const TextStyle(
                fontFamily: FansivibeTypography.textFamily,
                fontSize: 11,
                fontWeight: FontWeight.w700,
                color: _AtelierColors.goldPrimary,
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        // 4 Milestones Row
        Row(
          children: [
            Expanded(
              child: _buildMilestoneTile(
                icon: Icons.explore_outlined,
                title: 'STYLE\nEXPLORER',
                unlocked: true,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _buildMilestoneTile(
                icon: Icons.checkroom_outlined,
                title: 'WARDROBE\nBUILDER',
                unlocked: true,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _buildMilestoneTile(
                icon: Icons.radar_outlined,
                title: 'TREND\nSPOTTER',
                unlocked: true,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _buildMilestoneTile(
                icon: Icons.bookmark_border_rounded,
                title: 'LOOK\nCURATOR',
                unlocked: true,
              ),
            ),
          ],
        ),
        const SizedBox(height: 14),
        // Style Streak Card
        Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          decoration: BoxDecoration(
            color: _AtelierColors.surfaceLow,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: _AtelierColors.subtleOutline.withValues(alpha: 0.2),
              width: 1.0,
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Row(
                  children: [
                    const Icon(
                      Icons.local_fire_department_rounded,
                      size: 18,
                      color: _AtelierColors.goldPrimary,
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '$streakDays-Day Streak',
                            style: const TextStyle(
                              fontFamily: FansivibeTypography.displayFamily,
                              fontSize: 15,
                              fontWeight: FontWeight.w400,
                              color: _AtelierColors.textPrimary,
                            ),
                          ),
                          const SizedBox(height: 2),
                          const Text(
                            'Your style practice continues.',
                            style: TextStyle(
                              fontFamily: FansivibeTypography.textFamily,
                              fontSize: 10.5,
                              color: _AtelierColors.textSecondary,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              // 7-day capsule row
              Row(
                children: List.generate(7, (index) {
                  final active = index < 5;
                  return Container(
                    margin: const EdgeInsets.only(left: 4),
                    width: 12,
                    height: 12,
                    decoration: BoxDecoration(
                      color: active ? _AtelierColors.goldPrimary : _AtelierColors.surfaceHigh,
                      shape: BoxShape.circle,
                    ),
                    child: active
                        ? const Center(
                            child: Icon(
                              Icons.check,
                              size: 8,
                              color: _AtelierColors.goldDarkText,
                            ),
                          )
                        : null,
                  );
                }),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildMilestoneTile({
    required IconData icon,
    required String title,
    required bool unlocked,
  }) {
    return Container(
      height: 96,
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: _AtelierColors.surfaceLow,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: unlocked
              ? _AtelierColors.goldPrimary.withValues(alpha: 0.3)
              : _AtelierColors.subtleOutline.withValues(alpha: 0.2),
          width: 1.0,
        ),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            icon,
            size: 20,
            color: unlocked ? _AtelierColors.goldPrimary : _AtelierColors.surfaceFloating,
          ),
          const SizedBox(height: 8),
          Text(
            title,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: FansivibeTypography.textFamily,
              fontSize: 8.5,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.8,
              height: 1.25,
              color: unlocked ? _AtelierColors.textPrimary : _AtelierColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 13. PERSONALIZED RECOMMENDATIONS (Commerce Hook to For You)
// ---------------------------------------------------------------------------

class EstablishedPersonalizedRecommendations extends StatelessWidget {
  final VoidCallback onDiscoverForYou;

  const EstablishedPersonalizedRecommendations({
    super.key,
    required this.onDiscoverForYou,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: _AtelierColors.surfaceLow,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(
          color: _AtelierColors.goldPrimary.withValues(alpha: 0.25),
          width: 1.0,
        ),
        boxShadow: [
          BoxShadow(
            color: _AtelierColors.goldPrimary.withValues(alpha: 0.05),
            blurRadius: 24,
            spreadRadius: 2,
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'PERSONALIZED RECOMMENDATIONS',
            style: TextStyle(
              fontFamily: FansivibeTypography.textFamily,
              fontSize: 10,
              fontWeight: FontWeight.w700,
              letterSpacing: 2.2,
              color: _AtelierColors.goldPrimary,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Shop Your Style Signature',
            style: TextStyle(
              fontFamily: FansivibeTypography.displayFamily,
              fontSize: 22,
              fontWeight: FontWeight.w400,
              color: _AtelierColors.textPrimary,
            ),
          ),
          const SizedBox(height: 6),
          const Text(
            'Selected pieces matched specifically to your profile and wardrobe.',
            style: TextStyle(
              fontFamily: FansivibeTypography.textFamily,
              fontSize: 13,
              height: 1.45,
              color: _AtelierColors.textSecondary,
            ),
          ),
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            height: 48,
            child: ElevatedButton(
              onPressed: onDiscoverForYou,
              style: ElevatedButton.styleFrom(
                backgroundColor: _AtelierColors.goldPrimary,
                foregroundColor: _AtelierColors.goldDarkText,
                elevation: 0,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(24),
                ),
              ),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    'DISCOVER FOR YOU →',
                    style: TextStyle(
                      fontFamily: FansivibeTypography.textFamily,
                      fontSize: 12.5,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.4,
                      color: _AtelierColors.goldDarkText,
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

// ---------------------------------------------------------------------------
// 14. ATELIER GOVERNANCE (Account, Settings, Membership)
// ---------------------------------------------------------------------------

class EstablishedAtelierGovernance extends StatelessWidget {
  final int syncedWardrobeCount;
  final String membershipTier;
  final VoidCallback onPreferences;
  final VoidCallback onStyleProfile;
  final VoidCallback onWardrobeSync;
  final VoidCallback onNotifications;
  final VoidCallback onPrivacy;
  final VoidCallback onManageMembership;

  const EstablishedAtelierGovernance({
    super.key,
    required this.syncedWardrobeCount,
    this.membershipTier = 'Fansivibe Atelier • Pro Tier',
    required this.onPreferences,
    required this.onStyleProfile,
    required this.onWardrobeSync,
    required this.onNotifications,
    required this.onPrivacy,
    required this.onManageMembership,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: Text(
                'Atelier Governance',
                style: TextStyle(
                  fontFamily: FansivibeTypography.displayFamily,
                  fontSize: 22,
                  fontWeight: FontWeight.w400,
                  color: _AtelierColors.textPrimary,
                ),
              ),
            ),
            SizedBox(width: 8),
            Text(
              'Settings & Membership',
              style: TextStyle(
                fontFamily: FansivibeTypography.textFamily,
                fontSize: 11,
                color: _AtelierColors.textSecondary,
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        Container(
          width: double.infinity,
          decoration: BoxDecoration(
            color: _AtelierColors.surfaceLow,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: _AtelierColors.subtleOutline.withValues(alpha: 0.2),
              width: 1.0,
            ),
          ),
          child: Column(
            children: [
              // Membership Row inside Governance
              Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: _AtelierColors.surfaceHigh,
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: _AtelierColors.goldPrimary.withValues(alpha: 0.4),
                          width: 1.0,
                        ),
                      ),
                      child: const Center(
                        child: Icon(
                          Icons.workspace_premium_rounded,
                          color: _AtelierColors.goldPrimary,
                          size: 20,
                        ),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'MEMBERSHIP',
                            style: TextStyle(
                              fontFamily: FansivibeTypography.textFamily,
                              fontSize: 9.5,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 1.2,
                              color: _AtelierColors.textSecondary,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            membershipTier,
                            style: const TextStyle(
                              fontFamily: FansivibeTypography.displayFamily,
                              fontSize: 15,
                              fontWeight: FontWeight.w400,
                              color: _AtelierColors.textPrimary,
                            ),
                          ),
                        ],
                      ),
                    ),
                    InkWell(
                      onTap: onManageMembership,
                      child: const Padding(
                        padding: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        child: Text(
                          'MANAGE →',
                          style: TextStyle(
                            fontFamily: FansivibeTypography.textFamily,
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 1.0,
                            color: _AtelierColors.goldPrimary,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),

              Divider(
                color: _AtelierColors.subtleOutline.withValues(alpha: 0.2),
                height: 1,
              ),

              // Governance Rows
              _buildGovernanceRow(
                icon: Icons.tune_rounded,
                title: 'Preferences',
                subtitle: 'Tailoring, Silhouette, Persona',
                onTap: onPreferences,
              ),
              _buildGovernanceRow(
                icon: Icons.straighten_rounded,
                title: 'Style Profile & Measurements',
                subtitle: 'Anthropometrics & Fit',
                onTap: onStyleProfile,
              ),
              _buildGovernanceRow(
                icon: Icons.sync_rounded,
                title: 'Wardrobe Sync',
                subtitle: '$syncedWardrobeCount items synced',
                onTap: onWardrobeSync,
              ),
              _buildGovernanceRow(
                icon: Icons.notifications_none_rounded,
                title: 'Notifications & Drops',
                subtitle: 'Personalized release alerts',
                onTap: onNotifications,
              ),
              _buildGovernanceRow(
                icon: Icons.lock_outline_rounded,
                title: 'Privacy & Atelier Lookbook',
                subtitle: 'Data controls & visibility',
                onTap: onPrivacy,
                isLast: true,
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildGovernanceRow({
    required IconData icon,
    required String title,
    required String subtitle,
    required VoidCallback onTap,
    bool isLast = false,
  }) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          border: isLast
              ? null
              : Border(
                  bottom: BorderSide(
                    color: _AtelierColors.subtleOutline.withValues(alpha: 0.15),
                    width: 0.8,
                  ),
                ),
        ),
        child: Row(
          children: [
            Icon(
              icon,
              size: 20,
              color: _AtelierColors.textSecondary,
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontFamily: FansivibeTypography.textFamily,
                      fontSize: 13.5,
                      fontWeight: FontWeight.w500,
                      color: _AtelierColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    style: const TextStyle(
                      fontFamily: FansivibeTypography.textFamily,
                      fontSize: 11,
                      color: _AtelierColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
            const Icon(
              Icons.chevron_right_rounded,
              size: 18,
              color: _AtelierColors.textSecondary,
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 15. SUPPORT & SIGN OUT
// ---------------------------------------------------------------------------

class EstablishedSupportAndSignOut extends StatelessWidget {
  final VoidCallback onHelp;
  final VoidCallback onFeedback;
  final VoidCallback onSignOut;
  final bool isSigningOut;

  const EstablishedSupportAndSignOut({
    super.key,
    required this.onHelp,
    required this.onFeedback,
    required this.onSignOut,
    this.isSigningOut = false,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Two compact secondary buttons side-by-side
        Row(
          children: [
            Expanded(
              child: InkWell(
                onTap: onHelp,
                borderRadius: BorderRadius.circular(20),
                child: Container(
                  height: 42,
                  decoration: BoxDecoration(
                    color: _AtelierColors.surfaceLow,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: _AtelierColors.subtleOutline.withValues(alpha: 0.25),
                      width: 1.0,
                    ),
                  ),
                  child: const Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.headset_mic_outlined,
                        size: 14,
                        color: _AtelierColors.goldPrimary,
                      ),
                      SizedBox(width: 8),
                      Text(
                        'Help & Concierge',
                        style: TextStyle(
                          fontFamily: FansivibeTypography.textFamily,
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                          color: _AtelierColors.textPrimary,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: InkWell(
                onTap: onFeedback,
                borderRadius: BorderRadius.circular(20),
                child: Container(
                  height: 42,
                  decoration: BoxDecoration(
                    color: _AtelierColors.surfaceLow,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: _AtelierColors.subtleOutline.withValues(alpha: 0.25),
                      width: 1.0,
                    ),
                  ),
                  child: const Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.rate_review_outlined,
                        size: 14,
                        color: _AtelierColors.goldPrimary,
                      ),
                      SizedBox(width: 8),
                      Text(
                        'Provide Feedback',
                        style: TextStyle(
                          fontFamily: FansivibeTypography.textFamily,
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                          color: _AtelierColors.textPrimary,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),

        const SizedBox(height: 24),

        // Restrained Sign Out Button
        TextButton(
          onPressed: isSigningOut ? null : onSignOut,
          style: TextButton.styleFrom(
            foregroundColor: _AtelierColors.textSecondary,
          ),
          child: isSigningOut
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: _AtelierColors.goldPrimary,
                  ),
                )
              : const Text(
                  'SIGN OUT',
                  style: TextStyle(
                    fontFamily: FansivibeTypography.textFamily,
                    fontSize: 11.5,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 2.0,
                    color: _AtelierColors.textSecondary,
                  ),
                ),
        ),
      ],
    );
  }
}
