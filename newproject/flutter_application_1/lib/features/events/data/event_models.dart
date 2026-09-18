/// Data models for the M8 event calendar backend surface (STEP 19.22).
///
/// Wire shapes mirror the frozen M8 contract exactly (camelCase):
/// `UserEvent {id, title, eventType, eventDate, time?, location?, notes?,
/// createdAt, updatedAt}` inside the offset envelope
/// `{items: EventSummary[], page, page_size, total}`, and the M8-C
/// `OutfitRecommendation {title, matchScore, components[], reasons[],
/// selectedOccasion}` honest subset (sourceless keys are absent on the
/// wire and stay absent here — never fabricated).
///
/// `id` is always the backend UUID string. Local numeric IDs are never
/// produced, stored, or sent by this layer. `eventType` is the frozen
/// backend TYPE CODE (never a display label).
library;

/// One owned event as returned by the M8 backend.
class EventItem {
  /// Creates an [EventItem].
  const EventItem({
    required this.id,
    required this.title,
    required this.eventType,
    required this.eventDate,
    required this.createdAt,
    required this.updatedAt,
    this.eventTime,
    this.location,
    this.notes,
  });

  /// Backend UUID of the event (path parameter for PUT/DELETE/outfit).
  final String id;

  /// Display title.
  final String title;

  /// Frozen backend type CODE (`casual`/`formal`/`business`/`date`/
  /// `party`/`travel`/`workout`/`other`). Never a display label.
  final String eventType;

  /// ISO date (`YYYY-MM-DD`).
  final String eventDate;

  /// Wall-clock time (`HH:mm`) or null when absent.
  final String? eventTime;

  /// Free-text location or null when absent.
  final String? location;

  /// Free-text notes or null when absent.
  final String? notes;

  /// Creation instant.
  final DateTime createdAt;

  /// Last-edit instant (server-bumped on PUT).
  final DateTime updatedAt;

  /// Display date (`Aug 15, 2026`) derived from the ISO wire value.
  String get displayDate {
    final parts = eventDate.split('-');
    if (parts.length != 3) return eventDate;
    final year = int.tryParse(parts[0]);
    final month = int.tryParse(parts[1]);
    final day = int.tryParse(parts[2]);
    if (year == null || month == null || day == null) return eventDate;
    if (month < 1 || month > 12) return eventDate;
    return '${_months[month - 1]} $day, $year';
  }

  /// Display time (`7:00 PM`) derived from the `HH:mm` wire value,
  /// or null when the event carries no time.
  String? get displayTime {
    final raw = eventTime;
    if (raw == null) return null;
    final parts = raw.split(':');
    if (parts.length != 2) return raw;
    final hour = int.tryParse(parts[0]);
    final minute = int.tryParse(parts[1]);
    if (hour == null || minute == null) return raw;
    if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return raw;
    final period = hour < 12 ? 'AM' : 'PM';
    final hour12 = hour % 12 == 0 ? 12 : hour % 12;
    return '$hour12:${minute.toString().padLeft(2, '0')} $period';
  }

  /// Creates an [EventItem] from the backend wire map.
  ///
  /// Accepts both the full `UserEvent` detail shape and the
  /// `EventSummary` list-card shape (`GET /v1/events` omits
  /// `location`/`notes`/`createdAt`/`updatedAt`). Missing timestamps fall
  /// back to the event date at midnight UTC — derived from the real wire
  /// value, never invented. A malformed row still throws into the
  /// client's null path rather than posing as an event.
  factory EventItem.fromJson(Map<String, dynamic> json) {
    final eventDate = json['eventDate'] as String;
    // ponytail: summary rows carry no timestamps; derive midnight-UTC
    // from eventDate. Full detail rows keep their real timestamps.
    final fallbackStamp =
        DateTime.tryParse('${eventDate}T00:00:00.000Z') ?? DateTime.now();
    final createdRaw = json['createdAt'] as String?;
    final updatedRaw = json['updatedAt'] as String?;
    return EventItem(
      id: json['id'] as String,
      title: json['title'] as String,
      eventType: json['eventType'] as String,
      eventDate: eventDate,
      eventTime: json['time'] as String?,
      location: json['location'] as String?,
      notes: json['notes'] as String?,
      createdAt: createdRaw == null ? fallbackStamp : DateTime.parse(createdRaw),
      updatedAt: updatedRaw == null ? fallbackStamp : DateTime.parse(updatedRaw),
    );
  }

