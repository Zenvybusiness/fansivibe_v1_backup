/// Data models for the backend saved-looks collection (DEC-013, STEP 18.4).
///
/// Wire shapes mirror `POST/GET /v1/looks/saved` exactly (camelCase):
/// `{id, lookId?, title, sourceContext?, snapshot, sourceRunId?,
/// createdAt}` inside the offset envelope
/// `{items, page, page_size, total}`. `sourceContext` is preserved verbatim
/// — including null for legacy rows — and is never inferred (DEC-010).
///
/// One saved look as returned by `GET /v1/looks/saved`.
class SavedLookItem {
  /// Creates a [SavedLookItem].
  const SavedLookItem({
    required this.id,
    required this.title,
    required this.createdAt,
    this.lookId,
    this.sourceContext,
    this.snapshot = const {},
    this.sourceRunId,
  });

  /// Backend UUID of the saved look (the DELETE path parameter).
  final String id;

  /// Catalog look code, when the save references one (null for outfits).
  final String? lookId;

  /// Display title.
  final String title;

  /// Backend-owned domain discriminator (`hairstyle`/`grooming`/`outfit`,
  /// null = legacy row). Preserved verbatim, never inferred.
  final String? sourceContext;

  /// Frozen recommendation snapshot stored at save time.
  final Map<String, dynamic> snapshot;

  /// Producing run id, when provenance was captured.
  final String? sourceRunId;

  /// Save instant.
  final DateTime createdAt;

  /// `selectedItemIds` carried by outfit snapshots (canonical backend
  /// wardrobe UUID strings). Empty for non-outfit snapshots. Read-only:
  /// v1 renders the count only and never resolves item names (DEC-013).
  List<String> get selectedItemIds {
    final raw = snapshot['selectedItemIds'];
    if (raw is! List) return const [];
    return [
      for (final e in raw)
        if (e is String) e,
    ];
  }

  /// Creates a [SavedLookItem] from the backend wire map.
  factory SavedLookItem.fromJson(Map<String, dynamic> json) => SavedLookItem(
    id: json['id'] as String? ?? '',
    lookId: json['lookId'] as String?,
    title: json['title'] as String? ?? '',
    sourceContext: json['sourceContext'] as String?,
    snapshot:
        (json['snapshot'] as Map?)?.map(
          (key, value) => MapEntry(key.toString(), value),
        ) ??
        const {},
    sourceRunId: json['sourceRunId'] as String?,
    createdAt:
        DateTime.tryParse(json['createdAt'] as String? ?? '') ??
        DateTime.fromMillisecondsSinceEpoch(0),
  );

  /// Serializes this item back to the backend wire shape.
  Map<String, dynamic> toJson() => {
    'id': id,
    if (lookId != null) 'lookId': lookId,
    'title': title,
    'sourceContext': sourceContext,
    'snapshot': snapshot,
    if (sourceRunId != null) 'sourceRunId': sourceRunId,
    'createdAt': createdAt.toIso8601String(),
  };

  /// Copy with modified fields.
  SavedLookItem copyWith({
    String? id,
    String? Function()? lookId,
    String? title,
    String? Function()? sourceContext,
    Map<String, dynamic>? snapshot,
    String? Function()? sourceRunId,
    DateTime? createdAt,
  }) {
    return SavedLookItem(
      id: id ?? this.id,
      lookId: lookId != null ? lookId() : this.lookId,
      title: title ?? this.title,
      sourceContext: sourceContext != null
          ? sourceContext()
          : this.sourceContext,
      snapshot: snapshot ?? this.snapshot,
      sourceRunId: sourceRunId != null ? sourceRunId() : this.sourceRunId,
      createdAt: createdAt ?? this.createdAt,
    );
  }
}

/// Paginated saved-looks page (`GET /v1/looks/saved` envelope).
class SavedLookListPage {
  /// Creates a [SavedLookListPage].
  const SavedLookListPage({
    required this.items,
    required this.page,
    required this.pageSize,
    required this.total,
  });

  /// Saved looks on this page (`createdAt` desc per contract).
  final List<SavedLookItem> items;

  /// 1-based page number echoed by the backend.
  final int page;

  /// Page size echoed by the backend.
  final int pageSize;

  /// Total owned rows across all pages.
  final int total;

  /// Whether this page carries no rows.
  bool get isEmpty => items.isEmpty;

  /// Creates a [SavedLookListPage] from the backend wire map.
  factory SavedLookListPage.fromJson(Map<String, dynamic> json) =>
      SavedLookListPage(
        items: (json['items'] as List<dynamic>? ?? const [])
            .map((e) => SavedLookItem.fromJson(e as Map<String, dynamic>))
            .toList(),
        page: json['page'] as int? ?? 1,
        pageSize: json['page_size'] as int? ?? 0,
        total: json['total'] as int? ?? 0,
      );
}

/// Outcome of `DELETE /v1/looks/saved/{saved_look_id}`.
///
/// The client returns null (never an outcome) when the backend is
/// unreachable or rejects the request — the project null-on-failure
/// convention — so callers keep the row and allow a retry.
enum SavedLookDeleteOutcome {
  /// Backend answered 204: the row is gone.
  deleted,

  /// Backend answered 404: the row is already gone. The caller removes it
  /// locally without claiming a successful server-side delete.
  alreadyGone,
}
