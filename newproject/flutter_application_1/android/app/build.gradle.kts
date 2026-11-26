import java.io.FileInputStream
import java.util.Properties

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties()
if (keystorePropertiesFile.exists()) {
    FileInputStream(keystorePropertiesFile).use { stream ->
        keystoreProperties.load(stream)
    }
}

android {
    namespace = "com.fansivibe.fansivibe"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_11.toString()
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.fansivibe.fansivibe"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    fun isTruthyGradleProperty(name: String): Boolean {
        if (!project.hasProperty(name)) return false
        val value = project.property(name)?.toString()?.trim() ?: ""
        return !value.equals("false", ignoreCase = true)
    }

    val isStrictReleaseSigning = isTruthyGradleProperty("requireReleaseSigning") ||
        System.getenv("REQUIRE_RELEASE_SIGNING") == "true" ||
        System.getenv("CI") == "true" ||
        isTruthyGradleProperty("prodRelease")

    val envKeyAlias = System.getenv("FANSIVIBE_ANDROID_KEY_ALIAS")
        ?: System.getenv("ANDROID_KEY_ALIAS")
    val envKeyPassword = System.getenv("FANSIVIBE_ANDROID_KEY_PASSWORD")
        ?: System.getenv("ANDROID_KEY_PASSWORD")
    val envStorePassword = System.getenv("FANSIVIBE_ANDROID_KEYSTORE_PASSWORD")
        ?: System.getenv("ANDROID_KEYSTORE_PASSWORD")
    val envStoreFile = System.getenv("FANSIVIBE_ANDROID_KEYSTORE_PATH")
        ?: System.getenv("ANDROID_KEYSTORE_PATH")

    val resolvedKeyAlias = (keystoreProperties["keyAlias"] as String?)?.trim()?.takeIf { it.isNotEmpty() }
        ?: envKeyAlias?.trim()?.takeIf { it.isNotEmpty() }
    val resolvedKeyPassword = (keystoreProperties["keyPassword"] as String?)?.trim()?.takeIf { it.isNotEmpty() }
        ?: envKeyPassword?.trim()?.takeIf { it.isNotEmpty() }
    val resolvedStorePassword = (keystoreProperties["storePassword"] as String?)?.trim()?.takeIf { it.isNotEmpty() }
        ?: envStorePassword?.trim()?.takeIf { it.isNotEmpty() }
    val resolvedStoreFilePath = (keystoreProperties["storeFile"] as String?)?.trim()?.takeIf { it.isNotEmpty() }
        ?: envStoreFile?.trim()?.takeIf { it.isNotEmpty() }
    val resolvedStoreFile = resolvedStoreFilePath?.let { path ->
        val candidate = file(path)
        if (candidate.isAbsolute || candidate.exists()) candidate else rootProject.file(path)
    }

    signingConfigs {
        create("release") {
            keyAlias = resolvedKeyAlias
            keyPassword = resolvedKeyPassword
            storeFile = resolvedStoreFile
            storePassword = resolvedStorePassword
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            val hasAllSigningInputs = !resolvedKeyAlias.isNullOrBlank() &&
                !resolvedKeyPassword.isNullOrBlank() &&
                !resolvedStorePassword.isNullOrBlank() &&
                resolvedStoreFile != null
            signingConfig = if (hasAllSigningInputs) {
                if (!resolvedStoreFile!!.isFile) {
                    throw GradleException("Configured release keystore file does not exist or is not a file: ${resolvedStoreFile.path}")
                }
                signingConfigs.getByName("release")
            } else if (isStrictReleaseSigning) {
                throw GradleException(
                    "Production release signing requires complete android/key.properties or signing env vars " +
                        "(FANSIVIBE_ANDROID_KEYSTORE_PATH, FANSIVIBE_ANDROID_KEYSTORE_PASSWORD, " +
                        "FANSIVIBE_ANDROID_KEY_ALIAS, FANSIVIBE_ANDROID_KEY_PASSWORD). " +
                        "Silent fallback to debug signing is prohibited."
                )
            } else {
                logger.warn("WARNING: Release signing credentials not found. Falling back to debug signing for local test builds ONLY.")
                signingConfigs.getByName("debug")
            }
        }
    }
}

flutter {
    source = "../.."
}