  /// Serializes this item back to the backend wire shape.
  Map<String, dynamic> toJson() => {
    'id': id,
    'title': title,
    'eventType': eventType,
    'eventDate': eventDate,
    'time': eventTime,
    'location': location,
    'notes': notes,
    'createdAt': createdAt.toIso8601String(),
    'updatedAt': updatedAt.toIso8601String(),
  };

  /// Copy with modified fields.
  EventItem copyWith({
    String? id,
    String? title,
    String? eventType,
    String? eventDate,
    String? Function()? eventTime,
    String? Function()? location,
    String? Function()? notes,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) {
    return EventItem(
      id: id ?? this.id,
      title: title ?? this.title,
      eventType: eventType ?? this.eventType,
      eventDate: eventDate ?? this.eventDate,
      eventTime: eventTime != null ? eventTime() : this.eventTime,
      location: location != null ? location() : this.location,
      notes: notes != null ? notes() : this.notes,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }
}

/// Paginated events page (`GET /v1/events` envelope).
class EventListPage {
  /// Creates an [EventListPage].
  const EventListPage({
    required this.items,
    required this.page,
    required this.pageSize,
    required this.total,
  });

  /// Events on this page (upcoming-first per contract).
  final List<EventItem> items;

  /// 1-based page number echoed by the backend.
  final int page;

  /// Page size echoed by the backend.
  final int pageSize;

  /// Total owned rows across all pages.
  final int total;

  /// Whether this page carries no rows.
  bool get isEmpty => items.isEmpty;

  /// Creates an [EventListPage] from the backend wire map.
  ///
  /// `items` is required (a missing list throws into the client's null
  /// path rather than posing as an empty calendar); pagination counters
  /// fall back to echoed defaults.
  factory EventListPage.fromJson(Map<String, dynamic> json) => EventListPage(
    items: (json['items'] as List<dynamic>)
        .map((e) => EventItem.fromJson(e as Map<String, dynamic>))
        .toList(),
    page: json['page'] as int? ?? 1,
    pageSize: json['page_size'] as int? ?? 0,
    total: json['total'] as int? ?? 0,
  );
}

/// `POST /v1/events` request body.
class EventCreateRequest {
  /// Creates an [EventCreateRequest].
  const EventCreateRequest({
    required this.title,
    required this.eventType,
    required this.eventDate,
    this.eventTime,
    this.location,
    this.notes,
  });

  /// Display title (1..200).
  final String title;

  /// Frozen backend type CODE.
  final String eventType;

  /// ISO date (`YYYY-MM-DD`), not in the past.
  final String eventDate;

  /// Wall-clock time (`HH:mm`) or null when absent.
  final String? eventTime;

  /// Location text or null when absent (blank maps to null upstream).
  final String? location;

  /// Notes text or null when absent (blank maps to null upstream).
  final String? notes;

  /// Serializes to the exact `EventCreate` wire shape.
  Map<String, dynamic> toJson() => {
    'title': title,
    'eventType': eventType,
    'eventDate': eventDate,
    'time': eventTime,
    'location': location,
    'notes': notes,
  };
}

/// `PUT /v1/events/{event_id}` request body (full replacement).
class EventUpdateRequest {
  /// Creates an [EventUpdateRequest].
  const EventUpdateRequest({
    required this.title,
    required this.eventType,
    required this.eventDate,
    this.eventTime,
    this.location,
    this.notes,
  });

  /// Display title (1..200).
  final String title;

  /// Frozen backend type CODE.
  final String eventType;

  /// ISO date (`YYYY-MM-DD`), not in the past.
  final String eventDate;

  /// Wall-clock time (`HH:mm`); null clears a previously set time.
  final String? eventTime;

  /// Location text; null clears a previously set location.
  final String? location;

  /// Notes text; null clears previously set notes.
  final String? notes;

  /// Serializes to the exact `EventUpdate` wire shape.
  Map<String, dynamic> toJson() => {
    'title': title,
    'eventType': eventType,
    'eventDate': eventDate,
    'time': eventTime,
    'location': location,
    'notes': notes,
  };
}

/// One wardrobe component inside an event outfit recommendation.
class EventOutfitComponent {
  /// Creates an [EventOutfitComponent].
  const EventOutfitComponent({
    required this.id,
    required this.name,
    required this.category,
    required this.color,
    required this.reason,
    this.material,
  });

  /// Backend wardrobe UUID (verbatim — never resolved locally).
  final String id;

  /// Wardrobe item name (verbatim backend text).
  final String name;

  /// Wardrobe category code (verbatim).
  final String category;

  /// Wardrobe color code (verbatim; hex has no server source).
  final String color;

  /// Wardrobe material code, when the item carries one.
  final String? material;

  /// Grounded selection reason (verbatim backend text).
  final String reason;

  /// Creates an [EventOutfitComponent] from the backend wire map.
  factory EventOutfitComponent.fromJson(Map<String, dynamic> json) =>
      EventOutfitComponent(
        id: json['id'] as String,
        name: json['name'] as String,
        category: json['category'] as String,
        color: json['color'] as String,
        material: json['material'] as String?,
        reason: json['reason'] as String,
      );
}

/// M8-C event outfit recommendation (`POST /v1/events/{id}/outfit`).
///
/// Honest backend subset: sourceless keys (`selectedMood`,
/// `selectedColorPalette`, `colorHex`, harmony/fit prose) are absent on
/// the wire and have no fields here — never fabricated.
class EventOutfit {
  /// Creates an [EventOutfit].
  const EventOutfit({
    required this.title,
    required this.matchScore,
    required this.components,
    required this.reasons,
    required this.selectedOccasion,
  });

  /// Recommendation title (verbatim backend text).
  final String title;

  /// Ensemble match score, family 0..1 float scale (verbatim).
  final double matchScore;

  /// Owned wardrobe components backing the recommendation.
  final List<EventOutfitComponent> components;

  /// Grounded reason bullets (verbatim backend text).
  final List<String> reasons;

  /// Derivation occasion: the event TYPE CODE (verbatim).
  final String selectedOccasion;

  /// Creates an [EventOutfit] from the backend wire map.
  factory EventOutfit.fromJson(Map<String, dynamic> json) => EventOutfit(
    title: json['title'] as String,
    matchScore: (json['matchScore'] as num).toDouble(),
    components: (json['components'] as List<dynamic>? ?? const [])
        .map((e) => EventOutfitComponent.fromJson(e as Map<String, dynamic>))
        .toList(),
    reasons: (json['reasons'] as List<dynamic>? ?? const [])
        .map((e) => e as String)
        .toList(),
    selectedOccasion: json['selectedOccasion'] as String,
  );
}

/// Outcome of `POST /v1/events/{event_id}/outfit`.
///
/// 200 carries the recommendation; 204 (empty wardrobe / no legal
/// candidate) is a truthful "none available" state — never an error
/// and never a fabricated outfit. Null (client/repository) means the
/// request itself failed and is safe to retry.
class EventOutfitResult {
  /// Creates an [EventOutfitResult].
  const EventOutfitResult._({required this.available, this.outfit});

  /// Backend derived a recommendation.
  const EventOutfitResult.available(EventOutfit outfit)
    : this._(available: true, outfit: outfit);

  /// Backend answered 204: no outfit is derivable right now.
  const EventOutfitResult.noneAvailable() : this._(available: false);

  /// Whether a recommendation is present.
  final bool available;

  /// The recommendation, when [available].
  final EventOutfit? outfit;
}

/// Outcome of `DELETE /v1/events/{event_id}`.
///
/// The client returns null (never an outcome) when the backend is
/// unreachable or rejects the request — the project null-on-failure
/// convention — so callers keep the row and allow a retry.
enum EventDeleteOutcome {
  /// Backend answered 204: the row is gone.
  deleted,

  /// Backend answered 404: the row is already gone. The caller drops it
  /// locally without claiming a successful server-side delete.
  alreadyGone,
}

const List<String> _months = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];
