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
import tempfile

load_dotenv()


class ImageService:
    def __init__(self):
        api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        self.client = OpenAI(api_key=api_key)
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

    def _is_valid_image_result(self, value: Optional[str]) -> bool:
        if not value or not isinstance(value, str):
            return False

        s = value.strip()
        if not s:
            return False

        if s.startswith("ERROR:"):
            return False

        if s.startswith("data:image/"):
            return True

        # 순수 base64도 허용
        s_clean = s.replace("\n", "").replace("\r", "")
        if len(s_clean) > 1000 and re.fullmatch(r"[A-Za-z0-9+/=_-]+", s_clean):
            return True

        if s.startswith("http://") or s.startswith("https://"):
            return True

        return False

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

            if isinstance(random_item, dict) and "url" in random_item:
                return random_item["url"]
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

            if hasattr(upload_response, "error") and upload_response.error:
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

        if s.startswith("data:"):
            print("[DEBUG] Base64 data URL 감지, 디코딩 시작")
            base64_data = s.split(",", 1)[1] if "," in s else s
            base64_data = base64_data.strip()
            try:
                decoded = base64.b64decode(base64_data)
                print(f"[DEBUG] Base64 디코딩 완료: {len(decoded)} bytes")
                return decoded
            except Exception:
                print("[DEBUG] Base64 data URL 디코딩 실패, 다른 방식 시도")

        if "://" not in s:
            s_clean = s.replace("\n", "").replace("\r", "")
            if len(s_clean) > 1000 and re.fullmatch(r"[A-Za-z0-9+/=_-]+", s_clean) is not None:
                print("[DEBUG] 순수 base64 감지, 디코딩 시작")
                try:
                    try:
                        decoded = base64.b64decode(s_clean, validate=True)
                    except Exception:
                        padded = s_clean + "=" * ((4 - len(s_clean) % 4) % 4)
                        decoded = base64.urlsafe_b64decode(padded)

                    print(f"[DEBUG] 순수 base64 디코딩 완료: {len(decoded)} bytes")
                    return decoded
                except Exception:
                    print("[DEBUG] 순수 base64 디코딩 실패, URL로 처리 시도")

        print(f"[DEBUG] 일반 URL 다운로드 시작: {s}")
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(s, timeout=30.0)
            response.raise_for_status()
            print(f"[DEBUG] URL 다운로드 완료: {len(response.content)} bytes")
            return response.content

    async def edit_images(self, image1_url: str, image2_url: str, custom_prompt: Optional[str] = None) -> Optional[str]:
        try:
            print("[DEBUG] 이미지 다운로드 시작")
            image1_content = await self.download_image(image1_url)
            image2_content = await self.download_image(image2_url)

            pose_instruction = ""
            if custom_prompt and custom_prompt.strip():
                pose_instruction = f"\n\n포즈/상황: {custom_prompt.strip()}"

            prompt = f"""첫 번째 이미지(사람 얼굴)와 두 번째 이미지(조선 수군 캐릭터)를 합성하여 캐리커처를 만들어주세요.

얼굴 이미지에서 반영:
- 첫 번째 이미지의 눈, 코, 입, 얼굴형, 헤어스타일을 반영할 것
- 갸름한 얼굴, 귀여운 느낌을 유지할 것
- 사용자가 안경을 착용한 경우에만 안경을 유지하고, 착용하지 않았다면 절대로 안경을 추가하지 말 것

캐릭터 이미지에서 반영:
- 두 번째 이미지의 의상, 갑옷, 무기와 캐릭터 디자인을 그대로 유지
- 두 번째 이미지의 그림 화풍(선, 색감, 채색 스타일)을 그대로 유지

공통 규칙:
- 손과 팔은 반드시 2개로 그릴 것
- 전신이 모두 보이도록 그리고 캐릭터를 화면 중앙에 배치할 것
- 입력된 장소나 상황이 있다면 해당 장소가 보이는 배경을 생성할 것
{pose_instruction}
"""

            print("[DEBUG] OpenAI images.edit API 호출 시작")

            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f1:
                f1.write(image1_content)
                path1 = f1.name

            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f2:
                f2.write(image2_content)
                path2 = f2.name

            try:
                with open(path1, "rb") as img1, open(path2, "rb") as img2:
                    response = self.client.images.edit(
                        model="gpt-image-1",
                        image=[img1, img2],
                        prompt=prompt,
                        n=1,
                        size="1024x1024",
                    )

                print("[DEBUG] API 호출 완료")

                image_b64 = response.data[0].b64_json if response and response.data else None

                if image_b64 and isinstance(image_b64, str):
                    image_b64 = image_b64.strip()
                    print("[DEBUG] 이미지 추출 성공 (base64)")
                    return image_b64

                print("[ERROR] 이미지 생성 결과 없음")
                return None

            finally:
                if os.path.exists(path1):
                    os.unlink(path1)
                if os.path.exists(path2):
                    os.unlink(path2)

        except Exception as e:
            print(f"[ERROR] 이미지 처리 오류: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return None

    async def cartoonize_with_character(self, image_url: str, character_id: str, custom_prompt: Optional[str] = None):
        import time

        timing = {
            "character_image_fetch": None,
            "step1_generation": None,
            "step2_generation": None,
            "image_upload": None,
            "total_time": None,
        }

        start_time = time.time()

        try:
            step_start = time.time()
            print(f"[DEBUG] 1단계: 캐릭터 ID {character_id}로 이미지 URL 가져오는 중...")
            character_image_url = self.get_random_character_image(character_id)
            timing["character_image_fetch"] = round(time.time() - step_start, 2)

            if not character_image_url:
                print(f"[ERROR] 캐릭터 ID {character_id}에 해당하는 이미지를 찾을 수 없습니다.")
                timing["total_time"] = round(time.time() - start_time, 2)
                return {
                    "success": False,
                    "error": f"캐릭터 ID {character_id}에 해당하는 이미지를 찾을 수 없습니다.",
                    "timing": timing,
                }

            print(f"[DEBUG] 1단계 완료 (소요시간: {timing['character_image_fetch']}초)")

            step_start = time.time()
            print(f"[DEBUG] 2단계: 이미지 합성 시작 (image1={image_url}, image2={character_image_url})")

            result_image_b64 = await self.edit_images(
                image1_url=str(image_url),
                image2_url=character_image_url,
                custom_prompt=custom_prompt,
            )

            total_generation_time = round(time.time() - step_start, 2)

            timing["step1_generation"] = total_generation_time / 2 if custom_prompt else total_generation_time
            timing["step2_generation"] = total_generation_time / 2 if custom_prompt else None

            if not self._is_valid_image_result(result_image_b64):
                print("[ERROR] 이미지 합성 실패 또는 잘못된 결과 형식")
                timing["total_time"] = round(time.time() - start_time, 2)
                return {
                    "success": False,
                    "error": "이미지 합성에 실패했습니다.",
                    "character_image_url": character_image_url,
                    "timing": timing,
                }

            result_image_b64 = result_image_b64.strip()
            result_image_data_url = f"data:image/png;base64,{result_image_b64}"

            print(f"[DEBUG] 2단계 완료 (소요시간: {total_generation_time}초)")
            print(f"[DEBUG] 결과 이미지 base64 시작 부분: {result_image_b64[:60]}...")

            timing["total_time"] = round(time.time() - start_time, 2)
            print(f"[DEBUG] 전체 완료! 총 소요시간: {timing['total_time']}초")

            return {
                "success": True,
                "result_image_b64": result_image_b64,
                "result_image_data_url": result_image_data_url,
                "character_image_url": character_image_url,
                "timing": timing,
            }

        except Exception as e:
            timing["total_time"] = round(time.time() - start_time, 2)
            print(f"[ERROR] cartoonize_with_character 오류: {str(e)}")
            import traceback
            print(f"[ERROR] 상세 스택:\n{traceback.format_exc()}")
            return {
                "success": False,
                "error": f"이미지 처리 중 오류 발생: {str(e)}",
                "timing": timing,
            }
