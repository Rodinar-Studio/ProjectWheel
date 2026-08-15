@echo off
set ANDROID_HOME=C:\Android
set ANDROID_SDK_ROOT=C:\Android
set JAVA_HOME=C:\jdk21
set PATH=C:\jdk21\bin;%PATH%
cd /d C:\ProjectWheel\gyro_pedal_app
echo === Running flutter build apk ===
call C:\flutter\flutter\bin\flutter.bat build apk --release
echo === Build complete ===
