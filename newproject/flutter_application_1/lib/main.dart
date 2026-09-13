import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'app/app.dart';
import 'core/config/app_config.dart';
import 'shared/crash_reporting/crash_reporting_service.dart';
import 'shared/crash_reporting/global_error_handler.dart';
import 'shared/utils/local_storage.dart';

void main() {
  runZonedGuarded(() async {
    WidgetsFlutterBinding.ensureInitialized();
    GlobalErrorHandler.initialize();
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
    // P0-4: fail fast with a clear error when a production build is
    // misconfigured (missing/localhost/non-HTTPS) instead of silently
    // issuing unusable network requests. Development keeps working.
    AppConfig.validateOrThrow();
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

