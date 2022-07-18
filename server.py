import sys
from functools import wraps
from flask import (
    Flask,
    render_template,
    request, redirect,
    url_for,
    session,
    flash)
from flask_socketio import SocketIO, join_room
import re
import pypyodbc as odbc
import random
import datetime
import hashlib

DRIVER = 'SQL Server'
SERVER_NAME = 'DESKTOP-G53AD83'
DATABASE_NAME = 'CHAT_APP'

conn_string = f"""
    Driver={{{DRIVER}}};
    Server={SERVER_NAME};
    Database={DATABASE_NAME};
    Trust_Connection=yes"""

try:
    conn = odbc.connect(conn_string, autocommit=True)
except Exception as e:
    print(e)
    print("task is terminated")
    sys.exit()
else:
    cursor = conn.cursor()

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = "4Zqp3k27j934G2J02Mi7y548Ztz9lCu8"
socketio = SocketIO(app)


# Function to generate random roomId
def room_id_generate():
    alphabets = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n',
                 'o', 'p', 'q', 'r', 't', 'u', 'v', 'w', 'x', 'y', 'z',
                 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O',
                 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']

    numbers = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0']

    length = 15
    room_id = []

    for i in range(0, length):
        room_id.append(random.choice(alphabets))
        room_id.append(random.choice(numbers))

    random.shuffle(room_id)
    generated_room_id = ""
    for i in range(0, len(room_id)):
        generated_room_id += room_id[i]
    try:
        cursor.execute("SELECT DISTINCT roomID FROM Messages WHERE roomID='%s'" % generated_room_id)
        result = cursor.fetchone()
    except Exception as er:
        print(er)
    else:
        if result:
            room_id_generate()
    return generated_room_id


# Login decorator to ensure user is logged in before accessing certain routes
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_account" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated


@app.route("/")
def home():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    # Output message if something goes wrong...
    msg = ''
    # Check if "username" and "password" POST requests exist (user submitted form)
    if 'login_btn' in request.form:
        if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
            # Create variables for easy access
            username = request.form['username']
            password = request.form['password']
            encrypt_password = hashlib.sha512(password.encode()).hexdigest()
            # Check if account exists
            cursor.execute("SELECT * FROM Accounts WHERE username ='%s' AND password='%s'" % (username, encrypt_password))
            # Fetch one record and return result
            user_account = cursor.fetchone()
            # If account exists in accounts table in our database
            if user_account:
                # Create session data, we can access this data in other routes
                session["user_account"] = {
                    "id": user_account["id"],
                    "username": user_account["username"],
                    "email": user_account["email"],
                    "name": user_account["name"]
                }
                cursor.execute("UPDATE Accounts SET is_active=1 WHERE username='%s'" % username)
                # Redirect to home page
                return redirect(url_for('message'))

            else:
                # Account doesnt exist or username/password incorrect
                msg = 'Incorrect username/password!'
                # Show the login form with message (if any)
    return render_template("index.html", msg=msg)


@app.route("/#register-form", methods=['GET', 'POST'])
def register():
    msg = ""
    # Check if "username", "password" and "email" POST requests exist (user submitted form)
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form \
            and 'email' in request.form:
        # Create variables for easy access
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        name = request.form['name']

        cursor.execute("SELECT * FROM Accounts WHERE email = '%s'" % email)
        account = cursor.fetchone()
        cursor.execute("SELECT * FROM Accounts WHERE username = '%s'" % username)
        user = cursor.fetchone()
        # If account exists show error and validation checks
        if account:
            msg = 'Account already exists!'
        elif user:
            msg = 'Username already exists!'
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            msg = 'Invalid email address!'
        elif not re.match(r'[A-Za-z0-9]+', username):
            msg = 'Username must contain only characters and numbers!'
        elif not username or not password or not email:
            msg = 'Please fill out the form!'
        else:
            password = hashlib.sha512(password.encode()).hexdigest()
            # Account doesnt exists and the form data is valid, now insert new account into accounts table
            cursor.execute("INSERT INTO Accounts(username, password, email, name) VALUES "
                           "('%s', '%s', '%s', '%s')" % (username, password, email, name))
            cursor.commit()
            msg = 'You have successfully registered!'
    elif request.method == 'POST':
        # Form is empty... (no POST data)
        msg = 'Please fill out the form!'
    # Show registration form with message (if any)
    return render_template('index.html', msg=msg)


@app.route('/logout')
def logout():
    session_user = session["user_account"]["username"]
    session.pop('user_account')
    cursor.execute("UPDATE Accounts SET is_active=0 WHERE username='%s'" % session_user)
    cursor.commit()
    return redirect(url_for('home'))


