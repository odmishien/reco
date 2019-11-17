from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from ibm_watson import SpeechToTextV1
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
from janome.tokenizer import Tokenizer
import json
import datetime
import os
import re
import collections
import hashlib

from database import init_db, db
import models
from models import User, Log

ALLOWED_EXTENSIONS = ['mp3', 'flac', 'wav']
ALLOWED_NOUN_KIND = ['サ変接続', '形容動詞語幹', '副詞可能', '一般', '固有名詞']
UPLOAD_DIR = 'audio_logs'
LOG_DIR = 'log'
TOPICS_NUM = 5
DEBUG_MODE = False
DEBUG_DATA_PATH = 'test_data/sound.json'

app = Flask(__name__)
app.secret_key = 'hoge'
app.debug = True
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root@mysql:3306/reco'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True
init_db(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_get'

t = Tokenizer()

@app.route('/')
@login_required
def index():
    return render_template("index.html")

@app.route('/login', methods=['GET'])
def login_get():
    return render_template("login.html")

@app.route('/login', methods=['POST'])
def login_post():
    username = request.form['username']
    password = request.form['password']

    error = None
    user = validate_user(username, password)

    if not username:
        error = 'ユーザー名を入力してください'
    elif not password:
        error = 'パスワードを入力してください'
    elif not user:
        error = 'ユーザ名またはパスワードが正しくありません'

    if error is not None:
        print(error)
        flash(error, category='alert')
        return redirect(url_for('login_get'))
    login_user(user)
    return redirect(url_for('index'))

@app.route('/signup', methods=['GET'])
def signup_get():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    else:
        return render_template("signup.html")

@app.route('/signup', methods=['POST'])
def signup_post():
    username = request.form['username']
    password = request.form['password']
    print(username, password)
    error = None

    if not username:
        error = 'ユーザー名を入力してください'
    elif not password:
        error = 'パスワードを入力してください'
    elif User.query.filter_by(name=username).first():
        error = 'そのユーザー名はすでに使われています'

    if error is not None:
        print(error)
        flash(error, category='alert')
        return redirect(url_for('signup_get'))

    new_user = User(username, hash_pass(password))
    print(new_user)
    db.session.add(new_user)
    db.session.commit()

    return redirect(url_for('index'))

@app.route('/logout', methods=['GET'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('login_get'))

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if DEBUG_MODE:
        with open(DEBUG_DATA_PATH, 'r') as f:
            result = json.load(f)
        log_id = parse_and_save_result(result)
        return redirect('/log/{}'.format(log_id))

    else:
        audio = request.files['audio']
        if audio.filename == '':
            return redirect('/')

        if allowed_file(audio.filename):
            raw_audio_file_name = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.' + audio.filename.rsplit('.', 1)[1].lower()
            audio_path = os.path.join(UPLOAD_DIR, raw_audio_file_name)
            audio.save(audio_path)
            result = post_audio_to_speech_to_textAPI(audio_path)
            delete_raw_audio_file(audio_path)
            log_id = parse_and_save_result(result)
            return redirect('/log/{}'.format(log_id))
        else:
            return redirect('/')

@app.route('/log/<log_id>')
@login_required
def log(log_id):
    log = get_log_by_id(log_id, current_user.get_id())
    if not log:
        abort(404)
    else:
        res = {}
        res["topic"] = log.topic
        res["posession"] = log.posession
        res["active_rate"] = log.active_rate
        res["score"] = log.score
        res["total_time"] = log.total_time
        res["created_at"] = log.created_at
        return render_template("log.html", res=res)

@app.route('/overview')
@login_required
def overview():
    res = get_overview()
    return render_template("overview.html", res=res)

@login_manager.user_loader
def user_loader(user_id):
    return User.query.get(user_id)

# 便利メソッド
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def post_audio_to_speech_to_textAPI(filename):
        authenticator = IAMAuthenticator(
            'VNYNGcQrwZaumnTJMani2qbBa8veDOfjXQBRXsr3l5rX')
        speech_to_text = SpeechToTextV1(authenticator=authenticator)
        speech_to_text.set_service_url(
            'https://gateway-tok.watsonplatform.net/speech-to-text/api')
        lang = "ja-JP_BroadbandModel"
        with open(filename, 'rb') as audio_file:
            speech_recognition_results = speech_to_text.recognize(
                audio=audio_file,
                model=lang,
                content_type='audio/mp3',
                timestamps=True,
                speaker_labels=True,
            ).get_result()
        return speech_recognition_results

def delete_raw_audio_file(filename):
    os.remove(filename)

def parse_and_save_result(result):
    sentences = {}
    pauses = {}
    pause_scores = {}
    posession_per_speaker = {}
    final_score = []
    best_sentence_ids = []
    topic = []
    active_rate = 0
    total_pause = 0
    total_time = 0
    sentence_counter = 0

    speaker_labels = result['speaker_labels']
    for label in speaker_labels:
        start = float(label['from'])
        end = float(label['to'])
        speak_time = end - start
        speaker_id = str(label['speaker'])
        if speaker_id in posession_per_speaker:
            posession_per_speaker[speaker_id] += speak_time
        else:
            posession_per_speaker[speaker_id] = speak_time
        total_time += speak_time
    for speaker_id in posession_per_speaker.keys():
        time = posession_per_speaker[speaker_id]
        posession = time / total_time
        posession_per_speaker[speaker_id] = posession

    if len(posession_per_speaker) == 2:
        speaker_ids = list(posession_per_speaker.keys())
        weight = 1 - abs(posession_per_speaker[speaker_ids[0]] - posession_per_speaker[speaker_ids[1]])
    else:
        weight = 1
        posession_per_speaker = {"0": 0, "1": 0}

    for x in result['results']:
        for y in x['alternatives']:
            sentence_id = str(sentence_counter)
            sentences[sentence_id] = {}
            sentences[sentence_id]["sentence_start"] = y['timestamps'][0][1]
            sentences[sentence_id]["sentence_end"] = y['timestamps'][-1][2]
            sentences[sentence_id]["body"] = y["transcript"]
            sentence_counter += 1

    for k in sentences.keys():
        if k != str(len(sentences) - 1):
            pause = sentences[str(int(k)+1)]['sentence_start'] - sentences[k]['sentence_end']
            pauses["{pre}_{post}".format(pre=k, post=str(int(k)+1))] = pause
            total_pause += pause
    if len(sentences) < 10:
        split_num = len(sentences) - 1
    else:
        split_num = 10
    splits = [(len(pauses) + i) // split_num for i in range(split_num)]
    for k in pauses.keys():
        pause_score = 1/pauses[k]
        pause_scores[k] = pause_score
    non_final_score = []
    counter = 0
    for s in splits:
        area_score = 0
        for i in range(0, s):
            key = str(counter + i) + '_' + str(counter + i + 1)
            area_score += pause_scores[key]
        non_final_score.append(area_score)
        counter += s
    final_score = []
    for i, score in enumerate(non_final_score):
        if splits[i] != 0:
            final = score / splits[i]
            final_score.append(final)
        else:
            final_score.append(0)
    weighted_final_score = []
    for score in final_score:
        weighted_final = score * weight
        weighted_final_score.append(weighted_final)
    best_score_index = weighted_final_score.index(max(weighted_final_score))
    best_area_num = splits[best_score_index]
    id_counter = 0
    for i in splits[0:best_score_index-1]:
        id_counter += i
    for j in range(best_area_num):
        id_counter += 1
        best_sentence_ids.append(str(id_counter))

    for sentence_id in best_sentence_ids:
        sentence_body = sentences[sentence_id]["body"]
        sentence_body = sentence_body.replace(" ", "")
        for token in t.tokenize(sentence_body):
            part_of_speech = token.part_of_speech.split(',')
            if part_of_speech[0] == "名詞" and part_of_speech[1] in ALLOWED_NOUN_KIND:
                if token.surface != '_' and token.surface != 'D':
                    topic.append(token.surface)

    active_rate = 1 - (total_pause / total_time)

    user_id = current_user.get_id()
    created_at = datetime.datetime.now()

    log = Log(user_id, topic, posession_per_speaker, active_rate, weighted_final_score, total_time, created_at)

    db.session.add(log)
    db.session.commit()

    return log.id

def get_overview():
    overview = {}
    overview["logs"] = []
    topics = []
    top_topics = []

    logs = Log.query.filter_by(user_id=current_user.get_id()).all()

    for log in logs:
        topics.extend(log.topic)
        log_obj = {}
        log_obj["active_rate"] = log.active_rate
        data = log.score
        s = sum(data)
        N = len(data)
        mean_score = s / N
        log_obj["score"] = mean_score
        log_obj["created_at"] = log.created_at
        overview["logs"].append(log_obj)
    c = collections.Counter(topics)
    for i in range(TOPICS_NUM):
        if i < len(c.most_common()):
            top_topics.append(c.most_common()[i][0])
        else:
            break
    overview["topics"] = top_topics
    return overview

def hash_pass(password):
    md5 = hashlib.md5()
    md5.update(password.encode("UTF-8"))
    return md5.hexdigest()

def validate_user(username, password):
    user = User.query.filter_by(name=username).first()
    if not user:
        return None
    if user.password != hash_pass(password):
        return None
    return user

def get_log_by_id(log_id, user_id):
    log = Log.query.filter_by(id=log_id).first()
    if log.user_id == user_id:
        return log
    else:
        return None

if __name__ == "__main__":
    app.run()
