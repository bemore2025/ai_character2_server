import base64
import os
import httpx
from openai import OpenAI
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

class ImageService:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def download_image(self, image_url: str) -> bytes:
        """URL로부터 이미지를 다운로드"""
        async with httpx.AsyncClient() as client:
            response = await client.get(image_url, timeout=30.0)
            response.raise_for_status()
            return response.content
    
    def encode_image(self, file_content: bytes) -> str:
        """이미지 파일을 base64로 인코딩"""
        return base64.b64encode(file_content).decode("utf-8")
    
    def create_file(self, file_content: bytes, filename: str) -> str:
        """OpenAI에 파일 업로드하고 file_id 반환"""
        import tempfile
        import io
        
        # 파일 내용을 임시 파일로 저장
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
        
        try:
            with open(temp_file_path, "rb") as file_content:
                result = self.client.files.create(
                    file=file_content,
                    purpose="vision",
                )
                return result.id
        finally:
            # 임시 파일 삭제
            os.unlink(temp_file_path)
    
    async def edit_images(self, image1_url: str, image2_url: str) -> Optional[str]:
        """두 이미지를 합성하여 캐리커처 생성"""
        try:
            # URL로부터 이미지 다운로드
            image1_content = await self.download_image(image1_url)
            image2_content = await self.download_image(image2_url)

            # 고정 프롬프트 사용
            full_prompt = """
첫 번째 이미지의 얼굴을 캐리커처 스타일로 변환해주세요.
그런 다음 두 번째 이미지의 사람에게 합성하세요.

전신이 다 나오게 그려줘, 단순한 캐릭터 스타일, 굵고 부드러운 선의 화풍, 눈을 크게 묘사, 날씬한 얼굴, 최대한 닮게 그려줘. 귀여운 얼굴, 만화 스타일, 우스꽝스럽지 않은 표정, 과장하지 않은 표정, 배경색은 하늘색으로 칠해줘.
"""

            # 이미지 인코딩
            image1_base64 = self.encode_image(image1_content)
            image2_base64 = self.encode_image(image2_content)

            # URL에서 파일명 추출
            image1_filename = image1_url.split('/')[-1] or "image1.jpg"
            image2_filename = image2_url.split('/')[-1] or "image2.jpg"

            # OpenAI에 파일 업로드
            image1_file_id = self.create_file(image1_content, image1_filename)
            image2_file_id = self.create_file(image2_content, image2_filename)
            
            # OpenAI API 호출
            response = self.client.responses.create(
                model="gpt-4.1",
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": full_prompt},
                            {
                                "type": "input_image",
                                "image_url": f"data:image/jpeg;base64,{image1_base64}",
                            },
                            {
                                "type": "input_image",
                                "image_url": f"data:image/png;base64,{image2_base64}",
                            },
                            {
                                "type": "input_image",
                                "file_id": image1_file_id,
                            },
                            {
                                "type": "input_image",
                                "file_id": image2_file_id,
                            }
                        ],
                    }
                ],
                tools=[{"type": "image_generation"}],
            )
            
            # 이미지 생성 결과 추출
            image_generation_calls = [
                output
                for output in response.output
                if output.type == "image_generation_call"
            ]
            
            image_data = [output.result for output in image_generation_calls]
            
            if image_data:
                return image_data[0]
            else:
                return None
                
        except Exception as e:
            print(f"이미지 처리 중 오류 발생: {str(e)}")
            return None
