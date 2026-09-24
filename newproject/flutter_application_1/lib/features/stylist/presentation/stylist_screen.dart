import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/events/data/event_mock_data.dart';
import 'package:fansivibe/features/events/data/event_models.dart';
import 'package:fansivibe/features/events/data/events_repository.dart';
import 'package:fansivibe/features/wardrobe/data/local_wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Legacy action descriptor retained for backward compatibility with existing tests.
class StylistActionData {
  const StylistActionData({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.icon,
    this.accentColor = FansivibeColors.accentGold,
  });

  final String id;
  final String title;
  final String subtitle;
  final IconData icon;
  final Color accentColor;

  static const List<StylistActionData> mockActions = [
    StylistActionData(
      id: 'scan_outfit',
      title: 'Scan My Outfit',
      subtitle: 'Get instant AI feedback in under 2 seconds',
      icon: Icons.crop_free,
    ),
    StylistActionData(
      id: 'build_outfit',
      title: 'Build Outfit',
      subtitle: 'Utilize your existing collection',
      icon: Icons.checkroom_outlined,
      accentColor: Color(0xFF8B7D6B),
    ),
    StylistActionData(
      id: 'hairstyle',
      title: 'Hairstyle',
      subtitle: 'Find your perfect hairstyle',
      icon: Icons.content_cut_rounded,
      accentColor: Color(0xFF7B8E6B),
    ),
    StylistActionData(
      id: 'grooming',
      title: 'Beard / Glasses',
      subtitle: 'Grooming and accessory suggestions',
      icon: Icons.face_retouching_natural_outlined,
      accentColor: Color(0xFF6B8E8E),
    ),
    StylistActionData(
      id: 'event',
      title: 'Event Planning',
      subtitle: 'Plan outfits for upcoming events',
      icon: Icons.event_outlined,
      accentColor: Color(0xFF8E6B8E),
    ),
  ];
}

/// Fansivibe AI Stylist Screen.
///
/// Visual and structural source of truth: Ai stylest.pdf.
///
/// Hierarchy:
/// 1. Header: F A N S I V I B E, notification bell, profile avatar, "AI Stylist" title,
///    and "What do you need help with today?".
/// 2. Primary Card: "Scan My Outfit" with satin gold luxury gradient.
/// 3. Secondary Card: "Build Outfit From My Wardrobe" connected to actual wardrobe data.
/// 4. Face & Grooming: "Hairstyle Recommendation" and "Beard / Glasses Suggestion".
/// 5. Plan for an Event: "Add Event" and real upcoming events or graceful empty state.
class StylistScreen extends StatefulWidget {
  const StylistScreen({
    this.wardrobeRepository,
    this.eventsRepository,
    super.key,
  });

  final WardrobeRepository? wardrobeRepository;
  final EventsRepository? eventsRepository;

  @override
  State<StylistScreen> createState() => _StylistScreenState();
}

class _StylistScreenState extends State<StylistScreen> {
  late final WardrobeRepository _wardrobeRepository;
  late final EventsRepository _eventsRepository;

  Future<int>? _wardrobeCountFuture;
  Future<EventListPage?>? _eventsFuture;
  bool _isEventSectionExpanded = true;

  @override
  void initState() {
    super.initState();
    _initRepositories();
    _loadData();
  }

  void _initRepositories() {
    _wardrobeRepository =
        widget.wardrobeRepository ??
        (isGuestUser ? LocalWardrobeRepository() : WardrobeRepositoryImpl());

    _eventsRepository = widget.eventsRepository ?? EventsRepositoryImpl();
  }

  void _loadData() {
    // Check wardrobe collection status
    _wardrobeCountFuture = _wardrobeRepository
        .listItems(pageSize: 1)
        .then((items) => items.length)
        .catchError((_) => 0);

    // Fetch upcoming events for authenticated users
    if (isGuestUser) {
      _eventsFuture = Future.value(null);
    } else {
      _eventsFuture = _eventsRepository.listEvents(pageSize: 5);
    }
  }

  void _reloadEvents() {
    if (isGuestUser) return;
    setState(() {
      _eventsFuture = _eventsRepository.listEvents(pageSize: 5);
    });
  }

