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
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
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

    val isStrictReleaseSigning = project.hasProperty("requireReleaseSigning") ||
        System.getenv("REQUIRE_RELEASE_SIGNING") == "true" ||
        System.getenv("CI") == "true" ||
        project.hasProperty("prodRelease")

    signingConfigs {
        create("release") {
            keyAlias = keystoreProperties["keyAlias"] as String?
            keyPassword = keystoreProperties["keyPassword"] as String?
            storeFile = (keystoreProperties["storeFile"] as String?)?.let { file(it) }
            storePassword = keystoreProperties["storePassword"] as String?
        }
    }

    buildTypes {
        release {
            signingConfig = if (keystorePropertiesFile.exists()) {
                val hasAllKeys = !(keystoreProperties["keyAlias"] as String?).isNullOrBlank() &&
                    !(keystoreProperties["keyPassword"] as String?).isNullOrBlank() &&
                    !(keystoreProperties["storePassword"] as String?).isNullOrBlank() &&
                    !(keystoreProperties["storeFile"] as String?).isNullOrBlank()
                if (hasAllKeys) {
                    signingConfigs.getByName("release")
                } else if (isStrictReleaseSigning) {
                    throw GradleException("Production release signing requires complete key.properties (keyAlias, keyPassword, storePassword, storeFile).")
                } else {
                    logger.warn("WARNING: key.properties is incomplete. Falling back to debug signing for local test builds ONLY.")
                    signingConfigs.getByName("debug")
                }
            } else if (isStrictReleaseSigning) {
                throw GradleException("Production release signing requires key.properties. Silent fallback to debug signing is prohibited.")
            } else {
                logger.warn("WARNING: key.properties not found. Falling back to debug signing for local test builds ONLY.")
                signingConfigs.getByName("debug")
            }
        }
    }
}

flutter {
    source = "../.."
}
