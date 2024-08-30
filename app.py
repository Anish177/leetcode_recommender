import os
import csv
import random
from collections import defaultdict
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

QUESTIONS_PER_PAGE = 20

user_stats = {
    "solved_tags": defaultdict(int),
    "solved_difficulties": defaultdict(int),
    "solved_questions": set(),
}


def load_questions():
    loading_questions = {}
    loading_companies = []
    for filename in os.listdir("data"):
        if filename.endswith(".csv"):
            company = filename[:-4]
            loading_companies.append(company)
            loading_questions[company] = []
            with open(os.path.join("data", filename), "r", encoding="utf-8") as file:
                reader = csv.reader(file)
                for row in reader:
                    loading_questions[company].append(
                        {
                            "id": row[1],
                            "name": row[2],
                            "difficulty": row[3],
                            "tags": row[4].split(","),
                            "url": (
                                f"https://leetcode.com/problems/{row[2].lower().replace(' ', '-')}"
                            ),
                            "completed": False,
                        }
                    )

    all_questions = set()
    for company_questions in loading_questions.values():
        all_questions.update(
            (q["id"], q["name"], q["difficulty"], ",".join(q["tags"]))
            for q in company_questions
        )

    loading_questions["All"] = [
        {
            "id": q[0],
            "name": q[1],
            "difficulty": q[2],
            "tags": q[3].split(","),
            "url": f"https://leetcode.com/problems/{q[1].lower().replace(' ', '-')}",
            "completed": False,
        }
        for q in all_questions
    ]

    return loading_questions, ["All"] + sorted(loading_companies)


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
    company = data["company"]
    question_id = data["questionId"]
    completed = data["completed"]

    for question in questions[company]:
        if question["id"] == question_id:
            question["completed"] = completed
            break

    if company != "All":
        for question in questions["All"]:
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
    company = request.args.get("company", "All")
    possible_questions = [q for q in questions[company] if not q["completed"]]

    if not possible_questions:
        return jsonify({"message": "All questions completed"})

    def recommendation_score(question):
        tag_score = sum(user_stats["solved_tags"].get(tag, 0) for tag in question["tags"])
        difficulty_score = user_stats["solved_difficulties"].get(question["difficulty"], 0)
        return tag_score + difficulty_score + random.uniform(0, 1)
    
    possible_questions.sort(key=recommendation_score)

    return jsonify(possible_questions[0])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
