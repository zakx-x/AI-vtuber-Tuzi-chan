import cv2
import face_recognition
import numpy as np

def buka_mata_tuzi():
    known_face_encodings = []
    known_face_names = []

    try:
        zak_image = face_recognition.load_image_file("zak.jpg")
        zak_face_encoding = face_recognition.face_encodings(zak_image)[0]
        known_face_encodings.append(zak_face_encoding)
        known_face_names.append("ZAK")
        print("\n[Tuzi Vision]: Memori visual ZAK berhasil dimuat.")
    except:
        print("\n[Tuzi Vision]: File 'zak.jpg' tidak ditemukan! Pastikan foto berada di folder yang sama.")

    video_capture = cv2.VideoCapture(0)
    print("[Tuzi Vision]: Aktif. Tekan 't' untuk mengajari Tuzi. Tekan 'q' untuk keluar.")

    while True:
        ret, frame = video_capture.read()
        if not ret:
            break
        
        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small_frame = small_frame[:, :, ::-1] 
        
        face_locations = face_recognition.face_locations(rgb_small_frame)
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
        
        face_names = []
        for face_encoding in face_encodings:
            matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
            name = "Unknown"
            
            face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
            if len(face_distances) > 0:
                best_match_index = np.argmin(face_distances)
                if matches[best_match_index]:
                    name = known_face_names[best_match_index]
            
            face_names.append(name)
            
        for (top, right, bottom, left), name in zip(face_locations, face_names):
            top *= 4; right *= 4; bottom *= 4; left *= 4 
            
            color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
            
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            cv2.rectangle(frame, (left, bottom - 35), (right, bottom), color, cv2.FILLED)
            cv2.putText(frame, name, (left + 6, bottom - 6), cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 255, 255), 1)

        cv2.imshow('Mata Tuzi', frame)
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('t'):
            if "Unknown" in face_names:
                print("\n[Tuzi]: Saya melihat wajah yang tidak dikenal.")
                unknown_index = face_names.index("Unknown")
                new_encoding = face_encodings[unknown_index]
                
                new_name = input("Siapa nama orang ini? ")
                known_face_encodings.append(new_encoding)
                known_face_names.append(new_name.upper())
                print(f"[Tuzi]: Mengerti, saya akan mengingat {new_name.upper()}!")
            else:
                print("\n[Tuzi]: Tidak ada orang asing di layar.")
                
        elif key == ord('q'):
            break

    video_capture.release()
    cv2.destroyAllWindows()
    print("\n[Tuzi Vision]: Mode penglihatan dimatikan. Kembali ke mode obrolan.")