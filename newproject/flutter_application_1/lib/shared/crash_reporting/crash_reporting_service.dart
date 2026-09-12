import 'package:flutter/foundation.dart';
import 'error_sanitizer.dart';

/// Represents a captured, sanitized crash or error report.
@immutable
class CrashReport {
  const CrashReport({
    required this.timestamp,
    required this.error,
    this.stackTrace,
    this.reason,
    required this.metadata,
    required this.fatal,
  });

  final DateTime timestamp;
  final String error;
  final String? stackTrace;
  final String? reason;
  final Map<String, dynamic> metadata;
  final bool fatal;

  @override
  String toString() =>
      'CrashReport(error: $error, reason: $reason, fatal: $fatal, metadata: $metadata)';
}

/// Sink interface for external crash reporting providers (e.g. Sentry, Crashlytics).
abstract class CrashReportSink {
  void recordError(CrashReport report);
}

/// Central crash and error reporting service abstraction for FansiVibe.
///
/// Dispatches sanitized error reports to registered sinks and maintains a
/// bounded in-memory log of recent reports for local diagnostics and testing.
class CrashReportingService {
  CrashReportingService._internal();

  static final CrashReportingService _instance = CrashReportingService._internal();
  static CrashReportingService get instance => _instance;

  factory CrashReportingService() => _instance;

  static const int maxRecentReports = 50;
  final List<CrashReportSink> _sinks = [];
  final List<CrashReport> _recentReports = [];

  /// Registered external sinks.
  List<CrashReportSink> get sinks => List.unmodifiable(_sinks);

  /// Bounded collection of recent sanitized reports.
  List<CrashReport> get recentReports => List.unmodifiable(_recentReports);

  /// Registers a new reporting sink.
  void addSink(CrashReportSink sink) {
    if (!_sinks.contains(sink)) {
      _sinks.add(sink);
    }
  }

  /// Removes an existing reporting sink.
  void removeSink(CrashReportSink sink) {
    _sinks.remove(sink);
  }

  /// Clears all sinks (useful for test isolation).
  void clearSinks() {
    _sinks.clear();
  }

  /// Clears stored recent reports (useful for test isolation).
  void clearReports() {
    _recentReports.clear();
  }

  /// Captures and reports an unexpected error.
  ///
  /// All metadata and strings are sanitized prior to dispatching to ensure
  /// secrets, passwords, tokens, image bytes, and sensitive user data
  /// are never logged or exported.
  void reportError(
    Object error,
    StackTrace? stackTrace, {
    String? reason,
    Map<String, dynamic>? metadata,
    bool fatal = false,
  }) {
    try {
      final sanitizedError = ErrorSanitizer.sanitizeString(error.toString());
      final sanitizedStack =
          stackTrace != null ? ErrorSanitizer.sanitizeString(stackTrace.toString()) : null;
      final sanitizedReason =
          reason != null ? ErrorSanitizer.sanitizeString(reason) : null;
      final sanitizedMetadata = ErrorSanitizer.sanitizeMap(metadata);

      final report = CrashReport(
        timestamp: DateTime.now().toUtc(),
        error: sanitizedError,
        stackTrace: sanitizedStack,
        reason: sanitizedReason,
        metadata: sanitizedMetadata,
        fatal: fatal,
      );

      _recentReports.add(report);
      if (_recentReports.length > maxRecentReports) {
        _recentReports.removeAt(0);
      }

      for (final sink in _sinks) {
        try {
          sink.recordError(report);
        } catch (_) {
          // Sinks must never cause secondary failures.
        }
      }

      if (kDebugMode) {
        debugPrint(
          '[CrashReportingService] Captured ${fatal ? 'fatal ' : ''}error: '
          '${report.error}${report.reason != null ? ' (reason: ${report.reason})' : ''}',
        );
      }
    } catch (_) {
      // Global error reporting must be completely safe and never throw.
    }
  }

  /// Captures a Flutter framework error from [FlutterErrorDetails].
  void reportFlutterError(FlutterErrorDetails details) {
    final metadata = <String, dynamic>{
      'library': details.library ?? 'Flutter framework',
    };
    if (details.context != null) {
      metadata['context'] = details.context.toString();
    }

    reportError(
      details.exception,
      details.stack,
      reason: details.context?.toString() ?? 'FlutterError.onError',
      metadata: metadata,
      fatal: false,
    );
  }
}
