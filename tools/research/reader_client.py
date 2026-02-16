from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReaderClient:
    mode: str
    public_base: str
    self_hosted_base: str

    def build_reader_url(self, url: str) -> str:
        base = self.public_base
        if self.mode == "self_hosted" and self.self_hosted_base:
            base = self.self_hosted_base

        base = base.rstrip("/")
        url = url.lstrip("/")
        return f"{base}/{url}"
