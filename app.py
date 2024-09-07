import os
import csv
import random
from collections import defaultdict
from datetime import datetime
import json
from flask import Flask, render_template, jsonify, request, make_response
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise ValueError("No SECRET_KEY set for Flask application")

QUESTIONS_PER_PAGE = 20


def load_questions():
    loading_questions = {}
    loading_companies = []
    unique_questions = {}

    for filename in os.listdir("data"):
        if filename.endswith(".csv"):
            company = filename[:-4]
            loading_companies.append(company)
            loading_questions[company] = []
            with open(os.path.join("data", filename), "r", encoding="utf-8") as file:
                reader = csv.reader(file)
                total_questions = sum(1 for _ in reader)
                file.seek(0)
                for ind, row in enumerate(reader):
                    question_name = row[2]
                    question_id = row[1]

                    question_data = {
                        "id": question_id,
                        "name": question_name,
                        "difficulty": row[3],
                        "tags": row[4].split(",") if row[4] else [],
                        "url": f"https://leetcode.com/problems/{question_name.lower().replace(' ', '-')}",
                        "completed": False,
                        "recency_score": total_questions - ind,
                    }

                    loading_questions[company].append(question_data)

                    if question_name not in unique_questions:
                        unique_questions[question_name] = question_data

    loading_questions["All"] = list(unique_questions.values())

    return loading_questions, ["All"] + sorted(loading_companies)


questions, companies = load_questions()


def get_user_stats():
    user_stats = request.cookies.get("user_stats")
    if user_stats:
        try:
            user_stats = json.loads(user_stats)
            user_stats["solved_questions"] = set(user_stats["solved_questions"])
        except json.JSONDecodeError:
            user_stats = None

    if not user_stats:
        user_stats = {
            "solved_tags": defaultdict(int),
            "solved_difficulties": defaultdict(int),
            "solved_questions": set(),
            "last_solved_time": {},
        }
    return user_stats


def set_user_stats(response, user_stats):
    user_stats_copy = user_stats.copy()
    user_stats_copy["solved_questions"] = list(user_stats_copy["solved_questions"])
    response.set_cookie(
        "user_stats",
        json.dumps(user_stats_copy),
        max_age=31536000,
        httponly=True,
        secure=True,
        samesite="Lax",
    )


@app.route("/")
def index():
    return render_template("index.html", companies=companies)


@app.route("/questions/<company>")
def get_questions(company):
    page = request.args.get("page", 1, type=int)
    tags = request.args.get("tag", "").split(",")
    difficulties = request.args.get("difficulty", "").split(",")
    search_query = request.args.get("search", "").lower()
    company_questions = questions.get(company, [])

    user_stats = get_user_stats()

    if tags and tags[0]:
        company_questions = [
            q for q in company_questions if all(tag in q["tags"] for tag in tags)
        ]

    if difficulties and difficulties[0]:
        company_questions = [
            q for q in company_questions if q["difficulty"] in difficulties
        ]

    if search_query:
        company_questions = [
            q
            for q in company_questions
            if search_query in q["name"].lower() or search_query in q["id"].lower()
        ]

    # Update completed status based on user_stats
    for question in company_questions:
        question["completed"] = question["id"] in user_stats["solved_questions"]

    total_pages = (len(company_questions) - 1) // QUESTIONS_PER_PAGE + 1
    start = (page - 1) * QUESTIONS_PER_PAGE
    end = start + QUESTIONS_PER_PAGE

    response = jsonify(
        {
            "questions": company_questions[start:end],
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

    user_stats = get_user_stats()

    if completed:
        user_stats["solved_questions"].add(question_id)
        for question in questions["All"]:
            if question["id"] == question_id:
                for tag in question["tags"]:
                    user_stats["solved_tags"][tag] = (
                        user_stats["solved_tags"].get(tag, 0) + 1
                    )
                user_stats["solved_difficulties"][question["difficulty"]] = (
                    user_stats["solved_difficulties"].get(question["difficulty"], 0) + 1
                )
                user_stats["last_solved_time"][question_id] = datetime.now().isoformat()
                break
    else:
        user_stats["solved_questions"].discard(question_id)
        for question in questions["All"]:
            if question["id"] == question_id:
                for tag in question["tags"]:
                    user_stats["solved_tags"][tag] = max(
                        0, user_stats["solved_tags"].get(tag, 0) - 1
                    )
                user_stats["solved_difficulties"][question["difficulty"]] = max(
                    0,
                    user_stats["solved_difficulties"].get(question["difficulty"], 0)
                    - 1,
                )
                user_stats["last_solved_time"].pop(question_id, None)
                break

    response = make_response(jsonify({"success": True}))
    set_user_stats(response, user_stats)
    return response


@app.route("/random_question/<company>")
def random_question(company):
    user_stats = get_user_stats()
    uncompleted = [
        q for q in questions[company] if q["id"] not in user_stats["solved_questions"]
    ]
    if uncompleted:
        return jsonify(random.choice(uncompleted))

    return jsonify({"message": "All questions completed"})


@app.route("/reset_progress", methods=["POST"])
def reset_progress():
    response = make_response(jsonify({"success": True}))
    response.delete_cookie("user_stats")
    return response


@app.route("/recommend_question", methods=["GET"])
def recommend_question():
    user_stats = get_user_stats()
    company = request.args.get("company", "All")
    possible_questions = [
        q for q in questions[company] if q["id"] not in user_stats["solved_questions"]
    ]

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
        recency_score = question["recency_score"]
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
    return jsonify(recommended_question)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
