$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$javaBin = 'D:\Program Files\Java\jdk1.8.0_301\bin'
$toolsDir = Join-Path $PSScriptRoot 'build-tools/android/tools/android-9'
$platformJar = Join-Path $PSScriptRoot 'build-tools/android/platform/android-9/android.jar'
New-Item -ItemType Directory -Force android-cloud/out,android-cloud/res,android/private,dist | Out-Null
& "$javaBin/javac.exe" -encoding UTF-8 -source 1.8 -target 1.8 -bootclasspath $platformJar -d android-cloud/out android-cloud/src/com/zhizhen/study/MainActivity.java
if($LASTEXITCODE){throw 'Java compilation failed'}
& "$toolsDir/aapt.exe" package -f -M android-cloud/AndroidManifest.xml -S android-cloud/res -I $platformJar -F android-cloud/unsigned.apk
if($LASTEXITCODE){throw 'Resources failed'}
& "$javaBin/java.exe" -jar "$toolsDir/lib/dx.jar" --dex --output=android-cloud/classes.dex android-cloud/out
if($LASTEXITCODE){throw 'DEX failed'}
Push-Location android-cloud
& "$toolsDir/aapt.exe" add unsigned.apk classes.dex
Pop-Location
& "$toolsDir/zipalign.exe" -f 4 android-cloud/unsigned.apk android-cloud/aligned.apk
if(!(Test-Path android/private/release.jks)){
  $signPassword = [Guid]::NewGuid().ToString('N')
  Set-Content android/private/password.txt $signPassword -NoNewline
  & "$javaBin/keytool.exe" -genkeypair -keystore android/private/release.jks -storepass $signPassword -keypass $signPassword -alias zhizhen -keyalg RSA -keysize 2048 -validity 10000 -dname 'CN=Zhizhen Personal App'
}
$env:ZHIZHEN_SIGN_PASSWORD = Get-Content android/private/password.txt -Raw
& "$javaBin/java.exe" -jar "$toolsDir/lib/apksigner.jar" sign --ks android/private/release.jks --ks-key-alias zhizhen --ks-pass env:ZHIZHEN_SIGN_PASSWORD --key-pass env:ZHIZHEN_SIGN_PASSWORD --out dist/multi-user/Zhizhen-Online-Android.apk android-cloud/aligned.apk
if($LASTEXITCODE){throw 'Signing failed'}
& "$javaBin/java.exe" -jar "$toolsDir/lib/apksigner.jar" verify --verbose dist/multi-user/Zhizhen-Online-Android.apk
Remove-Item Env:ZHIZHEN_SIGN_PASSWORD
