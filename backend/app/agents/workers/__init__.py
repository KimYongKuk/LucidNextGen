"""Worker Agents for A2A Architecture"""

from .base_worker import BaseWorker
from .web_search_worker import WebSearchWorker
from .corp_rag_worker import CorpRAGWorker
from .user_files_worker import UserFilesWorker
from .youtube_worker import YouTubeWorker
from .url_fetch_worker import URLFetchWorker
from .it_support_worker import ITSupportWorker
from .acct_support_worker import AcctSupportWorker
from .visualization_worker import VisualizationWorker
from .ppt_worker import PPTWorker
from .mail_worker import MailWorker
from .approval_worker import ApprovalWorker
from .direct_worker import DirectResponseWorker

# Worker Registry
WORKER_REGISTRY = {
    "WebSearchWorker": WebSearchWorker,
    "CorpRAGWorker": CorpRAGWorker,
    "UserFilesWorker": UserFilesWorker,
    "YouTubeWorker": YouTubeWorker,
    "URLFetchWorker": URLFetchWorker,
    "ITSupportWorker": ITSupportWorker,
    "AcctSupportWorker": AcctSupportWorker,
    "VisualizationWorker": VisualizationWorker,
    "PPTWorker": PPTWorker,
    "MailWorker": MailWorker,
    "ApprovalWorker": ApprovalWorker,
    "DirectResponseWorker": DirectResponseWorker,
}


def get_worker(name: str) -> BaseWorker:
    """Worker 인스턴스 반환"""
    if name not in WORKER_REGISTRY:
        raise ValueError(f"Unknown worker: {name}")
    return WORKER_REGISTRY[name]()


__all__ = [
    "BaseWorker",
    "WebSearchWorker",
    "CorpRAGWorker",
    "UserFilesWorker",
    "YouTubeWorker",
    "URLFetchWorker",
    "ITSupportWorker",
    "AcctSupportWorker",
    "VisualizationWorker",
    "PPTWorker",
    "MailWorker",
    "ApprovalWorker",
    "DirectResponseWorker",
    "WORKER_REGISTRY",
    "get_worker",
]
