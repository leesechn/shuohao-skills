"""Protocol test: spawn the server over stdio, list tools, call hb_still without a key (expects a friendly error)."""
import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]


async def main():
    env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
    params = StdioServerParameters(command=sys.executable, args=["tools/hetbahn_studio/server.py"], env=env, cwd=str(ROOT))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            names = sorted(t.name for t in tools.tools)
            print("tools:", names)
            assert names == ["hb_clip", "hb_contact_sheet", "hb_ledger_export", "hb_logo_composite", "hb_music", "hb_still"]
            res = await s.call_tool("hb_still", {"shot_id": "TEST", "prompt": "test", "n": 1})
            txt = res.content[0].text
            print("no-key hb_still ->", getattr(res, "is_error", getattr(res, "isError", None)), txt[:160])
            assert getattr(res, "is_error", getattr(res, "isError", None)) and "GEMINI_API_KEY" in txt
            res = await s.call_tool("hb_logo_composite", {"image": "out/B_캐러셀_4x5/5_엔드.png"})
            txt = res.content[0].text
            print("no-logo hb_logo_composite ->", getattr(res, "is_error", getattr(res, "isError", None)), txt[:120])
            assert getattr(res, "is_error", getattr(res, "isError", None)) == (not (ROOT / "assets/logo_hetbahn.png").exists())
    print("OK")


asyncio.run(main())
