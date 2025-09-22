import os
import wave
from typing import List, Optional


class AudioService:
    """Service for handling audio recording and file management"""

    @staticmethod
    def create_audio_directory(conversation_id: str) -> str:
        """Create audio directory for a conversation"""
        audio_dir = f"store/audio/{conversation_id}"
        os.makedirs(audio_dir, exist_ok=True)
        return audio_dir

    @staticmethod
    def save_audio_chunks(
        audio_chunks: List[bytes],
        conversation_id: str,
        message_id: str,
        role: str,
        sample_rate: int = 8000,
        channels: int = 1,
    ) -> Optional[str]:
        """Save audio chunks to a WAV file using the predictable path store/audio/{conversation_id}/{message_id}.wav"""
        try:
            # Create directory
            audio_dir = AudioService.create_audio_directory(conversation_id)

            # Create filename with message_id only (no role suffix)
            filename = f"{message_id}.wav"
            file_path = os.path.join(audio_dir, filename)

            print(f"Saving audio chunk to {file_path}")

            # Combine all audio chunks
            if not audio_chunks:
                return None

            combined_audio = b"".join(audio_chunks)

            # Save as WAV file
            with wave.open(file_path, "wb") as wav_file:
                wav_file.setnchannels(channels)
                wav_file.setsampwidth(2)  # 16-bit audio
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(combined_audio)

            print(f"🎵 Saved audio file: {file_path} ({len(combined_audio)} bytes)")
            return file_path

        except Exception as e:
            print(f"❌ Error saving audio file: {e}")
            return None

    @staticmethod
    def get_audio_file_path(conversation_id: str, message_id: str) -> str:
        """Get the expected audio file path for a message (store/audio/{conversation_id}/{message_id}.wav)"""
        audio_dir = f"store/audio/{conversation_id}"
        return os.path.join(audio_dir, f"{message_id}.wav")

    @staticmethod
    def cleanup_conversation_audio(conversation_id: str) -> bool:
        """Clean up audio files for a conversation"""
        try:
            audio_dir = f"store/audio/{conversation_id}"
            if os.path.exists(audio_dir):
                for file in os.listdir(audio_dir):
                    file_path = os.path.join(audio_dir, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                os.rmdir(audio_dir)
                print(f"🗑️ Cleaned up audio directory: {audio_dir}")
                return True
        except Exception as e:
            print(f"❌ Error cleaning up audio: {e}")
        return False

    @staticmethod
    def get_conversation_audio_files(conversation_id: str) -> List[str]:
        """Get list of all audio files for a conversation"""
        try:
            audio_dir = f"store/audio/{conversation_id}"
            if os.path.exists(audio_dir):
                files = []
                for file in os.listdir(audio_dir):
                    if file.endswith(".wav"):
                        files.append(os.path.join(audio_dir, file))
                return sorted(files)
        except Exception as e:
            print(f"❌ Error listing audio files: {e}")
        return []
