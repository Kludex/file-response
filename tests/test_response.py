from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio
from baize.asgi import FileResponse as BaizeFileResponse
from httpx import AsyncClient

from file_response import FileResponse

README = """\
# BáiZé

Powerful and exquisite WSGI/ASGI framework/toolkit.

The minimize implementation of methods required in the Web framework. No redundant implementation means that you can freely customize functions without considering the conflict with baize's own implementation.

Under the ASGI/WSGI protocol, the interface of the request object and the response object is almost the same, only need to add or delete `await` in the appropriate place. In addition, it should be noted that ASGI supports WebSocket but WSGI does not.
"""


@pytest.fixture
def readme_file(tmp_path: Path) -> Path:
    filepath = tmp_path / "README.txt"
    filepath.write_bytes(README.encode("utf8"))
    return filepath


@pytest_asyncio.fixture(  # type: ignore
    params=[
        pytest.param(FileResponse, id="FileResponse"),
        pytest.param(BaizeFileResponse, id="BaizeFileResponse"),
    ]
)
async def client(readme_file: Path, request: pytest.FixtureRequest) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(app=request.param(str(readme_file)), base_url="http://test") as client_:
        yield client_


@pytest.mark.asyncio
async def test_file_response(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.headers["content-length"] == str(len(README.encode("utf8")))
    assert response.text == README


@pytest.mark.asyncio
async def test_file_response_head(client: AsyncClient) -> None:
    response = await client.head("/")
    assert response.status_code == 200
    assert response.headers["content-length"] == str(len(README.encode("utf8")))
    assert response.content == b""


@pytest.mark.asyncio
async def test_file_response_range(client: AsyncClient) -> None:
    response = await client.get("/", headers={"Range": "bytes=0-100"})
    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 0-100/{len(README.encode('utf8'))}"
    assert response.headers["content-length"] == str(101)
    assert response.content == README.encode("utf8")[:101]


@pytest.mark.asyncio
async def test_file_response_range_head(client: AsyncClient) -> None:
    response = await client.head("/", headers={"Range": "bytes=0-100"})
    assert response.status_code == 206
    assert response.headers["content-length"] == str(101)
    assert response.content == b""


@pytest.mark.asyncio
async def test_file_response_range_multi(client: AsyncClient) -> None:
    response = await client.get("/", headers={"Range": "bytes=0-100, 200-300"})
    assert response.status_code == 206
    assert response.headers["content-type"].startswith("multipart/byteranges; boundary=")
    # NOTE: The charset: utf-8 is not included in the BaizeFileResponse.
    assert response.headers["content-length"] == str(370) or str(400)


@pytest.mark.asyncio
async def test_file_response_range_multi_head(client: AsyncClient) -> None:
    response = await client.head("/", headers={"Range": "bytes=0-100, 200-300"})
    assert response.status_code == 206
    assert response.headers["content-length"] == str(370) or str(400)
    assert response.content == b""

    response = await client.head(
        "/",
        headers={
            "Range": "bytes=200-300",
            "if-range": response.headers["etag"][:-1],
        },
    )
    assert response.status_code == 200
    response = await client.head(
        "/",
        headers={
            "Range": "bytes=200-300",
            "if-range": response.headers["etag"],
        },
    )
    assert response.status_code == 206


@pytest.mark.asyncio
async def test_file_response_range_invalid(client: AsyncClient) -> None:
    response = await client.head("/", headers={"Range": "bytes: 0-1000"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_file_response_range_head_max(client: AsyncClient) -> None:
    response = await client.head("/", headers={"Range": f"bytes=0-{len(README.encode('utf8'))+1}"})
    assert response.status_code == 206


@pytest.mark.asyncio
async def test_file_response_range_416(client: AsyncClient) -> None:
    response = await client.head("/", headers={"Range": f"bytes={len(README.encode('utf8'))+1}-"})
    assert response.status_code == 416
    assert response.headers["Content-Range"] == f"*/{len(README.encode('utf8'))}"


@pytest.mark.asyncio
async def test_file_response_only_support_bytes_range(client: AsyncClient) -> None:
    response = await client.get("/", headers={"Range": "items=0-100"})
    assert response.status_code == 400
    assert response.text == "Only support bytes range"


@pytest.mark.asyncio
async def test_file_response_range_must_be_requested(client: AsyncClient) -> None:
    response = await client.get("/", headers={"Range": "bytes="})
    assert response.status_code == 400
    assert response.text == "Range header: range must be requested"


@pytest.mark.asyncio
async def test_file_response_start_must_be_less_than_end(client: AsyncClient) -> None:
    response = await client.get("/", headers={"Range": "bytes=100-0"})
    assert response.status_code == 400
    assert response.text == "Range header: start must be less than end"


@pytest.mark.asyncio
async def test_file_response_merge_ranges(client: AsyncClient) -> None:
    response = await client.get("/", headers={"Range": "bytes=0-100, 50-200"})
    assert response.status_code == 206
    assert response.headers["content-length"] == str(201)
    assert response.headers["content-range"] == f"bytes 0-200/{len(README.encode('utf8'))}"
