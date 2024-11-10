import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
import psutil
from pymongo import MongoClient
from datetime import datetime
import matplotlib.pyplot as plt
import io
import base64

# 加载 .env 文件中的环境变量
load_dotenv()

app = Flask(__name__)
app.secret_key = 'super_secret_key'  # 请替换为更安全的密钥
bcrypt = Bcrypt(app)

# 从 .env 文件中获取 MongoDB 连接信息
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# 连接到 MongoDB 数据库
client = MongoClient(MONGODB_URI)
db = client[MONGODB_DB_NAME]  # 使用 .env 中指定的数据库名称
users_collection = db["users"]  # 用户数据集合


# 首页重定向到登录页
@app.route('/')
def index():
    return redirect(url_for('login'))


# 注册路由
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        if users_collection.find_one({'username': username}):
            flash("该用户名已存在！", "warning")
        else:
            users_collection.insert_one({
                'username': username,
                'password': hashed_password,
                'history': []
            })
            flash("注册成功！请登录。", "success")
            return redirect(url_for('login'))

    return render_template('register.html')


# 登录路由
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = users_collection.find_one({'username': username})

        if user and bcrypt.check_password_hash(user['password'], password):
            session['username'] = username
            flash("欢迎您登录已经成功！", "success")
            return redirect(url_for('calculate'))
        else:
            flash("用户名或密码错误！", "danger")

    return render_template('login.html')


# 登出路由
@app.route('/logout', methods=['POST'])
def logout():
    session.pop('username', None)  # 删除会话中的用户名
    flash('成功退出登录', 'success')
    return redirect(url_for('login'))  # 重定向到登录页面


# 计算 BMI 和体脂率页面
@app.route('/calculate', methods=['GET', 'POST'])
def calculate():
    if 'username' not in session:
        flash("请先登录！", "danger")
        return redirect(url_for('login'))

    if request.method == 'POST':
        weight = float(request.form['weight'])
        height = float(request.form['height']) / 100  # 转换为米
        age = int(request.form['age'])
        gender = request.form['gender']

        bmi = weight / (height ** 2)

        # 体脂率计算
        if gender == 'male':
            body_fat = 1.20 * bmi + 0.23 * age - 16.2
        else:
            body_fat = 1.20 * bmi + 0.23 * age - 5.4

        # BMI 标准比对
        if bmi < 18.5:
            bmi_status = "偏瘦"
        elif 18.5 <= bmi < 24:
            bmi_status = "正常"
        else:
            bmi_status = "偏胖"

        # 存储到数据库历史记录
        username = session['username']
        history_entry = {
            'date': datetime.now(),
            'weight': weight,
            'height': height * 100,
            'age': age,
            'gender': gender,
            'bmi': round(bmi, 2),
            'body_fat': round(body_fat, 2),
            'bmi_status': bmi_status
        }
        users_collection.update_one({'username': username}, {'$push': {'history': history_entry}})

        flash("计算成功！", "success")
        return render_template('calculate.html', bmi=round(bmi, 2), body_fat=round(body_fat, 2), bmi_status=bmi_status)

    return render_template('calculate.html')


# 查看历史记录
@app.route('/history')
def history():
    if 'username' not in session:
        flash("请先登录！", "danger")
        return redirect(url_for('login'))

    username = session['username']
    user = users_collection.find_one({'username': username})
    history = user.get('history', [])

    # 提取最近 5 次的 BMI 数据
    recent_history = history[-5:] if len(history) > 5 else history
    bmi_values = [entry['bmi'] for entry in recent_history]
    dates = [entry['date'].strftime('%Y-%m-%d') for entry in recent_history]

    # 生成折线图
    img = io.BytesIO()
    plt.figure(figsize=(10, 4))
    plt.plot(dates, bmi_values, marker='o', linestyle='-')
    plt.xlabel('date')
    plt.ylabel('BMI')
    plt.title('BMI trend')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(img, format='png')
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode()

    return render_template('history.html', history=history, plot_url=plot_url)


# 清空历史记录
@app.route('/clear_history', methods=['POST'])
def clear_history():
    if 'username' not in session:
        flash("请先登录！", "danger")
        return redirect(url_for('login'))

    username = session['username']
    users_collection.update_one({'username': username}, {'$set': {'history': []}})
    flash("历史记录已清空！", "success")
    return redirect(url_for('history'))


# 管理员登录路由
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            flash("管理员登录成功！", "success")
            return redirect(url_for('admin'))
        else:
            flash("管理员用户名或密码错误！", "danger")

    return render_template('admin_login.html')


# 管理员页面
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin_logged_in'):
        flash("请先以管理员身份登录！", "danger")
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        if 'add_user' in request.form:
            new_username = request.form['new_username']
            new_password = request.form['new_password']
            hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
            is_admin = 'new_is_admin' in request.form

            if users_collection.find_one({'username': new_username}):
                flash("该用户名已存在！", "warning")
            else:
                users_collection.insert_one({
                    'username': new_username,
                    'password': hashed_password,
                    'history': [],
                    'is_admin': is_admin
                })
                flash("新用户添加成功！", "success")

        elif 'delete_user' in request.form:
            delete_username = request.form['delete_username']
            users_collection.delete_one({'username': delete_username})
            flash(f"用户 {delete_username} 已被删除。", "success")

        elif 'change_password' in request.form:
            change_username = request.form['change_username']
            new_password = request.form['new_password']
            hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
            users_collection.update_one({'username': change_username}, {'$set': {'password': hashed_password}})
            flash(f"用户 {change_username} 的密码已更新。", "success")

    cpu_load = psutil.cpu_percent(interval=1)
    memory_info = psutil.virtual_memory()
    users = users_collection.find()

    return render_template('admin.html', cpu_load=cpu_load, memory_info=memory_info, users=users)


if __name__ == "__main__":
    app.run(debug=True)
