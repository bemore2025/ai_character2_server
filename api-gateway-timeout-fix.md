# API Gateway 타임아웃 문제 해결 가이드

## 문제 상황

- API Gateway URL: `https://9wdz4rve0l.execute-api.ap-northeast-2.amazonaws.com/`
- EC2 백엔드: `http://43.201.75.62:8000`
- 증상: API Gateway를 통한 요청이 다운됨 (타임아웃)

## 원인

API Gateway의 통합 타임아웃 제한:

- **HTTP/HTTP_PROXY 통합**: 최대 29초 (변경 불가)
- **Lambda 통합**: 최대 15분 (900초)

이미지 생성 작업은 2-3분 소요되므로 HTTP 통합으로는 불가능합니다.

## 해결 방법

### 방법 1: 비동기 처리 (권장)

#### 1-1. 백엔드에 비동기 작업 큐 추가

```python
# app/services/async_job_service.py
import uuid
from typing import Dict, Optional
import asyncio
from datetime import datetime

class AsyncJobService:
    def __init__(self):
        self.jobs: Dict[str, dict] = {}

    def create_job(self, job_type: str, params: dict) -> str:
        """작업 생성 및 job_id 반환"""
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = {
            'status': 'pending',
            'job_type': job_type,
            'params': params,
            'created_at': datetime.now().isoformat(),
            'result': None,
            'error': None
        }
        return job_id

    def get_job_status(self, job_id: str) -> Optional[dict]:
        """작업 상태 조회"""
        return self.jobs.get(job_id)

    def update_job(self, job_id: str, status: str, result=None, error=None):
        """작업 상태 업데이트"""
        if job_id in self.jobs:
            self.jobs[job_id]['status'] = status
            self.jobs[job_id]['result'] = result
            self.jobs[job_id]['error'] = error
            self.jobs[job_id]['updated_at'] = datetime.now().isoformat()

# 전역 인스턴스
async_job_service = AsyncJobService()
```

#### 1-2. 비동기 엔드포인트 추가

```python
# app/routes/image_routes.py에 추가

from app.services.async_job_service import async_job_service
import asyncio

@router.post("/cartoonize/async", response_model=dict)
async def cartoonize_image_async(request: CartoonizeRequest):
    """
    비동기 이미지 생성 시작
    즉시 job_id를 반환하고 백그라운드에서 처리
    """
    # job_id 생성
    job_id = async_job_service.create_job(
        job_type='cartoonize',
        params={
            'image_url': str(request.image_url),
            'character_id': request.character_id,
            'custom_prompt': request.custom_prompt
        }
    )

    # 백그라운드 작업 시작
    asyncio.create_task(process_cartoonize_job(job_id, request))

    return {
        'success': True,
        'job_id': job_id,
        'status': 'pending',
        'message': '작업이 시작되었습니다. job_id로 상태를 확인하세요.'
    }

@router.get("/job/{job_id}", response_model=dict)
async def get_job_status(job_id: str):
    """작업 상태 조회"""
    job = async_job_service.get_job_status(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    return {
        'success': True,
        'job_id': job_id,
        'status': job['status'],
        'result': job.get('result'),
        'error': job.get('error'),
        'created_at': job.get('created_at'),
        'updated_at': job.get('updated_at')
    }

async def process_cartoonize_job(job_id: str, request: CartoonizeRequest):
    """백그라운드에서 실제 작업 처리"""
    try:
        async_job_service.update_job(job_id, 'processing')

        # 실제 이미지 생성
        result = await image_service.cartoonize_with_character(
            image_url=str(request.image_url),
            character_id=request.character_id,
            custom_prompt=request.custom_prompt
        )

        if result['success']:
            async_job_service.update_job(
                job_id,
                'completed',
                result=result
            )
        else:
            async_job_service.update_job(
                job_id,
                'failed',
                error=result.get('error')
            )
    except Exception as e:
        async_job_service.update_job(
            job_id,
            'failed',
            error=str(e)
        )
```

#### 1-3. 프론트엔드 폴링 패턴

