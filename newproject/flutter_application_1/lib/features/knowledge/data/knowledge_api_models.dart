// Knowledge catalog DTOs for the M5 reads (#18–#22, STEP 19.5, DEC-014).
//
// Wire shapes follow `API_CONTRACT_RULES.md` §12.5: camelCase keys,
// offset envelopes with the `page_size` wire key. Parsing is strict —
// wrong types throw into the client's null path rather than posing
// garbage as catalog data.

/// One controlled-vocabulary row (#19/#20/#21).
class KnowledgeVocabularyItem {
  const KnowledgeVocabularyItem({
    required this.code,
    required this.label,
    required this.sortOrder,
  });

  final String code;
  final String label;
  final int sortOrder;

  KnowledgeVocabularyItem copyWith({
    String? code,
    String? label,
    int? sortOrder,
  }) => KnowledgeVocabularyItem(
    code: code ?? this.code,
    label: label ?? this.label,
    sortOrder: sortOrder ?? this.sortOrder,
  );

  factory KnowledgeVocabularyItem.fromJson(Map<String, dynamic> json) =>
      KnowledgeVocabularyItem(
        code: json['code'] as String,
        label: json['label'] as String,
        sortOrder: json['sortOrder'] as int,
      );

  Map<String, dynamic> toJson() => {
    'code': code,
    'label': label,
    'sortOrder': sortOrder,
  };
}

/// One system-owned item-type reference row (#22, DEC-014 P-2 frozen shape).
class KnowledgeItemReference {
  const KnowledgeItemReference({
    required this.code,
    required this.label,
    required this.category,
    required this.sortOrder,
  });

  final String code;
  final String label;
  final String category;
  final int sortOrder;

  KnowledgeItemReference copyWith({
    String? code,
    String? label,
    String? category,
    int? sortOrder,
  }) => KnowledgeItemReference(
    code: code ?? this.code,
    label: label ?? this.label,
    category: category ?? this.category,
    sortOrder: sortOrder ?? this.sortOrder,
  );

  factory KnowledgeItemReference.fromJson(Map<String, dynamic> json) =>
      KnowledgeItemReference(
        code: json['code'] as String,
        label: json['label'] as String,
        category: json['category'] as String,
        sortOrder: json['sortOrder'] as int,
      );

  Map<String, dynamic> toJson() => {
    'code': code,
    'label': label,
    'category': category,
    'sortOrder': sortOrder,
  };
}

/// One curated catalog look (#18).
///
/// Verbatim catalog content fields only — rows carry no occasion/style
/// attributes (DEC-014 P-3), so none exist here.
class KnowledgeLook {
  const KnowledgeLook({
    required this.code,
    required this.title,
    required this.description,
    required this.reasons,
    required this.stylingTips,
    required this.maintenance,
    required this.bestFor,
  });

  final String code;
  final String title;
  final String description;
  final List<String> reasons;
  final String stylingTips;
  final String maintenance;
  final String bestFor;

  KnowledgeLook copyWith({
    String? code,
    String? title,
    String? description,
    List<String>? reasons,
    String? stylingTips,
    String? maintenance,
    String? bestFor,
  }) => KnowledgeLook(
    code: code ?? this.code,
    title: title ?? this.title,
    description: description ?? this.description,
    reasons: reasons ?? this.reasons,
    stylingTips: stylingTips ?? this.stylingTips,
    maintenance: maintenance ?? this.maintenance,
    bestFor: bestFor ?? this.bestFor,
  );

  factory KnowledgeLook.fromJson(Map<String, dynamic> json) => KnowledgeLook(
    code: json['code'] as String,
    title: json['title'] as String,
    description: json['description'] as String,
    reasons: (json['reasons'] as List<dynamic>)
        .map((e) => e as String)
        .toList(),
    stylingTips: json['stylingTips'] as String,
    maintenance: json['maintenance'] as String,
    bestFor: json['bestFor'] as String,
  );

  Map<String, dynamic> toJson() => {
    'code': code,
    'title': title,
    'description': description,
    'reasons': reasons,
    'stylingTips': stylingTips,
    'maintenance': maintenance,
    'bestFor': bestFor,
  };
}

/// Offset envelope for `GET /v1/knowledge/looks` (#18).
class KnowledgeLookList {
  const KnowledgeLookList({
    required this.items,
    required this.page,
    required this.pageSize,
    required this.total,
  });

  final List<KnowledgeLook> items;
  final int page;
  final int pageSize;
  final int total;

