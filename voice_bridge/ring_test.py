"""Place one real test call: ring the phone through ntfy, hold the voice review, print what the owner said."""
import logging

from voice_bridge import call_user_for_review

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

if __name__ == "__main__":
    print(call_user_for_review(
        status_summary=("Nova was upgraded today: a new website design kit with real photos and fonts, a Hey Nova wake word, "
                        "verified research with sources, 54 skills, and a redesigned dashboard and email."),
        questions=("Can you hear me clearly? Which should come first tomorrow: finding cafes without websites, "
                   "or polishing the website concepts?"),
    ))
