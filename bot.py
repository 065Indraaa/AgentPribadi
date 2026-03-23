import os
import logging
import tempfile
import asyncio
from pathlib import Path
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from openai import OpenAI

# ============================================
#   KONFIGURASI - ISI DI SINI
# =============================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8748967261:AAHX33EjBKctGw3ZvSlJoEIXvrjv_tQcNqA").strip()
MEGALLM_API_KEY    = os.environ.get("MEGALLM_API_KEY", "sk-mega-0787d693edf23072bfb73b3f11ba78bdafc276c4005dc079d836c04113ceb6bd").strip()
MEGALLM_BASE_URL   = os.environ.get("MEGALLM_BASE_URL", "https://ai.megallm.io/v1").strip()
MODEL_NAME         = "Qwen 3.5 397B"   # Qwen 3.5 397B di MegaLLM

# =============================================
#   SETUP LOGGING
# =============================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =============================================
#   SETUP CLIENT MEGALLM
# =============================================
client = OpenAI(
    api_key=MEGALLM_API_KEY,
    base_url=MEGALLM_BASE_URL,
)

# =============================================
#   SYSTEM PROMPT - IDENTITAS ASISTEN
# =============================================
SYSTEM_PROMPT = """Kamu adalah asisten akademik pribadi untuk mahasiswa Pendidikan Teknologi Informasi di Universitas Negeri Surabaya (UNESA).

Tugas utamamu:
1. Menjawab semua pertanyaan seputar perkuliahan, mata kuliah, tugas, dan kehidupan akademik.
2. Mengerjakan dan menjelaskan soal-soal dari semua mata kuliah Pendidikan Teknologi Informasi.
3. Membuat rangkuman materi dari teks atau file yang dikirimkan.
4. Membaca isi file (PDF, Word, teks) dan membantu menganalisis isinya.
5. Membantu memahami konsep-konsep di bidang teknologi informasi, pemrograman, jaringan, database, dll.

Aturan cara menjawab yang WAJIB kamu ikuti:
- Gunakan bahasa Indonesia yang santai tapi tetap jelas dan sopan, seperti kakak senior yang bantu adik tingkatnya.
- JANGAN gunakan simbol bintang (asterisk *) sama sekali dalam jawaban.
- JANGAN gunakan markdown formatting seperti **bold**, *italic*, atau #heading.
- Gunakan angka (1. 2. 3.) atau huruf (a. b. c.) untuk membuat daftar, bukan simbol.
- Pisahkan bagian-bagian jawaban dengan baris kosong supaya mudah dibaca.
- Kalau ada jawaban soal, tampilkan langkah-langkahnya secara urut dan jelas.
- Kalau ada istilah teknis, kasih penjelasan singkatnya.
- Jawaban harus akurat, tidak boleh asal-asalan, terutama soal materi kuliah.
- Kalau ada soal hitungan, tunjukkan proses perhitungannya step by step.
- Akhiri jawaban dengan kalimat penutup yang ramah jika dirasa perlu.

Prodi: Pendidikan Teknologi Informasi
Universitas: Universitas Negeri Surabaya (UNESA)
Fokus bidang: Pemrograman, Jaringan Komputer, Database, Multimedia, Kependidikan TI, dll."""


# =============================================
#   RIWAYAT PERCAKAPAN PER USER
# =============================================
conversation_history: dict[int, list] = {}

def get_history(user_id: int) -> list:
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    return conversation_history[user_id]

def add_to_history(user_id: int, role: str, content: str):
    history = get_history(user_id)
    history.append({"role": role, "content": content})
    # Batasi riwayat ke 20 pesan terakhir supaya tidak terlalu panjang
    if len(history) > 20:
        conversation_history[user_id] = history[-20:]

def clear_history(user_id: int):
    conversation_history[user_id] = []


# =============================================
#   FUNGSI TANYA KE AI
# =============================================
def ask_ai(user_id: int, user_message: str) -> str:
    if not MEGALLM_API_KEY:
        logger.error("MEGALLM_API_KEY is not set — cannot make API request.")
        return "Maaf, konfigurasi API belum lengkap. Hubungi admin bot ya."

    add_to_history(user_id, "user", user_message)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += get_history(user_id)

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.7,
            max_tokens=3000,
        )
        reply = response.choices[0].message.content.strip()

        # Bersihkan simbol markdown yang mungkin masih muncul
        reply = bersihkan_format(reply)

        add_to_history(user_id, "assistant", reply)
        return reply

    except Exception as e:
        logger.error(f"Error dari MegaLLM: {e}")
        return "Maaf, ada gangguan saat menghubungi AI. Coba lagi beberapa saat ya."


