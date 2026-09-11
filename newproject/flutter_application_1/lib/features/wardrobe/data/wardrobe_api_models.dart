

/// Media reference for item images, as defined in §13.3 of WARDROBE_API.md.
class MediaRef {
  const MediaRef({
    required this.objectKey,
    required this.mediaType,
    this.width,
    this.height,
    this.sizeBytes,
    this.contentHash,
    this.isGenerated,
    this.uploadedAt,
  });

  final String objectKey;
  final String mediaType;
  final int? width;
  final int? height;
  final int? sizeBytes;
  final String? contentHash;
  final bool? isGenerated;
  final DateTime? uploadedAt;

  MediaRef copyWith({
    String? objectKey,
    String? mediaType,
    int? width,
    int? height,
    int? sizeBytes,
    String? contentHash,
    bool? isGenerated,
    DateTime? uploadedAt,
  }) =>
      MediaRef(
        objectKey: objectKey ?? this.objectKey,
        mediaType: mediaType ?? this.mediaType,
        width: width ?? this.width,
        height: height ?? this.height,
        sizeBytes: sizeBytes ?? this.sizeBytes,
        contentHash: contentHash ?? this.contentHash,
        isGenerated: isGenerated ?? this.isGenerated,
        uploadedAt: uploadedAt ?? this.uploadedAt,
      );

  factory MediaRef.fromJson(Map<String, dynamic> json) => MediaRef(
        objectKey: json['objectKey'] as String,
        mediaType: json['mediaType'] as String,
        width: json['width'] as int?,
        height: json['height'] as int?,
        sizeBytes: json['sizeBytes'] as int?,
        contentHash: json['contentHash'] as String?,
        isGenerated: json['isGenerated'] as bool?,
        uploadedAt: json['uploadedAt'] != null
            ? DateTime.tryParse(json['uploadedAt'] as String)
            : null,
      );

Map<String, dynamic> toJson() => {
        'objectKey': objectKey,
        'mediaType': mediaType,
        'width': width,
        'height': height,
        'sizeBytes': sizeBytes,
        'contentHash': contentHash,
        'isGenerated': isGenerated,
        if (uploadedAt != null) 'uploadedAt': uploadedAt!.toIso8601String(),
      };
}

/// Vocabulary item from the knowledge catalog, as defined in §5.6 of WARDROBE_API.md.
class VocabularyItem {
  const VocabularyItem({
    required this.code,
    required this.label,
    this.sortOrder,
    this.active = true,
  });

  final String code;
  final String label;
  final int? sortOrder;
  final bool active;

  factory VocabularyItem.fromJson(Map<String, dynamic> json) => VocabularyItem(
        code: json['code'] as String,
        label: json['label'] as String,
        sortOrder: json['sortOrder'] as int?,
        active: json['active'] as bool? ?? true,
      );

  Map<String, dynamic> toJson() => {
        'code': code,
        'label': label,
        'sortOrder': sortOrder,
        'active': active,
      };
}

