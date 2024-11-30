from flask import Flask, request, render_template, send_file, jsonify
import os
import subprocess
import yt_dlp
import zipfile
from mutagen.mp3 import MP3
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import smtplib

app = Flask(__name__, template_folder=os.path.abspath('templates'))

def search_videos(query, max_results):
    search_url = f'https://www.youtube.com/results?search_query={query}'
    ydl_opts = {
        'quiet': True,
        'extract_flat': 'in_playlist',
        'force_generic_extractor': True,
        'no_warnings': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(search_url, download=False)
        entries = info_dict.get('entries', [])

        video_urls = [entry['url'] for entry in entries if entry.get('ie_key') == 'Youtube' and 'url' in entry][:max_results]
    
    return video_urls

def download_audios(video_urls, output_folder):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_folder, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for url in video_urls:
            print(f"Downloading audio: {url}")
            ydl.download([url])

def trim_audios(output_folder, trim_duration):
    for file_name in os.listdir(output_folder):
        if file_name.endswith(".mp3") and not file_name.startswith("trimmed_"):
            file_path = os.path.join(output_folder, file_name)
            trimmed_mp3_file_path = os.path.join(output_folder, "trimmed_" + file_name)

            audio = MP3(file_path)
            duration = audio.info.length

            start_time = max(0, (duration - trim_duration) / 2)

            command = [
                'ffmpeg', '-i', file_path,
                '-ss', str(start_time),
                '-t', f'00:00:{trim_duration}',
                '-c', 'copy',
                trimmed_mp3_file_path
            ]
            subprocess.run(command, check=True)
            print(f"Trimmed audio: {file_path}")

            os.remove(file_path)

def create_mashup(output_folder, mashup_filename="mashup.mp3"):
    trimmed_files = [os.path.join(output_folder, f) for f in os.listdir(output_folder) if f.startswith("trimmed_") and f.endswith(".mp3")]

    if not trimmed_files:
        print("No trimmed audio files found for mashup.")
        return

    file_list_path = os.path.join(output_folder, "file_list.txt")
    with open(file_list_path, 'w', encoding='utf-8') as file:
        for audio_file in trimmed_files:
            safe_path = audio_file.replace('\\', '/').replace("'", "'\\''")
            file.write(f"file '{safe_path}'\n")

    mashup_file_path = os.path.join(output_folder, mashup_filename)
    command = [
        'ffmpeg', '-f', 'concat', '-safe', '0', '-i', file_list_path,
        '-c', 'copy', mashup_file_path
    ]
    try:
        subprocess.run(command, check=True, encoding='utf-8')
        print(f"Created mashup: {mashup_file_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error creating mashup: {e}")

    os.remove(file_list_path)

    for file in trimmed_files:
        os.remove(file)

def zip_mashup(output_folder, zip_filename="mashup.zip"):
    mashup_file_path = os.path.join(output_folder, "mashup.mp3")
    zip_file_path = os.path.join(output_folder, zip_filename)

    if not os.path.exists(mashup_file_path):
        print(f"Error: Mashup file not found at {mashup_file_path}")
        return None

    try:
        with zipfile.ZipFile(zip_file_path, 'w') as zipf:
            zipf.write(mashup_file_path, arcname=os.path.basename(mashup_file_path))
            print(f"Added to ZIP: {mashup_file_path}")
        return zip_file_path
    except Exception as e:
        print(f"Error creating ZIP file: {str(e)}")
        return None

def send_email(recipient_email, zip_file_path, singer_name):
    if zip_file_path is None or not os.path.exists(zip_file_path):
        print(f"Error: ZIP file not found at {zip_file_path}")
        return 
    
    sender_email = "ishmanalagh@gmail.com" 
    password = "oxip jmqu hskv xwya" 

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = f"Your {singer_name} Mashup is Ready!"

    body = f"Here's your mashup for {singer_name}. Enjoy!"
    msg.attach(MIMEText(body, 'plain'))

    try:
        with open(zip_file_path, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
        
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename= {os.path.basename(zip_file_path)}",
        )
        msg.attach(part)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, password)
            server.send_message(msg)
        
        print(f"Email sent successfully to {recipient_email}")
    except Exception as e:
        print(f"Error sending email: {str(e)}")

def process_mashup(singer_name, num_videos, trim_duration, recipient_email, output_folder):
    try:
        video_urls = search_videos(singer_name, num_videos)
        download_audios(video_urls, output_folder)

        trim_audios(output_folder, trim_duration)

        create_mashup(output_folder)

        zip_file_path = zip_mashup(output_folder)

        if zip_file_path:
            send_email(recipient_email, zip_file_path, singer_name)
            print(f"Process completed for {singer_name}. Mashup sent to {recipient_email}")
        else:
            print(f"Error: Unable to create zip file for {singer_name}")

    except Exception as e:
        print(f"Error processing mashup for {singer_name}: {str(e)}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate_mashup', methods=['POST'])
def generate_mashup():
    singer_name = request.form['singerName']
    num_videos = int(request.form['numVideos'])
    trim_duration = int(request.form['trimDuration'])
    recipient_email = request.form['email']

    num_videos = max(1, min(num_videos, 10)) 
    trim_duration = max(10, min(trim_duration, 30))

    output_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output', singer_name.replace(' ', '_'))
    os.makedirs(output_folder, exist_ok=True)

    thread = threading.Thread(target=process_mashup, args=(singer_name, num_videos, trim_duration, recipient_email, output_folder))
    thread.start()

    return jsonify({"message": f"Mashup generation started. The file will be sent to {recipient_email} when ready."})

if __name__ == '__main__':
    app.run(debug=True)