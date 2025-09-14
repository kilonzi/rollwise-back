import os
import uuid
import audioop
from datetime import datetime
from typing import Optional

from app.models import get_db, Call, CallMessage
from app.config.settings import settings


class CallService:
    def __init__(self):
        self.calls = {}

    async def start_call(self, call_sid: str, from_number: str, to_number: str) -> str:
        """Start a new call session"""
        call_id = str(uuid.uuid4())

        # Create transcript directory
        transcript_dir = "transcripts"
        os.makedirs(transcript_dir, exist_ok=True)
        transcript_file = f"{transcript_dir}/{call_id}.txt"

        # Save to database
        db = next(get_db())
        try:
            call = Call(
                id=call_id,
                call_sid=call_sid,
                from_number=from_number,
                to_number=to_number,
                transcript_file=transcript_file,
            )
            db.add(call)
            db.commit()

            # Store in memory for quick access
            self.calls[call_id] = {
                "call_sid": call_sid,
                "from_number": from_number,
                "to_number": to_number,
                "transcript_file": transcript_file,
                "started_at": datetime.now(),
            }

        finally:
            db.close()

        return call_id

    async def end_call(self, call_id: str):
        """End a call session"""
        if call_id in self.calls:
            # Update database
            db = next(get_db())
            try:
                call = db.query(Call).filter(Call.id == call_id).first()
                if call:
                    call.ended_at = datetime.now()
                    if call.started_at:
                        duration = (call.ended_at - call.started_at).total_seconds()
                        call.duration_seconds = int(duration)
                    call.status = "completed"
                    db.commit()
            finally:
                db.close()

            # Remove from memory
            del self.calls[call_id]

    async def save_transcript(self, call_id: str, speaker: str, content: str):
        """Save transcript entry"""
        if call_id not in self.calls:
            return

        call_info = self.calls[call_id]
        transcript_file = call_info["transcript_file"]

        # Save to file
        with open(transcript_file, "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {speaker.upper()}: {content}\n")

        # Save to database
        db = next(get_db())
        try:
            message = CallMessage(
                call_id=call_id,
                sender=speaker.lower(),
                content=content,
                message_type="transcript",
            )
            db.add(message)
            db.commit()
        finally:
            db.close()

    def process_audio_chunk(self, audio_data: bytes) -> Optional[bytes]:
        """Process audio chunk with silence detection"""
        try:
            # Check RMS (volume level) to detect silence
            rms = audioop.rms(audio_data, 2)
            if rms > settings.silence_threshold:
                return audio_data
            return None
        except audioop.error:
            # If audio processing fails, return the original data
            return audio_data

    def get_call_info(self, call_id: str) -> Optional[dict]:
        """Get call information"""
        return self.calls.get(call_id)


# Global call service instance
call_service = CallService()
