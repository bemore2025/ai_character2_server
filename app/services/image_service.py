import os
import base64
import re
import httpx
from openai import OpenAI
from dotenv import load_dotenv
from typing import Optional
from supabase import create_client, Client
import random
import uuid

load_dotenv()

class ImageService:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.supabase = self._get_supabase_client()

    def _get_supabase_client(self) -> Optional[Client]:
        """Supabase 클라이언트를 설정합니다."""
        try:
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_ACCESS_KEY")

            if not url or not key:
                print("[WARNING] SUPABASE_URL 또는 SUPABASE_ACCESS_KEY 환경변수가 설정되지 않았습니다.")
                return None

            return create_client(url, key)
        except Exception as e:
            print(f"[ERROR] Supabase 클라이언트 초기화 실패: {e}")
            return None

    def get_random_character_image(self, character_id: str) -> Optional[str]:
        """
        character_id를 이용해 character 테이블에서 picture_cartoon 중 랜덤한 이미지 URL을 반환합니다.

        Args:
            character_id (str): 찾을 캐릭터의 ID

        Returns:
            str: 랜덤하게 선택된 이미지 URL
            None: 에러가 발생하거나 데이터가 없는 경우
        """
        try:
            if not self.supabase:
                print("[ERROR] Supabase 클라이언트가 초기화되지 않았습니다.")
                return None

            # character 테이블에서 해당 ID의 picture_cartoon 가져오기
            response = self.supabase.table("character").select("picture_cartoon").eq("id", character_id).execute()

            if not response.data:
                print(f"[ERROR] 캐릭터 ID {character_id}를 찾을 수 없습니다.")
                return None

            picture_cartoon = response.data[0].get("picture_cartoon")

            if not picture_cartoon or not isinstance(picture_cartoon, list) or len(picture_cartoon) == 0:
                print(f"[ERROR] 캐릭터 ID {character_id}의 picture_cartoon이 비어있거나 올바르지 않습니다.")
                return None

            # 리스트에서 랜덤하게 하나 선택
            random_item = random.choice(picture_cartoon)

            # 딕셔너리 형태인 경우 url 키의 값을 추출
            if isinstance(random_item, dict) and 'url' in random_item:
                return random_item['url']
            # 문자열인 경우 그대로 반환
            elif isinstance(random_item, str):
                return random_item
            else:
                print(f"[ERROR] 예상치 못한 데이터 형태: {type(random_item)}, 값: {random_item}")
                return None

        except Exception as e:
            print(f"[ERROR] 캐릭터 이미지 가져오기 중 오류 발생: {str(e)}")
            return None

    def upload_image_to_supabase(self, image_data: bytes, file_name: str = None) -> Optional[str]:
        """
        이미지 데이터를 Supabase 스토리지에 업로드하고 공개 URL을 반환합니다.

        Args:
            image_data (bytes): 업로드할 이미지 데이터
            file_name (str): 파일명 (None인 경우 UUID로 생성)

        Returns:
            str: 업로드된 이미지의 공개 URL
            None: 에러가 발생한 경우
        """
        try:
            if not self.supabase:
                print("[ERROR] Supabase 클라이언트가 초기화되지 않았습니다.")
                return None

            # 파일명 생성
            if not file_name:
                file_name = f"cartoon_{uuid.uuid4().hex}.png"

            print(f"[DEBUG] Supabase에 이미지 업로드 중: {file_name}")

            # 버킷명
            bucket_name = "images"

            # 이미지 업로드
            upload_response = self.supabase.storage.from_(bucket_name).upload(
                path=file_name,
                file=image_data,
                file_options={"content-type": "image/png"}
            )

            # Supabase storage 응답 확인
            if hasattr(upload_response, 'error') and upload_response.error:
                print(f"[ERROR] 업로드 실패: {upload_response.error}")
                return None
            else:
                print(f"[DEBUG] 이미지 업로드 성공: {file_name}")

                # 공개 URL 생성
                public_url = self.supabase.storage.from_(bucket_name).get_public_url(file_name)
                print(f"[DEBUG] 공개 URL: {public_url}")

                return public_url

        except Exception as e:
            print(f"[ERROR] Supabase 업로드 중 오류 발생: {str(e)}")
            return None

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
        
        # URL 쿼리 파라미터 제거 (예: image.png? -> image.png)
        filename = filename.split('?')[0]
        
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
        """두 이미지를 1단계로 합성 (gpt-image-1.5, 속도 최적화)"""
        try:
            print(f"[DEBUG] 이미지 다운로드 시작")
            image1_content = await self.download_image(image1_url)
            image2_content = await self.download_image(image2_url)

            image1_filename = image1_url.split('/')[-1].split('?')[0] or "face.jpg"
            image2_filename = image2_url.split('/')[-1].split('?')[0] or "character.jpg"

            print(f"[DEBUG] 파일 업로드 시작")
            file_id1 = self.create_file(image1_content, image1_filename)
            file_id2 = self.create_file(image2_content, image2_filename)

            pose_instruction = ""
            if custom_prompt and custom_prompt.strip():
                pose_instruction = f"\n\n**포즈/상황:** {custom_prompt.strip()}"

            prompt = f"""
첫 번째 이미지(사람 얼굴)와 두 번째 이미지(조선 수군 캐릭터)를 합성하여 캐리커처를 만들어주세요.

**얼굴 이미지에서 반영:**
- 눈, 코, 입, 얼굴형을 캐리커처 스타일로 과장하여 표현
- 헤어스타일과 색상 반영
- 안경 착용 여부 반영

**캐릭터 이미지에서 반영:**
- 의상, 갑옷, 무기 등 캐릭터 복장 그대로 유지
- 그림 화풍(선 굵기, 색감, 채색 스타일) 그대로 유지
- 조선시대 수군 일러스트 스타일 유지

**공통 규칙:**
- 전신이 모두 나오게 그릴 것
- 귀엽고 과장된 캐리커처 만화 스타일
- 깔끔한 단색 배경{pose_instruction}
"""

            print(f"[DEBUG] gpt-image-1.5 API 호출 시작 (단일 호출)")
            response = self.client.responses.create(
                model="gpt-image-1.5",
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                            {"type": "input_image", "file_id": file_id1},
                            {"type": "input_image", "file_id": file_id2},
                        ],
                    }
                ],
                tools=[{"type": "image_generation", "quality": "medium"}],
            )
            print(f"[DEBUG] API 호출 완료")

            image_generation_calls = [
                output for output in response.output
                if output.type == "image_generation_call"
            ]

            if not image_generation_calls:
                print(f"[ERROR] 이미지 생성 결과 없음")
                return None

            return image_generation_calls[0].result

        except Exception as e:
            print(f"[ERROR] 이미지 처리 오류: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return None
```

---

**⑤ 붙여넣기 후 344번 줄이 빈 줄, 345번 줄이 `async def cartoonize_with_character` 이면 정상입니다.**

**⑥ 화면 오른쪽 위 초록색 "Commit changes" 버튼 클릭**
```
Commit message 입력:
feat: gpt-image-1.5 모델 교체 및 속도 개선 (2단계→1단계)

    async def cartoonize_with_character(self, image_url: str, character_id: str, custom_prompt: Optional[str] = None):
        """
        target.py와 동일한 구조의 캐릭터 이미지 합성 함수
        1. character_id로 캐릭터 이미지 URL 가져오기
        2. 기존 edit_images 함수로 이미지 합성 (2단계: 얼굴+화풍, 포즈변경)
        3. 결과 이미지를 Supabase에 업로드

        Returns:
            dict: {
                'result_image_url': str (Supabase URL),
                'character_image_url': str,
                'timing': dict
            }
        """
        import time

        timing = {
            'character_image_fetch': None,
            'step1_generation': None,
            'step2_generation': None,
            'image_upload': None,
            'total_time': None
        }

        start_time = time.time()

        try:
            # 1단계: 캐릭터 이미지 URL 가져오기
            step_start = time.time()
            print(f"[DEBUG] 1단계: 캐릭터 ID {character_id}로 이미지 URL 가져오는 중...")
            character_image_url = self.get_random_character_image(character_id)
            timing['character_image_fetch'] = round(time.time() - step_start, 2)

            if not character_image_url:
                print(f"[ERROR] 캐릭터 ID {character_id}에 해당하는 이미지를 찾을 수 없습니다.")
                timing['total_time'] = round(time.time() - start_time, 2)
                return {
                    'success': False,
                    'error': f"캐릭터 ID {character_id}에 해당하는 이미지를 찾을 수 없습니다.",
                    'timing': timing
                }

            print(f"[DEBUG] 1단계 완료 (소요시간: {timing['character_image_fetch']}초)")

            # 2단계: 기존 edit_images 함수로 이미지 합성
            # (내부적으로 2단계로 나뉘어 처리됨: 얼굴+화풍 합성, 포즈 변경)
            step_start = time.time()
            print(f"[DEBUG] 2단계: 이미지 합성 시작 (image1={image_url}, image2={character_image_url})")
            result_image_url = await self.edit_images(
                image1_url=str(image_url),
                image2_url=character_image_url,
                custom_prompt=custom_prompt
            )
            total_generation_time = round(time.time() - step_start, 2)

            # edit_images가 2단계로 처리되므로 전체 생성 시간을 기록
            timing['step1_generation'] = total_generation_time / 2 if custom_prompt else total_generation_time
            timing['step2_generation'] = total_generation_time / 2 if custom_prompt else None

            if not result_image_url:
                print(f"[ERROR] 이미지 합성 실패")
                timing['total_time'] = round(time.time() - start_time, 2)
                return {
                    'success': False,
                    'error': '이미지 합성에 실패했습니다.',
                    'character_image_url': character_image_url,
                    'timing': timing
                }

            print(f"[DEBUG] 2단계 완료 (소요시간: {total_generation_time}초)")
            print(f"[DEBUG] 결과 이미지 URL 시작 부분: {result_image_url[:100]}...")

            # 3단계: 결과 이미지를 Supabase에 업로드
            step_start = time.time()
            print(f"[DEBUG] 3단계: 결과 이미지를 Supabase에 업로드 중...")

            # 결과 이미지 다운로드
            result_image_data = await self.download_image(result_image_url)

            # Supabase에 업로드
            file_name = f"cartoon_result_{uuid.uuid4().hex}.png"
            supabase_url = self.upload_image_to_supabase(result_image_data, file_name)

            timing['image_upload'] = round(time.time() - step_start, 2)
            timing['total_time'] = round(time.time() - start_time, 2)

            if not supabase_url:
                print(f"[WARNING] Supabase 업로드 실패, 원본 URL 반환")
                # Supabase 업로드 실패해도 원본 URL은 반환
                return {
                    'success': True,
                    'result_image_url': result_image_url,  # 원본 OpenAI URL
                    'character_image_url': character_image_url,
                    'timing': timing,
                    'warning': 'Supabase 업로드 실패, OpenAI URL 반환'
                }

            print(f"[DEBUG] 3단계 완료 (소요시간: {timing['image_upload']}초)")
            print(f"[DEBUG] 전체 완료! 총 소요시간: {timing['total_time']}초")

            return {
                'success': True,
                'result_image_url': supabase_url,  # Supabase URL
                'character_image_url': character_image_url,
                'timing': timing
            }

        except Exception as e:
            timing['total_time'] = round(time.time() - start_time, 2)
            print(f"[ERROR] cartoonize_with_character 오류: {str(e)}")
            import traceback
            print(f"[ERROR] 상세 스택:\n{traceback.format_exc()}")
            return {
                'success': False,
                'error': f"이미지 처리 중 오류 발생: {str(e)}",
                'timing': timing
            }
