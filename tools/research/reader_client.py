from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReaderClient:
    mode: str
    public_base: str
    self_hosted_base: str

    def build_reader_url(self, url: str) -> str:
        mode = (self.mode or "").strip().lower()
        if mode == "public":
            base = self.public_base
        elif mode == "self_hosted":
            if not self.self_hosted_base:
                raise ValueError("reader self_hosted_base is required when mode=self_hosted")
            base = self.self_hosted_base
        elif mode == "both":
            base = self.self_hosted_base or self.public_base
        elif mode == "off":
            raise ValueError("reader fallback disabled (mode=off)")
        else:
            raise ValueError(f"unsupported reader mode: {self.mode!r}")

        if not base:
            raise ValueError("reader base url is required")

        base = base.rstrip("/")
        target = (url or "").lstrip("/")
        if not target:
            raise ValueError("reader target url is required")
        return f"{base}/{target}"
