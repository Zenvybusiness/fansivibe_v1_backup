import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'crash_reporting_service.dart';
import 'global_error_widget.dart';

/// Configures global error boundaries for the Flutter framework and platform.
abstract final class GlobalErrorHandler {
  GlobalErrorHandler._();

  static FlutterExceptionHandler? _originalFlutterOnError;
  static ErrorWidgetBuilder? _originalErrorWidgetBuilder;
  static bool _initialized = false;

  /// Whether the global error handler has been initialized.
  static bool get isInitialized => _initialized;

  /// Initializes top-level framework error handlers, platform error handlers,
  /// and the user-facing [ErrorWidget.builder].
  static void initialize({bool overrideErrorWidget = true}) {
    if (_initialized) return;

    _originalFlutterOnError = FlutterError.onError;
    _originalErrorWidgetBuilder = ErrorWidget.builder;

    // 1. Flutter framework errors (e.g. layout errors, build errors)
    FlutterError.onError = (FlutterErrorDetails details) {
      CrashReportingService.instance.reportFlutterError(details);

      if (kDebugMode) {
        // Preserve default developer console presentation in debug mode.
        _originalFlutterOnError?.call(details);
      }
    };

    // 2. Uncaught asynchronous errors from the platform dispatcher
    PlatformDispatcher.instance.onError = (Object error, StackTrace stack) {
      CrashReportingService.instance.reportError(
        error,
        stack,
        reason: 'PlatformDispatcher.onError',
        fatal: true,
      );
      // Return true to prevent error from bubbling and crashing the platform host.
      return true;
    };

    // 3. User-facing error widget for rendering failures
    if (overrideErrorWidget) {
      ErrorWidget.builder = (FlutterErrorDetails details) {
        return GlobalErrorWidget(details: details);
      };
    }

    _initialized = true;
  }

  /// Restores default handlers (primarily for unit test teardown).
  static void reset() {
    if (!_initialized) return;

    FlutterError.onError = _originalFlutterOnError;
    if (_originalErrorWidgetBuilder != null) {
      ErrorWidget.builder = _originalErrorWidgetBuilder!;
    }
    PlatformDispatcher.instance.onError = null;

    _initialized = false;
  }
}
