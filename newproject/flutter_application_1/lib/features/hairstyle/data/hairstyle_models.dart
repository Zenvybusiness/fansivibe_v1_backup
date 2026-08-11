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

class AnalysisRunPage {
  const AnalysisRunPage({
    required this.items,
    required this.page,
    required this.pageSize,
    required this.total,
  });

  final List<AnalysisRun> items;
  final int page;
  final int pageSize;
  final int total;

  bool get isEmpty => items.isEmpty;

  factory AnalysisRunPage.fromJson(Map<String, dynamic> json) =>
      AnalysisRunPage(
        items: (json['items'] as List<dynamic>? ?? const [])
            .map((e) => AnalysisRun.fromJson(e as Map<String, dynamic>))
            .toList(),
        page: json['page'] as int? ?? 1,
        pageSize: json['page_size'] as int? ?? 0,
        total: json['total'] as int? ?? 0,
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
