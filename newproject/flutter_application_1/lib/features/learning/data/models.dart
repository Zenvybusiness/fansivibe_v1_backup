import 'dart:convert';

/// A wardrobe item in the user's evolving model.
///
/// [imageBase64] carries the exact photo the user took/selected for the
/// item (base64 of the bounded photo bytes, see the wardrobe photo
/// helper), or null for manual entries without a photo. Additive and
/// optional: older persisted rows without the key still parse (null),
/// and imageless entries keep the existing empty-image UI.
class WardrobeEntry {
  const WardrobeEntry({
    required this.id,
    required this.name,
    required this.category,
    required this.color,
    this.material,
    this.isFavorite = false,
    this.fit,
    this.fitConfidence,
    this.sourceRunId,
    this.candidateId,
    this.extractionConfidence,
    this.imageBase64,
    this.isAuthenticatedMirror = false,
    this.createdAt,
    this.updatedAt,
  });

  static final RegExp _numericSeedIdPattern = RegExp(r'^\d+$');

  final String id;
  final String name;
  final String category;
  final String color;
  final String? material;
  final bool isFavorite;
  final String? fit;
  final double? fitConfidence;
  final String? sourceRunId;
  final String? candidateId;
  final double? extractionConfidence;

  /// Base64 photo bytes for the item, or null when it has no photo.
  final String? imageBase64;

  /// True when this entry is an on-device mirror of an authenticated
  /// server-backed wardrobe item (never exposed to Guest mode or other users).
  final bool isAuthenticatedMirror;

  final DateTime? createdAt;
  final DateTime? updatedAt;

  /// Whether this entry is a genuine device-local guest item.
  ///
  /// Genuine guest items use `local-*` IDs (or numeric seed IDs in test
  /// fixtures) and are never marked [isAuthenticatedMirror]. Server UUIDs and
  /// authenticated mirrors return false.
  bool get isGuestLocal =>
      !isAuthenticatedMirror &&
      (id.startsWith('local-') || _numericSeedIdPattern.hasMatch(id));

  WardrobeEntry copyWith({
    String? name,
    String? category,
    String? color,
    String? material,
    bool clearMaterial = false,
    bool? isFavorite,
    String? fit,
    bool clearFit = false,
    double? fitConfidence,
    String? sourceRunId,
    String? candidateId,
    double? extractionConfidence,
    String? imageBase64,
    bool clearImageBase64 = false,
    bool? isAuthenticatedMirror,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) => WardrobeEntry(
    id: id,
    name: name ?? this.name,
    category: category ?? this.category,
    color: color ?? this.color,
    material: clearMaterial ? null : (material ?? this.material),
    isFavorite: isFavorite ?? this.isFavorite,
    fit: clearFit ? null : (fit ?? this.fit),
    fitConfidence: fitConfidence ?? this.fitConfidence,
    sourceRunId: sourceRunId ?? this.sourceRunId,
    candidateId: candidateId ?? this.candidateId,
    extractionConfidence: extractionConfidence ?? this.extractionConfidence,
    imageBase64: clearImageBase64 ? null : (imageBase64 ?? this.imageBase64),
    isAuthenticatedMirror: isAuthenticatedMirror ?? this.isAuthenticatedMirror,
    createdAt: createdAt ?? this.createdAt,
    updatedAt: updatedAt ?? this.updatedAt,
  );

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'category': category,
    'color': color,
    'material': material,
    'isFavorite': isFavorite,
    if (fit != null) 'fit': fit,
    if (fitConfidence != null) 'fitConfidence': fitConfidence,
    if (sourceRunId != null) 'sourceRunId': sourceRunId,
    if (candidateId != null) 'candidateId': candidateId,
    if (extractionConfidence != null)
      'extractionConfidence': extractionConfidence,
    if (imageBase64 != null) 'imageBase64': imageBase64,
    if (isAuthenticatedMirror) 'isAuthenticatedMirror': true,
    if (createdAt != null) 'createdAt': createdAt!.toIso8601String(),
    if (updatedAt != null) 'updatedAt': updatedAt!.toIso8601String(),
  };

  factory WardrobeEntry.fromJson(Map<String, dynamic> json) => WardrobeEntry(
    id: json['id'] as String,
    name: json['name'] as String,
    category: json['category'] as String,
    color: json['color'] as String,
    material: json['material'] as String?,
    isFavorite: json['isFavorite'] as bool? ?? false,
    fit: json['fit'] as String?,
    fitConfidence: (json['fitConfidence'] as num?)?.toDouble(),
    sourceRunId: json['sourceRunId'] as String?,
    candidateId: json['candidateId'] as String?,
    extractionConfidence: (json['extractionConfidence'] as num?)?.toDouble(),
    imageBase64: json['imageBase64'] as String?,
    isAuthenticatedMirror: json['isAuthenticatedMirror'] as bool? ?? false,
    createdAt: json['createdAt'] != null
        ? DateTime.tryParse(json['createdAt'] as String)
        : null,
    updatedAt: json['updatedAt'] != null
        ? DateTime.tryParse(json['updatedAt'] as String)
        : null,
  );
}

