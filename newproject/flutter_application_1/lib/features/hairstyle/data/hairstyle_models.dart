import 'hairstyle_mock_data.dart';

class AnalysisRun {
  const AnalysisRun({
    required this.runId,
    required this.runType,
    required this.status,
    this.createdAt,
    this.completedAt,
    this.result,
  });

  final String runId;
  final String runType;
  final String status;
  final DateTime? createdAt;
  final DateTime? completedAt;
  final Map<String, dynamic>? result;

  bool get isCompleted => status == 'completed';

  factory AnalysisRun.fromJson(Map<String, dynamic> json) => AnalysisRun(
    runId: json['run_id'] as String? ?? '',
    runType: json['run_type'] as String? ?? '',
    status: json['status'] as String? ?? 'pending',
    createdAt: DateTime.tryParse(json['created_at'] as String? ?? ''),
    completedAt: DateTime.tryParse(json['completed_at'] as String? ?? ''),
    result: json['result'] as Map<String, dynamic>?,
  );
}

class SavedLook {
  const SavedLook({
    required this.id,
    required this.lookId,
    required this.title,
    required this.createdAt,
  });

  final String id;
  final String lookId;
  final String title;
  final DateTime createdAt;

  factory SavedLook.fromJson(Map<String, dynamic> json) => SavedLook(
    id: json['id'] as String? ?? '',
    lookId: json['look_id'] as String? ?? '',
    title: json['title'] as String? ?? '',
    createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ??
        DateTime.fromMillisecondsSinceEpoch(0),
  );
}

HairstyleAnalysisResult hairstyleResultFromRun(AnalysisRun run) {
  final result = run.result;
  if (result != null) {
    return HairstyleAnalysisResult.fromRunResult(result);
  }
  return HairstyleAnalysisResult.mock;
}
