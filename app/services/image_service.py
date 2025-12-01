import os
import base64
import re
import httpx
from openai import OpenAI
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

class ImageService:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def download_image(self, image_url: str) -> bytes:
        """URL, data URL, 또는 순수 base64 문자열을 이미지 바이트로 변환"""
        s = (image_url or "").strip()

        # data URL 처리
        if s.startswith('data:'):
            print(f"[DEBUG] Base64 data URL 감지, 디코딩 시작")
            base64_data = s.split(',', 1)[1] if ',' in s else s
            base64_data = base64_data.strip()
            try:
                decoded = base64.b64decode(base64_data)
                print(f"[DEBUG] Base64 디코딩 완료: {len(decoded)} bytes")
                return decoded
            except Exception as _:
                print(f"[DEBUG] Base64 data URL 디코딩 실패, 다른 방식 시도")

        # 순수 base64 문자열 처리 (스킴이 없고, 길고, base64 문자셋으로만 구성)
        if '://' not in s:
            s_clean = s.replace('\n', '').replace('\r', '')
            if len(s_clean) > 1000 and re.fullmatch(r'[A-Za-z0-9+/=_-]+', s_clean) is not None:
                print(f"[DEBUG] 순수 base64 감지, 디코딩 시작")
                try:
                    try:
                        decoded = base64.b64decode(s_clean, validate=True)
                    except Exception:
                        # URL-safe base64 대응 및 패딩 보정
                        padded = s_clean + '=' * ((4 - len(s_clean) % 4) % 4)
                        decoded = base64.urlsafe_b64decode(padded)
                    print(f"[DEBUG] 순수 base64 디코딩 완료: {len(decoded)} bytes")
                    return decoded
                except Exception as _:
                    print(f"[DEBUG] 순수 base64 디코딩 실패, URL로 처리 시도")

        # 일반 URL 다운로드
        print(f"[DEBUG] 일반 URL 다운로드 시작: {s}")
        async with httpx.AsyncClient() as client:
            response = await client.get(s, timeout=30.0)
            response.raise_for_status()
            print(f"[DEBUG] URL 다운로드 완료: {len(response.content)} bytes")
            return response.content
    
    def create_file(self, file_content: bytes, filename: str) -> str:
        """OpenAI에 파일 업로드하고 file_id 반환"""
        import tempfile
        
        print(f"[DEBUG] create_file 호출: filename={filename}, size={len(file_content)} bytes")
        
        # 파일 내용을 임시 파일로 저장
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
        
        print(f"[DEBUG] 임시 파일 생성: {temp_file_path}")
        
        try:
            with open(temp_file_path, "rb") as f:
                print(f"[DEBUG] Files API 호출 시작")
                result = self.client.files.create(
                    file=f,
                    purpose="vision",
                )
                print(f"[DEBUG] Files API 호출 완료: file_id={result.id}")
                return result.id
        finally:
            # 임시 파일 삭제
            os.unlink(temp_file_path)
            print(f"[DEBUG] 임시 파일 삭제 완료")
    
    async def edit_images(self, image1_url: str, image2_url: str, custom_prompt: Optional[str] = None) -> Optional[str]:
        """두 이미지를 2단계로 합성하여 캐리커처 생성
        1단계: 얼굴 합성 (첫 번째 이미지 얼굴 + 두 번째 이미지 화풍)
        2단계: 포즈 변경 (1단계 결과물 + custom_prompt 포즈)
        """
        try:
            # 이미지 다운로드 및 파일 업로드
            print(f"[DEBUG] 이미지 다운로드 시작: {image1_url}, {image2_url}")
            image1_content = await self.download_image(image1_url)
            image2_content = await self.download_image(image2_url)
            print(f"[DEBUG] 이미지 다운로드 완료. 크기: {len(image1_content)} bytes, {len(image2_content)} bytes")
            
            # OpenAI Files API에 업로드
            image1_filename = image1_url.split('/')[-1] or "image1.jpg"
            image2_filename = image2_url.split('/')[-1] or "image2.jpg"
            
            print(f"[DEBUG] 파일 업로드 시작: {image1_filename}, {image2_filename}")
            file_id1 = self.create_file(image1_content, image1_filename)
            file_id2 = self.create_file(image2_content, image2_filename)
            print(f"[DEBUG] 파일 업로드 완료. file_id1={file_id1}, file_id2={file_id2}")

            # === 1단계: 얼굴 + 화풍 합성 ===
            step1_prompt = """
첫 번째 이미지의 얼굴을 참고하여, 두 번째 이미지의 화풍으로 캐리커처를 생성하세요:

**첫 번째 이미지에서 참고:**
- 얼굴 특징(눈, 코, 입, 얼굴형) 정확하게 참고
- 헤어스타일과 색상 참고
- 눈을 크게 묘사하면서 원본 특징 유지

**두 번째 이미지에서 참고:**
- 몸통의 그림 화풍과 스타일 참고
- 단순한 캐릭터 스타일
- 굵고 부드러운 선
- 의상 스타일

**전체 적용:**
- 날씬한 얼굴형
- 귀여운 만화 스타일
- 자연스러운 표정
- 배경색은 하늘색
- 전신이 다 나오게 그려줘
"""

            # 1단계 API 호출 (File ID 사용)
            print(f"[DEBUG] 1단계 API 호출 시작")
            print(f"[DEBUG] Request payload: model=gpt-4.1, file_ids=[{file_id1}, {file_id2}]")
            response1 = self.client.responses.create(
                model="gpt-4.1",
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": step1_prompt},
                            {
                                "type": "input_image",
                                "file_id": file_id1,
                            },
                            {
                                "type": "input_image",
                                "file_id": file_id2,
                            }
                        ],
                    }
                ],
                tools=[{"type": "image_generation"}],
            )
            print(f"[DEBUG] 1단계 API 호출 완료")

            # 1단계 결과 추출
            image_generation_calls = [
                output
                for output in response1.output
                if output.type == "image_generation_call"
            ]

            if not image_generation_calls:
                print(f"[ERROR] 1단계 결과에서 image_generation_call을 찾을 수 없음")
                return None

            step1_image_url = image_generation_calls[0].result
            print(f"[DEBUG] 1단계 결과 URL 길이: {len(step1_image_url)} chars")
            print(f"[DEBUG] 1단계 결과 URL 시작 부분: {step1_image_url[:100]}...")

            # custom_prompt가 없으면 1단계 결과 그대로 반환
            if not custom_prompt or not custom_prompt.strip():
                return step1_image_url

            # === 2단계: 포즈 변경 ===
            # 1단계 결과 이미지 다운로드 및 파일 업로드
            step1_content = await self.download_image(step1_image_url)
            file_id_step1 = self.create_file(step1_content, "step1_result.png")
            
            step2_prompt = f"""
이미지의 화풍과 얼굴, 몸통, 의상을 그대로 유지하면서 포즈만 변경해주세요:

**절대 변경하지 말 것:**
- 그림 화풍 (선 굵기, 색감, 채색 스타일)
- 얼굴 특징
- 헤어스타일
- 의상 디자인과 색상
- 체형과 몸의 형상

**변경할 것:**
- 포즈와 자세만 다음과 같이 변경: {custom_prompt.strip()}
- 전신이 다 나오게 그려줘
"""

            # 2단계 API 호출 (File ID 사용)
            response2 = self.client.responses.create(
                model="gpt-4.1",
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": step2_prompt},
                            {
                                "type": "input_image",
                                "file_id": file_id_step1,
                            }
                        ],
                    }
                ],
                tools=[{"type": "image_generation"}],
            )

            # 2단계 결과 추출
            image_generation_calls2 = [
                output
                for output in response2.output
                if output.type == "image_generation_call"
            ]

            if image_generation_calls2:
                return image_generation_calls2[0].result
            else:
                return step1_image_url  # 2단계 실패시 1단계 결과 반환

        except Exception as e:
            print(f"[ERROR] 이미지 처리 중 오류 발생: {str(e)}")
            print(f"[ERROR] 오류 타입: {type(e).__name__}")
            import traceback
            print(f"[ERROR] 상세 스택:\n{traceback.format_exc()}")
            return None