@app.route('/message', methods=["POST"])
@login_required
def new_chat():
    if request.method == 'POST':
        session_user = session["user_account"]["username"]
        new_chat_data = request.get_json()
        new_username = new_chat_data["new_username"]
        room_id = room_id_generate()
        query = "SELECT roomID FROM Messages WHERE roomID='%s'"
        cursor.execute(query % room_id)
        result = cursor.fetchone()
        if result:
            return redirect(url_for('message', rid=result[0][0]))
        else:
            current_time = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            query_to_create_new_room = """INSERT INTO Messages VALUES (?, ?, ? , '', ?)"""
            try:
                cursor.execute(query_to_create_new_room, (room_id, session_user, new_username, current_time))
            except Exception as er:
                print(er)
                cursor.rollback()
            else:
                cursor.commit()
                return redirect(url_for('message', rid=room_id))

    return redirect(url_for('message'))


@app.route('/message/', methods=["POST"])
@login_required
def add_new_contact():
    if request.method == 'POST':
        new_contact_data = request.get_json()
        new_username = new_contact_data["new_contact_username"]
        new_email = new_contact_data["new_contact_email"]
        session_user = session["user_account"]["username"]

        query = "INSERT INTO ContactList VALUES(?, ?, ?)"
        try:
            cursor.execute(query, (session_user, new_username, new_email))
        except Exception as er:
            print(er)
            cursor.rollback()
        else:
            cursor.commit()

    return redirect(url_for('message'))


@app.route('/message/', methods=["GET", "POST"])
@login_required
def message():
    room_id = request.args.get("rid")
    session_user = session["user_account"]["username"]
    recent_data = []
    try:
        query = """SELECT Messages.* FROM Messages INNER JOIN(
            SELECT roomID, MAX(msg_time) as latest FROM Messages WHERE 
            sender_name=? OR recipient_name=?
            GROUP BY roomID
        ) M 
        ON Messages.msg_time = M.latest and Messages.roomID = M.roomID
        ORDER BY msg_time DESC;"""
        cursor.execute(query, (session_user, session_user))
        recent_chat_list = cursor.fetchall()
        cursor.commit()
    except Exception as er:
        print(er)
        recent_chat_list = []

    cursor.execute("SELECT username, email, name, is_active FROM Accounts")
    account_list = cursor.fetchall()
    cursor.commit()
    username_list = []
    email_list = []
    name_list = []
    activity_list = []
    for i in account_list:
        username_list.append(i[0])
        email_list.append(i[1])
        name_list.append(i[2])
        activity_list.append(i[3])

    for i in recent_chat_list:
        if i[2] == session["user_account"]["username"]:
            messaged_user = i[1]
        else:
            messaged_user = i[2]

        messaged_user_name = ''
        activity_status = ''
        try:
            cursor.execute("SELECT name, is_active FROM Accounts WHERE username='%s'" % messaged_user)
            result = cursor.fetchone()
            messaged_user_name = result[0]
            activity = result[1]

            if activity == 1:
                activity_status = "online"
            else:
                activity_status = "away"
        except Exception as er:
            print(er)
            cursor.rollback()
        else:
            cursor.commit()
        last_msg = i[3]
        if last_msg == '' and i[1] != session_user:
            recent_data.append(
                {
                    "messaged_username": messaged_user,
                    "messaged_user_name": messaged_user_name,
                    "last_msg": last_msg,
                    "is_active": activity_status,
                    "room_id": i[0],
                    "show": 0
                }
            )
        else:
            recent_data.append(
                {
                    "messaged_username": messaged_user,
                    "messaged_user_name": messaged_user_name,
                    "last_msg": last_msg,
                    "is_active": activity_status,
                    "room_id": i[0],
                    "show": 1
                }
            )

    cursor.execute("SELECT sender_name, recipient_name, conversation, msg_time FROM Messages WHERE "
                   "roomID = '%s' AND conversation!='' ORDER BY msg_time ASC" % room_id)
    messages_data = cursor.fetchall()
    cursor.commit()
    if not messages_data:
        messages_data = []
    return render_template(
        'chat.html',
        email_list=email_list,
        username_list=username_list,
        user_data=session['user_account'],
        recent_data=recent_data,
        messages_data=messages_data,
        room_id=room_id
    )


@socketio.on('join-chat')
def join_private_chat(data):
    room = data["rid"]
    join_room(room=room)
    socketio.emit(
        "joined-chat",
        room=room
    )


@socketio.on('outgoing')
def chatting_event(json, methods=["GET", "POST"]):
    room_id = json["rid"]
    timestamp = json["timestamp"]
    conversation = json["conversation"]
    sender_username = json["sender_username"]

    try:
        cursor.execute("SELECT DISTINCT sender_name, recipient_name FROM Messages WHERE roomID='%s'"
                       % room_id)
        result = cursor.fetchone()
        if result[0] == sender_username:
            recipient_username = result[1]
        else:
            recipient_username = result[0]
            cursor.commit()

        query1 = "INSERT INTO Messages VALUES (?, ?, ?, ?, ?)"
        cursor.execute(query1, (room_id, sender_username, recipient_username, conversation, timestamp))
    except Exception as err:
        cursor.rollback()
        print(err)

    socketio.emit(
        'received_msg',
        json,
        room=room_id,
        include_self=False
    )


if __name__ == '__main__':
    socketio.run(app, debug=True)
