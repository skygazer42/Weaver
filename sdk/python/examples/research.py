import os

from weaver_sdk import WeaverClient


def main() -> None:
    base_url = os.getenv("WEAVER_BASE_URL", "http://127.0.0.1:8001")
    client = WeaverClient(base_url=base_url)

    for ev in client.chat_sse(
        {"messages": [{"role": "user", "content": "Give me a 3-bullet summary of Weaver."}]}
    ):
        if ev["type"] == "text":
            print(ev["data"]["content"], end="", flush=True)
        if ev["type"] == "done":
            break

    print()
    print("thread_id:", client.last_thread_id)


if __name__ == "__main__":
    main()

