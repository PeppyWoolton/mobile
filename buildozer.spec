[app]
title = Вязальное производство
package.name = knitting
package.domain = ru.peppywoolton
source.dir = .
source.include_exts = py
version = 2.1
requirements = python3,kivy,pillow,pyzbar,zbar,kivy_garden.zbarcam
orientation = portrait
fullscreen = 0

# Доступ в сеть (HTTP к локальному серверу)
android.permissions = INTERNET, ACCESS_NETWORK_STATE, CAMERA
# Разрешить http (не https) к серверу в локальной сети
android.allow_cleartext_traffic = True

android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
