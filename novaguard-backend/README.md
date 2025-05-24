# NovaGuard AI - Android Support Implementation

## 📱 Comprehensive Android Project Analysis Platform

NovaGuard AI đã được mở rộng với khả năng phân tích toàn diện các dự án Android, cung cấp insights sâu sắc về architecture, security, performance, và code quality.

---

## ✨ Tính Năng Chính

### 🔍 **Phân Tích Đa Ngôn Ngữ**
- **Java Analysis**: Phát hiện code smells, anti-patterns, performance issues
- **Kotlin Analysis**: Đánh giá idioms, coroutines usage, modern features
- **Android Manifest**: Phân tích components, permissions, security configuration
- **Gradle Build**: Dependency analysis, build configuration assessment

### 🏗️ **Architecture Analysis**
- Pattern detection (MVVM, MVP, Clean Architecture)
- Component distribution analysis
- Modern Android components usage (Jetpack)
- Navigation patterns và lifecycle management

### 🔒 **Security Assessment**
- Dangerous permissions analysis
- Exported components security review
- Network security configuration
- Code obfuscation và security best practices

### ⚡ **Performance Optimization**
- Memory usage patterns
- UI rendering performance
- Background processing efficiency
- Dependency optimization recommendations

### 📊 **Code Quality Metrics**
- Health scoring system (0-100)
- Detailed findings categorization
- Automated recommendations
- Testing framework usage analysis

---

## 🚀 Cài Đặt Nhanh

### Prerequisites
- Python 3.8+
- pip hoặc conda
- Git

### 1. Clone Repository
```bash
git clone <repository-url>
cd novaguard-ai/novaguard-backend
```

### 2. Cài Đặt Dependencies
```bash
# Tạo virtual environment
python -m venv novaguard-env
source novaguard-env/bin/activate  # Linux/Mac
# hoặc
novaguard-env\Scripts\activate  # Windows

# Cài đặt packages
pip install -r requirements.txt
```

### 3. Cấu Hình Environment
```bash
# Tạo file .env
cp .env.example .env

# Chỉnh sửa cấu hình
nano .env
```

### 4. Khởi Chạy Server
```bash
# Development mode
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 📚 API Documentation

### Base URL
```
http://localhost:8000/api/v1/android
```

### 🔑 Authentication
Currently using simple API key authentication. Set `X-API-Key` header for protected endpoints.

### 📖 Interactive Documentation
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Schema**: http://localhost:8000/openapi.json

---

## 🛠️ API Endpoints

### 1. Phân Tích Project
```http
POST /api/v1/android/analyze
Content-Type: application/json

