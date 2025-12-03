from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.image_routes import router as image_router
import uvicorn

app = FastAPI(
    title="Image Edit API",
    description="OpenAI DALL-E를 사용한 이미지 편집 및 캐리커처 합성 API",
    version="1.0.0"
)

# CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(image_router)

@app.get("/")
async def root():
    return {
        "message": "Image Edit API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "edit": "/api/v1/edit",
            "health": "/api/v1/health"
        }
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "message": "Image Edit API is running"}

@app.get("/api/v1/health")
async def health_v1():
    return {"status": "healthy", "message": "Image Edit API is running"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True,
        timeout_keep_alive=300,  # 5분으로 연결 유지 시간 증가
        timeout_graceful_shutdown=30  # graceful shutdown 시간
    )