from pathlib import Path
import yt_dlp


def download_youtube_video(url: str, output_dir: str = "videos") -> str:
    """
    Download a YouTube video to `output_dir` using yt-dlp and return the local file path.

    - Always outputs an .mp4 file
    - Uses the video ID as the filename
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "format": "bestvideo*+bestaudio/best",  # Force video+audio merge
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        file_path = Path(ydl.prepare_filename(info))
        # Normalize extension to .mp4 if needed
        if file_path.suffix.lower() != ".mp4":
            file_path = file_path.with_suffix(".mp4")
        return str(file_path)
