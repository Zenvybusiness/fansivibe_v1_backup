import 'package:flutter/widgets.dart';

/// Explicit camera lifecycle states:
/// OFF → OPENING → ACTIVE → STOPPING → OFF.
enum CameraLifecycleState {
  off,
  opening,
  active,
  stopping,
}

/// Lightweight coordinator that allows camera screens to register their shutdown
/// callbacks so that tab switches, route covering, and backgrounding immediately
/// stop any active hardware camera sessions.
class CameraLifecycleCoordinator {
  CameraLifecycleCoordinator._();

  static final Set<void Function()> _listeners = <void Function()>{};

  /// Registers an active camera shutdown listener.
  static void register(void Function() onStopRequested) {
    _listeners.add(onStopRequested);
  }

  /// Unregisters the shutdown listener when the screen is disposed.
  static void unregister(void Function() onStopRequested) {
    _listeners.remove(onStopRequested);
  }

  /// Requests all active camera sessions to immediately stop streaming and release hardware.
  static void stopAll() {
    for (final listener in List<void Function()>.from(_listeners)) {
      try {
        listener();
      } catch (e) {
        debugPrint('Error in camera stop listener: $e');
      }
    }
  }
}

/// NavigatorObserver that triggers [CameraLifecycleCoordinator.stopAll] whenever
/// a new route is pushed or replaced on top of a camera route.
class CameraRouteObserver extends NavigatorObserver {
  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    super.didPush(route, previousRoute);
    CameraLifecycleCoordinator.stopAll();
  }

  @override
  void didReplace({Route<dynamic>? newRoute, Route<dynamic>? oldRoute}) {
    super.didReplace(newRoute: newRoute, oldRoute: oldRoute);
    CameraLifecycleCoordinator.stopAll();
  }
}

final CameraRouteObserver cameraRouteObserver = CameraRouteObserver();
