import uuid
from typing import Dict, Optional
from datetime import datetime


class AsyncJobService:
    """비동기 작업 관리 서비스"""
    
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
            'updated_at': None,
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
    
    def delete_job(self, job_id: str):
        """작업 삭제 (완료된 작업 정리용)"""
        if job_id in self.jobs:
            del self.jobs[job_id]


# 전역 인스턴스
async_job_service = AsyncJobService()
