
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session

from tempfile import mkdtemp

from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

import requests

app = Flask(__name__)

DATABASE_URL = "postgres://jyszivevhmwpov:1debdbe20471451509c65c8330f36fa3aa1ae596dc92a33f15c25bdd27e7dae5@ec2-54-75-245-196.eu-west-1.compute.amazonaws.com:5432/ddp5ajgcbtnhad"

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# dont sort jsonified respone
app.config["JSON_SORT_KEYS"] = False

# Set up database
engine = create_engine(DATABASE_URL)
db = scoped_session(sessionmaker(bind=engine))


@app.route("/", methods=["GET"])
def index():

    if session.get("user_id") is None:
        return redirect("/login")

    # get username
    rows = db.execute("SELECT * FROM users WHERE user_id = :id",
                      {"id": session.get("user_id")}).fetchall()
    user = rows[0]["username"]

    return render_template("index.html", user=user)


@app.route("/login", methods=["GET", "POST"])
def login():

    # forget previous user
    session.clear()

    if request.method == "POST":

        if not request.form.get("username"):
            flash("Enter Username!", "danger")
            return render_template("login.html")

        if not request.form.get("password"):
            flash("Enter Password!", "danger")
            return render_template("login.html")

        # get username and password from database
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          {"username": request.form.get("username")}).fetchall()

        # make sure they exist and match
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            flash("Invalid Username or Password!", "danger")
            return render_template("login.html")

        # Remember which user has logged in and flash success
        session["user_id"] = rows[0]["user_id"]
        flash("Successfully logged in!", "success")
        return redirect("/")

    # acces via GET
    else:
        return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    # forget previous user
    session.clear()

    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            flash("Enter Username!", "danger")
            return render_template("register.html")

        # Ensure password was submitted
        if not request.form.get("password"):
            flash("Enter Password!", "danger")
            return render_template("register.html")

        # Ensure confirmation was submitted
        if not request.form.get("confirmation"):
            flash("Confirm Password!", "danger")
            return render_template("register.html")

        # Ensure that passwords match
        if request.form.get("password") != request.form.get("confirmation"):
            flash("Passwords don't match!", "danger")
            return render_template("register.html")

        # Ensure user doesnt exist already
        rows = db.execute(
            "SELECT * FROM users WHERE username= :username", {"username": request.form.get("username")}).fetchone()
        if rows:
            flash('Username already exists!', 'danger')
            return render_template("register.html")

        # Hash password
        hash = generate_password_hash(request.form.get("password"))

        # store user in db
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                   {"username": request.form.get("username"), "hash": hash})
        db.commit()

        # get new user_id from database
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          {"username": request.form.get("username")}).fetchall()

        # Remember which user has logged in and flash success
        session["user_id"] = rows[0]["user_id"]
        flash("Successfully registered and logged in!", "success")
        return redirect("/")

    # acces via GET
    else:
        return render_template("register.html")


@app.route("/logout")
def logout():

    # forget previous user
    session.clear()

    flash("Successfully logged out!", "success")
    return render_template("login.html")


@app.route("/search", methods=["POST"])
def search():

    # get username
    rows = db.execute("SELECT * FROM users WHERE user_id = :id",
                      {"id": session.get("user_id")}).fetchall()
    user = rows[0]["username"]

    # get form data
    isbn = request.form.get("isbn")
    title = request.form.get("title").upper()
    author = request.form.get("author").upper()

    # if form empty
    if not isbn and not title and not author:
        flash("Enter at least one field!", "danger")
        return render_template("index.html", user=user)

    # search database for isbn, title or author
    if isbn:
        rows = db.execute(
            "SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchall()

    elif title and author:
        rows = db.execute(
            "SELECT * FROM books WHERE UPPER(title) LIKE CONCAT('%', :title, '%') AND UPPER(author) LIKE CONCAT('%', :author, '%')", {"title": title, "author": author}).fetchall()

    elif title:
        rows = db.execute(
            "SELECT * FROM books WHERE UPPER(title) LIKE CONCAT('%', :title, '%')", {"title": title}).fetchall()

    elif author:
        rows = db.execute(
            "SELECT * FROM books WHERE UPPER(author) LIKE CONCAT('%', :author, '%')", {"author": author}).fetchall()

    # if no entries found
    if not rows:
        flash("No Entries found!", "danger")
        return render_template("index.html", user=user)

    # return search results and user
    return render_template("search.html", rows=rows, user=user)


@app.route("/book/<int:book_id>", methods=["GET", "POST"])
def book(book_id):

    # get username
    rows = db.execute("SELECT * FROM users WHERE user_id = :id",
                      {"id": session.get("user_id")}).fetchall()
    user = rows[0]["username"]

    if request.method == "POST":

        # get values from form
        rating = request.form.get("rating")
        review = request.form.get("review")

        # make entry in reviews db
        db.execute("INSERT INTO reviews (user_id, book_id, rating, review, username) VALUES (:user_id, :book_id, :rating, :review, :usern)",
                   {"user_id": session.get("user_id"), "book_id": book_id, "rating": rating, "review": review, "usern": user})
        db.commit()

        # flash successful entry
        flash("Review successfully added!", "success")

    # get book detail from id
    row = db.execute("SELECT * FROM books WHERE id = :book_id",
                     {"book_id": book_id}).fetchone()

    # get goodreads stats with isbn
    key = 'gvlQ3F8KG7Z3kr89nAQiw'
    res = requests.get("https://www.goodreads.com/book/review_counts.json",
                       params={"key": key, "isbns": row.isbn})

    good_count = res.json()["books"][0]["reviews_count"]
    good_rating = res.json()["books"][0]["average_rating"]

    # get all reviews for this book
    reviews = db.execute("SELECT * FROM reviews WHERE book_id = :book_id",
                         {"book_id": book_id}).fetchall()

    # check if user revied this book
    user_review = False
    for review in reviews:
        if review.user_id == session.get("user_id"):
            user_review = True

    return render_template("book.html", row=row, user=user, good_count=good_count, good_rating=good_rating, user_review=user_review,                reviews=reviews)


@app.route("/api/<string:isbn>")
def api(isbn):

    # get book detail from isbn
    row = db.execute("SELECT * FROM books WHERE isbn = :isbn",
                     {"isbn": isbn}).fetchone()
    if not row:
        response = {'message': 'ISBN not found'}
        return jsonify(response), 404

    # get reviews with book_id
    rating = db.execute("SELECT AVG(rating), COUNT(rating) FROM reviews WHERE book_id = :id", {
                        "id": row.id}).fetchall()

    response = {
        'title': row.title,
        'author': row.author,
        'year': row.year,
        'isbn': isbn,
        'review_count': rating[0][1],
        'average_score': round(float(rating[0][0]), 2)
    }

    return jsonify(response)