def bersihkan_format(teks: str) -> str:
    """Bersihkan simbol markdown supaya lebih bersih di Telegram."""
    import re
    # Hapus bold/italic markdown
    teks = re.sub(r'\*\*(.+?)\*\*', r'\1', teks)
    teks = re.sub(r'\*(.+?)\*', r'\1', teks)
    teks = re.sub(r'__(.+?)__', r'\1', teks)
    teks = re.sub(r'_(.+?)_', r'\1', teks)
    # Hapus heading markdown
    teks = re.sub(r'^#{1,6}\s+', '', teks, flags=re.MULTILINE)
    # Hapus backtick triple tapi biarkan isinya
    teks = re.sub(r'```[\w]*\n?', '', teks)
    teks = re.sub(r'```', '', teks)
    return teks.strip()


# =============================================
#   BACA ISI FILE
# =============================================
def baca_file_teks(path: str) -> str:
    """Baca file teks biasa."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def baca_file_pdf(path: str) -> str:
    """Baca isi PDF."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(path)
        teks = ""
        for page in doc:
            teks += page.get_text()
        return teks
    except ImportError:
        return "[PyMuPDF tidak terinstall. Jalankan: pip install pymupdf]"
    except Exception as e:
        return f"[Gagal membaca PDF: {e}]"

def baca_file_docx(path: str) -> str:
    """Baca isi file Word (.docx)."""
    try:
        import docx
        doc = docx.Document(path)
        teks = "\n".join([para.text for para in doc.paragraphs])
        return teks
    except ImportError:
        return "[python-docx tidak terinstall. Jalankan: pip install python-docx]"
    except Exception as e:
        return f"[Gagal membaca DOCX: {e}]"

