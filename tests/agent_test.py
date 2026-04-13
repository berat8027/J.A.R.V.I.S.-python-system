import sys
sys.path.insert(0, ".")
from modules.speech import SpeechSpeaker, Priority
import time

speaker = SpeechSpeaker()
print("1. mesaj gönderiliyor...")
speaker.speak("Merhaba efendim, test bir", blocking=True)
print("1. mesaj bitti")

speaker.speak("İkinci mesaj", blocking=True)
print("2. mesaj bitti")

speaker.speak("Üçüncü mesaj", blocking=False)
print("3. mesaj kuyruğa eklendi")
time.sleep(5)
print("Bitti")