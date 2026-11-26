package com.fansivibe.fansivibe

import android.Manifest
import android.content.ContentValues
import android.content.pm.PackageManager
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File

class MainActivity : FlutterActivity() {
    companion object {
        private const val MEDIA_SAVE_CHANNEL = "com.fansivibe.fansivibe/media_save"
        private const val WRITE_STORAGE_REQUEST_CODE = 4401
    }

    private var pendingSaveArgs: Triple<ByteArray, String, String>? = null
    private var pendingSaveResult: MethodChannel.Result? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, MEDIA_SAVE_CHANNEL)
            .setMethodCallHandler { call, result ->
                if (call.method == "saveImageToGallery") {
                    val bytes = call.argument<ByteArray>("bytes")
                    val filename = call.argument<String>("filename") ?: "fansivibe_tryon.jpg"
                    val mimeType = call.argument<String>("mimeType") ?: "image/jpeg"
                    if (bytes == null || bytes.isEmpty()) {
                        result.success(
                            mapOf(
                                "status" to "failed",
                                "message" to "No image data provided."
                            )
                        )
                        return@setMethodCallHandler
                    }
                    handleSaveImage(bytes, filename, mimeType, result)
                } else {
                    result.notImplemented()
                }
            }
    }

    private fun handleSaveImage(
        bytes: ByteArray,
        filename: String,
        mimeType: String,
        result: MethodChannel.Result
    ) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            val granted = ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.WRITE_EXTERNAL_STORAGE
            ) == PackageManager.PERMISSION_GRANTED
            if (!granted) {
                if (pendingSaveResult != null) {
                    result.success(
                        mapOf(
                            "status" to "failed",
                            "message" to "Another save request is already awaiting permission."
                        )
                    )
                    return
                }
                pendingSaveArgs = Triple(bytes, filename, mimeType)
                pendingSaveResult = result
                ActivityCompat.requestPermissions(
                    this,
                    arrayOf(Manifest.permission.WRITE_EXTERNAL_STORAGE),
                    WRITE_STORAGE_REQUEST_CODE
                )
                return
            }
        }
        result.success(writeToMediaStore(bytes, filename, mimeType))
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == WRITE_STORAGE_REQUEST_CODE) {
            val pending = pendingSaveArgs
            val res = pendingSaveResult
            pendingSaveArgs = null
            pendingSaveResult = null
            if (res == null) return
            val granted = grantResults.isNotEmpty() &&
                grantResults[0] == PackageManager.PERMISSION_GRANTED
            if (!granted || pending == null) {
                val permanentlyDenied = !ActivityCompat.shouldShowRequestPermissionRationale(
                    this,
                    Manifest.permission.WRITE_EXTERNAL_STORAGE
                )
                res.success(
                    mapOf(
                        "status" to "permission_denied",
                        "permanentlyDenied" to permanentlyDenied,
                        "message" to if (permanentlyDenied) {
                            "Storage permission permanently denied. Enable storage access in Android App Settings to save photos."
                        } else {
                            "Storage permission is required to save photos on this Android version."
                        }
                    )
                )
                return
            }
            res.success(writeToMediaStore(pending.first, pending.second, pending.third))
        }
    }

    private fun writeToMediaStore(
        bytes: ByteArray,
        filename: String,
        mimeType: String
    ): Map<String, Any> {
        val resolver = applicationContext.contentResolver
        var insertedUri: android.net.Uri? = null
        return try {
            val values = ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, filename)
                put(MediaStore.Images.Media.MIME_TYPE, mimeType)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    put(
                        MediaStore.Images.Media.RELATIVE_PATH,
                        "${Environment.DIRECTORY_PICTURES}/Fansivibe"
                    )
                    put(MediaStore.Images.Media.IS_PENDING, 1)
                } else {
                    val pictures = Environment.getExternalStoragePublicDirectory(
                        Environment.DIRECTORY_PICTURES
                    )
                    val dir = File(pictures, "Fansivibe")
                    if (!dir.exists()) dir.mkdirs()
                    val file = File(dir, filename)
                    put(MediaStore.Images.Media.DATA, file.absolutePath)
                }
            }
            val uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
                ?: return mapOf(
                    "status" to "failed",
                    "message" to "Unable to create gallery entry."
                )
            insertedUri = uri
            val stream = resolver.openOutputStream(uri)
            if (stream == null) {
                resolver.delete(uri, null, null)
                return mapOf(
                    "status" to "failed",
                    "message" to "Unable to open gallery output stream."
                )
            }
            stream.use { out ->
                out.write(bytes)
                out.flush()
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val doneValues = ContentValues().apply {
                    put(MediaStore.Images.Media.IS_PENDING, 0)
                }
                resolver.update(uri, doneValues, null, null)
            }
            mapOf(
                "status" to "saved",
                "location" to "Pictures/Fansivibe/$filename",
                "message" to "Saved to Pictures/Fansivibe/$filename"
            )
        } catch (e: Exception) {
            if (insertedUri != null) {
                try {
                    resolver.delete(insertedUri, null, null)
                } catch (_: Exception) {
                }
            }
            mapOf(
                "status" to "failed",
                "message" to (e.message ?: "Failed to write image to gallery.")
            )
        }
    }
}
