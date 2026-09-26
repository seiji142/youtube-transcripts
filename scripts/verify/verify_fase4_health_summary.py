"""Verificación real Fase 4 E2/E3: summary + health sobre video cacheado."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mcp_server import youtube_health, youtube_transcript_summary  # noqa: E402

URL = "https://www.youtube.com/watch?v=1m7fTsJzoao"
VIDEO_ID = "1m7fTsJzoao"


def main() -> int:
    failures: list[str] = []

    summary = youtube_transcript_summary(URL, max_sections=3, sentences_per_section=2)
    print("--- summary ---")
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:3000])
    if summary.get("status") != "completed":
        failures.append("summary status != completed")
    else:
        if not summary.get("sections"):
            failures.append("summary sin secciones")
        if not summary.get("overall"):
            failures.append("summary sin overall")
        for section in summary.get("sections", []):
            for sentence in section["sentences"]:
                if "&t=" not in sentence["url"]:
                    failures.append("oración sin cita &t=")
        for sentence in summary.get("overall", []):
            if "&t=" not in sentence["url"]:
                failures.append("overall sin cita &t=")

    health = youtube_health()
    print("--- health ---")
    print(json.dumps(health, ensure_ascii=False, indent=2))
    if health.get("status") != "completed":
        failures.append("health status != completed")
    else:
        names = [p["name"] for p in health["providers"]]
        if "youtube_captions" not in names or "yt_dlp_subtitles" not in names:
            failures.append(f"health sin proveedores esperados: {names}")
        if health.get("worker", {}).get("name") != "faster_whisper":
            failures.append("health sin worker faster_whisper")
        # el summary no toca proveedores: sus métricas siguen en 0 llamadas
        for provider in health["providers"]:
            if provider["breaker"] != "closed":
                failures.append(f"breaker {provider['name']} no cerrado")

    print("FAILURES:", failures if failures else "ninguna — VERIFICACIÓN OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
