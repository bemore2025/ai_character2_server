# Image Edit API

OpenAI DALL-E를 사용한 이미지 편집 및 캐리커처 합성 API

## 기능

- 두 이미지를 입력받아 캐리커처로 합성
- 커스텀 프롬프트를 통한 동적 이미지 편집
- FastAPI 기반 REST API
- 파일 업로드 및 검증

## 설치

```bash
pip install -r requirements.txt
```

## 환경 설정

`.env` 파일을 생성하고 OpenAI API 키를 설정하세요:

```bash
cp .env.example .env
# .env 파일에 OPENAI_API_KEY=your_key_here 추가
```

## 실행

```bash
python main.py
```

API는 `http://localhost:8000`에서 실행됩니다.

## API 문서

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 엔드포인트

### POST /api/v1/edit

두 이미지를 합성하여 캐리커처를 생성합니다.

**요청:**

- `image1`: 첫 번째 이미지 (multipart/form-data)
- `image2`: 두 번째 이미지 (multipart/form-data)
- `prompt`: 이미지 편집 프롬프트 (form-data)

**응답:**

```json
{
  "success": true,
  "image_data": "base64_encoded_image",
  "message": "이미지 합성이 성공적으로 완료되었습니다."
}
```

### GET /api/v1/health

API 상태 확인

## 사용 예시

### Python 클라이언트

```python
import requests

# 이미지 파일들 준비
files = {
    'image1': open('face.jpg', 'rb'),
    'image2': open('body.jpg', 'rb'),
    'prompt': (None, '첫 번째 이미지의 얼굴을 캐리커처 스타일로 변환하여 두 번째 이미지의 사람에게 합성해주세요. 배경은 투명하게 해줘.')
}

response = requests.post('http://localhost:8000/api/v1/edit', files=files)

if response.json()['success']:
    import base64
    image_data = base64.b64decode(response.json()['image_data'])
    with open('result.png', 'wb') as f:
        f.write(image_data)
    print('결과 이미지가 저장되었습니다.')
```

### cURL

```bash
curl -X POST "http://localhost:8000/api/v1/edit" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "image1=@face.jpg" \
  -F "image2=@body.jpg" \
  -F "prompt=첫 번째 이미지의 얼굴을 캐리커처 스타일로 변환하여 두 번째 이미지의 사람에게 합성해주세요. 배경은 투명하게 해줘."
```

## 프로젝트 구조

```
.
├── main.py                 # FastAPI 메인 애플리케이션
├── requirements.txt        # 의존성 패키지
├── .env.example           # 환경 변수 예시
└── app/
    ├── __init__.py
    ├── models/
    │   ├── __init__.py
    │   └── schemas.py      # Pydantic 모델
    ├── services/
    │   ├── __init__.py
    │   └── image_service.py # 이미지 처리 서비스
    └── routes/
        ├── __init__.py
        └── image_routes.py # API 라우터
```

## 제한사항

- 지원 파일 형식: JPEG, PNG
- 최대 파일 크기: 10MB
- OpenAI API 키 필요
