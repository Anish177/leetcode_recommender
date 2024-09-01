import os
import csv
import random
from collections import defaultdict
from datetime import datetime
from flask import Flask, render_template, jsonify, request, session
from dotenv import dotenv_values

app = Flask(__name__)

# app.secret_key = dotenv_values('.env')['SECRET_KEY']
app.secret_key = os.environ.get('SECRET_KEY')
# print("SECRET_KEY:", app.secret_key)


QUESTIONS_PER_PAGE = 20

user_stats = {
    "solved_tags": defaultdict(int),
    "solved_difficulties": defaultdict(int),
    "solved_questions": set(),
    "last_solved_time": {},
}


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


def get_user_stats():
    if 'user_stats' not in session:
        session['user_stats'] = {
            "solved_tags": defaultdict(int),
            "solved_difficulties": defaultdict(int),
            "solved_questions": list(),  # Store as a list
            "last_solved_time": {},
        }
    else:
        # Convert lists back to sets for internal usage
        session['user_stats']['solved_questions'] = set(session['user_stats']['solved_questions'])
        
    return session['user_stats']



questions, companies = load_questions()


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

    total_pages = (len(company_questions) - 1) // QUESTIONS_PER_PAGE + 1
    start = (page - 1) * QUESTIONS_PER_PAGE
    end = start + QUESTIONS_PER_PAGE
    return jsonify(
        {
            "questions": company_questions[start:end],
            "total_pages": total_pages,
            "current_page": page,
        }
    )


@app.route("/update_progress", methods=["POST"])
def update_progress():
    data = request.json
    question_id = data["questionId"]
    completed = data["completed"]

    user_stats = get_user_stats()

    for _, company_questions in questions.items():
        for question in company_questions:
            if question["id"] == question_id:
                question["completed"] = completed
                break

    if completed:
        user_stats["solved_questions"].add(question_id)
        for tag in question["tags"]:
            user_stats["solved_tags"][tag] += 1
        user_stats["solved_difficulties"][question["difficulty"]] += 1
    else:
        user_stats["solved_questions"].discard(question_id)
        for tag in question["tags"]:
            user_stats["solved_tags"][tag] = max(0, user_stats["solved_tags"][tag] - 1)
        user_stats["solved_difficulties"][question["difficulty"]] = max(
            0, user_stats["solved_difficulties"][question["difficulty"]] - 1
        )

    session['user_stats']['solved_questions'] = list(user_stats['solved_questions'])
    session['user_stats'] = user_stats
    return jsonify({"success": True})



@app.route("/random_question/<company>")
def random_question(company):
    uncompleted = [q for q in questions[company] if not q["completed"]]
    if uncompleted:
        return jsonify(random.choice(uncompleted))

    return jsonify({"message": "All questions completed"})


@app.route("/reset_progress", methods=["POST"])
def reset_progress():
    for _, companies_questions in questions.items():
        for question in companies_questions:
            question["completed"] = False

    user_stats["solved_tags"].clear()
    user_stats["solved_difficulties"].clear()
    user_stats["solved_questions"].clear()

    return jsonify({"success": True})


@app.route("/recommend_question", methods=["GET"])
def recommend_question():
    user_stats = get_user_stats()
    company = request.args.get("company", "All")
    possible_questions = [q for q in questions[company] if not q["completed"]]

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
                current_time - user_stats["last_solved_time"][question["id"]]
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
