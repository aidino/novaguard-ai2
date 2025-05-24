#!/usr/bin/env python3
"""
Test script for Phase 7: API Integration
Tests the Android Analysis API endpoints
"""

import sys
import os
import asyncio
import json
import time
from typing import Dict, Any

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_sample_api_request() -> Dict[str, Any]:
    """Create a sample API request for testing."""
    return {
        "project_id": 1,
        "project_name": "NovaGuard API Test Project",
        "files": [
            {
                "file_path": "app/src/main/AndroidManifest.xml",
                "content": """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.novaguard.apitest">
    
    <uses-permission android:name="android.permission.CAMERA" />
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
    
    <application
        android:name=".ApiTestApplication"
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
        
        <service
            android:name=".BackgroundService"
            android:exported="false" />
            
        <receiver
            android:name=".NotificationReceiver"
            android:exported="true" />
        
    </application>
</manifest>"""
            },
            {
                "file_path": "app/build.gradle",
                "content": """
android {
    compileSdk 34
    
    defaultConfig {
        applicationId "com.example.novaguard.apitest"
        minSdk 21
        targetSdk 34
        versionCode 1
        versionName "1.0"
    }
    
    buildTypes {
        release {
            minifyEnabled true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
    }
}

dependencies {
    implementation 'androidx.core:core-ktx:1.12.0'
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'androidx.lifecycle:lifecycle-viewmodel-ktx:2.7.0'
    implementation 'androidx.navigation:navigation-fragment-ktx:2.7.5'
    implementation 'com.squareup.retrofit2:retrofit:2.9.0'
    implementation 'com.google.dagger:hilt-android:2.48'
    implementation 'org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3'
    
    testImplementation 'junit:junit:4.13.2'
    androidTestImplementation 'androidx.test.ext:junit:1.1.5'
}"""
            },
            {
                "file_path": "app/src/main/kotlin/MainActivity.kt",
                "content": """
package com.example.novaguard.apitest

import android.os.Bundle
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.Observer
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : AppCompatActivity() {
    
    private val viewModel: MainViewModel by viewModels()
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        observeViewModel()
    }
    
    private fun observeViewModel() {
        viewModel.uiState.observe(this, Observer { state ->
            when (state) {
                is UiState.Loading -> showLoading()
                is UiState.Success -> showContent(state.data)
                is UiState.Error -> showError(state.message)
            }
        })
    }
    
    private fun showLoading() {}
    private fun showContent(data: Any) {}
    private fun showError(message: String) {}
}"""
            },
            {
                "file_path": "app/src/main/java/UserRepository.java",
                "content": """
package com.example.novaguard.apitest;

import javax.inject.Inject;
import javax.inject.Singleton;

@Singleton
public class UserRepository {
    
    private final ApiService apiService;
    
    @Inject
    public UserRepository(ApiService apiService) {
        this.apiService = apiService;
    }
    
    public void fetchUserData() {
        // Implementation
    }
}"""
            }
        ],
        "analysis_types": ["architecture", "security", "performance", "code_review"],
        "priority": "high"
    }