```javascript
// 비동기 작업 시작
async function startCartoonize(imageUrl, characterId, customPrompt) {
  const response = await fetch("/api/v1/cartoonize/async", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      image_url: imageUrl,
      character_id: characterId,
      custom_prompt: customPrompt,
    }),
  });

  const data = await response.json();
  return data.job_id;
}

// 작업 상태 폴링
async function pollJobStatus(jobId, onProgress) {
  const maxAttempts = 60; // 최대 5분 (5초 간격)
  let attempts = 0;

  while (attempts < maxAttempts) {
    const response = await fetch(`/api/v1/job/${jobId}`);
    const data = await response.json();

    onProgress(data);

    if (data.status === "completed") {
      return data.result;
    } else if (data.status === "failed") {
      throw new Error(data.error || "작업 실패");
    }

    // 5초 대기
    await new Promise((resolve) => setTimeout(resolve, 5000));
    attempts++;
  }

  throw new Error("작업 타임아웃");
}

// 사용 예시
async function createCartoon() {
  try {
    // 1. 작업 시작
    const jobId = await startCartoonize(imageUrl, characterId, prompt);
    console.log("작업 시작:", jobId);

    // 2. 상태 폴링
    const result = await pollJobStatus(jobId, (status) => {
      console.log("진행 상태:", status.status);
      // UI 업데이트 (로딩 표시 등)
    });

    // 3. 완료
    console.log("완료:", result.result_image_url);
  } catch (error) {
    console.error("에러:", error);
  }
}
```

### 방법 2: WebSocket 사용 (실시간 진행 상황)

```python
# main.py에 WebSocket 추가
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws/cartoonize")
async def websocket_cartoonize(websocket: WebSocket):
    await websocket.accept()

    try:
        # 클라이언트로부터 요청 받기
        data = await websocket.receive_json()

        # 진행 상황 전송하면서 작업 수행
        await websocket.send_json({'status': 'started'})

        # 실제 작업 (진행 상황 전송)
        result = await image_service.cartoonize_with_character(
            image_url=data['image_url'],
            character_id=data['character_id'],
            custom_prompt=data.get('custom_prompt')
        )

        # 결과 전송
        await websocket.send_json({
            'status': 'completed',
            'result': result
        })

    except WebSocketDisconnect:
        print("WebSocket 연결 종료")
    except Exception as e:
        await websocket.send_json({
            'status': 'error',
            'error': str(e)
        })
```

### 방법 3: API Gateway 설정 변경 (제한적)

API Gateway 콘솔에서:

1. **통합 요청** → **통합 유형**을 확인
2. HTTP 통합인 경우 → **Lambda 프록시 통합**으로 변경 고려
3. 또는 **Application Load Balancer** 직접 연결

**주의**: HTTP 통합은 29초 제한을 변경할 수 없습니다.

### 방법 4: ALB 직접 사용 (권장)

API Gateway 대신 Application Load Balancer 사용:

1. **ALB 생성**

   - Target Group: EC2 인스턴스 (43.201.75.62:8000)
   - Health Check: `/health`
   - Timeout: 300초로 설정

2. **보안 그룹 설정**

   - ALB → EC2: 8000 포트 허용

3. **프론트엔드 URL 변경**
   - API Gateway URL → ALB DNS 이름

## 권장 솔루션

**단기**: 방법 1 (비동기 처리) 구현

- API Gateway 29초 제한 우회
- 프론트엔드 변경 최소화
- 즉시 적용 가능

**장기**: 방법 4 (ALB 사용)

- 타임아웃 제한 없음
- 더 나은 성능
- 비용 효율적

## 즉시 테스트 가능한 임시 방법

직접 EC2 IP로 테스트:

```bash
# API Gateway 우회하고 직접 EC2로 요청
curl -X POST http://43.201.75.62:8000/api/v1/cartoonize \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "your-image-url",
    "character_id": "character-id",
    "custom_prompt": "optional-prompt"
  }'
```

이렇게 하면 타임아웃 없이 작동합니다.
