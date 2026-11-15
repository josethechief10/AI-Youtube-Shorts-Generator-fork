import os
import json
import re
import time
from google import genai
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "gemini-3.5-flash"
RETRYABLE_STATUSES = (429, 500, 502, 503, 504)
MAX_RETRY_WAIT = 90


def _get_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Create a .env file or set the environment variable before running.")
    return genai.Client(api_key=api_key)


def _get_model():
    return os.getenv("GEMINI_MODEL") or DEFAULT_MODEL


def _is_retryable(error):
    status = getattr(error, "code", None) or getattr(error, "status_code", None)
    if status in RETRYABLE_STATUSES:
        return True
    text = str(error)
    return any(str(code) in text for code in RETRYABLE_STATUSES)


def _retry_delay(error):
    match = re.search(r"'retryDelay':\s*'(\d+(?:\.\d+)?)s'", str(error))
    if not match:
        return None
    return min(float(match.group(1)) + 1, MAX_RETRY_WAIT)


def _generate(prompt, retries=4):
    client = _get_client()
    model = _get_model()

    for attempt in range(retries):
        try:
            return client.models.generate_content(model=model, contents=prompt)
        except Exception as e:
            if attempt == retries - 1 or not _is_retryable(e):
                raise
            wait = _retry_delay(e) or 2 ** (attempt + 1)
            print(f"   ⚠️ Gemini unavailable (attempt {attempt+1}/{retries}). Retrying in {wait:.0f}s...")
            time.sleep(wait)


class ContentBrain:
    def get_trending_topic(self, lang="es"):
        language_name = {
            "es": "Spanish",
            "pt-BR": "Brazilian Portuguese",
            "en": "English",
        }.get(lang, "Spanish")

        prompt = (
            f"Give me 1 specific, viral, and engaging topic for a YouTube Short "
            f"documentary/edutainment channel. It should be a surprising fact, "
            f"science question, mystery, or intriguing real-world event. "
            f"Return ONLY the topic name in {language_name}."
        )
        response = _generate(prompt)
        topic = response.text.strip()
        print(f"🎯 Selected Topic: {topic}")
        return topic

    def generate_script(self, topic, lang="es"):
        lang_instruction = {
            "es": "SPANISH (neutral Latin American Spanish)",
            "pt-BR": "PORTUGUESE (Brazil)",
            "en": "ENGLISH",
        }.get(lang, "SPANISH (neutral Latin American Spanish)")

        print(f"📝 Writing script in {lang_instruction} for: {topic}...")

        prompt = f"""
You are the lead scriptwriter for a high-retention "Edutainment" YouTube Shorts channel.

Topic: {topic}

### GOAL
Create a 45-60 second Short. Every sentence should have a visual change.

### SCRIPT REQUIREMENTS
- Language: Write the narration strictly in {lang_instruction}.
- Perspective: Strictly 3rd Person. Avoid addressing the viewer directly with "tú/you".
- Tone: Engaging, fast-paced, logical, cinematic, but factually responsible.
- Structure: 8-9 scenes total.
- Flow: Hook -> Context -> Mechanism -> Twist -> Conclusion.
- Keep the narration concise enough for 45-60 seconds.

### VISUAL REQUIREMENTS
There is NO stock-video API in this version.
For every scene provide TWO short visual concepts in ENGLISH. These are used to create local animated visual cards, so make them concrete and visually recognizable.
- visual_1: visual idea for the first half.
- visual_2: visual idea for the second half.
- Avoid abstract emotions. Prefer objects, places, phenomena, diagrams, planets, clocks, maps, laboratory equipment, etc.

### OUTPUT FORMAT
Return ONLY valid JSON. No markdown fences.

[
  {{
    "id": 1,
    "text": "Narration sentence in the selected language.",
    "visual_1": "earth rotating space",
    "visual_2": "clock stopping five seconds",
    "mood": "mysterious"
  }}
]
"""

        for attempt in range(3):
            response = _generate(prompt)
            clean_text = response.text.replace(chr(96) * 3 + "json", "").replace(chr(96) * 3, "").strip()

            try:
                script_data = json.loads(clean_text)
            except json.JSONDecodeError:
                print(f"   ⚠️ Invalid JSON (attempt {attempt+1}/3). Raw output:")
                print(clean_text[:500])
                continue

            script_data = self._sanitize(script_data)
            if script_data:
                return script_data

            print(f"   ⚠️ Script had no usable scenes (attempt {attempt+1}/3).")

        print("❌ Script generation failed after 3 attempts.")
        return None

    def generate_metadata(self, topic, script_data):
        narration = " ".join(scene["text"] for scene in script_data)

        prompt = f"""
Write YouTube Shorts metadata for this video.

Topic: {topic}
Narration: {narration}

Rules:
- "title": under 80 characters, curiosity-driven, no clickbait punctuation spam.
- "description": 2-3 sentences summarizing the video, then a blank line, then "#Shorts".
- "tags": 8-12 lowercase search keywords, no "#" prefix.

Return ONLY strict JSON:
{{"title": "...", "description": "...", "tags": ["...", "..."]}}
"""

        fallback = {
            "title": topic[:80],
            "description": f"{topic}\n\n#Shorts",
            "tags": [],
        }

        try:
            response = _generate(prompt)
            clean_text = response.text.replace(String.fromCharCode(96).repeat(3) + "json", "").replace(String.fromCharCode(96).repeat(3), "").strip()
            metadata = json.loads(clean_text)
        except Exception as e:
            print(f"   ⚠️ Metadata generation failed ({e}). Using the topic as the title.")
            return fallback

        if not isinstance(metadata, dict) or not str(metadata.get("title", "")).strip():
            print("   ⚠️ Metadata had no usable title. Using the topic as the title.")
            return fallback

        tags = metadata.get("tags") or []
        if not isinstance(tags, list):
            tags = []

        description = str(metadata.get("description", "")).strip() or fallback["description"]
        if "#Shorts" not in description:
            description = f"{description}\n\n#Shorts"

        return {
            "title": str(metadata["title"]).strip(),
            "description": description,
            "tags": [str(tag).strip() for tag in tags if str(tag).strip()],
        }

    @staticmethod
    def _sanitize(script_data):
        if not isinstance(script_data, list):
            print(f"   ⚠️ Expected a list of scenes, got {type(script_data).__name__}.")
            return None

        scenes = []
        for raw in script_data:
            if not isinstance(raw, dict):
                continue

            text = str(raw.get("text", "")).strip()
            if not text:
                continue

            scene = dict(raw)
            scene["text"] = text
            scene["id"] = len(scenes) + 1
            scenes.append(scene)

        return scenes or None


if __name__ == "__main__":
    brain = ContentBrain()
    topic = brain.get_trending_topic()
    script = brain.generate_script(topic)

    with open("script.json", "w") as f:
        json.dump(script, f, indent=4, ensure_ascii=False)
        print("✅ Script saved to script.json")