/// The full wardrobe item DTO returned by the API, as defined in §4.7 and §5.1 of
/// WARDROBE_API.md.
class WardrobeItem {
  const WardrobeItem({
    required this.id,
    required this.name,
    required this.category,
    required this.color,
    this.material,
    this.isFavorite = false,
    this.imageRef,
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final String name;
  final String category;
  final String color;
  final String? material;
  final bool isFavorite;
  final MediaRef? imageRef;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  WardrobeItem copyWith({
    String? id,
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
    MediaRef? imageRef,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) =>
      WardrobeItem(
        id: id ?? this.id,
        name: name ?? this.name,
        category: category ?? this.category,
        color: color ?? this.color,
        material: material ?? this.material,
        isFavorite: isFavorite ?? this.isFavorite,
        imageRef: imageRef ?? this.imageRef,
        createdAt: createdAt ?? this.createdAt,
        updatedAt: updatedAt ?? this.updatedAt,
      );

  factory WardrobeItem.fromJson(Map<String, dynamic> json) => WardrobeItem(
        id: json['id'] as String,
        name: json['name'] as String,
        category: json['category'] as String,
        color: json['color'] as String,
        material: json['material'] as String?,
        isFavorite: json['isFavorite'] as bool? ?? false,
        imageRef: json['imageRef'] != null
            ? MediaRef.fromJson(json['imageRef'] as Map<String, dynamic>)
            : null,
        createdAt: json['createdAt'] != null
            ? DateTime.tryParse(json['createdAt'] as String)
            : null,
        updatedAt: json['updatedAt'] != null
            ? DateTime.tryParse(json['updatedAt'] as String)
            : null,
      );

Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'category': category,
        'color': color,
        'material': material,
        'isFavorite': isFavorite,
        'imageRef': imageRef?.toJson(),
        if (createdAt != null) 'createdAt': createdAt!.toIso8601String(),
        if (updatedAt != null) 'updatedAt': updatedAt!.toIso8601String(),
      };
}

/// The payload for creating a new wardrobe item (POST /v1/wardrobe/items), as defined
/// in §5.3 of WARDROBE_API.md.
class WardrobeItemCreate {
  const WardrobeItemCreate({
    required this.name,
    required this.category,
    required this.color,
    this.material,
    this.imageRef,
  });

  final String name;
  final String category;
  final String color;
  final String? material;
  final MediaRef? imageRef;

  WardrobeItemCreate copyWith({
    String? name,
    String? category,
    String? color,
    String? material,
    MediaRef? imageRef,
  }) => WardrobeItemCreate(
        name: name ?? this.name,
        category: category ?? this.category,
        color: color ?? this.color,
        material: material ?? this.material,
        imageRef: imageRef ?? this.imageRef,
      );

  factory WardrobeItemCreate.fromJson(Map<String, dynamic> json) => WardrobeItemCreate(
        name: json['name'] as String,
        category: json['category'] as String,
        color: json['color'] as String,
        material: json['material'] as String?,
        imageRef: json['imageRef'] != null
            ? MediaRef.fromJson(json['imageRef'] as Map<String, dynamic>)
            : null,
      );

  Map<String, dynamic> toJson() => {
        'name': name,
        'category': category,
        'color': color,
        'material': material,
        'imageRef': imageRef?.toJson(),
      };
}

/// The partial payload for updating a wardrobe item (PATCH /v1/wardrobe/items/{item_id}),
/// as defined in §5.4 of WARDROBE_API.md.
class WardrobeItemPatch {
  const WardrobeItemPatch({
    this.name,
    this.category,
    this.color,
    this.material,
    this.isFavorite,
  });

  final String? name;
  final String? category;
  final String? color;
  final String? material;
  final bool? isFavorite;

  WardrobeItemPatch copyWith({
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
  }) => WardrobeItemPatch(
        name: name ?? this.name,
        category: category ?? this.category,
        color: color ?? this.color,
        material: material ?? this.material,
        isFavorite: isFavorite ?? this.isFavorite,
      );

  factory WardrobeItemPatch.fromJson(Map<String, dynamic> json) => WardrobeItemPatch(
        name: json['name'] as String?,
        category: json['category'] as String?,
        color: json['color'] as String?,
        material: json['material'] as String?,
        isFavorite: json['isFavorite'] as bool?,
      );

  Map<String, dynamic> toJson() => {
        if (name != null) 'name': name!,
        if (category != null) 'category': category!,
        if (color != null) 'color': color!,
        if (material != null) 'material': material!,
        if (isFavorite != null) 'isFavorite': isFavorite!,
      };
}

/// The list envelope returned by `GET /v1/wardrobe/items`, as defined in §4.4 and
/// §5.1 of WARDROBE_API.md.
class ListEnvelope {
  const ListEnvelope({
    required this.items,
    required this.page,
    required this.pageSize,
    required this.total,
  });

  final List<WardrobeItem> items;
  final int page;
  final int pageSize;
  final int total;

  factory ListEnvelope.fromJson(Map<String, dynamic> json) => ListEnvelope(
        items: (json['items'] as List<dynamic>? ?? const [])
            .map((e) => WardrobeItem.fromJson(e as Map<String, dynamic>))
            .toList(),
        page: json['page'] as int? ?? 1,
        pageSize: json['page_size'] as int? ?? 20,
        total: json['total'] as int? ?? 0,
      );

  List<WardrobeItem> get sortedByCreatedAt =>
      items
          .where((item) => item.createdAt != null)
          .map((item) => item)
          .toList()
          ..sort((a, b) => b.createdAt!.compareTo(a.createdAt!));

  List<WardrobeItem> get sortedByName => items..sort((a, b) => a.name.compareTo(b.name));

  bool get isEmpty => items.isEmpty;

  ListEnvelope copyWith({
    List<WardrobeItem>? items,
    int? page,
    int? pageSize,
    int? total,
  }) => ListEnvelope(
        items: items ?? this.items,
        page: page ?? this.page,
        pageSize: pageSize ?? this.pageSize,
        total: total ?? this.total,
      );

  Map<String, dynamic> toJson() => {
        'items': items.map((e) => e.toJson()).toList(),
        'page': page,
        'page_size': pageSize,
        'total': total,
      };
}

/// The derived wardrobe insight DTO returned by `GET /v1/wardrobe/insight`
/// (W-7/UC-14).
///
/// The backend composes [title] and [insight] from persisted wardrobe facts
/// (plus saved-look coverage since Step 14.4) — Flutter renders them
/// verbatim and never reconstructs the text locally. [action]/[route] are
/// currently omitted by the backend; when present they decode compatibly
/// but Flutter must not invent navigation for them.
class WardrobeInsight {
  const WardrobeInsight({
    required this.title,
    required this.insight,
    this.action,
    this.route,
  });

  final String title;
  final String insight;
  final String? action;
  final String? route;

  WardrobeInsight copyWith({
    String? title,
    String? insight,
    String? action,
    String? route,
  }) =>
      WardrobeInsight(
        title: title ?? this.title,
        insight: insight ?? this.insight,
        action: action ?? this.action,
        route: route ?? this.route,
      );

  factory WardrobeInsight.fromJson(Map<String, dynamic> json) => WardrobeInsight(
        title: json['title'] as String,
        insight: json['insight'] as String,
        action: json['action'] as String?,
        route: json['route'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'title': title,
        'insight': insight,
        'action': action,
        'route': route,
      };
}

/// The payload for logging a wear event (`POST /v1/wardrobe/wears`),
/// as defined by the Step 15.4 backend contract.
///
/// [itemIds] are backend wardrobe UUIDs passed through verbatim — the
/// client never translates local mock IDs into backend UUIDs. [wornAt]
/// is omitted from the wire body when null (server defaults to now).
class WearEventLogRequest {
  const WearEventLogRequest({
    required this.itemIds,
    this.wornAt,
  });

  final List<String> itemIds;
  final DateTime? wornAt;

  WearEventLogRequest copyWith({
    List<String>? itemIds,
    DateTime? wornAt,
  }) =>
      WearEventLogRequest(
        itemIds: itemIds ?? this.itemIds,
        wornAt: wornAt ?? this.wornAt,
      );

  factory WearEventLogRequest.fromJson(Map<String, dynamic> json) =>
      WearEventLogRequest(
        itemIds: (json['itemIds'] as List<dynamic>? ?? const [])
            .map((e) => e as String)
            .toList(),
        wornAt: json['wornAt'] != null
            ? DateTime.tryParse(json['wornAt'] as String)
            : null,
      );

  Map<String, dynamic> toJson() => {
        'itemIds': itemIds,
        if (wornAt != null) 'wornAt': wornAt!.toUtc().toIso8601String(),
      };
}

/// One persisted wear-event row returned by the wear surface.
class WearEvent {
  const WearEvent({
    required this.id,
    required this.wardrobeItemId,
    required this.wornAt,
    required this.wearGroupId,
    required this.createdAt,
  });

  final String id;
  final String wardrobeItemId;
  final DateTime? wornAt;
  final String wearGroupId;
  final DateTime? createdAt;

  factory WearEvent.fromJson(Map<String, dynamic> json) => WearEvent(
        id: json['id'] as String,
        wardrobeItemId: json['wardrobeItemId'] as String,
        wornAt: json['wornAt'] != null
            ? DateTime.tryParse(json['wornAt'] as String)
            : null,
        wearGroupId: json['wearGroupId'] as String,
        createdAt: json['createdAt'] != null
            ? DateTime.tryParse(json['createdAt'] as String)
            : null,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'wardrobeItemId': wardrobeItemId,
        if (wornAt != null) 'wornAt': wornAt!.toUtc().toIso8601String(),
        'wearGroupId': wearGroupId,
        if (createdAt != null) 'createdAt': createdAt!.toUtc().toIso8601String(),
      };
}

/// The response for `POST /v1/wardrobe/wears` (STEP 15.4/15.4B).
///
/// [created] distinguishes a fresh log (`true`) from an idempotent replay
/// (`false`, still HTTP 201) — both carry the same group and rows.
class WearEventLogResponse {
  const WearEventLogResponse({
    required this.wears,
    required this.wearGroupId,
    required this.wornAt,
    required this.created,
  });

  final List<WearEvent> wears;
  final String wearGroupId;
  final DateTime? wornAt;
  final bool created;

  factory WearEventLogResponse.fromJson(Map<String, dynamic> json) =>
      WearEventLogResponse(
        wears: (json['wears'] as List<dynamic>? ?? const [])
            .map((e) => WearEvent.fromJson(e as Map<String, dynamic>))
            .toList(),
        wearGroupId: json['wearGroupId'] as String,
        wornAt: json['wornAt'] != null
            ? DateTime.tryParse(json['wornAt'] as String)
            : null,
        created: json['created'] as bool? ?? false,
      );

  Map<String, dynamic> toJson() => {
        'wears': wears.map((e) => e.toJson()).toList(),
        'wearGroupId': wearGroupId,
        if (wornAt != null) 'wornAt': wornAt!.toUtc().toIso8601String(),
        'created': created,
      };
}