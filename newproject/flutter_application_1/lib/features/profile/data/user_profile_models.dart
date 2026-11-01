import 'package:flutter/foundation.dart';

/// Field-level provenance metadata matching Batch 1A architecture.
@immutable
class UserAttributeProvenance {
  final dynamic value;
  final String source;
  final String? sourceRunId;
  final double? confidence;
  final String? observedAt;
  final bool confirmedByUser;
  final String? confirmedAt;

  const UserAttributeProvenance({
    required this.value,
    required this.source,
    this.sourceRunId,
    this.confidence,
    this.observedAt,
    this.confirmedByUser = false,
    this.confirmedAt,
  });

  factory UserAttributeProvenance.fromJson(Map<String, dynamic> json) {
    return UserAttributeProvenance(
      value: json['value'],
      source: json['source'] as String? ?? 'unknown',
      sourceRunId: json['source_run_id'] as String?,
      confidence: (json['confidence'] as num?)?.toDouble(),
      observedAt: json['observed_at'] as String?,
      confirmedByUser: json['confirmed_by_user'] as bool? ?? false,
      confirmedAt: json['confirmed_at'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
    'value': value,
    'source': source,
    if (sourceRunId != null) 'source_run_id': sourceRunId,
    if (confidence != null) 'confidence': confidence,
    if (observedAt != null) 'observed_at': observedAt,
    'confirmed_by_user': confirmedByUser,
    if (confirmedAt != null) 'confirmed_at': confirmedAt,
  };
}

/// Typed representation of the user's style profile (biometrics and archetype).
@immutable
class UserStyleProfile {
  final String? faceShape;
  final String? skinTone;
  final String? bodyType;
  final String? styleType;
  final String? sourceRunId;
  final Map<String, dynamic> extra;

  const UserStyleProfile({
    this.faceShape,
    this.skinTone,
    this.bodyType,
    this.styleType,
    this.sourceRunId,
    this.extra = const {},
  });

  factory UserStyleProfile.fromJson(Map<String, dynamic> json) {
    return UserStyleProfile(
      faceShape:
          json['faceShape'] as String? ?? json['face_shape'] as String?,
      skinTone: json['skinTone'] as String? ?? json['skin_tone'] as String?,
      bodyType: json['bodyType'] as String? ?? json['body_type'] as String?,
      styleType: json['styleType'] as String? ?? json['style_type'] as String?,
      sourceRunId:
          json['sourceRunId'] as String? ?? json['source_run_id'] as String?,
      extra: Map<String, dynamic>.from(json),
    );
  }

  Map<String, dynamic> toJson() => {
    if (faceShape != null) 'faceShape': faceShape,
    if (skinTone != null) 'skinTone': skinTone,
    if (bodyType != null) 'bodyType': bodyType,
    if (styleType != null) 'styleType': styleType,
    if (sourceRunId != null) 'sourceRunId': sourceRunId,
    ...extra,
  };

  UserStyleProfile copyWith({
    String? faceShape,
    String? skinTone,
    String? bodyType,
    String? styleType,
    String? sourceRunId,
    Map<String, dynamic>? extra,
  }) {
    return UserStyleProfile(
      faceShape: faceShape ?? this.faceShape,
      skinTone: skinTone ?? this.skinTone,
      bodyType: bodyType ?? this.bodyType,
      styleType: styleType ?? this.styleType,
      sourceRunId: sourceRunId ?? this.sourceRunId,
      extra: extra ?? this.extra,
    );
  }

  /// Whether all 4 primary style biometrics/archetypes are populated.
  bool get isAssessed =>
      faceShape != null &&
      faceShape!.trim().isNotEmpty &&
      faceShape!.toLowerCase() != 'unknown' &&
      faceShape!.toLowerCase() != 'pending assessment' &&
      skinTone != null &&
      skinTone!.trim().isNotEmpty &&
      bodyType != null &&
      bodyType!.trim().isNotEmpty &&
      styleType != null &&
      styleType!.trim().isNotEmpty;

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is UserStyleProfile &&
        other.faceShape == faceShape &&
        other.skinTone == skinTone &&
        other.bodyType == bodyType &&
        other.styleType == styleType &&
        other.sourceRunId == sourceRunId;
  }

  @override
  int get hashCode => Object.hash(
    faceShape,
    skinTone,
    bodyType,
    styleType,
    sourceRunId,
  );
}

/// The authoritative User Profile model returned by `GET /v1/users/me`.
@immutable
class UserProfile {
  final String displayName;
  final UserStyleProfile styleProfile;
  final Map<String, dynamic> preferences;
  final Map<String, dynamic> settings;
  final Map<String, dynamic> flags;
  final int version;
  final Map<String, dynamic>? memorySummary;

  const UserProfile({
    required this.displayName,
    required this.styleProfile,
    this.preferences = const {},
    this.settings = const {},
    this.flags = const {},
    required this.version,
    this.memorySummary,
  });

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      displayName:
          json['displayName'] as String? ??
          json['display_name'] as String? ??
          '',
      styleProfile: json['styleProfile'] != null
          ? UserStyleProfile.fromJson(
              Map<String, dynamic>.from(json['styleProfile'] as Map),
            )
          : json['style_profile'] != null
              ? UserStyleProfile.fromJson(
                  Map<String, dynamic>.from(json['style_profile'] as Map),
                )
              : const UserStyleProfile(),
      preferences: Map<String, dynamic>.from(
        json['preferences'] as Map? ?? const {},
      ),
      settings: Map<String, dynamic>.from(
        json['settings'] as Map? ?? const {},
      ),
      flags: Map<String, dynamic>.from(
        json['flags'] as Map? ?? const {},
      ),
      version: json['version'] as int? ?? 1,
      memorySummary: json['memorySummary'] != null
          ? Map<String, dynamic>.from(json['memorySummary'] as Map)
          : json['memory_summary'] != null
              ? Map<String, dynamic>.from(json['memory_summary'] as Map)
              : null,
    );
  }

  Map<String, dynamic> toJson() => {
    'displayName': displayName,
    'styleProfile': styleProfile.toJson(),
    'preferences': preferences,
    'settings': settings,
    'flags': flags,
    'version': version,
    if (memorySummary != null) 'memorySummary': memorySummary,
  };

  UserProfile copyWith({
    String? displayName,
    UserStyleProfile? styleProfile,
    Map<String, dynamic>? preferences,
    Map<String, dynamic>? settings,
    Map<String, dynamic>? flags,
    int? version,
    Map<String, dynamic>? memorySummary,
  }) {
    return UserProfile(
      displayName: displayName ?? this.displayName,
      styleProfile: styleProfile ?? this.styleProfile,
      preferences: preferences ?? this.preferences,
      settings: settings ?? this.settings,
      flags: flags ?? this.flags,
      version: version ?? this.version,
      memorySummary: memorySummary ?? this.memorySummary,
    );
  }

  /// Empty profile representation for uninitialized or blank state.
  static const empty = UserProfile(
    displayName: '',
    styleProfile: UserStyleProfile(),
    version: 1,
  );

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is UserProfile &&
        other.displayName == displayName &&
        other.styleProfile == styleProfile &&
        other.version == version;
  }

  @override
  int get hashCode => Object.hash(displayName, styleProfile, version);
}
