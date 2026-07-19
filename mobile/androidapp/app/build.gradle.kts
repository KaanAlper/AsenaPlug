plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "asena.plug"
    compileSdk = 35
    buildToolsVersion = "35.0.0"

    defaultConfig {
        applicationId = "com.kaanalper.asenaplug"   // Play paket kimliği (namespace=asena.plug kaynak paketi ayrı)
        minSdk = 26
        targetSdk = 34
        // CI her build'de artırır (Play aynı versionCode'u reddeder); yerelde 1.
        versionCode = (System.getenv("ANDROID_VERSION_CODE")?.toIntOrNull()) ?: 1
        versionName = System.getenv("ANDROID_VERSION_NAME") ?: "0.1-poc"
        ndk { abiFilters += "arm64-v8a" }   // aar arm64-only
    }

    // Release imzası — CI keystore'u ANDROID_KEYSTORE_BASE64 secret'ından çözüp
    // ANDROID_KEYSTORE_PATH env'ini verir. Yerelde keystore yoksa release imzasız kalır (dev debug kullanır).
    signingConfigs {
        create("release") {
            val ksPath = System.getenv("ANDROID_KEYSTORE_PATH")
            if (ksPath != null && file(ksPath).exists()) {
                storeFile = file(ksPath)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS")
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    buildFeatures { compose = true }

    buildTypes {
        getByName("debug") { isMinifyEnabled = false }
        getByName("release") {
            isMinifyEnabled = false   // aar native kod içeriyor; şimdilik shrink yok
            val ksPath = System.getenv("ANDROID_KEYSTORE_PATH")
            signingConfig = if (ksPath != null && file(ksPath).exists())
                signingConfigs.getByName("release") else null
        }
    }
}

dependencies {
    implementation(files("libs/asenacore.aar"))

    implementation(platform("androidx.compose:compose-bom:2024.10.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-core")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
