# Fansivibe Black Screen Root-Cause Report

Date: 2026-08-17
Scope: `newproject/flutter_application_1`

## 1. Black-screen symptom

`flutter run -d chrome` compiled and started the Dart app successfully
(`Starting application from main method in: org-dartlang-app:/web_entrypoint.dart`),
the VM debug service connected, but the browser displayed a **completely
black screen** — no FANSIVIBE wordmark, no mirror, no buttons, no text, no
bottom navigation. Only a flat dark surface was painted.

## 2. Browser console error

**None.** The browser console contained no exception, no red error, and no
stack trace. Captured console output (debug DDC load + bootstrapping):

```
Injecting <script> tag. Using callback.
DDC is about to load 677/677 scripts with pool size = 1000
Starting application from main method in: org-dartlang-app:/web_entrypoint.dart.
```

No `Runtime.exceptionThrown`, no `FlutterError`, no app-level error.

## 3. Terminal output

```
WARNING: Falling back to CPU-only rendering. Reason:
webGLVersion is -1
```

plus the normal Flutter web-server debug output. This warning was **not** the
root cause (see §6).

## 4. First failing stack frame

There is no stack trace because the app **never threw**. The failure was a
silent logic bug: an animation controller was created but never started, so
every frame rendered the widget tree at opacity 0.

- File: `lib/features/onboarding/presentation/screens/entry_screen.dart`
- Class: `_EntryScreenState`
- Line: `initState()` — `_controller` created (line 34) but `forward()` never called.

## 5. Root cause

`EntryScreen` builds its entire content inside `_Reveal` wrappers whose
`Opacity(opacity: anim.value)` and `Transform.translate` are driven by
`_controller` (a 1200 ms `AnimationController`) through staggered
`Interval` animations (`_buildAnim(0.0, 0.3)` … `_buildAnim(0.85, 1.0)`).

At animation value `0`, every `_Reveal` renders `Opacity(0)` — invisible
content. The entrance animation was never started:

- `_controller` is created in `initState()` but **`_controller.forward()` is
  never called**, so `_controller.value` stays `0` forever.
- The separate breathing glow (`_breathController..repeat(reverse: true)`)
  runs, but it only modulates a subtle radial gradient **inside** the mirror,
  which is itself wrapped in an `_Reveal` at opacity 0 — invisible too.

The result: the whole widget subtree exists in the tree and lays out, but
every leaf is painted at alpha 0. Only the `Scaffold` background
(`FansivibeColors.surface`) paints — a uniform dark screen.

### Regression origin

`git log` on `entry_screen.dart`:

- `1df7455` (entry screen redesign): `_controller.forward()` present.
- `bcc8141`: `_controller.forward()` present.
- **`23ca8de`**: single line `-    _controller.forward();` removed.
- `9db3196` (the `_breath` LateInitializationError fix): did not restore it.

The `_breath` fix (9db3196) was correct and necessary, but it only addressed
the earlier `LateInitializationError`. The black screen is a **separate**
regression from `23ca8de` that the widget tests never caught because
`find.text(...)` matches widgets regardless of their opacity.

## 6. Why the WebGL warning is not related

The warning `webGLVersion is -1` / CPU-only rendering describes the Chrome VM
environment (VirtualBox, no hardware GPU/WebGL). It is unrelated because:

- Reproducing the app in a headless browser **with working software WebGL**
  (SwiftShader) still produced the exact uniform black screen — same symptom
  as the user's environment.
- The failure is deterministic Dart logic (controller never started), not a
  rasterizer/backend failure.
- After the fix, the same screens render content normally.

## 7. Startup chain

```
main()                     lib/main.dart
  runApp(const FansivibeApp())
    FansivibeApp           lib/app/app.dart
      MaterialApp.router(routerConfig: appRouter)
        appRouter          lib/app/router/app_router.dart
          GoRouter(initialLocation: '/entry', routes: appRoutes)
            /entry -> EntryScreen      (StatefulShellRoute NOT the initial route)
              EntryScreen.initState()  ← _controller.forward() missing
```

