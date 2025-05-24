#!/usr/bin/env python3
"""
Test script for Phase 6: Enhanced Analysis Integration
Tests the complete Android analysis pipeline with integrated components
"""

import sys
import os
import asyncio

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from analysis_module import (
    EnhancedAnalysisEngine,
    AnalysisRequest,
    AnalysisResult,
    AndroidComponent,
    AndroidPermission, 
    GradleDependency
)
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_sample_android_project() -> dict:
    """Create a comprehensive sample Android project for testing."""
    return {
        "app/src/main/AndroidManifest.xml": """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.novaguard.testapp">
    
    <uses-permission android:name="android.permission.CAMERA" />
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" />
    
    <application
        android:name=".TestApplication"
        android:allowBackup="false"
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
        
        <activity
            android:name=".ProfileActivity"
            android:exported="false" />
            
        <service
            android:name=".BackgroundService"
            android:exported="false" />
            
        <receiver
            android:name=".NotificationReceiver"
            android:exported="true">
            <intent-filter>
                <action android:name="com.example.CUSTOM_ACTION" />
            </intent-filter>
        </receiver>
        
    </application>
</manifest>""",

        "app/build.gradle": """
android {
    compileSdk 34
    
    defaultConfig {
        applicationId "com.example.novaguard.testapp"
        minSdk 21
        targetSdk 34
        versionCode 1
        versionName "1.0"
        
        testInstrumentationRunner "androidx.test.runner.AndroidJUnitRunner"
    }
    
    buildTypes {
        release {
            minifyEnabled true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
        debug {
            debuggable true
        }
    }
    
    compileOptions {
        sourceCompatibility JavaVersion.VERSION_1_8
        targetCompatibility JavaVersion.VERSION_1_8
    }
    
    kotlinOptions {
        jvmTarget = '1.8'
    }
}

dependencies {
    // Core Android
    implementation 'androidx.core:core-ktx:1.12.0'
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.10.0'
    implementation 'androidx.constraintlayout:constraintlayout:2.1.4'
    
    // Architecture Components
    implementation 'androidx.lifecycle:lifecycle-viewmodel-ktx:2.7.0'
    implementation 'androidx.lifecycle:lifecycle-livedata-ktx:2.7.0'
    implementation 'androidx.navigation:navigation-fragment-ktx:2.7.5'
    implementation 'androidx.navigation:navigation-ui-ktx:2.7.5'
    implementation 'androidx.room:room-runtime:2.6.1'
    implementation 'androidx.room:room-ktx:2.6.1'
    kapt 'androidx.room:room-compiler:2.6.1'
    
    // Networking
    implementation 'com.squareup.retrofit2:retrofit:2.9.0'
    implementation 'com.squareup.retrofit2:converter-gson:2.9.0'
    implementation 'com.squareup.okhttp3:logging-interceptor:4.12.0'
    
    // Image Loading
    implementation 'com.github.bumptech.glide:glide:4.16.0'
    
    // Dependency Injection
    implementation 'com.google.dagger:hilt-android:2.48'
    kapt 'com.google.dagger:hilt-compiler:2.48'
    
    // Coroutines
    implementation 'org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3'
    
    // Testing
    testImplementation 'junit:junit:4.13.2'
    testImplementation 'org.mockito:mockito-core:5.7.0'
    testImplementation 'androidx.arch.core:core-testing:2.2.0'
    testImplementation 'org.jetbrains.kotlinx:kotlinx-coroutines-test:1.7.3'
    
    androidTestImplementation 'androidx.test.ext:junit:1.1.5'
    androidTestImplementation 'androidx.test.espresso:espresso-core:3.5.1'
    androidTestImplementation 'androidx.test:runner:1.5.2'
    androidTestImplementation 'androidx.test:rules:1.5.0'
}""",

        "app/src/main/kotlin/com/example/novaguard/testapp/MainActivity.kt": """
package com.example.novaguard.testapp

import android.os.Bundle
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.Observer
import androidx.navigation.findNavController
import androidx.navigation.ui.setupActionBarWithNavController
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : AppCompatActivity() {
    
    private val viewModel: MainViewModel by viewModels()
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        setupNavigation()
        observeViewModel()
    }
    
    private fun setupNavigation() {
        val navController = findNavController(R.id.nav_host_fragment)
        setupActionBarWithNavController(navController)
    }
    
    private fun observeViewModel() {
        viewModel.uiState.observe(this, Observer { state ->
            when (state) {
                is MainUiState.Loading -> showLoading()
                is MainUiState.Success -> showContent(state.data)
                is MainUiState.Error -> showError(state.message)
            }
        })
    }
    
    private fun showLoading() {
        // Show loading state
    }
    
    private fun showContent(data: Any) {
        // Show content
    }
    
    private fun showError(message: String) {
        // Show error
    }
}""",

        "app/src/main/kotlin/com/example/novaguard/testapp/MainViewModel.kt": """
package com.example.novaguard.testapp

import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class MainViewModel @Inject constructor(
    private val repository: UserRepository
) : ViewModel() {
    
    private val _uiState = MutableLiveData<MainUiState>()
    val uiState: LiveData<MainUiState> = _uiState
    
    init {
        loadData()
    }
    
    private fun loadData() {
        viewModelScope.launch {
            _uiState.value = MainUiState.Loading
            try {
                val data = repository.getUserData()
                _uiState.value = MainUiState.Success(data)
            } catch (e: Exception) {
                _uiState.value = MainUiState.Error(e.message ?: "Unknown error")
            }
        }
    }
    
    fun refresh() {
        loadData()
    }
}

sealed class MainUiState {
    object Loading : MainUiState()
    data class Success(val data: Any) : MainUiState()
    data class Error(val message: String) : MainUiState()
}""",

        "app/src/main/java/com/example/novaguard/testapp/UserRepository.java": """
package com.example.novaguard.testapp;

import javax.inject.Inject;
import javax.inject.Singleton;
import java.util.concurrent.CompletableFuture;

@Singleton
public class UserRepository {
    
    private final ApiService apiService;
    private final UserDao userDao;
    
    @Inject
    public UserRepository(ApiService apiService, UserDao userDao) {
        this.apiService = apiService;
        this.userDao = userDao;
    }
    
    public CompletableFuture<Object> getUserData() {
        return CompletableFuture.supplyAsync(() -> {
            try {
                // Fetch from network
                Object networkData = apiService.getUser().execute().body();
                
                // Cache in database
                if (networkData != null) {
                    userDao.insertUser(networkData);
                }
                
                return networkData;
            } catch (Exception e) {
                // Fallback to cached data
                return userDao.getUser();
            }
        });
    }
    
    public void clearCache() {
        userDao.deleteAll();
    }
}""",

        "app/src/main/kotlin/com/example/novaguard/testapp/BackgroundService.kt": """
package com.example.novaguard.testapp

import android.app.Service
import android.content.Intent
import android.os.IBinder
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class BackgroundService : Service() {
    
    @Inject
    lateinit var repository: UserRepository
    
    private val serviceScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    
    override fun onBind(intent: Intent?): IBinder? = null
    
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_SYNC_DATA -> syncData()
            ACTION_CLEANUP -> cleanup()
        }
        return START_NOT_STICKY
    }
    
    private fun syncData() {
        serviceScope.launch {
            try {
                repository.getUserData()
                scheduleNextSync()
            } catch (e: Exception) {
                // Handle error
            } finally {
                stopSelf()
            }
        }
    }
    
    private fun cleanup() {
        serviceScope.launch {
            repository.clearCache()
            stopSelf()
        }
    }
    
    private fun scheduleNextSync() {
        val workRequest = OneTimeWorkRequestBuilder<SyncWorker>()
            .build()
        WorkManager.getInstance(this).enqueue(workRequest)
    }
    
    companion object {
        const val ACTION_SYNC_DATA = "com.example.SYNC_DATA"
        const val ACTION_CLEANUP = "com.example.CLEANUP"
    }
}"""
    }

