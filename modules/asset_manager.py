import hashlib
import os
import subprocess
from dotenv import load_dotenv


class AssetManager:
    """
    Local visual generator.

    This version intentionally does not use Pexels or another stock-video API.
    It creates short animated vertical visual cards with FFmpeg using the visual
    concepts produced by Gemini.
    """

    def __init__(self):
        load_dotenv()
        self.assets_dir = os.path.join(os.getcwd(), "assets", "video_clips")
        os.makedirs(self.assets_dir, exist_ok=True)
        self.width = 1080
        self.height = 1920
        self.fps = 30
        self.clip_duration = 5

        self.font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if not os.path.exists(self.font):
            self.font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    def _color_for(self, text):
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        r = int(digest[0:2], 16)
        g = int(digest[2:4], 16)
        b = int(digest[4:6], 16)
        factor = 0.28
        return f"#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}"

    def _write_text_file(self, path, text):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def generate_visual(self, concept, scene_id, variant):
        safe_hash = hashlib.sha256(
            f"{scene_id}-{variant}-{concept}".encode("utf-8")
        ).hexdigest()[:12]

        output_path = os.path.join(
            self.assets_dir,
            f"scene_{scene_id}_{variant}_{safe_hash}.mp4"
        )
        text_path = os.path.join(
            self.assets_dir,
            f"scene_{scene_id}_{variant}_{safe_hash}.txt"
        )

        if os.path.exists(output_path):
            return output_path

        self._write_text_file(text_path, concept.upper())
        background = self._color_for(concept)

        filter_complex = (
            f"color=c={background}:s={self.width}x{self.height}:r={self.fps},"
            f"noise=alls=12:allf=t,"
            f"drawtext=fontfile='{self.font}':"
            f"text='ESCENA {scene_id}':fontcolor=white:fontsize=42:"
            f"x=(w-text_w)/2:y=220:alpha=0.75,"
            f"drawtext=fontfile='{self.font}':"
            f"textfile='{text_path}':fontcolor=white:fontsize=72:"
            f"line_spacing=18:x=(w-text_w)/2:y=(h-text_h)/2:alpha=1,"
            f"vignette=PI/5"
        )

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", filter_complex,
            "-t", str(self.clip_duration),
            "-r", str(self.fps),
            "-c:v", "libx264", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            output_path,
        ]

        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            print(f"   🎨 Generated local visual: scene {scene_id} {variant}")
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Local visual generation failed for scene {scene_id} {variant}:")
            print(e.stderr[-1000:])
            return None
        finally:
            if os.path.exists(text_path):
                os.remove(text_path)

    def get_videos(self, script_data):
        print("🎨 Generating local visual cards (Pexels disabled)...")
        video_pairs = []

        for scene in script_data:
            scene_id = scene["id"]
            query_a = str(scene.get("visual_1", scene.get("keywords", "abstract visual")))
            query_b = str(scene.get("visual_2", query_a))

            path_a = self.generate_visual(query_a, scene_id, "a")
            path_b = self.generate_visual(query_b, scene_id, "b")

            if path_a and path_b:
                video_pairs.append((path_a, path_b))
                print(f"   ✅ Scene {scene_id} ready (A + B).")
            elif path_a:
                video_pairs.append((path_a, path_a))
                print(f"   ⚠️ Scene {scene_id}: using A twice.")
            elif path_b:
                video_pairs.append((path_b, path_b))
                print(f"   ⚠️ Scene {scene_id}: using B twice.")
            else:
                video_pairs.append(None)
                print(f"   ❌ Scene {scene_id}: no visual generated.")

        return video_pairs