  factory KnowledgeLookList.fromJson(Map<String, dynamic> json) =>
      KnowledgeLookList(
        items: (json['items'] as List<dynamic>? ?? const [])
            .map((e) => KnowledgeLook.fromJson(e as Map<String, dynamic>))
            .toList(),
        page: json['page'] as int? ?? 1,
        pageSize: json['page_size'] as int? ?? 20,
        total: json['total'] as int? ?? 0,
      );

  bool get isEmpty => items.isEmpty;

  KnowledgeLookList copyWith({
    List<KnowledgeLook>? items,
    int? page,
    int? pageSize,
    int? total,
  }) => KnowledgeLookList(
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

/// Offset envelope for `#19`/`#20`/`#21` vocabulary reads.
class KnowledgeVocabularyList {
  const KnowledgeVocabularyList({
    required this.items,
    required this.page,
    required this.pageSize,
    required this.total,
  });

  final List<KnowledgeVocabularyItem> items;
  final int page;
  final int pageSize;
  final int total;

  factory KnowledgeVocabularyList.fromJson(Map<String, dynamic> json) =>
      KnowledgeVocabularyList(
        items: (json['items'] as List<dynamic>? ?? const [])
            .map(
              (e) =>
                  KnowledgeVocabularyItem.fromJson(e as Map<String, dynamic>),
            )
            .toList(),
        page: json['page'] as int? ?? 1,
        pageSize: json['page_size'] as int? ?? 20,
        total: json['total'] as int? ?? 0,
      );

  bool get isEmpty => items.isEmpty;

  KnowledgeVocabularyList copyWith({
    List<KnowledgeVocabularyItem>? items,
    int? page,
    int? pageSize,
    int? total,
  }) => KnowledgeVocabularyList(
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

/// Offset envelope for `GET /v1/knowledge/items` (#22).
class KnowledgeItemReferenceList {
  const KnowledgeItemReferenceList({
    required this.items,
    required this.page,
    required this.pageSize,
    required this.total,
  });

  final List<KnowledgeItemReference> items;
  final int page;
  final int pageSize;
  final int total;

  factory KnowledgeItemReferenceList.fromJson(Map<String, dynamic> json) =>
      KnowledgeItemReferenceList(
        items: (json['items'] as List<dynamic>? ?? const [])
            .map(
              (e) => KnowledgeItemReference.fromJson(e as Map<String, dynamic>),
            )
            .toList(),
        page: json['page'] as int? ?? 1,
        pageSize: json['page_size'] as int? ?? 20,
        total: json['total'] as int? ?? 0,
      );

  bool get isEmpty => items.isEmpty;

  KnowledgeItemReferenceList copyWith({
    List<KnowledgeItemReference>? items,
    int? page,
    int? pageSize,
    int? total,
  }) => KnowledgeItemReferenceList(
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

/// One FFO foundation schema summary (`GET /v1/knowledge/ffo`).
class FfoSchemaSummary {
  const FfoSchemaSummary({required this.name, required this.title});

  final String name;
  final String title;

  FfoSchemaSummary copyWith({String? name, String? title}) =>
      FfoSchemaSummary(name: name ?? this.name, title: title ?? this.title);

  factory FfoSchemaSummary.fromJson(Map<String, dynamic> json) =>
      FfoSchemaSummary(
        name: json['name'] as String,
        title: json['title'] as String,
      );

  Map<String, dynamic> toJson() => {'name': name, 'title': title};
}

/// Offset envelope for `GET /v1/knowledge/ffo`.
class FfoSchemaList {
  const FfoSchemaList({
    required this.items,
    required this.page,
    required this.pageSize,
    required this.total,
  });

  final List<FfoSchemaSummary> items;
  final int page;
  final int pageSize;
  final int total;

  factory FfoSchemaList.fromJson(Map<String, dynamic> json) => FfoSchemaList(
    items: (json['items'] as List<dynamic>? ?? const [])
        .map((e) => FfoSchemaSummary.fromJson(e as Map<String, dynamic>))
        .toList(),
    page: json['page'] as int? ?? 1,
    pageSize: json['page_size'] as int? ?? 20,
    total: json['total'] as int? ?? 0,
  );

  bool get isEmpty => items.isEmpty;

  FfoSchemaList copyWith({
    List<FfoSchemaSummary>? items,
    int? page,
    int? pageSize,
    int? total,
  }) => FfoSchemaList(
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
