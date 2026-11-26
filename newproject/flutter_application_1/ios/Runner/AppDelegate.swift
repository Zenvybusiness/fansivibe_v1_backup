import Flutter
import Photos
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate {
  private let mediaSaveChannelName = "com.fansivibe.fansivibe/media_save"

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    GeneratedPluginRegistrant.register(with: self)

    if let controller = window?.rootViewController as? FlutterViewController {
      let channel = FlutterMethodChannel(
        name: mediaSaveChannelName,
        binaryMessenger: controller.binaryMessenger
      )
      channel.setMethodCallHandler { [weak self] call, result in
        guard call.method == "saveImageToGallery" else {
          result(FlutterMethodNotImplemented)
          return
        }
        guard
          let args = call.arguments as? [String: Any],
          let typedData = args["bytes"] as? FlutterStandardTypedData,
          !typedData.data.isEmpty
        else {
          result([
            "status": "failed",
            "message": "No image data provided."
          ])
          return
        }
        self?.saveImageToPhotoLibrary(data: typedData.data, result: result)
      }
    }

    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  private func saveImageToPhotoLibrary(data: Data, result: @escaping FlutterResult) {
    let handleStatus: (PHAuthorizationStatus) -> Void = { status in
      let isAuthorized: Bool
      if #available(iOS 14, *) {
        isAuthorized = (status == .authorized || status == .limited)
      } else {
        isAuthorized = (status == .authorized)
      }

      guard isAuthorized else {
        let permanentlyDenied = (status == .denied || status == .restricted)
        DispatchQueue.main.async {
          result([
            "status": "permission_denied",
            "permanentlyDenied": permanentlyDenied,
            "message": permanentlyDenied
              ? "Photo library add permission is denied. Enable Photos access in iOS Settings to save results."
              : "Photo library permission is required to save try-on results."
          ])
        }
        return
      }

      PHPhotoLibrary.shared().performChanges({
        let request = PHAssetCreationRequest.forAsset()
        request.addResource(with: .photo, data: data, options: nil)
      }) { success, error in
        DispatchQueue.main.async {
          if success {
            result([
              "status": "saved",
              "location": "Photos",
              "message": "Saved to Photos."
            ])
          } else {
            result([
              "status": "failed",
              "message": error?.localizedDescription ?? "Could not save image to Photos."
            ])
          }
        }
      }
    }

    if #available(iOS 14, *) {
      PHPhotoLibrary.requestAuthorization(for: .addOnly, handler: handleStatus)
    } else {
      PHPhotoLibrary.requestAuthorization(handleStatus)
    }
  }
}
