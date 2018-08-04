import os

from flask import Flask, render_template, session, request
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
import requests  # for goodreads API
import json

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

@app.route("/")
def index():
    if "uid" in session:
        return render_template("search.html", session = session)
    else:
        return render_template("index.html", session = session)

@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email")
    password = request.form.get("password")
    userRecord = db.execute("SELECT * FROM users WHERE email = :email", {"email": email}).fetchone();
    if userRecord is None:
        return render_template("index.html", message="No such email", session = session)
    row = dict(userRecord)
    if row["password"] != password:
        return render_template("index.html", message="Bad password", session = session)

    session["uid"] = row["id"]
    session["email"] = row["email"]
    return render_template("search.html", session = session)

@app.route("/logout")
def logout():
    if "uid" in session:
        del session["uid"]
    return render_template("index.html")
    
@app.route("/registerinfo", methods=["POST"])
def registerinfo():
    return render_template("registerinfo.html")

@app.route("/newuser", methods=["POST"])
def newuser():
    email = request.form.get("email")
    password = request.form.get("password")
    firstName = request.form.get("firstName")
    lastName = request.form.get("lastName")
    if db.execute("SELECT * FROM users WHERE email = :email", {"email": email}).rowcount != 0:
        return render_template("registerinfo.html", message=f"Email address {email} already in use.")

    db.execute("INSERT INTO users (email, password, firstName, lastName) VALUES (:email, :password, :firstName, :lastName)",
            {"email":email, "password":password, "firstName":firstName, "lastName":lastName})
    db.commit()
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search():
    if not "uid" in session:
        return render_template("index.html")
    searchBy = request.form.get("searchBy")
    info = request.form.get("info").strip() + "%"
    result = db.execute(f"SELECT * FROM books WHERE {searchBy} like :{searchBy}", {f"{searchBy}": info }).fetchall()
    return render_template("searchresults.html", results=result)

@app.route("/bookinfo", methods=["GET"])
def bookinfo(isbn = ""):
    if not "uid" in session:
        return render_template("index.html")
    if not isbn:
        isbn = request.args["isbn"]
    bookinfo = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn }).fetchone()
    goodreads = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "T0HeAnJwJklPxkTYFlnJA", "isbns": isbn})
    reviews = db.execute("SELECT text, firstname, lastname, email FROM reviews JOIN users on reviews.userid = users.id WHERE isbn = :isbn and not userid = :userid", {"isbn": isbn, "userid":session["uid"] }).fetchall()
    myreview = db.execute("SELECT * FROM reviews WHERE isbn = :isbn and userid = :userid", {"isbn": isbn, "userid":session["uid"] }).fetchone()
    return render_template("bookinfo.html", results=bookinfo, goodreads=goodreads.json(), reviews = reviews, myreview = myreview)

@app.route("/review", methods=["POST"])
def review():
    if not "uid" in session:
        return render_template("index.html")
    reviewText = request.form.get("review").strip()
    isbn = request.form.get("isbn").strip()
    print(f"review={reviewText} isbn={isbn}")
    myreview = db.execute("SELECT * FROM reviews WHERE isbn = :isbn and userid = :userid", {"isbn": isbn, "userid":session["uid"] }).fetchone()
    if myreview:
        # it's an update
        db.execute("UPDATE reviews SET text=:text WHERE isbn = :isbn and userid = :userid", { "text": reviewText, "isbn":isbn, "userid":session["uid"]})
    else:
        db.execute("INSERT INTO reviews (isbn, userid, text) VALUES (:isbn, :userid, :text)", {"isbn": isbn, "userid":session["uid"], "text":reviewText})
    db.commit()
    return bookinfo(isbn)
  
@app.route("/api/<isbn>", methods=["GET"])
def api(isbn):
    bookinfo = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn }).fetchone()
    if bookinfo:
        bookinfo = dict(bookinfo)
        goodreads = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "T0HeAnJwJklPxkTYFlnJA", "isbns": isbn}).json()
        
        bookinfo["review_count"] = goodreads["books"][0]["work_ratings_count"]
        bookinfo["average_score"] =goodreads["books"][0]["average_rating"]
        return json.dumps(bookinfo)
    else:
        return render_template("error.html"), 404
    