## 8. File changed

- `newproject/flutter_application_1/lib/features/onboarding/presentation/screens/entry_screen.dart`
  — one line added in `initState()`.
- `newproject/flutter_application_1/test/entry_screen_test.dart` — new
  regression test asserting the entrance animation starts so content
  becomes visible (opacity 0 → 1).

## 9. Exact fix

In `_EntryScreenState.initState()`, after the `_buildAnim(...)` fields are
wired (before `_checkReturningUser()`):

```dart
_controller.forward();
```

This restores the intended 1200 ms staggered entrance animation exactly as it
existed before `23ca8de`. No durations, curves, intervals, layout, colors,
navigation, or architecture were changed. The `_breath` animation is untouched.

## 10. flutter analyze

`flutter analyze` → **0 errors, 0 warnings, 36 infos** (all pre-existing
lint-level infos in unrelated files). No issues in `entry_screen.dart` or
`entry_screen_test.dart`.

## 11. Flutter tests

- `flutter test test/entry_screen_test.dart` → **3 passed** (incl. new
  "entrance animation starts so content becomes visible" regression test).
- `flutter test` full suite → **390 passed / 0 failed** (389 baseline + 1 new).

## 12. Chrome runtime

Validated the exact `flutter run -d chrome` command (Brave in this VM):

- Compiles, launches Brave, VM debug service connects,
  `Starting application from main method in: org-dartlang-app:/web_entrypoint.dart.`
- First-boot frame of the real flutter-run browser at `/entry` renders the
  Fansivibe EntryScreen (wordmark, mirror, CTAs): non-black pixel fraction
  0% → 6.07%, 50 distinct colors, bright text/button pixels present.
- No exceptions, no errors in the tool log; only the expected env warning
  (WebGL/CPU) appears.

Supplementary rendering verification at the same window size
(`flutter run -d web-server` + headless CDP, fresh loads — the flutter-debug
web service only accepts one attach, so reloads of a chrome-device run are not
supported; fresh loads are the reliable harness):

| check        | non-black frac | result       |
|--------------|----------------|--------------|
| /entry        | 0.051          | content      |
| /home         | 0.344          | content      |
| /discover     | 0.264          | content      |
| /stylist      | 0.303          | content      |
| /wardrobe     | 0.279          | content      |
| /profile      | 0.306          | content      |

## 13. Browser console

**Clean.** No `Runtime.exceptionThrown`, no console errors, no Flutter errors,
in every validated run after the fix.

## 14. Navigation validation

Each shell branch deep-linked in a running app at the real VM window size
renders with content (see §12 table) — no black screen, no crash. Entry →
home tab switch (EntryScreen "Sign In" → `context.goNamed(home)`) routes into
the shell; the shell rendered with bottom NavigationBar (bright icon pixels in
the bottom-nav region). No route redesign; router/shell/navigation code was
not modified.

## 15. UI regression

Only the single restored call `_controller.forward()` in `EntryScreen`
`initState()`. Layout, colors, typography, spacing, radius, shadows, card
65/35 rule, Digital Atelier design system, animations (durations/curves/
intervals unchanged), navigation, and all other screens are untouched.

## 16. Remaining limitations

- The `webGLVersion is -1` CPU-rendering warning remains in this VirtualBox
  environment; it is cosmetic for rendering (verified not to block the UI).
- The flutter-debug web service (chrome device) accepts a single debug attach,
  so repeated reloads of a `flutter run -d chrome` session are flaky in
  headless automation; fresh loads via `flutter run -d web-server` served as
  the multi-route harness. The first boot of `flutter run -d chrome` itself
  rendered the app cleanly.
- The 36 pre-existing analyzer infos are unrelated lint-level notes, out of
  scope.
- Browser-based verification used a headless Chrome/CDP harness (the app was
  also verified through the normal web compile path); the same rendering path
  applies to the user's `flutter run -d chrome`.

---

FINAL: REPAIRED
