$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$javaBin = 'D:\Program Files\Java\jdk1.8.0_301\bin'
$toolsDir = Join-Path $PSScriptRoot 'build-tools/android/tools/android-9'
$platformJar = Join-Path $PSScriptRoot 'build-tools/android/platform/android-9/android.jar'
New-Item -ItemType Directory -Force android/out,android/res,android/private,dist | Out-Null
& "$javaBin/javac.exe" -encoding UTF-8 -source 1.8 -target 1.8 -bootclasspath $platformJar -d android/out android/src/com/zhizhen/study/MainActivity.java
if($LASTEXITCODE){throw 'Java compilation failed'}
& "$toolsDir/aapt.exe" package -f -M android/AndroidManifest.xml -S android/res -I $platformJar -F android/unsigned.apk
if($LASTEXITCODE){throw 'Resources failed'}
& "$javaBin/java.exe" -jar "$toolsDir/lib/dx.jar" --dex --output=android/classes.dex android/out
if($LASTEXITCODE){throw 'DEX failed'}
Push-Location android
& "$toolsDir/aapt.exe" add unsigned.apk classes.dex
Pop-Location
& "$toolsDir/zipalign.exe" -f 4 android/unsigned.apk android/aligned.apk
if(!(Test-Path android/private/release.jks)){
  $signPassword = [Guid]::NewGuid().ToString('N')
  Set-Content android/private/password.txt $signPassword -NoNewline
  & "$javaBin/keytool.exe" -genkeypair -keystore android/private/release.jks -storepass $signPassword -keypass $signPassword -alias zhizhen -keyalg RSA -keysize 2048 -validity 10000 -dname 'CN=Zhizhen Personal App'
}
$env:ZHIZHEN_SIGN_PASSWORD = Get-Content android/private/password.txt -Raw
& "$javaBin/java.exe" -jar "$toolsDir/lib/apksigner.jar" sign --ks android/private/release.jks --ks-key-alias zhizhen --ks-pass env:ZHIZHEN_SIGN_PASSWORD --key-pass env:ZHIZHEN_SIGN_PASSWORD --out dist/Zhizhen-Android.apk android/aligned.apk
if($LASTEXITCODE){throw 'Signing failed'}
& "$javaBin/java.exe" -jar "$toolsDir/lib/apksigner.jar" verify --verbose dist/Zhizhen-Android.apk
Remove-Item Env:ZHIZHEN_SIGN_PASSWORD
