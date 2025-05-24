#!/usr/bin/env python3
"""
Test Analysis Agents for Android support
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.analysis_module.java_analysis_agent import JavaAnalysisAgent
from app.analysis_module.kotlin_analysis_agent import KotlinAnalysisAgent
from app.ckg_builder.java_parser import JavaParser
from app.ckg_builder.kotlin_parser import KotlinParser

def test_java_analysis_agent():
    print("☕ Testing Java Analysis Agent...")
    
    # Sample Java code with various issues
    java_code = '''package com.example.myapp;

import android.app.Service;
import android.content.Intent;
import android.os.IBinder;
import android.util.Log;
import java.util.List;
import java.util.ArrayList;

public class MyLargeService extends Service {
    
    private static final String TAG = "MyLargeService";
    private boolean isRunning = false;
    private List<String> data = new ArrayList<>();
    
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
    
    // Method with too many parameters
    public void processData(String param1, String param2, String param3, String param4,
                           String param5, String param6, String param7, String param8,
                           String param9, String param10) {
        // Complex method with string concatenation in loop
        String result = "";
        for (int i = 0; i < 100; i++) {
            result += "Item " + i + " ";
        }
        Log.d(TAG, result);
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
    
    // Many more methods to simulate a God class...
    public void method1() {}
    public void method2() {}
    public void method3() {}
    public void method4() {}
    public void method5() {}
    public void method6() {}
    public void method7() {}
    public void method8() {}
    public void method9() {}
    public void method10() {}
    public void method11() {}
    public void method12() {}
    public void method13() {}
    public void method14() {}
    public void method15() {}
    public void method16() {}
    public void method17() {}
    public void method18() {}
    public void method19() {}
    public void method20() {}
    public void method21() {}
    public void method22() {}
}'''

    # Parse Java code
    parser = JavaParser()
    parsed_result = parser.parse(java_code, "MyLargeService.java")
    
    if not parsed_result:
        print("❌ Failed to parse Java code")
        return False
    
    # Analyze with Java Analysis Agent
    agent = JavaAnalysisAgent()
    analysis_result = agent.analyze_parsed_file(parsed_result)
    
    print(f"✅ Java Analysis completed")
    print(f"   - Total code smells: {analysis_result['summary']['total_code_smells']}")
    print(f"   - Critical issues: {analysis_result['summary']['critical_issues']}")
    print(f"   - High issues: {analysis_result['summary']['high_issues']}")
    print(f"   - Design patterns: {analysis_result['summary']['patterns_detected']}")
    
    # Print some specific issues
    for smell in analysis_result['code_smells'][:3]:
        print(f"   - {smell['type']}: {smell['description']}")
    
    return len(analysis_result['code_smells']) > 0

def test_kotlin_analysis_agent():
    print("\n🎯 Testing Kotlin Analysis Agent...")
    
    # Sample Kotlin code with various issues
    kotlin_code = '''package com.example.myapp

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.runBlocking

class MainViewModel : ViewModel() {
    
    // Mutable properties that could be immutable
    var _isLoading = false
    var _data = mutableListOf<String>()
    var _error: String? = null
    
    val isLoading: Boolean get() = _isLoading
    
    // Function with force unwrapping
    fun loadData() {
        val data = getData()!!  // Force unwrapping
        
        // Using GlobalScope (bad practice)
        GlobalScope.launch {
            _isLoading = true
            try {
                delay(1000)
                val result = fetchDataFromNetwork()
                _data.addAll(result)
            } finally {
                _isLoading = false
            }
        }
    }
    
    // Suspend function with blocking call
    suspend fun fetchDataFromNetwork(): List<String> {
        Thread.sleep(500)  // Blocking call in suspend function
        return listOf("Data 1", "Data 2", "Data 3")
    }
    
    // Function with excessive scope function usage
    fun processData() {
        _data.let { data ->
            data.run { 
                this.apply {
                    this.also { list ->
                        list.let { items ->
                            items.forEach { item ->
                                println(item)
                            }
                        }
                    }
                }
            }
        }
    }
    
    // Function with complex string templates
    fun generateReport(): String {
        return "Report: ${_data.size} items, loading: ${_isLoading}, error: ${_error ?: "none"}, " +
               "timestamp: ${System.currentTimeMillis()}, user: ${getCurrentUser()}, " +
               "version: ${getAppVersion()}, build: ${getBuildNumber()}"
    }
    
    private fun getData(): String? = null
    private fun getCurrentUser(): String = "user"
    private fun getAppVersion(): String = "1.0"
    private fun getBuildNumber(): String = "123"
    
    companion object {
        const val TAG = "MainViewModel"
    }
}

// Class that could be a data class
class User {
    val id: Long
    val name: String
    val email: String?
    
    constructor(id: Long, name: String, email: String?) {
        this.id = id
        this.name = name
        this.email = email
    }
}

// Data class with too many mutable properties
data class LargeDataClass(
    var prop1: String,
    var prop2: String,
    var prop3: String,
    var prop4: String,
    var prop5: String,
    var prop6: String,
    var prop7: String,
    var prop8: String,
    var prop9: String,
    var prop10: String,
    var prop11: String,
    var prop12: String
)'''

    # Parse Kotlin code
    parser = KotlinParser()
    parsed_result = parser.parse(kotlin_code, "MainViewModel.kt")
    
    if not parsed_result:
        print("❌ Failed to parse Kotlin code")
        return False
    
    # Analyze with Kotlin Analysis Agent
    agent = KotlinAnalysisAgent()
    analysis_result = agent.analyze_parsed_file(parsed_result)
    
    print(f"✅ Kotlin Analysis completed")
    print(f"   - Total issues: {analysis_result['summary']['total_issues']}")
    print(f"   - Idiom issues: {analysis_result['summary']['idiom_issues']}")
    print(f"   - Coroutine issues: {analysis_result['summary']['coroutine_issues']}")
    print(f"   - High priority: {analysis_result['summary']['high_priority']}")
    
    # Print some specific issues
    for issue in analysis_result['idiom_issues'][:3]:
        print(f"   - {issue['type']}: {issue['description']}")
    
    for issue in analysis_result['coroutine_issues'][:2]:
        print(f"   - {issue['type']}: {issue['description']}")
    
    return len(analysis_result['idiom_issues']) > 0 or len(analysis_result['coroutine_issues']) > 0

def test_integration():
    print("\n🔧 Testing Analysis Agent Integration...")
    
    # Test with real parsed data from previous tests
    java_parser = JavaParser()
    kotlin_parser = KotlinParser()
    
    # Simple test cases
    simple_java = '''
    public class SimpleClass {
        public void simpleMethod() {
            System.out.println("Hello");
        }
    }
    '''
    
    simple_kotlin = '''
    class SimpleClass {
        fun simpleMethod() {
            println("Hello")
        }
    }
    '''
    
    java_result = java_parser.parse(simple_java, "SimpleClass.java")
    kotlin_result = kotlin_parser.parse(simple_kotlin, "SimpleClass.kt")
    
    if java_result and kotlin_result:
        java_agent = JavaAnalysisAgent()
        kotlin_agent = KotlinAnalysisAgent()
        
        java_analysis = java_agent.analyze_parsed_file(java_result)
        kotlin_analysis = kotlin_agent.analyze_parsed_file(kotlin_result)
        
        print(f"✅ Integration test passed")
        print(f"   - Java analysis: {java_analysis['summary']}")
        print(f"   - Kotlin analysis: {kotlin_analysis['summary']}")
        
        return True
    else:
        print("❌ Integration test failed")
        return False

def main():
    print("🚀 Testing Analysis Agents for Android Support...\n")
    
    results = []
    
    try:
        results.append(test_java_analysis_agent())
    except Exception as e:
        print(f"❌ Java Analysis Agent failed: {e}")
        results.append(False)
    
    try:
        results.append(test_kotlin_analysis_agent())
    except Exception as e:
        print(f"❌ Kotlin Analysis Agent failed: {e}")
        results.append(False)
    
    try:
        results.append(test_integration())
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        results.append(False)
    
    print("\n" + "="*50)
    if all(results):
        print("✅ All Analysis Agent tests PASSED!")
        print("🎉 Phase 4: Language-Specific Analysis Agents completed!")
    else:
        print("❌ Some Analysis Agent tests failed!")
        print(f"Results: Java={results[0]}, Kotlin={results[1]}, Integration={results[2]}")
    print("="*50)

if __name__ == "__main__":
    main() 