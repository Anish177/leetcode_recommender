import os
import random
from datetime import datetime
import json
from flask import Flask, render_template, jsonify, request, make_response
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

load_dotenv()

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise ValueError("No SECRET_KEY set for Flask application")

# MongoDB Atlas connection
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise ValueError("No MONGO_URI set for MongoDB connection")

client = MongoClient(MONGO_URI)
db = client.leetcode_recommender
questions_collection = db.questions

QUESTIONS_PER_PAGE = 20


class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, set):
            return list(o)
        return json.JSONEncoder.default(self, o)


app.json_encoder = JSONEncoder


def load_companies():
    companies = list(questions_collection.distinct("company"))
    companies.insert(0, "All")
    return companies


companies = load_companies()


def get_user_stats(user_stats_json):
    if user_stats_json:
        user_stats = json.loads(user_stats_json)
        user_stats["solved_questions"] = set(user_stats["solved_questions"])
        return user_stats

    return {
        "solved_tags": {},
        "solved_difficulties": {},
        "solved_questions": set(),
        "last_solved_time": {},
    }


def set_user_stats(user_stats):
    user_stats_to_save = user_stats.copy()
    user_stats_to_save["solved_questions"] = list(user_stats["solved_questions"])
    return json.dumps(user_stats_to_save)


@app.route("/")
def index():
    return render_template("index.html", companies=companies)


@app.route("/questions/<company>")
def get_questions(company):
    page = request.args.get("page", 1, type=int)
    tags = request.args.get("tag", "").split(",")
    difficulties = request.args.get("difficulty", "").split(",")
    search_query = request.args.get("search", "").lower()

    query = {}
    if company != "All":
        query["company"] = company
    if tags and tags[0]:
        query["tags"] = {"$all": tags}
    if difficulties and difficulties[0]:
        query["difficulty"] = {"$in": difficulties}
    if search_query:
        query["$or"] = [
            {"name": {"$regex": search_query, "$options": "i"}},
            {"id": {"$regex": search_query, "$options": "i"}},
        ]

    # Use aggregation to remove duplicates
    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$id", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$sort": {"id": 1}},  # Sort by question ID to ensure consistent ordering
    ]

    total_questions = len(list(questions_collection.aggregate(pipeline)))
    total_pages = (total_questions - 1) // QUESTIONS_PER_PAGE + 1
    skip = (page - 1) * QUESTIONS_PER_PAGE

    pipeline.extend([{"$skip": skip}, {"$limit": QUESTIONS_PER_PAGE}])

    company_questions = list(questions_collection.aggregate(pipeline))

    user_stats_json = request.cookies.get("user_stats")
    if user_stats_json:
        user_stats = get_user_stats(user_stats_json)
        for question in company_questions:
            question["completed"] = question["id"] in user_stats["solved_questions"]

    # Convert ObjectId to string for each question
    for question in company_questions:
        question["_id"] = str(question["_id"])

    response = jsonify(
        {
            "questions": company_questions,
            "total_pages": total_pages,
            "current_page": page,
        }
    )

    return response


@app.route("/update_progress", methods=["POST"])
def update_progress():
    data = request.json
    question_id = data["questionId"]
    completed = data["completed"]

    user_stats_json = request.cookies.get("user_stats")
    user_stats = get_user_stats(user_stats_json)

    question = questions_collection.find_one({"_id": ObjectId(question_id)})
    if not question:
        return jsonify({"success": False, "message": "Question not found"}), 404

    if completed:
        user_stats["solved_questions"].add(question["id"])
        for tag in question["tags"]:
            user_stats["solved_tags"][tag] = user_stats["solved_tags"].get(tag, 0) + 1
        user_stats["solved_difficulties"][question["difficulty"]] = (
            user_stats["solved_difficulties"].get(question["difficulty"], 0) + 1
        )
        user_stats["last_solved_time"][question["id"]] = datetime.now().isoformat()
    else:
        user_stats["solved_questions"].discard(question["id"])
        for tag in question["tags"]:
            user_stats["solved_tags"][tag] = max(
                0, user_stats["solved_tags"].get(tag, 0) - 1
            )
        user_stats["solved_difficulties"][question["difficulty"]] = max(
            0, user_stats["solved_difficulties"].get(question["difficulty"], 0) - 1
        )
        user_stats["last_solved_time"].pop(question["id"], None)

    updated_user_stats_json = set_user_stats(user_stats)
    response = make_response(jsonify({"success": True}))
    response.set_cookie(
        "user_stats",
        updated_user_stats_json,
        max_age=31536000,
        httponly=True,
        secure=True,
        samesite="Lax",
    )
    return response


@app.route("/random_question/<company>")
def random_question(company):
    user_stats_json = request.cookies.get("user_stats")
    if user_stats_json:
        user_stats = get_user_stats(user_stats_json)
        solved_questions = user_stats["solved_questions"]
    else:
        solved_questions = set()

    query = {"id": {"$nin": list(solved_questions)}}
    if company != "All":
        query["company"] = company

    # Use aggregation to remove duplicates
    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$id", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$sample": {"size": 1}},  # Randomly select one question
    ]

    question = list(questions_collection.aggregate(pipeline))
    if question:
        question = question[0]
        question["_id"] = str(question["_id"])
        return jsonify(question)

    return jsonify({"message": "All questions completed"})


@app.route("/reset_progress", methods=["POST"])
def reset_progress():
    response = make_response(jsonify({"success": True}))
    response.delete_cookie("user_stats")
    return response


@app.route("/recommend_question", methods=["GET"])
def recommend_question():
    company = request.args.get("company", "All")
    user_stats_json = request.cookies.get("user_stats")

    if user_stats_json:
        user_stats = get_user_stats(user_stats_json)
    else:
        user_stats = {
            "solved_tags": {},
            "solved_difficulties": {},
            "solved_questions": set(),
            "last_solved_time": {},
        }

    query = {"id": {"$nin": list(user_stats["solved_questions"])}}
    if company != "All":
        query["company"] = company

    # Use aggregation to remove duplicates
    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$id", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
    ]

    possible_questions = list(questions_collection.aggregate(pipeline))

    if not possible_questions:
        return jsonify({"message": "All questions completed"})

    current_time = datetime.now()

    def recommendation_score(question):
        tag_score = sum(
            user_stats["solved_tags"].get(tag, 0) for tag in question["tags"]
        )
        difficulty_score = user_stats["solved_difficulties"].get(
            question["difficulty"], 0
        )
        recency_score = question.get(
            "recency_score", 0
        )  # Use 0 if recency_score is not present
        time_decay = 1.0
        if question["id"] in user_stats["last_solved_time"]:
            days_since_solved = (
                current_time
                - datetime.fromisoformat(user_stats["last_solved_time"][question["id"]])
            ).days
            time_decay = 1 / (1 + days_since_solved)

        combined_score = (
            0.2 * tag_score
            + 0.2 * difficulty_score
            + 0.1 * recency_score
            + 0.1 * (1 - time_decay)
        )

        return combined_score + random.uniform(0, 0.1)

    recommended_question = max(possible_questions, key=recommendation_score)
    recommended_question["_id"] = str(recommended_question["_id"])
    return jsonify(recommended_question)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
