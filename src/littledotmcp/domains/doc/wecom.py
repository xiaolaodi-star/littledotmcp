"""M9 企业微信文档后端客户端（骨架 + mock 冒烟）。

设计要点：
- 仅实现 token 缓存与 list/read/write 抽象，内部用 httpx 同步客户端；
- 凭据缺失（corp_id/agent_id/secret 任一为空）时所有方法返回可读降级错误，不抛未捕获异常；
- 网络/接口失败统一降级为可读结果（规约-07），不崩溃；
- 真实企微接口未接入（按计划 M9 为骨架，不接真实网络）。

降级返回约定：
- list_docs() -> (ok: bool, data: list[dict], message: str)
- read_doc() / write_doc() -> (ok: bool, doc_id: str, message: str)
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

# 企微 access_token 缓存有效期上限（秒），提前 5 分钟刷新
_TOKEN_TTL = 2 * 3600 - 300
_GET_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
# 占位接口（骨架，真实联调时替换）
_DOC_LIST_URL = "https://qyapi.weixin.qq.com/cgi-bin/wedoc/doc_list"
_DOC_GET_URL = "https://qyapi.weixin.qq.com/cgi-bin/wedoc/doc_get"
_DOC_CREATE_URL = "https://qyapi.weixin.qq.com/cgi-bin/wedoc/create_doc"


class WeComDocClient:
    """企微文档客户端骨架：token 缓存 + 文档 list/read/write 抽象。

    凭据缺失或网络异常时返回可读降级结果，绝不抛出未捕获异常。
    """

    def __init__(
        self,
        corp_id: str,
        agent_id: str,
        secret: str,
        *,
        timeout: float = 10.0,
    ) -> None:
        self.corp_id = (corp_id or "").strip()
        self.agent_id = (agent_id or "").strip()
        self.secret = (secret or "").strip()
        self._timeout = timeout
        self._token: str | None = None
        self._token_at: float = 0.0

    # ---- 凭据与 token ----

    @property
    def configured(self) -> bool:
        """凭据是否齐备。"""
        return bool(self.corp_id and self.agent_id and self.secret)

    def _get_token(self) -> tuple[bool, str, str]:
        """返回 (ok, token_or_empty, message)。"""
        if not self.configured:
            return False, "", "企微凭据未配置（wecom_corp_id/agent_id/secret 缺失）"
        if self._token and (time.monotonic() - self._token_at) < _TOKEN_TTL:
            return True, self._token, "ok"
        try:
            resp = httpx.get(
                _GET_TOKEN_URL,
                params={"corpid": self.corp_id, "corpsecret": self.secret},
                timeout=self._timeout,
            )
            data = resp.json()
            if data.get("errcode", 0) != 0:
                return False, "", f"获取企微 token 失败：{data.get('errmsg', 'unknown')}"
            token = data.get("access_token", "")
            if not token:
                return False, "", "获取企微 token 返回空"
            self._token = token
            self._token_at = time.monotonic()
            return True, token, "ok"
        except Exception as exc:  # 网络/解析异常降级
            logger.warning("企微 token 获取异常：%s", exc)
            return False, "", f"企微 token 获取异常：{exc}"

    # ---- 文档操作（骨架：真实联调时按企微接口填充） ----

    def list_docs(self) -> tuple[bool, list[dict], str]:
        ok, token, msg = self._get_token()
        if not ok:
            return False, [], msg
        try:
            resp = httpx.post(
                _DOC_LIST_URL,
                params={"access_token": token},
                json={"agentid": self.agent_id},
                timeout=self._timeout,
            )
            data = resp.json()
            if data.get("errcode", 0) != 0:
                return False, [], f"企微文档列表失败：{data.get('errmsg', 'unknown')}"
            return True, data.get("doc_list", []) or [], "ok"
        except Exception as exc:
            logger.warning("企微文档列表异常：%s", exc)
            return False, [], f"企微文档列表异常：{exc}"

    def read_doc(self, doc_id: str) -> tuple[bool, str, str]:
        ok, token, msg = self._get_token()
        if not ok:
            return False, "", msg
        try:
            resp = httpx.post(
                _DOC_GET_URL,
                params={"access_token": token},
                json={"docid": doc_id},
                timeout=self._timeout,
            )
            data = resp.json()
            if data.get("errcode", 0) != 0:
                return False, "", f"企微文档读取失败：{data.get('errmsg', 'unknown')}"
            return True, data.get("content", ""), "ok"
        except Exception as exc:
            logger.warning("企微文档读取异常：%s", exc)
            return False, "", f"企微文档读取异常：{exc}"

    def write_doc(self, name: str, content: str) -> tuple[bool, str, str]:
        ok, token, msg = self._get_token()
        if not ok:
            return False, "", msg
        try:
            resp = httpx.post(
                _DOC_CREATE_URL,
                params={"access_token": token},
                json={"doc_name": name, "content": content, "agentid": self.agent_id},
                timeout=self._timeout,
            )
            data = resp.json()
            if data.get("errcode", 0) != 0:
                return False, "", f"企微文档写入失败：{data.get('errmsg', 'unknown')}"
            doc_id = data.get("docid", "")
            if not doc_id:
                return False, "", "企微文档写入返回空 docid"
            return True, doc_id, "ok"
        except Exception as exc:
            logger.warning("企微文档写入异常：%s", exc)
            return False, "", f"企微文档写入异常：{exc}"


def build_wecom_client() -> WeComDocClient:
    """从全局配置构造企微客户端（凭据缺失亦可构造，运行时降级）。"""
    from ...config import get_settings

    s = get_settings()
    return WeComDocClient(
        corp_id=getattr(s, "wecom_corp_id", "") or "",
        agent_id=getattr(s, "wecom_agent_id", "") or "",
        secret=getattr(s, "wecom_secret", "") or "",
    )
