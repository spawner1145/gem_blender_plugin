"""Stdlib-only HTTP client; this module never touches bpy."""
import http.client
import json
from pathlib import Path
from urllib.parse import urlsplit
import uuid


class Cancelled(Exception):
    pass


class Client:
    def __init__(self, url):
        self.url = urlsplit(url.rstrip("/"))
        if self.url.scheme not in ("http", "https") or not self.url.hostname:
            raise ValueError("服务地址必须为 http:// 或 https:// 地址")

    def connection(self):
        cls = http.client.HTTPSConnection if self.url.scheme == "https" else http.client.HTTPConnection
        return cls(self.url.hostname, self.url.port, timeout=30)

    def path(self, route):
        return self.url.path.rstrip("/") + route

    def request(self, method, path):
        con = self.connection()
        try:
            con.request(method, self.path(path))
            response = con.getresponse()
            data = response.read(16 * 1024 * 1024)
            if response.status >= 300:
                self.raise_error(response.status, data)
            return json.loads(data)
        finally:
            con.close()

    @staticmethod
    def raise_error(status, data):
        try:
            detail = json.loads(data).get("detail", data.decode("utf-8", "replace"))
        except ValueError:
            detail = data.decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {status}: {detail}")

    def upload(self, video, options, cancel, progress):
        path = Path(video)
        if not path.is_file():
            raise ValueError("找不到视频文件")
        if path.stat().st_size > 512 * 1024 * 1024:
            raise ValueError("插件单次上传最多 512 MB，请先剪短视频")
        boundary = "GEM" + uuid.uuid4().hex
        # Fixed ASCII filename avoids multipart header/encoding issues on Chinese paths.
        head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"options\"\r\n\r\n"
                + json.dumps(options) + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"video\"; filename=\"video{path.suffix.lower()}\"\r\n"
                + "Content-Type: application/octet-stream\r\n\r\n").encode("utf-8")
        tail = f"\r\n--{boundary}--\r\n".encode()
        con = self.connection()
        try:
            con.putrequest("POST", self.path("/v1/jobs"))
            con.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
            con.putheader("Content-Length", str(len(head) + path.stat().st_size + len(tail)))
            con.endheaders()
            con.send(head)
            sent = 0
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    if cancel.is_set():
                        raise Cancelled()
                    con.send(chunk)
                    sent += len(chunk)
                    progress(sent / max(path.stat().st_size, 1))
            con.send(tail)
            response = con.getresponse()
            data = response.read()
            if response.status >= 300:
                self.raise_error(response.status, data)
            return json.loads(data)
        finally:
            con.close()

    def download_motion(self, job_id, destination):
        con = self.connection()
        try:
            con.request("GET", self.path(f"/v1/jobs/{job_id}/files/motion.json"))
            response = con.getresponse()
            if response.status >= 300:
                self.raise_error(response.status, response.read())
            total = 0
            with Path(destination).open("wb") as stream:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 100 * 1024 * 1024:
                        raise RuntimeError("动作文件超过 100 MB")
                    stream.write(chunk)
        finally:
            con.close()