async def test_enhanced_analysis_engine():
    """Test the Enhanced Analysis Engine with comprehensive analysis."""
    print("\n" + "="*60)
    print("🚀 Testing Enhanced Analysis Engine")
    print("="*60)
    
    try:
        # Initialize the engine
        engine = EnhancedAnalysisEngine(max_workers=2)
        
        # Create analysis request
        project_files = create_sample_android_project()
        request = AnalysisRequest(
            project_id=1,
            project_name="NovaGuard Test App",
            project_files=project_files,
            analysis_types=["architecture", "security", "performance", "code_review", "lifecycle"],
            priority="high"
        )
        
        print(f"📋 Analysis Request:")
        print(f"   Project: {request.project_name}")
        print(f"   Files: {len(request.project_files)}")
        print(f"   Analysis Types: {request.analysis_types}")
        print(f"   Priority: {request.priority}")
        
        # Perform analysis
        print(f"\n🔄 Starting comprehensive analysis...")
        result = await engine.analyze_project(request)
        
        # Display results
        print(f"\n✅ Analysis completed successfully!")
        print(f"   Execution Time: {result.execution_time:.2f}s")
        print(f"   Health Score: {result.metrics.get('health_score', 0)}/100")
        print(f"   Total Findings: {len(result.findings)}")
        print(f"   Recommendations: {len(result.recommendations)}")
        
        # Show detailed metrics
        print(f"\n📊 Detailed Metrics:")
        metrics = result.metrics
        print(f"   Architecture Score: {metrics.get('architecture_score', 0)}/100")
        print(f"   Security Score: {metrics.get('security_score', 0)}/100")
        print(f"   Performance Score: {metrics.get('performance_score', 0)}/100")
        print(f"   Kotlin Adoption: {metrics.get('kotlin_adoption', 0):.1f}%")
        print(f"   Modern Components: {metrics.get('modern_components', 0)}")
        print(f"   Dependencies: {metrics.get('dependency_count', 0)}")
        
        # Show severity distribution
        severity_dist = metrics.get('severity_distribution', {})
        print(f"\n🎯 Findings by Severity:")
        for severity, count in severity_dist.items():
            print(f"   {severity.capitalize()}: {count}")
        
        # Show sample findings
        print(f"\n🔍 Sample Findings:")
        for i, finding in enumerate(result.findings[:3]):
            print(f"   {i+1}. [{finding.get('severity', 'unknown').upper()}] {finding.get('title', 'No title')}")
            print(f"      {finding.get('description', 'No description')}")
        
        if len(result.findings) > 3:
            print(f"   ... and {len(result.findings) - 3} more findings")
        
        # Show recommendations
        print(f"\n💡 Recommendations:")
        for i, rec in enumerate(result.recommendations[:3]):
            print(f"   {i+1}. [{rec.get('priority', 'unknown').upper()}] {rec.get('title', 'No title')}")
            print(f"      {rec.get('description', 'No description')}")
        
        # Test analysis summary
        summary = engine.get_analysis_summary(result)
        print(f"\n📋 Analysis Summary:")
        for key, value in summary.items():
            print(f"   {key}: {value}")
        
        return True
        
    except Exception as e:
        print(f"❌ Enhanced Analysis Engine Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_analysis_categories():
    """Test individual analysis categories."""
    print("\n" + "="*60)
    print("🔧 Testing Individual Analysis Categories")
    print("="*60)
    
    try:
        engine = EnhancedAnalysisEngine(max_workers=1)
        project_files = create_sample_android_project()
        
        categories = ["architecture", "security", "performance", "code_review", "lifecycle"]
        results = {}
        
        for category in categories:
            print(f"\n🔄 Testing {category} analysis...")
            
            request = AnalysisRequest(
                project_id=1,
                project_name=f"Test {category.title()}",
                project_files=project_files,
                analysis_types=[category],
                priority="normal"
            )
            
            result = await engine.analyze_project(request)
            results[category] = result
            
            category_findings = [f for f in result.findings if f.get('category') == category]
            print(f"   ✅ {category.title()}: {len(category_findings)} findings")
            print(f"   Prompts generated: {len(result.rendered_prompts)}")
            print(f"   Execution time: {result.execution_time:.2f}s")
        
        # Summary
        print(f"\n📊 Category Analysis Summary:")
        total_findings = sum(len(r.findings) for r in results.values())
        total_time = sum(r.execution_time for r in results.values())
        
        print(f"   Total Categories: {len(categories)}")
        print(f"   Total Findings: {total_findings}")
        print(f"   Total Execution Time: {total_time:.2f}s")
        print(f"   Average per Category: {total_findings/len(categories):.1f} findings")
        
        return True
        
    except Exception as e:
        print(f"❌ Category Analysis Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_prompt_integration():
    """Test prompt template integration."""
    print("\n" + "="*60)
    print("📝 Testing Prompt Template Integration")
    print("="*60)
    
    try:
        engine = EnhancedAnalysisEngine()
        project_files = create_sample_android_project()
        
        request = AnalysisRequest(
            project_id=1,
            project_name="Prompt Integration Test",
            project_files=project_files,
            analysis_types=["architecture", "security"],
            priority="normal"
        )
        
        result = await engine.analyze_project(request)
        
        print(f"📄 Generated Prompts:")
        for prompt_name, prompt_content in result.rendered_prompts.items():
            print(f"   - {prompt_name}: {len(prompt_content)} characters")
            
            # Show snippet
            lines = prompt_content.split('\n')[:3]
            snippet = '\n'.join(lines)
            print(f"     Preview: {snippet}...")
            print()
        
        # Verify prompt-finding correlation
        prompt_findings = {}
        for finding in result.findings:
            prompt_name = finding.get('analysis_prompt', 'unknown')
            if prompt_name not in prompt_findings:
                prompt_findings[prompt_name] = 0
            prompt_findings[prompt_name] += 1
        
        print(f"🔗 Prompt-Finding Correlation:")
        for prompt_name, finding_count in prompt_findings.items():
            print(f"   {prompt_name}: {finding_count} findings")
        
        return True
        
    except Exception as e:
        print(f"❌ Prompt Integration Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test function."""
    print("🚀 Starting Phase 6: Enhanced Analysis Integration Tests")
    print("Testing comprehensive Android project analysis pipeline...")
    
    results = []
    
    # Run all tests
    tests = [
        ("Enhanced Analysis Engine", test_enhanced_analysis_engine),
        ("Analysis Categories", test_analysis_categories),
        ("Prompt Integration", test_prompt_integration)
    ]
    
    for test_name, test_func in tests:
        try:
            success = await test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Print summary
    print("\n" + "="*60)
    print("📋 PHASE 6 TEST SUMMARY")
    print("="*60)
    
    passed = 0
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status}: {test_name}")
        if success:
            passed += 1
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All Phase 6 tests passed! Enhanced Analysis Integration successful.")
        print("\nFeatures implemented:")
        print("✅ Comprehensive analysis pipeline")
        print("✅ Multi-category analysis (architecture, security, performance, code review, lifecycle)")
        print("✅ Context-aware prompt generation")
        print("✅ Intelligent findings generation")
        print("✅ Automated recommendations")
        print("✅ Detailed metrics and scoring")
        print("✅ Async processing with thread pool")
        print("✅ Analysis result aggregation")
        
        print("\nNext: Ready for Phase 7 - API Integration")
    else:
        print(f"⚠️  {total - passed} test(s) failed. Phase 6 needs attention.")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 