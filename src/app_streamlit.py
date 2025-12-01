"""Streamlit app for Nio Transcribe.

Main user interface for viral moment extraction and cut sheet generation.
"""

import streamlit as st
import traceback
import sys
import os

# Add the parent directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
from src.transcript_utils import get_transcript_from_youtube
from src.llm_client import extract_moments
from src.cutsheets import generate_cut_sheets
from src.export_utils import to_csv, to_markdown, format_clip_summary, to_ffmpeg_json, srt_to_ffmpeg_json

from src.pdf_utils import clips_to_pdf
from src.clipping import cut_from_ffmpeg_json
from src.video_download import download_youtube_video


def main():
    """Main Streamlit application."""
    st.set_page_config(
        page_title="Nio Transcribe",
        page_icon="✂️",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    # Initialize configuration
    try:
        config.validate_config()
    except RuntimeError as e:
        st.error(f"Configuration Error: {e}")
        st.info("Please set the required environment variables and restart the app.")
        st.stop()

    # App header
    st.title("✂️ Nio Transcribe")
    st.markdown("*Catholic Media Viral Moment Extraction Tool*")
    st.markdown("---")

    # Input section
    st.subheader("📺 Input")

    col1, col2 = st.columns([2, 1])

    with col1:
        youtube_url = st.text_input(
            "YouTube URL (optional)",
            placeholder="youtube.com/watch?v=dQw4w9WgXcQ or youtu.be/dQw4w9WgXcQ",
            help="Accepts any YouTube format: watch, youtu.be, shorts, embed (auto-normalized)"
        )

    with col2:
        language = st.selectbox(
            "Language",
            options=["en", "es", "fr", "de", "it", "pt"],
            index=0,
            help="Transcript language"
        )

    transcript_input = st.text_area(
        "Or paste transcript directly (optional)",
        height=200,
        placeholder="[00:00.56–00:02.63] Then the last one which is kind of the...\n[00:02.63–00:05.12] most important thing...",
        help="Paste a formatted transcript with timestamps"
    )

    # Generate button
    generate_button = st.button(
        "🚀 Generate Viral Clips",
        type="primary",
        use_container_width=True
    )

    if generate_button:
        # Validate input
        if not transcript_input.strip() and not youtube_url.strip():
            st.error("⚠️ Please provide either a YouTube URL or a transcript.")
            st.stop()

        # Process input
        with st.spinner("🔄 Processing..."):
            try:
                # Get transcript
                if transcript_input.strip():
                    transcript_text = transcript_input.strip()
                    metadata = {}
                    st.info("📝 Using provided transcript")
                else:
                    st.info(f"🎥 Fetching transcript from YouTube...")
                    transcript_text, metadata = get_transcript_from_youtube(youtube_url, language)
                    st.success("✅ Transcript fetched successfully")

                # Extract moments
                st.info("🎯 Extracting viral moments...")
                moments = extract_moments(transcript_text, metadata)
                st.success(f"✅ Found {len(moments)} potential viral moments")

                # Generate cut sheets
                st.info("📋 Generating editor cut sheets...")
                moments_with_cuts = generate_cut_sheets(moments)
                st.success("✅ Cut sheets generated")

                # Store results in session state
                st.session_state.moments_with_cuts = moments_with_cuts
                st.session_state.metadata = metadata
                st.session_state.transcript_text = transcript_text

            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                with st.expander("Technical Details"):
                    st.code(traceback.format_exc())
                st.stop()

    # Display results if available
    if "moments_with_cuts" in st.session_state:
        moments_with_cuts = st.session_state.moments_with_cuts
        metadata = st.session_state.metadata

        st.markdown("---")
        st.subheader("📊 Results")

        # Display metadata if available
        if metadata:
            display_video_metadata(metadata)

        # Display summary
        summary = format_clip_summary(moments_with_cuts)
        st.info(summary)


        # Display clips
        if moments_with_cuts:
            display_clips(moments_with_cuts)


            # --- Download Video Section ---
            st.markdown("---")
            st.subheader("🎥 Download Video From YouTube URL")

            url_for_download = st.text_input(
                "YouTube URL for auto-download (optional)",
                key="download_url_input",
                placeholder="https://www.youtube.com/watch?v=...",
            )

            if st.button("Download video from URL"):
                if not url_for_download.strip():
                    st.warning("Please paste a valid YouTube URL first.")
                else:
                    with st.spinner("Downloading video..."):
                        try:
                            local_path = download_youtube_video(url_for_download.strip())
                            st.session_state["downloaded_video_path"] = local_path
                            st.success(f"Video downloaded to: {local_path}")
                        except Exception as e:
                            st.error(f"Download failed: {e}")

            # --- Auto-Clipper Section ---
            st.markdown("---")
            st.subheader("🎬 Auto-Clip Video (FFmpeg)")

            mode = st.radio(
                "Timestamp source",
                options=["Catholic Cuts moments", "SRT file"],
                horizontal=True,
            )

            source_choice = st.radio(
                "Choose video source for auto-clipping:",
                ["Uploaded file", "Downloaded from URL"],
                key="video_source_choice",
            )

            uploaded_video = None
            if source_choice == "Uploaded file":
                uploaded_video = st.file_uploader(
                    "Upload the matching video file (MP4/MOV)",
                    type=["mp4", "mov", "m4v"],
                    key="autoclip_upload",
                )

            srt_file = None
            if mode == "SRT file":
                srt_file = st.file_uploader("Upload .srt file", type=["srt"], key="srt_uploader")

            if st.button("Run Auto-Clipper", use_container_width=True):
                # Resolve video_path based on choice
                video_path = None

                if source_choice == "Uploaded file":
                    if uploaded_video is None:
                        st.warning("Please upload a video file, or switch to 'Downloaded from URL'.")
                        st.stop()
                    else:
                        # Save uploaded file to a temp location
                        import tempfile, os
                        tmp_dir = tempfile.mkdtemp()
                        temp_path = os.path.join(tmp_dir, uploaded_video.name)
                        with open(temp_path, "wb") as f:
                            f.write(uploaded_video.read())
                        video_path = temp_path

                else:  # "Downloaded from URL"
                    video_path = st.session_state.get("downloaded_video_path")
                    if not video_path:
                        st.warning("No downloaded video found. Use the 'Download video from URL' section first.")
                        st.stop()

                # At this point we have a valid video_path and can generate ffmpeg_json
                with st.spinner("Cutting clips with ffmpeg..."):
                    try:
                        if mode == "Catholic Cuts moments":
                            ffmpeg_json = to_ffmpeg_json(moments_with_cuts)
                        else:
                            if srt_file is None:
                                st.error("Please upload an .srt file for SRT mode.")
                                st.stop()
                            srt_text = srt_file.read().decode("utf-8", errors="ignore")
                            ffmpeg_json = srt_to_ffmpeg_json(srt_text)

                        clip_paths = cut_from_ffmpeg_json(video_path, ffmpeg_json, output_dir="clips")

                        st.success(f"Generated {len(clip_paths)} clips into the 'clips' folder:")
                        for p in clip_paths:
                            st.write(p)
                    except Exception as e:
                        st.error(f"Error running auto-clipper: {e}")

            # Download section
            st.markdown("---")
            display_download_section(moments_with_cuts)
        else:
            st.warning("No viral moments found in the transcript.")


def display_video_metadata(metadata):
    """Display video metadata in a nice format."""
    if not metadata:
        return

    st.markdown("### 🎬 Video Information")

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        title = metadata.get("title", "")
        if title:
            st.markdown(f"**{title}**")

        channel = metadata.get("channel_name", "")
        if channel:
            st.markdown(f"*by {channel}*")

        url = metadata.get("url", "")
        if url:
            st.markdown(f"[🔗 Watch Video]({url})")

    with col2:
        duration = metadata.get("duration_seconds", 0)
        if duration:
            minutes = duration // 60
            seconds = duration % 60
            st.metric("Duration", f"{minutes}m {seconds}s")

        views = metadata.get("view_count", 0)
        if views:
            st.metric("Views", f"{views:,}")

    with col3:
        likes = metadata.get("like_count", 0)
        if likes:
            st.metric("Likes", f"{likes:,}")

        is_auto = metadata.get("is_auto_generated", False)
        caption_type = "Auto-generated" if is_auto else "Manual"
        st.metric("Captions", caption_type)

    # Thumbnail
    thumbnail = metadata.get("thumbnail", "")
    if thumbnail:
        with st.expander("📸 Thumbnail"):
            st.image(thumbnail, width=300)


def display_clips(moments_with_cuts):
    """Display the extracted clips in an organized way."""
    st.markdown("### ✂️ Viral Clips")

    for i, moment in enumerate(moments_with_cuts, 1):
        cut_sheet = moment.get("editor_cut_sheet", {})

        # Create expander title
        timestamps = moment.get("timestamps", "")
        energy_tag = moment.get("energy_tag", "")
        viral_trigger = moment.get("viral_trigger", "")
        clip_label = cut_sheet.get("clip_label", f"CLIP_{i}")

        expander_title = f"**Clip {i}: {clip_label}** • {timestamps} • {energy_tag} • {viral_trigger}"

        with st.expander(expander_title):
            # Quote
            quote = moment.get("quote", "")
            if quote:
                st.markdown("#### 💬 Quote")
                st.markdown(f"> {quote}")

            col1, col2 = st.columns([1, 1])

            with col1:
                # Moment details
                st.markdown("#### 🎯 Moment Details")

                why_hits = moment.get("why_it_hits", "")
                if why_hits:
                    st.markdown(f"**Why it hits:** {why_hits}")

                duration = moment.get("clip_duration_seconds", "")
                if duration:
                    st.markdown(f"**Duration:** {duration} seconds")

                flags = moment.get("flags", [])
                if flags:
                    st.markdown(f"**Flags:** {', '.join(flags)}")

                # Persona captions
                st.markdown("#### 👥 Persona Captions")
                personas = moment.get("persona_captions", {})

                for persona_key, persona_name in [
                    ("historian", "Historian"),
                    ("thomist", "Thomist"),
                    ("ex_protestant", "Ex-Protestant"),
                    ("meme_catholic", "Meme Catholic"),
                    ("old_world_catholic", "Old World Catholic"),
                    ("catholic", "Catholic")
                ]:
                    caption = personas.get(persona_key, "")
                    if caption:
                        st.markdown(f"**{persona_name}:** {caption}")

            with col2:
                # Editor cut sheet
                st.markdown("#### 📋 Editor Cut Sheet")

                st.markdown(f"**In/Out Points:** {cut_sheet.get('in_point', 'N/A')} → {cut_sheet.get('out_point', 'N/A')}")
                st.markdown(f"**Aspect Ratio:** {cut_sheet.get('aspect_ratio', '9:16')}")
                st.markdown(f"**Crop Note:** {cut_sheet.get('crop_note', 'N/A')}")

                hook = cut_sheet.get('opening_hook_subtitle', '')
                if hook:
                    st.markdown(f"**Hook Subtitle:** {hook}")

                emphasis = cut_sheet.get('emphasis_words_caps', [])
                if emphasis:
                    st.markdown(f"**Emphasis Words:** {', '.join(emphasis)}")

                st.markdown(f"**Pacing:** {cut_sheet.get('pacing_note', 'N/A')}")
                st.markdown(f"**B-Roll:** {cut_sheet.get('b_roll_ideas', 'none')}")
                st.markdown(f"**Text on Screen:** {cut_sheet.get('text_on_screen_idea', 'none')}")
                st.markdown(f"**Silence Handling:** {cut_sheet.get('silence_handling', 'none')}")
                st.markdown(f"**Thumbnail Text:** {cut_sheet.get('thumbnail_text', 'N/A')}")
                st.markdown(f"**Thumbnail Cue:** {cut_sheet.get('thumbnail_face_cue', 'N/A')}")
                st.markdown(f"**Platform Priority:** {cut_sheet.get('platform_priority', 'All')}")

                default_caption = cut_sheet.get('use_persona_caption', '')
                if default_caption:
                    st.markdown(f"**Default Caption:** {default_caption}")


def display_download_section(moments_with_cuts):
    """Display download options for the clips."""
    st.subheader("📥 Download")

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

    try:
        # Generate export data
        csv_data = to_csv(moments_with_cuts)
        md_data = to_markdown(moments_with_cuts)
        pdf_data = clips_to_pdf(moments_with_cuts, st.session_state.get("metadata"))
        ffmpeg_json = to_ffmpeg_json(moments_with_cuts)

        with col1:
            st.download_button(
                label="📊 Download CSV",
                data=csv_data,
                file_name="viral_clips.csv",
                mime="text/csv",
                use_container_width=True,
                help="Download as CSV for spreadsheet editing"
            )

        with col2:
            st.download_button(
                label="📝 Download Markdown",
                data=md_data,
                file_name="viral_clips.md",
                mime="text/markdown",
                use_container_width=True,
                help="Download as Markdown for documentation"
            )

        with col3:
            st.download_button(
                label="📄 Download PDF",
                data=pdf_data,
                file_name="viral_clips.pdf",
                mime="application/pdf",
                use_container_width=True,
                help="One cut-sheet PDF for editors"
            )

        with col4:
            st.download_button(
                label="🎬 Download FFmpeg JSON",
                data=ffmpeg_json,
                file_name="ffmpeg_clips.json",
                mime="application/json",
                use_container_width=True,
                help="Download JSON of clip start/end timestamps for ffmpeg auto-clipping"
            )

        # Optional: keep the preview expander
        with st.expander("👀 Preview Exports"):
            tab1, tab2, tab3 = st.tabs(["CSV Preview", "Markdown Preview", "FFmpeg JSON"])

            with tab1:
                if csv_data:
                    st.code(csv_data[:1000] + "..." if len(csv_data) > 1000 else csv_data)
                else:
                    st.info("No CSV data to preview")

            with tab2:
                if md_data:
                    st.markdown(md_data[:2000] + "..." if len(md_data) > 2000 else md_data)
                else:
                    st.info("No Markdown data to preview")

            with tab3:
                if ffmpeg_json:
                    st.code(ffmpeg_json[:1000] + "..." if len(ffmpeg_json) > 1000 else ffmpeg_json, language="json")
                else:
                    st.info("No FFmpeg JSON data to preview")

    except Exception as e:
        st.error(f"Error generating downloads: {e}")


if __name__ == "__main__":
    main()