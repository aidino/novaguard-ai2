#!/usr/bin/env python3
"""
Test script for Android support in NovaGuard CKG
"""

import asyncio
import tempfile
import os
from pathlib import Path
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

# Override NEO4J_URI for testing outside Docker
os.environ['NEO4J_URI'] = 'neo4j://localhost:7687'

# Sample Android files for testing
ANDROID_MANIFEST_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.myapp">

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />

    <application
        android:name=".MyApplication"
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
            android:name=".MyService"
            android:exported="false" />

        <receiver
            android:name=".MyReceiver"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.BOOT_COMPLETED" />
            </intent-filter>
        </receiver>

    </application>

</manifest>
"""

BUILD_GRADLE_SAMPLE = """
plugins {
    id 'com.android.application'
    id 'org.jetbrains.kotlin.android'
}

android {
    compileSdk 34

    defaultConfig {
        applicationId "com.example.myapp"
        minSdk 24
        targetSdk 34
        versionCode 1
        versionName "1.0"

        testInstrumentationRunner "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            minifyEnabled false
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
    }
}

dependencies {
    implementation 'androidx.core:core-ktx:1.12.0'
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.10.0'
    implementation 'androidx.constraintlayout:constraintlayout:2.1.4'
    
    testImplementation 'junit:junit:4.13.2'
    androidTestImplementation 'androidx.test.ext:junit:1.1.5'
    androidTestImplementation 'androidx.test.espresso:espresso-core:3.5.1'
}
"""

KOTLIN_ACTIVITY_SAMPLE = """
package com.example.myapp

import android.app.Activity
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.launch
import kotlinx.coroutines.GlobalScope

class MainActivity : AppCompatActivity() {
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        // Kotlin coroutine example
        GlobalScope.launch {
            performBackgroundTask()
        }
    }
    
    private suspend fun performBackgroundTask() {
        // Some async work
    }
    
    companion object {
        const val TAG = "MainActivity"
    }
}
"""

JAVA_SERVICE_SAMPLE = """
package com.example.myapp;

import android.app.Service;
import android.content.Intent;
import android.os.IBinder;
import androidx.annotation.Nullable;

public class MyService extends Service {
    
    @Override
    public void onCreate() {
        super.onCreate();
    }
    
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        return START_STICKY;
    }
    
    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
