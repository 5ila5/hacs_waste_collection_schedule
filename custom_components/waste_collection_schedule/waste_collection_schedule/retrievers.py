"""Standard retrieval methods for waste collection sources.

Each retriever is a function that takes a source instance and returns
a raw HTTP response. The source configures URL, params, headers etc
as instance/class attributes.

Preferred retrievers (curl_cffi, browser impersonation — works on Cloudflare-protected
sites and regular sites alike):

    retrieve = retrievers.http_get    # GET  — default in BaseSource
    retrieve = retrievers.http_post   # POST

Explicit fallback (plain requests — only use if curl_cffi causes a specific problem):

    retrieve = retrievers.legacy_http_get
    retrieve = retrievers.legacy_http_post
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Mapping, Protocol, TypeAlias, cast

import requests as _plain_requests
from curl_cffi import requests as _cffi_requests

if TYPE_CHECKING:
    from waste_collection_schedule.waste_collection_schedule.base_source import (
        BaseSource,
    )

    # RetrieverFunc: TypeAlias = Callable[
    #     [BaseSource], _plain_requests.Response | _cffi_requests.Response
    # ]

HeadersType: TypeAlias = Mapping[str, str | None] | None
ParamsType: TypeAlias = dict | list | tuple | None
JsonType: TypeAlias = dict | list | None

SourceParams: TypeAlias = dict[str, Any]
UrlArgs: TypeAlias = Callable[[SourceParams], str] | str
ParamsArgs: TypeAlias = Callable[[SourceParams], ParamsType] | ParamsType
HeadersArgs: TypeAlias = Callable[[SourceParams], HeadersType] | HeadersType
AnyArgs: TypeAlias = Callable[[SourceParams], Any] | Any
JsonArgs: TypeAlias = Callable[[SourceParams], JsonType] | JsonType


class RetrieverFunc(Protocol):
    def __init__(self, source: BaseSource, *args, **kwargs):  #
        ...

    def __call__(
        self, source: BaseSource
    ) -> _plain_requests.Response | _cffi_requests.Response:  #
        ...

    def _resolve[T: (
        str,
        ParamsType,
        JsonType,
        HeadersType,
    )](self, mapping: Callable[..., T] | T, source: BaseSource) -> T:
        if callable(mapping):
            return mapping(**source.params)
        return cast(T, mapping)


class HttpGetRetriever(RetrieverFunc):
    """HTTP GET using curl_cffi (browser impersonation). Default retriever.

    Works on both regular endpoints and Cloudflare-protected sites.
    Reads API_URL, _params, _headers, TIMEOUT from the source instance.
    """

    def __init__(
        self,
        url: UrlArgs | str,
        params: ParamsArgs = None,
        headers: HeadersArgs | None = None,
        timeout=30,
    ):
        self.params = params
        self.headers = headers
        self.timeout = timeout
        self.url = url

    def __call__(
        self, source: BaseSource
    ) -> _cffi_requests.Response | _plain_requests.Response:
        session = _cffi_requests.Session(impersonate="chrome")

        return session.get(
            self._resolve(self.url, source),
            params=self._resolve(self.params, source),
            headers=self._resolve(self.headers, source),
            timeout=self.timeout,
        )


class HttpPost(RetrieverFunc):
    """HTTP POST using curl_cffi (browser impersonation). Default POST retriever.

    Works on both regular endpoints and Cloudflare-protected sites.
    Reads API_URL, _params, _data, _json, _headers, TIMEOUT from the source instance.
    """

    def __init__(
        self,
        url: UrlArgs,
        params: ParamsArgs = None,
        data: AnyArgs | None = None,
        json: JsonArgs = None,
        headers: HeadersArgs | None = None,
        timeout=30,
    ):
        self.url = url
        self.params = params
        self.data = data
        self.json = json
        self.headers = headers
        self.timeout = timeout

    def __call__(
        self, source: BaseSource
    ) -> _cffi_requests.Response | _plain_requests.Response:
        session = _cffi_requests.Session(impersonate="chrome")
        j = self._resolve(self.json, source)
        return session.post(
            self._resolve(self.url, source),
            params=cast(ParamsType | None, self._resolve(self.params, source)),
            data=self._resolve(self.data, source),
            json=j,
            headers=self._resolve(self.headers, source) if self.headers else None,
            timeout=self.timeout,
        )


class HttpGetLegacy(HttpGetRetriever):
    """HTTP GET using plain requests. Explicit non-preferred fallback.

    Only use this if curl_cffi causes a specific, documented problem with
    this source. Prefer http_get (curl_cffi) in all other cases.

    Reads API_URL, _params, _headers, TIMEOUT from the source instance.
    """

    def __call__(self, source: BaseSource) -> _plain_requests.Response:
        return _plain_requests.get(
            self._resolve(self.url, source),
            params=self._resolve(self.params, source),
            headers=self._resolve(self.headers, source) if self.headers else None,
            timeout=self.timeout,
        )


class HttpGetLegacySSL(HttpGetLegacy):
    """Fetch via HTTP GET using a legacy SSL session.

    Use only for endpoints that require UNSAFE_LEGACY_RENEGOTIATION (SSL
    compatibility mode). Reads API_URL, _params, _headers, TIMEOUT from the
    source instance.
    """

    def __call__(self, source: BaseSource) -> _plain_requests.Response:
        from waste_collection_schedule.service.SSLError import get_legacy_session

        return get_legacy_session().get(
            self._resolve(self.url, source),
            params=self._resolve(self.params, source),
            headers=self._resolve(self.headers, source) if self.headers else None,
            timeout=self.timeout,
        )


class HttpPostLegacy(HttpPost):
    """HTTP POST using plain requests. Explicit non-preferred fallback.

    Only use this if curl_cffi causes a specific, documented problem with
    this source. Prefer http_post (curl_cffi) in all other cases.

    Reads API_URL, _params, _data, _json, _headers, TIMEOUT from the source instance.
    """

    def __call__(self, source: BaseSource) -> _plain_requests.Response:
        return _plain_requests.post(
            self._resolve(self.url, source),
            params=self._resolve(self.params, source) if self.params else None,
            data=self._resolve(self.data, source) if self.data else None,
            json=self._resolve(self.json, source) if self.json else None,
            headers=self._resolve(self.headers, source) if self.headers else None,
            timeout=self.timeout,
        )


class HttpPostLegacySSL(HttpPostLegacy):
    """Fetch via HTTP POST using a legacy SSL session.

    Use only for endpoints that require UNSAFE_LEGACY_RENEGOTIATION (SSL
    compatibility mode). Reads API_URL, _params, _data, _json, _headers, TIMEOUT
    from the source instance.
    """

    def __call__(self, source: BaseSource) -> _plain_requests.Response:
        from waste_collection_schedule.service.SSLError import get_legacy_session

        return get_legacy_session().post(
            self._resolve(self.url, source),
            params=self._resolve(self.params, source) if self.params else None,
            data=self._resolve(self.data, source) if self.data else None,
            json=self._resolve(self.json, source) if self.json else None,
            headers=self._resolve(self.headers, source) if self.headers else None,
            timeout=self.timeout,
        )