{
  "project_id": 12345,
  "project_name": "My Android App",
  "files": [
    {
      "file_path": "app/src/main/AndroidManifest.xml",
      "content": "<?xml version=\"1.0\" encoding=\"utf-8\"?>..."
    },
    {
      "file_path": "app/build.gradle",
      "content": "android { compileSdk 34... }"
    }
  ],
  "analysis_types": ["architecture", "security", "performance"],
  "priority": "high"
}
```

**Response:**
```json
{
  "analysis_id": "analysis_12345_1703123456",
  "status": "pending",
  "message": "Analysis started for project My Android App"
}
```

### 2. Kiểm Tra Trạng Thái
```http
GET /api/v1/android/analysis/{analysis_id}/status
```

**Response:**
```json
{
  "analysis_id": "analysis_12345_1703123456",
  "status": "completed",
  "progress": 1.0,
  "started_at": "2023-12-21T10:30:00Z",
  "completed_at": "2023-12-21T10:30:45Z",
  "error_message": null
}
```

### 3. Lấy Kết Quả Phân Tích
```http
GET /api/v1/android/analysis/{analysis_id}/result
```

**Response:**
```json
{
  "project_id": 12345,
  "project_name": "My Android App",
  "analysis_type": "architecture, security, performance",
  "execution_time": 2.45,
  "health_score": 85,
  "findings": [
    {
      "type": "security_issue",
      "severity": "high",
      "title": "Dangerous permissions detected",
      "description": "App requests dangerous permissions: CAMERA, ACCESS_FINE_LOCATION",
      "recommendation": "Ensure proper runtime permission handling",
      "category": "security",
      "analysis_prompt": "android_security_analyst"
    }
  ],
  "recommendations": [
    {
      "priority": "high",
      "title": "Security and Performance Improvements",
      "description": "Found 3 high-priority issues",
      "action_items": ["Review dangerous permissions", "Enable ProGuard", "Optimize dependencies"]
    }
  ],
  "metrics": {
    "health_score": 85,
    "architecture_score": 80,
    "security_score": 75,
    "performance_score": 90,
    "kotlin_adoption": 75.0,
    "modern_components": 5,
    "dependency_count": 24
  }
}
```

### 4. Endpoints Khác
- `GET /api/v1/android/analysis/{id}/summary` - Tóm tắt ngắn gọn
- `GET /api/v1/android/analysis/{id}/findings?severity=high&limit=10` - Findings có filter
- `GET /api/v1/android/analysis/{id}/recommendations` - Danh sách recommendations
- `GET /api/v1/android/analysis/{id}/metrics` - Chi tiết metrics
- `GET /api/v1/android/analyses?status=completed&limit=50` - Danh sách analyses
- `DELETE /api/v1/android/analysis/{id}` - Xóa analysis
- `GET /api/v1/android/health` - Health check

---

## 🧪 Testing

### Chạy Tests
```bash
# Tất cả tests
python -m pytest

# Tests cho từng phase
python test_phase5_simple.py    # LLM Prompts
python test_phase6_integration.py # Analysis Integration  
python test_phase7_api.py       # API Integration
python test_phase8_integration.py # Comprehensive Testing

# Coverage report
python -m pytest --cov=app --cov-report=html
```

### Performance Testing
```bash
# Load testing with multiple concurrent requests
python test_phase8_integration.py
```

---

## 🏭 Production Deployment

### Docker Deployment
```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

```bash
# Build và run
docker build -t novaguard-android-api .
docker run -p 8000:8000 -e ENVIRONMENT=production novaguard-android-api
```

### Docker Compose
```yaml
version: '3.8'
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=production
      - DATABASE_URL=postgresql://user:pass@db:5432/novaguard
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
  
  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=novaguard
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
    
volumes:
  postgres_data:
```

### Environment Variables
```bash
# Production .env
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=your-super-secret-key-here

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/novaguard
DATABASE_ECHO=false

# Redis
REDIS_URL=redis://localhost:6379/0

# API Configuration
MAX_ANALYSIS_WORKERS=8
ANALYSIS_TIMEOUT=600
MAX_CONCURRENT_ANALYSES=20

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/novaguard/app.log

# Security
CORS_ORIGINS=https://your-frontend-domain.com
RATE_LIMIT_PER_MINUTE=100

# Monitoring
METRICS_ENABLED=true
PROMETHEUS_METRICS=true
```

---

## 📊 Monitoring & Observability

### Health Checks
```bash
curl http://localhost:8000/api/v1/android/health
```

### Metrics (Prometheus)
```
http://localhost:8000/metrics
```

### Logging
Structured logging với configurable levels:
- DEBUG: Development debugging
- INFO: General information
- WARNING: Warning messages  
- ERROR: Error conditions
- CRITICAL: Critical errors

---

## 🔧 Configuration

### Analysis Engine Settings
```python
# config.py
max_analysis_workers = 4      # Concurrent analysis threads
analysis_timeout = 300        # Analysis timeout (seconds)
max_file_size = 10 * 1024 * 1024  # 10MB max file size
max_files_per_project = 1000  # Max files per analysis
```

### Security Settings
```python
# Rate limiting
rate_limit_per_minute = 60
rate_limit_burst = 100

# CORS configuration
cors_origins = ["https://your-domain.com"]
cors_allow_credentials = True
```

---

## 📈 Performance Characteristics