  String? get _resolvedDisplayName {
    final stored = LocalStorage.displayName;
    if (stored != null && stored.trim().isNotEmpty) {
      return stored.trim();
    }
    return null;
  }

  Future<void> _addEvent() async {
    if (isGuestUser) {
      promptGuestSignIn(
        context,
        action: 'Sign in to plan events. Browsing stays free.',
      );
      return;
    }
    final created = await context.pushNamed<EventItem>(RouteNames.eventAdd);
    if (created != null && mounted) {
      _reloadEvents();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('${created.title} added to your events'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  String _formatEventSubtitle(EventItem event) {
    final parts = event.eventDate.split('-');
    String dateStr = event.displayDate;
    if (parts.length == 3) {
      final monthNum = int.tryParse(parts[1]) ?? 1;
      const months = [
        'JAN',
        'FEB',
        'MAR',
        'APR',
        'MAY',
        'JUN',
        'JUL',
        'AUG',
        'SEP',
        'OCT',
        'NOV',
        'DEC',
      ];
      final month = (monthNum >= 1 && monthNum <= 12)
          ? months[monthNum - 1]
          : '';
      final day = parts[2].padLeft(2, '0');
      dateStr = '$month $day';
    }
    final typeName =
        EventType.byCodeOrNull(event.eventType)?.name.toUpperCase() ??
        event.eventType.toUpperCase();
    return '$dateStr \u2022 $typeName';
  }

  IconData _eventTypeIcon(String eventType) {
    switch (eventType.toLowerCase()) {
      case 'party':
        return Icons.nightlife_rounded;
      case 'date':
        return Icons.favorite_outline_rounded;
      case 'business':
        return Icons.business_center_outlined;
      case 'formal':
        return Icons.diamond_outlined;
      case 'travel':
        return Icons.flight_outlined;
      case 'workout':
        return Icons.fitness_center_outlined;
      case 'casual':
        return Icons.wb_sunny_outlined;
      default:
        return Icons.local_bar_rounded;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: FansivibeColors.surface,
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 20.0;
            final contentMaxWidth = maxWidth > 600 ? 540.0 : double.infinity;

            return SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              child: Center(
                child: ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: contentMaxWidth),
                  child: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: horizontalPadding,
                      vertical: 12,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // 1. Editorial Branding & Header
                        _buildHeader(context),
                        const SizedBox(height: 24),

                        // 2. Primary Action: Scan My Outfit
                        _buildScanOutfitHero(context),
                        const SizedBox(height: 16),

                        // 3. Secondary Action: Build Outfit From My Wardrobe
                        _buildBuildOutfitCard(context),
                        const SizedBox(height: 28),

                        // 4. Face & Grooming Section
                        _buildFaceAndGroomingSection(context),
                        const SizedBox(height: 28),

                        // 5. Plan for an Event Section
                        _buildPlanForEventSection(context),
                        const SizedBox(height: 36),
                      ],
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  // ── 1. HEADER & BRANDING ───────────────────────────────────────────────────

  Widget _buildHeader(BuildContext context) {
    final name = _resolvedDisplayName;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Top Branding Bar
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Text(
              'F A N S I V I B E',
              style: FansivibeTypography.labelMediumWithFamily.copyWith(
                color: FansivibeColors.onSurface.withValues(alpha: 0.8),
                letterSpacing: 3.0,
                fontSize: 11.5,
                fontWeight: FontWeight.w600,
              ),
            ),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Notification Bell with Badge Dot
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
                // Circular Profile Avatar
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
                        color: FansivibeColors.accentGold.withValues(alpha: 0.15),
                        border: Border.all(
                          color: FansivibeColors.accentGold.withValues(alpha: 0.4),
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
                                color: FansivibeColors.accentGold,
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
        const SizedBox(height: 24),
        // AI Stylist Title
        Text(
          'AI Stylist',
          style: FansivibeTypography.headlineMediumWithFamily.copyWith(
            fontSize: 34,
            fontWeight: FontWeight.w600,
            color: FansivibeColors.onSurface,
            height: 1.15,
          ),
        ),
        const SizedBox(height: 6),
        // Subtitle Context Question
        Text(
          'What do you need help with today?',
          style: FansivibeTypography.bodyLargeWithFamily.copyWith(
            fontSize: 15.5,
            color: FansivibeColors.textSecondary,
          ),
        ),
      ],
    );
  }

  // ── 2. PRIMARY ACTION: SCAN MY OUTFIT ──────────────────────────────────────

  Widget _buildScanOutfitHero(BuildContext context) {
    return Semantics(
      button: true,
      label: 'Scan My Outfit',
      child: InkWell(
        onTap: () => context.pushNamed(RouteNames.scanOutfit),
        borderRadius: BorderRadius.circular(24),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 22),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                Color(0xFFF6E6C7), // Radiant satin champagne
                Color(0xFFE8C88B), // Warm rich gold
                Color(0xFFD6AB5C), // Deep honey gold
              ],
            ),
            borderRadius: BorderRadius.circular(24),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFFD6AB5C).withValues(alpha: 0.22),
                blurRadius: 20,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Container(
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(
                      color: const Color(0xFF141311).withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Icon(
                      Icons.crop_free,
                      size: 24,
                      color: Color(0xFF141311),
                    ),
                  ),
                  const Icon(
                    Icons.arrow_outward_rounded,
                    size: 22,
                    color: Color(0xFF141311),
                  ),
                ],
              ),
              const SizedBox(height: 22),
              const Text(
                'Scan My Outfit',
                style: TextStyle(
                  fontFamily: FansivibeTypography.textFamily,
                  fontSize: 24,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF141311),
                  letterSpacing: -0.3,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                'Get instant AI feedback in under 2 seconds',
                style: TextStyle(
                  fontFamily: FansivibeTypography.textFamily,
                  fontSize: 13.5,
                  fontWeight: FontWeight.w500,
                  color: const Color(0xFF141311).withValues(alpha: 0.75),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // ── 3. SECONDARY ACTION: BUILD OUTFIT FROM MY WARDROBE ─────────────────────

  Widget _buildBuildOutfitCard(BuildContext context) {
    return FutureBuilder<int>(
      future: _wardrobeCountFuture,
      builder: (context, snapshot) {
        final hasItems = (snapshot.data ?? 0) > 0;
        final subtitle = hasItems
            ? 'Utilize your existing collection'
            : 'Add a few favorite pieces to start creating outfits with AI';

        return Semantics(
          button: true,
          label: 'Build Outfit From My Wardrobe',
          child: InkWell(
            onTap: () => context.pushNamed(RouteNames.buildOutfit),
            borderRadius: BorderRadius.circular(20),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
              decoration: BoxDecoration(
                color: const Color(0xFF161618),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                  color: Colors.white.withValues(alpha: 0.08),
                  width: 1.0,
                ),
              ),
              child: Row(
                children: [
                  Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: Colors.white.withValues(alpha: 0.06),
                    ),
                    child: const Icon(
                      Icons.checkroom_outlined,
                      color: FansivibeColors.textPrimary,
                      size: 24,
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Build Outfit',
                          style: FansivibeTypography.titleLargeWithFamily.copyWith(
                            fontSize: 17,
                            fontWeight: FontWeight.w600,
                            color: FansivibeColors.textPrimary,
                            height: 1.2,
                          ),
                        ),
                        Text(
                          'From My Wardrobe',
                          style: FansivibeTypography.titleLargeWithFamily.copyWith(
                            fontSize: 17,
                            fontWeight: FontWeight.w600,
                            color: FansivibeColors.textPrimary,
                            height: 1.2,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          subtitle,
                          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                            fontSize: 12.5,
                            color: FansivibeColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  // ── 4. FACE & GROOMING SECTION ─────────────────────────────────────────────

  Widget _buildFaceAndGroomingSection(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'FACE & GROOMING',
          style: FansivibeTypography.labelMediumWithFamily.copyWith(
            letterSpacing: 2.0,
            fontSize: 11.5,
            fontWeight: FontWeight.w600,
            color: const Color(0xFFC7A76B),
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            // Hairstyle Recommendation Card
            Expanded(
              child: Semantics(
                button: true,
                label: 'Hairstyle Recommendation',
                child: InkWell(
                  onTap: () => context.pushNamed(RouteNames.hairstyle),
                  borderRadius: BorderRadius.circular(18),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 14,
                    ),
                    decoration: BoxDecoration(
                      color: const Color(0xFF161618),
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(
                        color: Colors.white.withValues(alpha: 0.08),
                        width: 1.0,
                      ),
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 38,
                          height: 38,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: Colors.white.withValues(alpha: 0.06),
                          ),
                          child: const Icon(
                            Icons.content_cut_rounded,
                            color: FansivibeColors.textPrimary,
                            size: 18,
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Hairstyle',
                                style: FansivibeTypography.bodyLargeWithFamily
                                    .copyWith(
                                  fontSize: 13.5,
                                  fontWeight: FontWeight.w600,
                                  color: FansivibeColors.textPrimary,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                              Text(
                                'Recommendation',
                                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                                  fontSize: 11,
                                  color: FansivibeColors.textSecondary,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
            // Beard / Glasses Suggestion Card
            Expanded(
              child: Semantics(
                button: true,
                label: 'Beard / Glasses Suggestion',
                child: InkWell(
                  onTap: () => context.pushNamed(RouteNames.grooming),
                  borderRadius: BorderRadius.circular(18),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 14,
                    ),
                    decoration: BoxDecoration(
                      color: const Color(0xFF161618),
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(
                        color: Colors.white.withValues(alpha: 0.08),
                        width: 1.0,
                      ),
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 38,
                          height: 38,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: Colors.white.withValues(alpha: 0.06),
                          ),
                          child: const Icon(
                            Icons.face_retouching_natural_outlined,
                            color: FansivibeColors.textPrimary,
                            size: 19,
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Beard / Glasses',
                                style: FansivibeTypography.bodyLargeWithFamily
                                    .copyWith(
                                  fontSize: 13.5,
                                  fontWeight: FontWeight.w600,
                                  color: FansivibeColors.textPrimary,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                              Text(
                                'Suggestion',
                                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                                  fontSize: 11,
                                  color: FansivibeColors.textSecondary,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  // ── 5. PLAN FOR AN EVENT SECTION ───────────────────────────────────────────

  Widget _buildPlanForEventSection(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFF151517),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.08),
          width: 1.0,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header: Calendar Icon + Title + Expand/Collapse Chevron
          InkWell(
            onTap: () {
              setState(() {
                _isEventSectionExpanded = !_isEventSectionExpanded;
              });
            },
            borderRadius: BorderRadius.circular(12),
            child: Row(
              children: [
                const Icon(
                  Icons.calendar_today_outlined,
                  color: FansivibeColors.accentGold,
                  size: 20,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Plan for an Event',
                    style:
                        FansivibeTypography.headlineMediumWithFamily.copyWith(
                      fontSize: 18,
                      fontWeight: FontWeight.w500,
                      color: FansivibeColors.textPrimary,
                    ),
                  ),
                ),
                Icon(
                  _isEventSectionExpanded
                      ? Icons.keyboard_arrow_up_rounded
                      : Icons.keyboard_arrow_down_rounded,
                  color: FansivibeColors.textSecondary,
                  size: 22,
                ),
              ],
            ),
          ),

          if (_isEventSectionExpanded) ...[
            const SizedBox(height: 18),

            // "Add Event" Action Row
            Semantics(
              button: true,
              label: 'Add Event',
              child: InkWell(
                onTap: _addEvent,
                borderRadius: BorderRadius.circular(12),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(
                    children: [
                      Text(
                        'Add Event',
                        style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                          fontSize: 15,
                          fontWeight: FontWeight.w500,
                          color: FansivibeColors.textPrimary,
                        ),
                      ),
                      const Spacer(),
                      const Icon(
                        Icons.add_circle_outline_rounded,
                        color: FansivibeColors.accentGold,
                        size: 22,
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: 14),

            // Events List or Empty State
            FutureBuilder<EventListPage?>(
              future: _eventsFuture,
              builder: (context, snapshot) {
                if (isGuestUser) {
                  return _buildEventGuestState(context);
                }

                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Padding(
                    padding: EdgeInsets.symmetric(vertical: 24),
                    child: Center(
                      child: SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: FansivibeColors.accentGold,
                        ),
                      ),
                    ),
                  );
                }

                final page = snapshot.data;
                if (page == null || page.isEmpty) {
                  return _buildEventEmptyState(context);
                }

                // Render up to 3 upcoming events
                final upcomingEvents = page.items.take(3).toList();
                return Column(
                  children: upcomingEvents
                      .map((event) => _buildEventCard(context, event))
                      .toList(),
                );
              },
            ),

            const SizedBox(height: 8),

            // Link to Event Planning for full calendar and test navigation
            Align(
              alignment: Alignment.centerRight,
              child: Semantics(
                button: true,
                label: 'Event Planning',
                child: InkWell(
                  onTap: () => context.pushNamed(RouteNames.events),
                  borderRadius: BorderRadius.circular(8),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 6,
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          'Event Planning',
                          style: TextStyle(
                            fontFamily: FansivibeTypography.textFamily,
                            fontSize: 12.5,
                            fontWeight: FontWeight.w500,
                            color: FansivibeColors.accentGold.withValues(
                              alpha: 0.9,
                            ),
                          ),
                        ),
                        const SizedBox(width: 4),
                        Icon(
                          Icons.arrow_forward_rounded,
                          size: 14,
                          color: FansivibeColors.accentGold.withValues(
                            alpha: 0.9,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildEventCard(BuildContext context, EventItem event) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Semantics(
        button: true,
        label: '${event.title}, ${_formatEventSubtitle(event)}',
        child: InkWell(
          onTap: () async {
            final changed = await context.pushNamed<bool>(
              RouteNames.eventDetails,
              extra: event,
            );
            if (changed == true && mounted) {
              _reloadEvents();
            }
          },
          borderRadius: BorderRadius.circular(16),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
            decoration: BoxDecoration(
              color: const Color(0xFF1E1E22),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: Colors.white.withValues(alpha: 0.05),
                width: 1.0,
              ),
            ),
            child: Row(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Colors.white.withValues(alpha: 0.06),
                  ),
                  child: Icon(
                    _eventTypeIcon(event.eventType),
                    color: FansivibeColors.accentGold,
                    size: 20,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        event.title,
                        style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                          color: FansivibeColors.textPrimary,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 3),
                      Text(
                        _formatEventSubtitle(event),
                        style: FansivibeTypography.labelMediumWithFamily
                            .copyWith(
                          fontSize: 11,
                          fontWeight: FontWeight.w500,
                          letterSpacing: 0.8,
                          color: FansivibeColors.textSecondary,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                Icon(
                  Icons.chevron_right_rounded,
                  color: Colors.white.withValues(alpha: 0.3),
                  size: 20,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildEventEmptyState(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 16),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.02),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.04),
        ),
      ),
      child: Column(
        children: [
          Icon(
            Icons.event_available_outlined,
            color: FansivibeColors.accentGold.withValues(alpha: 0.6),
            size: 26,
          ),
          const SizedBox(height: 8),
          Text(
            'No upcoming events',
            style: FansivibeTypography.bodyLargeWithFamily.copyWith(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textPrimary,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            'Add an event to style the perfect look with AI for your upcoming occasions.',
            textAlign: TextAlign.center,
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              fontSize: 12,
              color: FansivibeColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildEventGuestState(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 16),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.02),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.04),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Event Styling',
            style: FansivibeTypography.bodyLargeWithFamily.copyWith(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textPrimary,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            'Sign in to save events and receive bespoke AI outfit recommendations.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              fontSize: 12,
              color: FansivibeColors.textSecondary,
            ),
          ),
          const SizedBox(height: 10),
          GestureDetector(
            onTap: () => promptGuestSignIn(
              context,
              action: 'Sign in to plan events. Browsing stays free.',
            ),
            child: Text(
              'Sign In \u2192',
              style: TextStyle(
                fontFamily: FansivibeTypography.textFamily,
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: FansivibeColors.accentGold,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
