plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Release signing comes from the environment (CI secrets). Without it the release build is signed with
// the debug key, which is installable for internal testing but cannot be uploaded to Google Play.
val keystorePath: String? = System.getenv("HQ_KEYSTORE")

android {
    namespace = "com.digitalburj.hq"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.digitalburj.hq"
        minSdk = 26
        targetSdk = 35
        versionCode = (System.getenv("HQ_VERSION_CODE") ?: "1").toInt()
        versionName = "1.0.0"
        buildConfigField("String", "HQ_URL", "\"https://hq.digitalburj.com/\"")
        buildConfigField("String", "HQ_HOST", "\"hq.digitalburj.com\"")
    }

    buildFeatures { buildConfig = true }

    signingConfigs {
        if (keystorePath != null) {
            create("release") {
                storeFile = file(keystorePath)
                storePassword = System.getenv("HQ_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("HQ_KEY_ALIAS")
                keyPassword = System.getenv("HQ_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            buildConfigField("boolean", "SECURE_SCREEN", "true")
            signingConfig = signingConfigs.getByName(if (keystorePath != null) "release" else "debug")
        }
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
            buildConfigField("boolean", "SECURE_SCREEN", "false")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    lint {
        abortOnError = true
        warningsAsErrors = false
        checkReleaseBuilds = true
    }
}

kotlin { jvmToolchain(17) }

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("androidx.core:core-splashscreen:1.0.1")
}
