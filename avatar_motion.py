import re


def handle_motion_command(text: str) -> dict | None:
  """Mendeteksi perintah gerakan fisik avatar dan perpindahan layar."""
  lower = text.lower().strip()

  if any(
      k in lower
      for k in ["backflip", "salto", "koprol", "putar badan", "muter"]
  ):
    return {
        "type": "action",
        "action": "backflip",
        "reply": "Waaah! Lihat nih, Tuzi bisa backflip!",
    }

  if any(
      k in lower
      for k in ["menoleh kanan", "nengok kanan", "lihat kanan", "lihat ke kanan"]
  ):
    return {
        "type": "action",
        "action": "look_right",
        "reply": "Tuzi menoleh ke kanan!",
    }

  if any(
      k in lower
      for k in ["menoleh kiri", "nengok kiri", "lihat kiri", "lihat ke kiri"]
  ):
    return {
        "type": "action",
        "action": "look_left",
        "reply": "Tuzi menoleh ke kiri!",
    }

  if any(
      k in lower
      for k in ["menoleh atas", "nengok atas", "lihat atas", "lihat ke atas"]
  ):
    return {
        "type": "action",
        "action": "look_up",
        "reply": "Tuzi melihat ke atas!",
    }

  if any(
      k in lower
      for k in ["menoleh bawah", "nengok bawah", "lihat bawah", "lihat ke bawah"]
  ):
    return {
        "type": "action",
        "action": "look_down",
        "reply": "Tuzi menoleh ke bawah!",
    }

  if any(
      k in lower
      for k in [
          "pindah ke kiri",
          "geser ke kiri",
          "ke sisi kiri",
          "ke pojok kiri",
      ]
  ):
    return {
        "type": "move",
        "target": "left",
        "reply": "Siap! Tuzi meluncur ke sisi kiri layar.",
    }

  if any(
      k in lower
      for k in [
          "pindah ke kanan",
          "geser ke kanan",
          "ke posisi awal",
          "kembali ke kanan",
      ]
  ):
    return {
        "type": "move",
        "target": "right",
        "reply": "Tuzi kembali ke sisi kanan layar ya!",
    }

  if any(
      k in lower
      for k in ["pindah ke tengah", "geser ke tengah", "ke tengah layar"]
  ):
    return {
        "type": "move",
        "target": "center",
        "reply": "Meluncur ke tengah layar!",
    }

  if any(k in lower for k in ["pindah ke atas", "ke pojok atas", "naik ke atas"]):
    return {
        "type": "move",
        "target": "top_right",
        "reply": "Tuzi pindah ke pojok atas!",
    }

  return None