import pyautogui
import time

print("Mulai! Lepaskan tangan dari mouse...")
time.sleep(3)

print("Bergerak ke tengah layar!")
# Menggerakkan mouse ke tengah (koordinat 800, 500)
pyautogui.moveTo(800, 500, duration=1)

print("Selesai!")