/// Face/analysis attributes learned from onboarding and scans.
class FaceProfile {
  const FaceProfile({
    this.faceShape,
    this.skinTone,
    this.bodyType,
    this.hairType,
    this.hairDensity,
    this.styleType,
  });

  final String? faceShape;
  final String? skinTone;
  final String? bodyType;
  final String? hairType;
  final String? hairDensity;
  final String? styleType;

  Map<String, dynamic> toJson() => {
    'faceShape': faceShape,
    'skinTone': skinTone,
    'bodyType': bodyType,
    'hairType': hairType,
    'hairDensity': hairDensity,
    'styleType': styleType,
  };

  factory FaceProfile.fromJson(Map<String, dynamic> json) => FaceProfile(
    faceShape: json['faceShape'] as String?,
    skinTone: json['skinTone'] as String?,
    bodyType: json['bodyType'] as String?,
    hairType: json['hairType'] as String?,
    hairDensity: json['hairDensity'] as String?,
    styleType: json['styleType'] as String?,
  );

  FaceProfile copyWith({
    String? faceShape,
    String? skinTone,
    String? bodyType,
    String? hairType,
    String? hairDensity,
    String? styleType,
  }) {
    return FaceProfile(
      faceShape: faceShape ?? this.faceShape,
      skinTone: skinTone ?? this.skinTone,
      bodyType: bodyType ?? this.bodyType,
      hairType: hairType ?? this.hairType,
      hairDensity: hairDensity ?? this.hairDensity,
      styleType: styleType ?? this.styleType,
    );
  }
}

/// A typed interaction signal. Signals accumulate over time and drive the
/// gradual learning: every add/save/scan/feedback the user makes is recorded.
class LearningSignal {
  const LearningSignal({
    required this.type,
    required this.label,
    this.timestamp,
  });

  final String type;
  final String label;
  final int? timestamp;

  Map<String, dynamic> toJson() => {
    'type': type,
    'label': label,
    'timestamp': timestamp ?? DateTime.now().millisecondsSinceEpoch,
  };

  factory LearningSignal.fromJson(Map<String, dynamic> json) => LearningSignal(
    type: json['type'] as String,
    label: json['label'] as String,
    timestamp: json['timestamp'] as int?,
  );
}

/// The evolving on-device user model. This is the source of truth for
/// personalization and is sent (as a snapshot) to the AI backend.
class UserModel {
  UserModel({
    required this.wardrobe,
    this.face,
    this.styleType,
    this.savedLooks = const [],
    this.preferredOccasions = const [],
    this.signals = const [],
  });

  final List<WardrobeEntry> wardrobe;
  final FaceProfile? face;
  final String? styleType;
  final List<String> savedLooks;
  final List<String> preferredOccasions;
  final List<LearningSignal> signals;

  UserModel copyWith({
    List<WardrobeEntry>? wardrobe,
    FaceProfile? face,
    String? styleType,
    List<String>? savedLooks,
    List<String>? preferredOccasions,
    List<LearningSignal>? signals,
  }) => UserModel(
    wardrobe: wardrobe ?? this.wardrobe,
    face: face ?? this.face,
    styleType: styleType ?? this.styleType,
    savedLooks: savedLooks ?? this.savedLooks,
    preferredOccasions: preferredOccasions ?? this.preferredOccasions,
    signals: signals ?? this.signals,
  );

  Map<String, dynamic> toJson() => {
    'wardrobe': wardrobe.map((e) => e.toJson()).toList(),
    'face': face?.toJson(),
    'styleType': styleType,
    'savedLooks': savedLooks,
    'preferredOccasions': preferredOccasions,
    'signals': signals.map((e) => e.toJson()).toList(),
  };

  static UserModel fromJson(Map<String, dynamic> json) => UserModel(
    wardrobe: (json['wardrobe'] as List<dynamic>? ?? [])
        .map((e) => WardrobeEntry.fromJson(e as Map<String, dynamic>))
        .toList(),
    face: json['face'] == null
        ? null
        : FaceProfile.fromJson(json['face'] as Map<String, dynamic>),
    styleType: json['styleType'] as String?,
    savedLooks: (json['savedLooks'] as List<dynamic>? ?? [])
        .map((e) => e as String)
        .toList(),
    preferredOccasions: (json['preferredOccasions'] as List<dynamic>? ?? [])
        .map((e) => e as String)
        .toList(),
    signals: (json['signals'] as List<dynamic>? ?? [])
        .map((e) => LearningSignal.fromJson(e as Map<String, dynamic>))
        .toList(),
  );

  String encode() => jsonEncode(toJson());

  static UserModel decode(String source) =>
      fromJson(jsonDecode(source) as Map<String, dynamic>);
}
