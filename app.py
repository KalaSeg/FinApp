# Imports
from flask import Flask, render_template, url_for, redirect, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, FileField
from wtforms.validators import InputRequired, Length, ValidationError, DataRequired
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
import os
import uuid
import pathlib
from google.cloud import storage
import requests
import base64

# App configuration
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SECRET_KEY"] = "thisismylongandcomplexsecret"
app.config["ENV"] = "production"
app.config["DEBUG"] = False
app.config["TESTING"] = False
UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
bucket_name = "trustusy-prd-5004091-client-services-storage-prd"
credentials_path = "/root/finance-sync.json"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# DB initialization
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# Login management
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
  return User.query.get(int(user_id))

# Define user class for DB
class User(db.Model, UserMixin):
  id = db.Column(db.Integer, primary_key=True)
  username = db.Column(db.String(20), nullable=False, unique=True)
  password = db.Column(db.String(80), nullable=False)
  photo = db.Column(db.String(200), nullable=True)



# Define registration and login form classes
class RegisterForm(FlaskForm):
  username = StringField(
    validators=[InputRequired(), Length(min=4, max=20)],
    render_kw={"placeholder": "Username"},
  )

  password = PasswordField(
    validators=[InputRequired(), Length(min=8, max=20)],
    render_kw={"placeholder": "Password"},
  )

  photo = FileField("Upload File", validators=[DataRequired()])

  submit = SubmitField("Register")

  def validate_username(self, username):
    existing_user_username = User.query.filter_by(username=username.data).first()
    if existing_user_username:
      flash("Username already exists.", "register_error")
      raise ValidationError(
        "That username already exists. Please choose a different one."
      )



class LoginForm(FlaskForm):
  username = StringField(
    validators=[InputRequired(), Length(min=4, max=20)],
    render_kw={"placeholder": "Username"},
  )

  password = PasswordField(
    validators=[InputRequired(), Length(min=8, max=20)],
    render_kw={"placeholder": "Password"},
  )

  submit = SubmitField("Login")



# Define bucket file copy function
def upload_file_to_gcp_bucket(bucket_name, source_file_path, destination_blob_name, credentials_path):
  storage_client = storage.Client.from_service_account_json(credentials_path)
  bucket = storage_client.bucket(bucket_name)
  blob = bucket.blob(destination_blob_name)
  blob.upload_from_filename(source_file_path)
  print(f"File {source_file_path} uploaded to gs://{bucket_name}/{destination_blob_name}")
  return f"gs://{bucket_name}/{destination_blob_name}"



# Define application paths
@app.route("/")
def index():
  return render_template("index.html")



@app.route("/posts")
def posts_page():
  return render_template("posts.html")



@app.route("/login", methods=["POST", "GET"])
def login():
  form = LoginForm()

  if form.validate_on_submit():
    existing_user = User.query.filter(User.username == form.username.data).first()

    if existing_user:
      if bcrypt.check_password_hash(existing_user.password, form.password.data):
        login_user(existing_user)
        return redirect(url_for("profile"))
      else:
        flash("Invalid username or password.", "login_error")
    else:
      flash("Invalid username or password.", "login_error")

  return render_template("login.html", form=form)



@app.route("/register", methods=["GET", "POST"])
def register():
  form = RegisterForm()

  if form.validate_on_submit():
    hashed_password = bcrypt.generate_password_hash(form.password.data)

    file = form.photo.data

    if file:
      original_filename = secure_filename(file.filename)
      file_extension = pathlib.Path(original_filename).suffix
      rand_filename = str(uuid.uuid1())
      saved_filename = rand_filename + file_extension
      local_upload_dir = app.config["UPLOAD_FOLDER"]
      os.makedirs(local_upload_dir, exist_ok=True)
      filepath = os.path.join(local_upload_dir, saved_filename)
      destination_blob_name = "profilepictures/" + saved_filename
      # Save file to disk
      file.save(filepath)
      # Copy file to Bucket
      upload_file_to_gcp_bucket(bucket_name=bucket_name, source_file_path=filepath, destination_blob_name=destination_blob_name, credentials_path=credentials_path)
      # Add new user to database
      new_user = User(username=form.username.data, password=hashed_password, photo=saved_filename)
      db.session.add(new_user)
      db.session.commit()
      # Remove file from disk
      os.remove(filepath)
      flash("Account created successfully! Please log in.", "register_success")
      return redirect(url_for("login"))

  return render_template("register.html", form=form)



@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
  # Access current_user's data
  username = current_user.username
  profile_pic_name = current_user.photo
  profile_pic_url = 'https://storage.googleapis.com/' + bucket_name + '/profilepictures/' + profile_pic_name 
  return render_template("profile.html", username=username, profile_pic_url=profile_pic_url)



@app.route("/profilepic", methods=["GET"])
@login_required
def profilepic():
  profile_pic_url = request.args.get("bucketurl")
  incoming_headers = dict(request.headers)
  incoming_headers.pop("Host", None)
  incoming_headers.pop("Cookie", None)

  if profile_pic_url:
    r = requests.get(profile_pic_url, headers=incoming_headers)
    image_binary = r.content
    image_encoded = base64.b64encode(image_binary)
    return image_encoded

  return redirect(url_for("profile"))



@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
  logout_user()
  return redirect(url_for("login"))



if __name__ == "__main__":
  app.run(host="0.0.0.0", port=80, debug=False)