#!/usr/bin/env python3
"""
Test Android parsers without database connection
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.ckg_builder.android_manifest_parser import AndroidManifestParser
from app.ckg_builder.gradle_parser import GradleParser
from app.ckg_builder.kotlin_parser import KotlinParser
from app.ckg_builder.java_parser import JavaParser

def test_android_manifest_parser():
    print("📱 Testing Android Manifest Parser...")
    
    manifest_content = '''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.myapp">

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.CAMERA" />
    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" />

    <application
        android:allowBackup="true"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:theme="@style/AppTheme">

        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <service
            android:name=".MyBackgroundService"
            android:enabled="true"
            android:exported="false" />

        <receiver
            android:name=".MyBroadcastReceiver"
            android:enabled="true"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.BOOT_COMPLETED" />
            </intent-filter>
        </receiver>

    </application>
</manifest>'''

    parser = AndroidManifestParser()
    result = parser.parse(manifest_content, "AndroidManifest.xml")
    
    if result:
        android_components = [cls for cls in result.classes if any(dec.startswith("@Android") for dec in cls.decorators)]
        permissions = [var for var in result.global_variables if var.scope_type == "permission"]
        app_attributes = [var for var in result.global_variables if var.scope_type in ["manifest_attribute", "application_attribute"]]
        
        print(f"✅ Parsed {len(android_components)} Android components")
        print(f"✅ Parsed {len(permissions)} permissions")
        print(f"✅ Parsed {len(app_attributes)} application attributes")
        
        # Print details
        for component in android_components:
            component_type = next((dec for dec in component.decorators if dec.startswith("@Android")), "Unknown")
            print(f"   - {component_type}: {component.name}")
        
        for permission in permissions:
            print(f"   - Permission: {permission.var_type}")
        
        return len(android_components) > 0
    else:
        print("❌ Failed to parse manifest")
        return False

def test_gradle_parser():
    print("\n🔧 Testing Gradle Parser...")
    
    gradle_content = '''plugins {
    id 'com.android.application'
    id 'org.jetbrains.kotlin.android'
}

android {
    namespace 'com.example.myapp'
    compileSdk 34

    defaultConfig {
        applicationId "com.example.myapp"
        minSdk 24
        targetSdk 34
        versionCode 1
        versionName "1.0"
    }
}

dependencies {
    implementation 'androidx.core:core-ktx:1.12.0'
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.10.0'
    implementation 'androidx.constraintlayout:constraintlayout:2.1.4'
    implementation 'androidx.lifecycle:lifecycle-viewmodel-ktx:2.7.0'
    implementation 'androidx.lifecycle:lifecycle-livedata-ktx:2.7.0'
    implementation 'androidx.navigation:navigation-fragment-ktx:2.7.4'
    implementation 'androidx.navigation:navigation-ui-ktx:2.7.4'
    
    testImplementation 'junit:junit:4.13.2'
    androidTestImplementation 'androidx.test.ext:junit:1.1.5'
    androidTestImplementation 'androidx.test.espresso:espresso-core:3.5.1'
}'''

    parser = GradleParser()
    result = parser.parse(gradle_content, "build.gradle")
    
    if result:
        # GradleParser stores dependencies in global_variables with scope_type="gradle_dependency"
        dependencies = [var for var in result.global_variables if var.scope_type == "gradle_dependency"]
        plugins = [imp for imp in result.imports if imp.import_type == "plugin"]
        
        print(f"✅ Parsed {len(dependencies)} dependencies")
        print(f"✅ Parsed {len(plugins)} plugins")
        
        # Print details
        for dep in dependencies[:3]:  # Show first 3
            print(f"   - {dep.name}: {dep.var_type}")
        
        for plugin in plugins:
            print(f"   - Plugin: {plugin.module_path}")
        
        return len(dependencies) > 0 or len(plugins) > 0
    else:
        print("❌ Failed to parse gradle")
        return False

def test_kotlin_parser():
    print("\n🎯 Testing Kotlin Parser...")
    
    kotlin_content = '''package com.example.myapp

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay

class MainViewModel : ViewModel() {
    
    private var _isLoading = false
    val isLoading: Boolean get() = _isLoading
    
    fun loadData() {
        viewModelScope.launch {
            _isLoading = true
            try {
                delay(1000)
                fetchDataFromNetwork()
            } finally {
                _isLoading = false
            }
        }
    }
    
    private suspend fun fetchDataFromNetwork(): String {
        delay(500)
        return "Data loaded"
    }
    
    companion object {
        const val TAG = "MainViewModel"
    }
}

data class User(
    val id: Long,
    val name: String,
    val email: String?
)

sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val exception: Throwable) : Result<Nothing>()
    object Loading : Result<Nothing>()
}'''

    parser = KotlinParser()
    result = parser.parse(kotlin_content, "MainViewModel.kt")
    
    if result:
        print(f"✅ Parsed {len(result.classes)} Kotlin classes")
        print(f"✅ Parsed {len(result.functions)} functions")
        print(f"✅ Parsed {len(result.imports)} imports")
        
        # Print details
        for cls in result.classes:
            print(f"   - Class: {cls.name} ({len(cls.methods)} methods)")
        
        for func in result.functions[:3]:  # Show first 3
            print(f"   - Function: {func.name}")
        
        return len(result.classes) > 0
    else:
        print("❌ Failed to parse kotlin")
        return False

def test_java_parser():
    print("\n☕ Testing Java Parser...")
    
    java_content = '''package com.example.myapp;

import android.app.Service;
import android.content.Intent;
import android.os.IBinder;
import android.util.Log;

public class MyBackgroundService extends Service {
    
    private static final String TAG = "MyBackgroundService";
    private boolean isRunning = false;
    
    @Override
    public void onCreate() {
        super.onCreate();
        Log.d(TAG, "Service created");
    }
    
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Log.d(TAG, "Service started");
        isRunning = true;
        startBackgroundWork();
        return START_STICKY;
    }
    
    @Override
    public void onDestroy() {
        super.onDestroy();
        isRunning = false;
        Log.d(TAG, "Service destroyed");
    }
    
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
    
    private void startBackgroundWork() {
        new Thread(() -> {
            while (isRunning) {
                try {
                    Thread.sleep(5000);
                    performWork();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
        }).start();
    }
    
    private void performWork() {
        Log.d(TAG, "Performing background work");
    }
}'''

    parser = JavaParser()
    result = parser.parse(java_content, "MyBackgroundService.java")
    
    if result:
        print(f"✅ Parsed {len(result.classes)} Java classes")
        print(f"✅ Parsed {len(result.functions)} methods")
        print(f"✅ Parsed {len(result.imports)} imports")
        
        # Print details
        for cls in result.classes:
            print(f"   - Class: {cls.name} ({len(cls.methods)} methods)")
        
        for func in result.functions[:3]:  # Show first 3
            print(f"   - Method: {func.name}")
        
        return len(result.classes) > 0
    else:
        print("❌ Failed to parse java")
        return False

def main():
    print("🚀 Testing Android Parsers (No Database)...\n")
    
    results = []
    
    try:
        results.append(test_android_manifest_parser())
    except Exception as e:
        print(f"❌ Android Manifest Parser failed: {e}")
        results.append(False)
    
    try:
        results.append(test_gradle_parser())
    except Exception as e:
        print(f"❌ Gradle Parser failed: {e}")
        results.append(False)
    
    try:
        results.append(test_kotlin_parser())
    except Exception as e:
        print(f"❌ Kotlin Parser failed: {e}")
        results.append(False)
    
    try:
        results.append(test_java_parser())
    except Exception as e:
        print(f"❌ Java Parser failed: {e}")
        results.append(False)
    
    print("\n" + "="*50)
    if all(results):
        print("✅ All Android parsers working correctly!")
    else:
        print("❌ Some parsers failed!")
        print(f"Results: Manifest={results[0]}, Gradle={results[1]}, Kotlin={results[2]}, Java={results[3]}")
    print("="*50)

if __name__ == "__main__":
    main() 