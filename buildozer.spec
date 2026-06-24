[app]
title = Document Scanner
package.name = documentscanner
package.domain = org.yourname
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = python3,kivy,opencv,pillow,pyjnius
orientation = portrait
fullscreen = 0
android.permissions = CAMERA, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.accept_sdk_license = True
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True
android.extra_manifest_application_arguments = android:requestLegacyExternalStorage="true"
android.release_artifact = apk
android.debug_artifact = apk
p4a.branch = master
p4a.commit = ccf59d25
p4a.bootstrap = sdl2
osx.kivy_version = 2.2.0
ios.kivy_ios_url = https://github.com/kivy/kivy-ios
ios.kivy_ios_branch = master
ios.ios_deploy_url = https://github.com/phonegap/ios-deploy
ios.ios_deploy_branch = 1.12.2
ios.codesign.allowed = false

[buildozer]
log_level = 2
warn_on_root = 1