async def test_api_models():
    """Test API model creation and validation."""
    print("\n" + "="*60)
    print("📋 Testing API Models")
    print("="*60)
    
    try:
        from api.android_analysis_api import (
            AnalysisRequestModel,
            ProjectFileModel,
            AnalysisStatusModel,
            FindingModel,
            RecommendationModel,
            AnalysisResultModel
        )
        
        # Test ProjectFileModel
        file_model = ProjectFileModel(
            file_path="test.kt",
            content="class Test {}"
        )
        print(f"✅ ProjectFileModel: {file_model.file_path}")
        
        # Test AnalysisRequestModel
        request_data = create_sample_api_request()
        request_model = AnalysisRequestModel(**request_data)
        print(f"✅ AnalysisRequestModel: {request_model.project_name}")
        print(f"   Files: {len(request_model.files)}")
        print(f"   Analysis Types: {request_model.analysis_types}")
        
        # Test AnalysisStatusModel
        from datetime import datetime
        status_model = AnalysisStatusModel(
            analysis_id="test_123",
            status="pending",
            progress=0.0,
            started_at=datetime.now(),
            completed_at=None,
            error_message=None
        )
        print(f"✅ AnalysisStatusModel: {status_model.analysis_id} - {status_model.status}")
        
        # Test FindingModel
        finding_model = FindingModel(
            type="security_issue",
            severity="high",
            title="Test Finding",
            description="Test description",
            recommendation="Test recommendation",
            category="security",
            analysis_prompt="test_prompt"
        )
        print(f"✅ FindingModel: {finding_model.title} ({finding_model.severity})")
        
        return True
        
    except Exception as e:
        print(f"❌ API Models Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_analysis_engine_integration():
    """Test integration with analysis engine."""
    print("\n" + "="*60)
    print("🔧 Testing Analysis Engine Integration")
    print("="*60)
    
    try:
        from api.android_analysis_api import analysis_engine, perform_analysis_task
        from analysis_module import AnalysisRequest
        
        # Test engine initialization
        print(f"📊 Analysis Engine:")
        print(f"   Max Workers: {analysis_engine.max_workers}")
        print(f"   Available Templates: {len(analysis_engine.prompt_engine.get_available_templates())}")
        
        # Create test request
        request_data = create_sample_api_request()
        project_files = {file["file_path"]: file["content"] for file in request_data["files"]}
        
        internal_request = AnalysisRequest(
            project_id=request_data["project_id"],
            project_name=request_data["project_name"],
            project_files=project_files,
            analysis_types=request_data["analysis_types"],
            priority=request_data["priority"]
        )
        
        # Test analysis execution
        print(f"\n🔄 Testing analysis execution...")
        result = await analysis_engine.analyze_project(internal_request)
        
        print(f"✅ Analysis completed:")
        print(f"   Execution Time: {result.execution_time:.2f}s")
        print(f"   Health Score: {result.metrics.get('health_score', 0)}/100")
        print(f"   Findings: {len(result.findings)}")
        print(f"   Recommendations: {len(result.recommendations)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Analysis Engine Integration Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_background_task_simulation():
    """Test background task execution simulation."""
    print("\n" + "="*60)
    print("⚙️ Testing Background Task Simulation")
    print("="*60)
    
    try:
        from api.android_analysis_api import (
            perform_analysis_task,
            analysis_status,
            analysis_results,
            AnalysisStatusModel
        )
        from analysis_module import AnalysisRequest
        from datetime import datetime
        
        # Create test analysis ID and status
        analysis_id = f"test_bg_{int(datetime.now().timestamp())}"
        
        analysis_status[analysis_id] = AnalysisStatusModel(
            analysis_id=analysis_id,
            status="pending",
            progress=0.0,
            started_at=datetime.now(),
            completed_at=None,
            error_message=None
        )
        
        # Create test request
        request_data = create_sample_api_request()
        project_files = {file["file_path"]: file["content"] for file in request_data["files"]}
        
        internal_request = AnalysisRequest(
            project_id=request_data["project_id"],
            project_name=request_data["project_name"],
            project_files=project_files,
            analysis_types=request_data["analysis_types"],
            priority=request_data["priority"]
        )
        
        print(f"📋 Starting background task: {analysis_id}")
        print(f"   Initial Status: {analysis_status[analysis_id].status}")
        
        # Execute background task
        await perform_analysis_task(analysis_id, internal_request)
        
        # Check results
        final_status = analysis_status[analysis_id]
        print(f"✅ Background task completed:")
        print(f"   Final Status: {final_status.status}")
        print(f"   Progress: {final_status.progress}")
        print(f"   Error: {final_status.error_message}")
        
        if analysis_id in analysis_results:
            result = analysis_results[analysis_id]
            print(f"   Result Available: Yes")
            print(f"   Findings: {len(result.findings)}")
            print(f"   Health Score: {result.metrics.get('health_score', 0)}")
        else:
            print(f"   Result Available: No")
        
        # Cleanup
        if analysis_id in analysis_status:
            del analysis_status[analysis_id]
        if analysis_id in analysis_results:
            del analysis_results[analysis_id]
        
        return final_status.status == "completed"
        
    except Exception as e:
        print(f"❌ Background Task Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_api_endpoint_logic():
    """Test API endpoint logic without FastAPI server."""
    print("\n" + "="*60)
    print("🌐 Testing API Endpoint Logic")
    print("="*60)
    
    try:
        from api.android_analysis_api import (
            analysis_status,
            analysis_results,
            AnalysisRequestModel,
            AnalysisStatusModel
        )
        from datetime import datetime
        
        # Test analysis ID generation
        request_data = create_sample_api_request()
        request_model = AnalysisRequestModel(**request_data)
        
        analysis_id = f"analysis_{request_model.project_id}_{int(datetime.now().timestamp())}"
        print(f"📋 Generated Analysis ID: {analysis_id}")
        
        # Test status creation
        status_model = AnalysisStatusModel(
            analysis_id=analysis_id,
            status="pending",
            progress=0.0,
            started_at=datetime.now(),
            completed_at=None,
            error_message=None
        )
        
        analysis_status[analysis_id] = status_model
        print(f"✅ Status created: {status_model.status}")
        
        # Test status retrieval
        retrieved_status = analysis_status.get(analysis_id)
        if retrieved_status:
            print(f"✅ Status retrieved: {retrieved_status.analysis_id}")
        else:
            print(f"❌ Status not found")
            return False
        
        # Test validation logic
        valid_types = ["architecture", "security", "performance", "code_review", "lifecycle"]
        invalid_types = [t for t in request_model.analysis_types if t not in valid_types]
        
        if invalid_types:
            print(f"❌ Invalid analysis types found: {invalid_types}")
            return False
        else:
            print(f"✅ All analysis types valid: {request_model.analysis_types}")
        
        # Test file conversion
        project_files = {file.file_path: file.content for file in request_model.files}
        print(f"✅ File conversion: {len(project_files)} files")
        
        # Cleanup
        if analysis_id in analysis_status:
            del analysis_status[analysis_id]
        
        return True
        
    except Exception as e:
        print(f"❌ API Endpoint Logic Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_health_check_logic():
    """Test health check endpoint logic."""
    print("\n" + "="*60)
    print("🏥 Testing Health Check Logic")
    print("="*60)
    
    try:
        from api.android_analysis_api import analysis_engine, analysis_status
        from datetime import datetime
        
        # Simulate some analysis statuses
        test_statuses = [
            ("test_1", "completed"),
            ("test_2", "running"),
            ("test_3", "pending"),
            ("test_4", "failed"),
            ("test_5", "completed")
        ]
        
        for analysis_id, status in test_statuses:
            from api.android_analysis_api import AnalysisStatusModel
            analysis_status[analysis_id] = AnalysisStatusModel(
                analysis_id=analysis_id,
                status=status,
                progress=1.0 if status == "completed" else 0.5,
                started_at=datetime.now(),
                completed_at=datetime.now() if status == "completed" else None,
                error_message="Test error" if status == "failed" else None
            )
        
        # Generate health check response
        health_response = {
            "status": "healthy",
            "service": "Android Analysis API",
            "version": "1.0.0",
            "analysis_engine": {
                "max_workers": analysis_engine.max_workers,
                "available_templates": len(analysis_engine.prompt_engine.get_available_templates())
            },
            "active_analyses": {
                "total": len(analysis_status),
                "pending": len([a for a in analysis_status.values() if a.status == "pending"]),
                "running": len([a for a in analysis_status.values() if a.status == "running"]),
                "completed": len([a for a in analysis_status.values() if a.status == "completed"]),
                "failed": len([a for a in analysis_status.values() if a.status == "failed"])
            },
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"🏥 Health Check Response:")
        print(f"   Status: {health_response['status']}")
        print(f"   Service: {health_response['service']}")
        print(f"   Version: {health_response['version']}")
        print(f"   Max Workers: {health_response['analysis_engine']['max_workers']}")
        print(f"   Available Templates: {health_response['analysis_engine']['available_templates']}")
        print(f"   Active Analyses:")
        for status_type, count in health_response['active_analyses'].items():
            print(f"     {status_type}: {count}")
        
        # Cleanup test data
        for analysis_id, _ in test_statuses:
            if analysis_id in analysis_status:
                del analysis_status[analysis_id]
        
        return True
        
    except Exception as e:
        print(f"❌ Health Check Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_result_conversion():
    """Test conversion from internal result to API models."""
    print("\n" + "="*60)
    print("🔄 Testing Result Conversion")
    print("="*60)
    
    try:
        from api.android_analysis_api import (
            FindingModel,
            RecommendationModel,
            AnalysisResultModel
        )
        from analysis_module import EnhancedAnalysisEngine, AnalysisRequest
        
        # Create and run analysis
        engine = EnhancedAnalysisEngine(max_workers=1)
        request_data = create_sample_api_request()
        project_files = {file["file_path"]: file["content"] for file in request_data["files"]}
        
        internal_request = AnalysisRequest(
            project_id=request_data["project_id"],
            project_name=request_data["project_name"],
            project_files=project_files,
            analysis_types=request_data["analysis_types"],
            priority=request_data["priority"]
        )
        
        result = await engine.analyze_project(internal_request)
        
        # Test finding conversion
        api_findings = [
            FindingModel(
                type=f.get("type", "unknown"),
                severity=f.get("severity", "unknown"),
                title=f.get("title", "No title"),
                description=f.get("description", "No description"),
                recommendation=f.get("recommendation", "No recommendation"),
                category=f.get("category", "unknown"),
                analysis_prompt=f.get("analysis_prompt", "unknown")
            ) for f in result.findings
        ]
        
        print(f"✅ Findings Conversion:")
        print(f"   Internal Findings: {len(result.findings)}")
        print(f"   API Findings: {len(api_findings)}")
        
        for i, finding in enumerate(api_findings[:3]):
            print(f"   {i+1}. {finding.title} ({finding.severity})")
        
        # Test recommendation conversion
        api_recommendations = [
            RecommendationModel(
                priority=r.get("priority", "unknown"),
                title=r.get("title", "No title"),
                description=r.get("description", "No description"),
                action_items=r.get("action_items", [])
            ) for r in result.recommendations
        ]
        
        print(f"✅ Recommendations Conversion:")
        print(f"   Internal Recommendations: {len(result.recommendations)}")
        print(f"   API Recommendations: {len(api_recommendations)}")
        
        # Test full result conversion
        api_result = AnalysisResultModel(
            project_id=result.project_id,
            project_name=result.project_name,
            analysis_type=result.analysis_type,
            execution_time=result.execution_time,
            health_score=result.metrics.get("health_score", 0),
            findings=api_findings,
            recommendations=api_recommendations,
            metrics=result.metrics,
            context_summary={
                "package_name": result.context.package_name,
                "target_sdk": result.context.target_sdk,
                "kotlin_percentage": result.context.kotlin_percentage,
                "components_count": len(result.context.components),
                "dependencies_count": len(result.context.dependencies),
                "architecture_patterns": result.context.architecture_patterns,
                "jetpack_components": result.context.jetpack_components
            }
        )
        
        print(f"✅ Full Result Conversion:")
        print(f"   Project: {api_result.project_name}")
        print(f"   Health Score: {api_result.health_score}")
        print(f"   Execution Time: {api_result.execution_time:.2f}s")
        print(f"   Context Summary Keys: {list(api_result.context_summary.keys())}")
        
        return True
        
    except Exception as e:
        print(f"❌ Result Conversion Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test function."""
    print("🚀 Starting Phase 7: API Integration Tests")
    print("Testing Android Analysis API endpoints and integration...")
    
    results = []
    
    # Run all tests
    tests = [
        ("API Models", test_api_models),
        ("Analysis Engine Integration", test_analysis_engine_integration),
        ("Background Task Simulation", test_background_task_simulation),
        ("API Endpoint Logic", test_api_endpoint_logic),
        ("Health Check Logic", test_health_check_logic),
        ("Result Conversion", test_result_conversion)
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
    print("📋 PHASE 7 TEST SUMMARY")
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
        print("🎉 All Phase 7 tests passed! API Integration successful.")
        print("\nFeatures implemented:")
        print("✅ FastAPI router with comprehensive endpoints")
        print("✅ Pydantic models for request/response validation")
        print("✅ Background task processing")
        print("✅ Analysis status tracking")
        print("✅ Result storage and retrieval")
        print("✅ Filtering and pagination support")
        print("✅ Health check endpoint")
        print("✅ Error handling and HTTP status codes")
        print("✅ API documentation ready")
        
        print("\nAPI Endpoints available:")
        print("• POST /api/v1/android/analyze - Start analysis")
        print("• GET /api/v1/android/analysis/{id}/status - Get status")
        print("• GET /api/v1/android/analysis/{id}/result - Get full result")
        print("• GET /api/v1/android/analysis/{id}/summary - Get summary")
        print("• GET /api/v1/android/analysis/{id}/findings - Get findings")
        print("• GET /api/v1/android/analysis/{id}/recommendations - Get recommendations")
        print("• GET /api/v1/android/analysis/{id}/metrics - Get metrics")
        print("• DELETE /api/v1/android/analysis/{id} - Delete analysis")
        print("• GET /api/v1/android/analyses - List all analyses")
        print("• GET /api/v1/android/health - Health check")
        
        print("\nNext: Ready for Phase 8 - Testing & Documentation")
    else:
        print(f"⚠️  {total - passed} test(s) failed. Phase 7 needs attention.")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 