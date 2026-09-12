import 'dart:async';
import 'package:flutter/material.dart';
import 'app/app.dart';
import 'shared/crash_reporting/crash_reporting_service.dart';
import 'shared/crash_reporting/global_error_handler.dart';

void main() {
  runZonedGuarded(() {
    WidgetsFlutterBinding.ensureInitialized();
    GlobalErrorHandler.initialize();
    runApp(const FansivibeApp());
  }, (error, stack) {
    CrashReportingService.instance.reportError(
      error,
      stack,
      reason: 'runZonedGuarded uncaught async error',
      fatal: true,
    );
  });
}