def proses_file(path: str, filename: str) -> str:
    """Pilih cara baca berdasarkan ekstensi file."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return baca_file_pdf(path)
    elif ext in [".docx", ".doc"]:
        return baca_file_docx(path)
    elif ext in [".txt", ".py", ".js", ".html", ".css", ".java", ".cpp", ".c", ".json", ".xml", ".csv", ".md"]:
        return baca_file_teks(path)
    else:
        # Coba baca sebagai teks
        try:
            return baca_file_teks(path)
        except:
            return f"[Format file {ext} belum didukung untuk dibaca otomatis.]"


# =============================================
#   HANDLER COMMAND /start
# =============================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nama = update.effective_user.first_name or "Kak"
    pesan = (
        f"Halo {nama}, selamat datang!\n\n"
        "Aku adalah asisten akademik kamu untuk kuliah di Pendidikan Teknologi Informasi UNESA.\n\n"
        "Apa saja yang bisa aku bantu:\n"
        "1. Menjawab soal-soal kuliah (semua mata kuliah)\n"
        "2. Membuat rangkuman materi\n"
        "3. Membaca dan menganalisis file yang kamu kirim (PDF, Word, teks, kode)\n"
        "4. Menjelaskan konsep-konsep TI\n"
        "5. Membantu tugas dan latihan soal\n\n"
        "Cara pakai:\n"
        "- Langsung ketik pertanyaan atau soalmu\n"
        "- Kirim file (PDF/Word/teks) lalu tulis instruksinya\n"
        "- Ketik /reset untuk memulai percakapan baru\n"
        "- Ketik /bantuan untuk melihat panduan lengkap\n\n"
        "Yuk mulai, ketik pertanyaan atau soalmu!"
    )
    await update.message.reply_text(pesan)


# =============================================
#   HANDLER COMMAND /reset
# =============================================
async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    clear_history(user_id)
    await update.message.reply_text(
        "Percakapan sudah direset. Kita mulai dari awal lagi ya!"
    )


# =============================================
#   HANDLER COMMAND /bantuan
# =============================================
async def cmd_bantuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pesan = (
        "Panduan Penggunaan Asisten Akademik PTI UNESA\n\n"
        "Perintah yang tersedia:\n"
        "/start   - Mulai dan lihat sambutan\n"
        "/reset   - Hapus riwayat percakapan, mulai baru\n"
        "/bantuan - Tampilkan panduan ini\n\n"
        "Cara menggunakan:\n\n"
        "1. Tanya langsung\n"
        "   Cukup ketik pertanyaanmu, contoh:\n"
        "   - Jelaskan apa itu normalisasi database\n"
        "   - Apa perbedaan TCP dan UDP?\n"
        "   - Kerjakan soal: hitungan subnet berikut...\n\n"
        "2. Kirim file untuk dibaca dan dianalisis\n"
        "   Kirim file PDF, Word, atau teks, lalu tulis instruksinya di caption, contoh:\n"
        "   - Buatkan rangkuman dari materi ini\n"
        "   - Kerjakan soal-soal yang ada di file ini\n"
        "   - Jelaskan isi materi ini dengan bahasa yang mudah\n\n"
        "3. Soal apapun bisa dikerjakan\n"
        "   Pemrograman, jaringan, database, algoritma, matematika, dll.\n\n"
        "Catatan: Aku mengingat percakapan kita (max 20 pesan terakhir).\n"
        "Gunakan /reset kalau mau ganti topik biar tidak bingung."
    )
    await update.message.reply_text(pesan)


# =============================================
#   HANDLER PESAN TEKS
# =============================================
async def handle_teks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    pesan_user = update.message.text

    # Tampilkan status "mengetik..."
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    jawaban = ask_ai(user_id, pesan_user)

    # Telegram punya batas 4096 karakter per pesan
    if len(jawaban) > 4000:
        bagian = [jawaban[i:i+4000] for i in range(0, len(jawaban), 4000)]
        for bagian_pesan in bagian:
            await update.message.reply_text(bagian_pesan)
    else:
        await update.message.reply_text(jawaban)


# =============================================
#   HANDLER FILE / DOKUMEN
# =============================================
async def handle_dokumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    dokumen: "Document" = update.message.document
    caption = update.message.caption or "Tolong baca dan analisis file ini. Buat rangkuman isinya."

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    await update.message.reply_text(
        f"Oke, sedang membaca file '{dokumen.file_name}', tunggu sebentar ya..."
    )

    # Download file ke folder sementara
    with tempfile.TemporaryDirectory() as tmpdir:
        path_file = os.path.join(tmpdir, dokumen.file_name)
        file_obj = await context.bot.get_file(dokumen.file_id)
        await file_obj.download_to_drive(path_file)

        # Baca isi file
        isi_file = proses_file(path_file, dokumen.file_name)

        if not isi_file.strip():
            await update.message.reply_text(
                "Maaf, file yang kamu kirim kosong atau tidak bisa dibaca."
            )
            return

        # Batasi panjang konten supaya tidak melebihi batas token
        if len(isi_file) > 15000:
            isi_file = isi_file[:15000] + "\n\n[... konten terpotong karena terlalu panjang ...]"

        # Gabungkan instruksi + isi file
        prompt = (
            f"Aku mengirimkan sebuah file bernama '{dokumen.file_name}'.\n\n"
            f"Instruksiku: {caption}\n\n"
            f"Berikut isi file tersebut:\n\n{isi_file}"
        )

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing"
        )

        jawaban = ask_ai(user_id, prompt)

        if len(jawaban) > 4000:
            bagian = [jawaban[i:i+4000] for i in range(0, len(jawaban), 4000)]
            for bagian_pesan in bagian:
                await update.message.reply_text(bagian_pesan)
        else:
            await update.message.reply_text(jawaban)


# =============================================
#   HANDLER ERROR
# =============================================
async def handle_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error terjadi: {context.error}")
    if update and update.message:
        await update.message.reply_text(
            "Ups, ada error yang tidak terduga. Coba kirim ulang pesanmu ya."
        )


# =============================================
#   MAIN - JALANKAN BOT
# =============================================
def main():
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: Environment variable TELEGRAM_BOT_TOKEN is not set. Exiting.")
        raise SystemExit(1)

    if not MEGALLM_API_KEY:
        print("ERROR: Environment variable MEGALLM_API_KEY is not set. Exiting.")
        raise SystemExit(1)

    # Debug logging — shows presence/length without exposing actual key values
    logger.info("Config check — TELEGRAM_BOT_TOKEN: %s (length: %d)",
                "SET" if TELEGRAM_BOT_TOKEN else "NOT SET", len(TELEGRAM_BOT_TOKEN))
    logger.info("Config check — MEGALLM_API_KEY: %s (length: %d)",
                "SET" if MEGALLM_API_KEY else "NOT SET", len(MEGALLM_API_KEY))
    logger.info("Config check — MEGALLM_BASE_URL: %s", MEGALLM_BASE_URL)

    print("=" * 50)
    print("  Asisten Akademik PTI UNESA - Telegram Bot")
    print("  Model: Qwen 3.5 | MegaLLM API")
    print("=" * 50)
    print("Bot sedang berjalan... Tekan Ctrl+C untuk berhenti.\n")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Daftarkan semua handler
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("reset",    cmd_reset))
    app.add_handler(CommandHandler("bantuan",  cmd_bantuan))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_teks))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_dokumen))
    app.add_error_handler(handle_error)

    # Jalankan bot dengan polling
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