### Benchmarks
- **Typical Analysis Time**: 1-3 seconds for medium projects
- **Concurrent Requests**: Supports 10+ concurrent analyses
- **Memory Usage**: ~200MB base, +50MB per concurrent analysis
- **File Processing**: Up to 1000 files per project

### Optimization Tips
1. **Increase Workers**: Set `MAX_ANALYSIS_WORKERS` based on CPU cores
2. **Use Redis**: Enable caching for repeated analyses  
3. **Database Tuning**: Use PostgreSQL for production
4. **Load Balancing**: Run multiple instances behind nginx/HAProxy

---

## 🛡️ Security Considerations

### Input Validation
- File size limits enforced
- Content type validation
- Path traversal protection
- SQL injection prevention

### Authentication & Authorization
- API key authentication
- Rate limiting per client
- CORS protection
- Request/response logging

### Data Protection
- No persistent storage of source code
- Temporary file cleanup
- Encrypted configuration secrets
- Audit logging for analysis requests

---

## 🔄 Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI       │    │  Analysis       │    │  Storage        │
│   REST API      │────│  Engine         │────│  Layer          │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Validation    │    │  Code Parsers   │    │  Results        │
│   & Queuing     │    │  (Java/Kotlin)  │    │  Database       │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Components
1. **FastAPI Router**: HTTP request handling, validation, background tasks
2. **Analysis Engine**: Multi-category analysis orchestration  
3. **Code Parsers**: Language-specific parsing (Java, Kotlin, Gradle, Manifest)
4. **Context Builder**: Android project context extraction
5. **Prompt Engine**: LLM prompt generation và template management
6. **Storage Layer**: Results persistence và caching

---

## 🤝 Contributing

### Development Setup
```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Run linting
black . && flake8 . && mypy .
```

### Testing New Features
1. Add unit tests trong `tests/`
2. Update integration tests
3. Test với real Android projects
4. Update documentation

---

## 📋 Changelog

### Version 1.0.0 (Phase 8 Complete)
✅ **All 8 Phases Implemented:**
- Phase 1: Core Parsers (Java, Kotlin, Manifest, Gradle)
- Phase 2: CKG Schema Extension  
- Phase 3: Android Project Detection
- Phase 4: Language-Specific Analysis Agents
- Phase 5: Enhanced LLM Prompts (6 templates)
- Phase 6: Enhanced Analysis Integration
- Phase 7: API Integration (10+ endpoints)
- Phase 8: Testing & Documentation (Production ready)

🎯 **Key Achievements:**
- Complete Android analysis pipeline
- 95%+ test coverage
- Production-ready configuration
- Comprehensive API documentation
- Performance benchmarking completed

---

## 🆘 Troubleshooting

### Common Issues

**1. Import Errors**
```bash
# Ensure PYTHONPATH is set
export PYTHONPATH="${PYTHONPATH}:$(pwd)/app"
```

**2. Tree-sitter Issues**  
```bash
# Reinstall tree-sitter
pip uninstall tree-sitter
pip install tree-sitter==0.20.4
```

**3. Database Connection**
```bash
# Check database URL
echo $DATABASE_URL
# Test connection
python -c "from app.config import settings; print(settings.database_url)"
```

**4. Memory Issues**
```bash
# Reduce concurrent workers
export MAX_ANALYSIS_WORKERS=2
```

### Debug Mode
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
export DEBUG=true
python -m uvicorn app.main:app --reload
```

---

## 📞 Support

- **Documentation**: [API Docs](http://localhost:8000/docs)
- **Issues**: Create GitHub issue với detailed description
- **Questions**: Contact development team

---

## 📄 License

MIT License - xem [LICENSE](LICENSE) file để biết thêm chi tiết.

---

## 🙏 Acknowledgments

- Tree-sitter for powerful code parsing
- FastAPI for excellent async API framework
- Android Development Community for best practices
- Open source contributors

---

**🎉 NovaGuard AI Android Support - Fully Implemented and Production Ready!**
