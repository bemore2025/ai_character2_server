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
        try:
            if not self.supabase:
                print("[ERROR] Supabase 클라이언트가 초기화되지 않았습니다.")
                return None
            response = self.supabase.table("character").select("picture_cartoon").eq("id", character_id).execute()
            if not response.data:
                print(f"[ERROR] 캐릭터 ID {character_id}를 찾을 수 없습니다.")
                return None
            picture_cartoon = response.data[0].get("picture_cartoon")
            if not picture_cartoon or not isinstance(picture_cartoon, list) or len(picture_cartoon) == 0:
                print(f"[ERROR] 캐릭터 ID {character_id}의 picture_cartoon이 비어있거나 올바르지 않습니다.")
                return None
            random_item = random.choice(picture_cartoon)
            if isinstance(random_item, dict) and 'url' in random_item:
                return random_item['url']
            elif isinstance(random_item, str):
                return random_item
            else:
                print(f"[ERROR] 예상치 못한 데이터 형태: {type(random_item)}, 값: {random_item}")
                return None
        except Exception as e:
            print(f"[ERROR] 캐릭터 이미지 가져오기 중 오류 발생: {str(e)}")
            return None

    def upload_image_to_supabase(self, image_data: bytes, file_name: str = None) -> Optional[str]:
        try:
            if not self.supabase:
                print("[ERROR] Supabase 클라이언트가 초기화되지 않았습니다.")
                return None
            if not file_name:
                file_name = f"cartoon_{uuid.uuid4().hex}.png"
            print(f"[DEBUG] Supabase에 이미지 업로드 중: {file_name}")
            bucket_name = "images"
            upload_response = self.supabase.storage.from_(bucket_name).upload(
                path=file_name,
                file=image_data,
                file_options={"content-type": "image/png"}
            )
            if hasattr(upload_response, 'error') and upload_response.error:
                print(f"[ERROR] 업로드 실패: {upload_response.error}")
                return None
            else:
                print(f"[DEBUG] 이미지 업로드 성공: {file_name}")
                public_url = self.supabase.storage.from_(bucket_name).get_public_url(file_name)
                print(f"[DEBUG] 공개 URL: {public_url}")
                return public_url
        except Exception as e:
            print(f"[ERROR] Supabase 업로드 중 오류 발생: {str(e)}")
            return None

    async def download_image(self, image_url: str) -> bytes:
        s = (image_url or "").strip()
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
        if '://' not in s:
            s_clean = s.replace('\n', '').replace('\r', '')
            if len(s_clean) > 1000 and re.fullmatch(r'[A-Za-z0-9+/=_-]+', s_clean) is not None:
                print(f"[DEBUG] 순수 base64 감지, 디코딩 시작")
                try:
                    try:
                        decoded = base64.b64decode(s_clean, validate=True)
                    except Exception:
                        padded = s_clean + '=' * ((4 - len(s_clean) % 4) % 4)
                        decoded = base64.urlsafe_b64decode(padded)
                    print(f"[DEBUG] 순수 base64 디코딩 완료: {len(decoded)} bytes")
                    return decoded
                except Exception as _:
                    print(f"[DEBUG] 순수 base64 디코딩 실패, URL로 처리 시도")
        print(f"[DEBUG] 일반 URL 다운로드 시작: {s}")
        async with httpx.AsyncClient() as client:
            response = await client.get(s, timeout=30.0)
            response.raise_for_status()
            print(f"[DEBUG] URL 다운로드 완료: {len(response.content)} bytes")
            return response.content

    def create_file(self, file_content: bytes, filename: str) -> str:
        import tempfile
        filename = filename.split('?')[0]
        print(f"[DEBUG] create_file 호출: filename={filename}, size={len(file_content)} bytes")
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

            print(f"[DEBUG] OpenAI API 1회 호출 시작")
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
            print(f"[DEBUG] 응답 타입들: {[o.type for o in response.output]}")

            # 1순위: image_generation_call 타입에서 추출
            image_generation_calls = [
                output for output in response.output
                if output.type == "image_generation_call"
            ]
            if image_generation_calls:
                print(f"[DEBUG] image_generation_call 타입에서 이미지 추출 성공")
                return image_generation_calls[0].result

            # 2순위: message 타입에서 이미지 추출 시도
            for output in response.output:
                print(f"[DEBUG] output 상세: {output.type} - {str(output)[:300]}")
                if output.type == "message":
                    for content_item in output.content:
                        if hasattr(content_item, "type") and content_item.type == "image_generation_call":
                            print(f"[DEBUG] message 안에서 image_generation_call 발견")
                            return content_item.result
                        if hasattr(content_item, "image_url") and content_item.image_url:
                            print(f"[DEBUG] message 안에서 image_url 발견")
                            return content_item.image_url
                        if hasattr(content_item, "result") and content_item.result:
                            print(f"[DEBUG] message 안에서 result 발견")
                            return content_item.result

            print(f"[ERROR] 이미지 생성 결과 없음. 전체 응답: {str(response.output)[:500]}")
            return None

        except Exception as e:
            print(f"[ERROR] 이미지 처리 오류: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return None

    async def cartoonize_with_character(self, image_url: str, character_id: str, custom_prompt: Optional[str] = None):
        """
        캐릭터 이미지 합성 함수
        1. character_id로 캐릭터 이미지 URL 가져오기
        2. edit_images 함수로 이미지 합성
        3. Supabase 저장 없이 OpenAI URL 바로 반환 (용량 절감)
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

            step_start = time.time()
            print(f"[DEBUG] 2단계: 이미지 합성 시작 (image1={image_url}, image2={character_image_url})")
            result_image_url = await self.edit_images(
                image1_url=str(image_url),
                image2_url=character_image_url,
                custom_prompt=custom_prompt
            )
            total_generation_time = round(time.time() - step_start, 2)

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

            timing['total_time'] = round(time.time() - start_time, 2)
            print(f"[DEBUG] 전체 완료! 총 소요시간: {timing['total_time']}초")

            return {
                'success': True,
                'result_image_url': result_image_url,
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