"""

async def test_android_support():
    """Test Android support in NovaGuard CKG"""
    print("🚀 Testing Android support in NovaGuard CKG...")
    
    # Import here to avoid issues if running outside container
    try:
        from app.ckg_builder.parsers import (
            get_android_manifest_parser, 
            get_gradle_parser,
            get_code_parser
        )
        from app.ckg_builder.builder import CKGBuilder
        from app.models import Project
        from app.core.graph_db import get_async_neo4j_driver
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("This script should be run inside the Docker container")
        return False
    
    success = True
    
    # Test 1: Android Manifest Parser
    print("\n📱 Testing Android Manifest Parser...")
    try:
        manifest_parser = get_android_manifest_parser()
        parsed_manifest = manifest_parser.parse(ANDROID_MANIFEST_SAMPLE, "AndroidManifest.xml")
        
        if parsed_manifest:
            print(f"✅ Parsed {len(parsed_manifest.classes)} Android components")
            print(f"✅ Parsed {len(parsed_manifest.global_variables)} manifest attributes")
            
            # Check for specific components
            activities = [c for c in parsed_manifest.classes if "@AndroidActivity" in c.decorators]
            services = [c for c in parsed_manifest.classes if "@AndroidService" in c.decorators]
            receivers = [c for c in parsed_manifest.classes if "@AndroidReceiver" in c.decorators]
            
            print(f"   - Activities: {len(activities)}")
            print(f"   - Services: {len(services)}")
            print(f"   - Receivers: {len(receivers)}")
        else:
            print("❌ Failed to parse Android manifest")
            success = False
    except Exception as e:
        print(f"❌ Android manifest parser error: {e}")
        success = False
    
    # Test 2: Gradle Parser
    print("\n🔧 Testing Gradle Parser...")
    try:
        gradle_parser = get_gradle_parser("build.gradle")
        parsed_gradle = gradle_parser.parse(BUILD_GRADLE_SAMPLE, "build.gradle")
        
        if parsed_gradle:
            dependencies = [v for v in parsed_gradle.global_variables if v.scope_type == "gradle_dependency"]
            plugins = [i for i in parsed_gradle.imports if i.import_type == "plugin"]
            
            print(f"✅ Parsed {len(dependencies)} dependencies")
            print(f"✅ Parsed {len(plugins)} plugins")
            
            # Show some dependencies
            for dep in dependencies[:3]:
                print(f"   - {dep.name}: {dep.var_type}")
        else:
            print("❌ Failed to parse Gradle file")
            success = False
    except Exception as e:
        print(f"❌ Gradle parser error: {e}")
        success = False
    
    # Test 3: Kotlin Parser
    print("\n🎯 Testing Kotlin Parser...")
    try:
        kotlin_parser = get_code_parser("kotlin")
        parsed_kotlin = kotlin_parser.parse(KOTLIN_ACTIVITY_SAMPLE, "MainActivity.kt")
        
        if parsed_kotlin:
            print(f"✅ Parsed {len(parsed_kotlin.classes)} Kotlin classes")
            print(f"✅ Parsed {len(parsed_kotlin.functions)} functions")
            print(f"✅ Parsed {len(parsed_kotlin.imports)} imports")
            
            # Check for coroutine usage
            for func in parsed_kotlin.functions:
                coroutine_calls = [call for call in func.calls if call[1] == "coroutine"]
                if coroutine_calls:
                    print(f"   - Found coroutine usage in {func.name}")
        else:
            print("❌ Failed to parse Kotlin file")
            success = False
    except Exception as e:
        print(f"❌ Kotlin parser error: {e}")
        success = False
    
    # Test 4: Java Parser
    print("\n☕ Testing Java Parser...")
    try:
        java_parser = get_code_parser("java")
        parsed_java = java_parser.parse(JAVA_SERVICE_SAMPLE, "MyService.java")
        
        if parsed_java:
            print(f"✅ Parsed {len(parsed_java.classes)} Java classes")
            print(f"✅ Parsed {len(parsed_java.functions)} methods")
            print(f"✅ Parsed {len(parsed_java.imports)} imports")
            
            # Check for annotations
            for cls in parsed_java.classes:
                if cls.decorators:
                    print(f"   - Class {cls.name} has decorators: {cls.decorators}")
        else:
            print("❌ Failed to parse Java file")
            success = False
    except Exception as e:
        print(f"❌ Java parser error: {e}")
        success = False
    
    # Test 5: CKG Integration (create temporary project)
    print("\n🗄️ Testing CKG Integration...")
    try:
        # Create a mock project
        class MockProject:
            def __init__(self):
                self.id = 999
                self.name = "Android Test Project"
                self.language = "kotlin"
        
        project = MockProject()
        
        # Create temporary directory with Android files
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create Android project structure
            (temp_path / "app").mkdir()
            (temp_path / "app" / "src" / "main" / "java" / "com" / "example" / "myapp").mkdir(parents=True)
            
            # Write sample files
            (temp_path / "app" / "src" / "main" / "AndroidManifest.xml").write_text(ANDROID_MANIFEST_SAMPLE)
            (temp_path / "app" / "build.gradle").write_text(BUILD_GRADLE_SAMPLE)
            (temp_path / "app" / "src" / "main" / "java" / "com" / "example" / "myapp" / "MainActivity.kt").write_text(KOTLIN_ACTIVITY_SAMPLE)
            (temp_path / "app" / "src" / "main" / "java" / "com" / "example" / "myapp" / "MyService.java").write_text(JAVA_SERVICE_SAMPLE)
            
            # Test CKG builder
            ckg_builder = CKGBuilder(project, project_graph_id="test_android_project_999")
            
            # Test individual file processing
            await ckg_builder.process_file_for_ckg(
                "app/src/main/AndroidManifest.xml", 
                ANDROID_MANIFEST_SAMPLE, 
                "android_special"
            )
            
            await ckg_builder.process_file_for_ckg(
                "app/build.gradle", 
                BUILD_GRADLE_SAMPLE, 
                "android_special"
            )
            
            await ckg_builder.process_file_for_ckg(
                "app/src/main/java/com/example/myapp/MainActivity.kt", 
                KOTLIN_ACTIVITY_SAMPLE, 
                "kotlin"
            )
            
            await ckg_builder.process_file_for_ckg(
                "app/src/main/java/com/example/myapp/MyService.java", 
                JAVA_SERVICE_SAMPLE, 
                "java"
            )
            
            print("✅ CKG integration test completed successfully")
            
    except Exception as e:
        print(f"❌ CKG integration error: {e}")
        success = False
    
    # Summary
    print(f"\n{'='*50}")
    if success:
        print("🎉 All Android support tests PASSED!")
        print("✅ Android Manifest parsing")
        print("✅ Gradle build file parsing") 
        print("✅ Kotlin code parsing")
        print("✅ Java code parsing")
        print("✅ CKG integration")
    else:
        print("❌ Some Android support tests FAILED!")
    
    print(f"{'='*50}")
    return success

if __name__ == "__main__":
    asyncio.run(test_android_support()) 